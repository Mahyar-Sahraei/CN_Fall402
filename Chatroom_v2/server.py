from time import sleep
from queue import Queue
from threading import Thread
import socket
import re
import logging
import hashlib
import json

from config import *


class Client:
    def __init__(self, name: str, password: str, socket: socket):
        self.socket = socket
        self.message_queue = Queue()
        self.name = name
        self.password = password
        self.status = STATUS.AVAILABLE
        self.active = True
        self.history = {}
        try:
            file = open(f"{self.name}_hist.json", "r")
            history_str = file.read()
            self.history = json.loads(history_str)
            file.close()
        except Exception:
            file = open(f"{self.name}_hist.json", "w")
            file.write("{}")
            file.close()

    def has_incoming_messages(self):
        return not self.message_queue.empty()

    def enqueue_message(self, message, sender_name):
        self.message_queue.put((message, sender_name))

    def dequeue_message(self):
        return self.message_queue.get()

    def shutdown(self):
        self.active = False
        self.socket.close()
        self.socket = None

        file = open(f"{self.name}_hist.json", "w")
        file.write(json.dumps(self.history))
        file.close()


class Server:
    def __init__(self, tcp_addr, udp_addr, max_client=100):
        self.max_client = max_client
        self.client_list = {}
        try:
            file = open(f"clients_list.json", "r")
            clients = json.loads(file.read())
            for client_name in clients:
                self.client_list[client_name] = Client(client_name, clients[client_name], None)
                self.client_list[client_name].active = False
            file.close()
        except Exception:
            file = open(f"clients_list.json", "w")
            file.write("{}")
            file.close()

        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.socket.bind(tcp_addr)

        self.udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.udp_socket.bind(udp_addr)

    def start(self):
        udp_thread = Thread(target=self.handle_udp)
        udp_thread.daemon = True
        udp_thread.start()

        self.socket.listen(5)

        logging.info("Server started, Listening to incoming connections.")
        while True:
            try:
                client_socket, _ = self.socket.accept()

                if len(self.client_list) <= self.max_client:
                    client = None
                    client_socket.send("?name".encode())
                    client_name = client_socket.recv(1024).decode()
                    client_socket.send("?pass".encode())
                    client_password = client_socket.recv(1024).decode()

                    if client_name in self.client_list:
                        client = self.client_list[client_name]
                        if hashlib.sha256(client_password.encode()).hexdigest() != client.password:
                            client_socket.send("reject".encode())
                            continue
                        else:
                            client_socket.send("accept".encode())
                            client.socket = client_socket
                            client.active = True
                    else:
                        hashed_pass = hashlib.sha256(client_password.encode()).hexdigest()
                        client = Client(client_name, hashed_pass, client_socket)
                        self.client_list[client_name] = client
                        client_socket.send("accept".encode())
                    
                    logging.info(f"{client.name} entered the server.")

                    req_thread = Thread(target=self.handle_req, args=[client])
                    req_thread.daemon = True
                    res_thread = Thread(target=self.handle_res, args=[client])
                    res_thread.daemon = True
                    
                    req_thread.start()
                    res_thread.start()

                else:
                    self.refuse(client_socket)

            except KeyboardInterrupt:
                self.socket.close()

                clients = {}
                for client_name in self.client_list:
                    clients[client_name] = self.client_list[client_name].password
                file = open("clients_list.json", "w")
                file.write(json.dumps(clients))
                file.close()

                logging.info("Server turned off.")
                exit(0)

    def handle_udp(self):
        while True:
            message, addr = self.udp_socket.recvfrom(1024)
            if message.decode() == "getactiveusers":
                activeusers = ""
                for name in self.client_list:
                    if self.client_list[name].active:
                        activeusers += f"{name};"
                self.udp_socket.sendto(activeusers.encode(), addr)

    def handle_req(self, client: Client):
        client.socket.settimeout(10)
        while client.active:
            try:
                message = client.socket.recv(2048).decode()

                if message == "alive":
                    continue

                elif message == "close":
                    client.shutdown()
                    logging.info(f"{client.name} left the server.")
                    break

                elif message == "gethistory":
                    client.socket.send(f"history:{json.dumps(client.history)}".encode())

                elif (matches := re.match(r"setstatus:(Available|Busy)", message)) is not None:
                    client.status = matches.groups()[0]

                elif (matches := re.match(r"setname:(.+)", message)) is not None:
                    client.name = matches.groups()[0]
                    logging.info(f"{client.name} changed his/her name to: {client.name}.")

                elif (matches := re.match(r"sendto:(.+)\smsg:(.+)", message, flags=re.S)) is not None:
                        receiver_names, sender_message = matches.groups()

                        for receiver_name in receiver_names.split(","):

                            if self.client_list[receiver_name] is not None:
                                receiver_client = self.client_list[receiver_name]
                                if receiver_client.status == STATUS.AVAILABLE:
                                    receiver_client.enqueue_message(sender_message, client.name)
                                    if receiver_client.history.get(client.name) is None:
                                        receiver_client.history[client.name] = []
                                    receiver_client.history[client.name].append(sender_message)
                                    client.socket.send(f"log:Message sent to {receiver_name} successfully.".encode())
                                    logging.info(f"{client.name} sent a message to: {receiver_name}.")
                                else:
                                    client.socket.send(f"log:Specified user ({receiver_name}) is busy right now.".encode())

                            else:
                                client.socket.send(f"log:Specified user ({receiver_name}) doesn't exist.".encode())

            except socket.error:
                client.shutdown()
                logging.info(f"{client.get_name_id()} disconnected.")
                break

    def handle_res(self, client: Client):
        while client.active:
            if client.has_incoming_messages():
                message, sender_name = client.dequeue_message()
                client.socket.send(f"msgfrom:{sender_name} msg:{message}".encode())
            else:
                sleep(2)

    def refuse(self, client_socket: socket):
        client_socket.send("Server is full! try again later.".encode())
        logging.info(f"A client got refused, due to limit of {self.max_client} clients")
        client_socket.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    server = Server(SERVER_TCP_ADDR, SERVER_UDP_ADDR)
    server.start()