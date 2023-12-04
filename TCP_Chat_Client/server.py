from time import sleep
from queue import Queue
from threading import Thread
import socket
import re
import logging

import numpy

from config import *


class Client:
    def __init__(self, identifier: int, addr: tuple[str, int], socket: socket):
        self.id = identifier
        self.addr = addr
        self.socket = socket
        self.message_queue = Queue()
        self.name = "Unknown"
        self.active = True

    def set_name(self, name):
        self.name = name

    def get_name_id(self):
        return f"{self.name}#{self.id}"

    def has_incoming_messages(self):
        return not self.message_queue.empty()

    def enqueue_message(self, message, sender_id, is_global="0"):
        self.message_queue.put((message, sender_id, is_global))

    def dequeue_message(self):
        return self.message_queue.get()

    def shutdown(self):
        self.active = False
        self.socket.close()


class Server:
    def __init__(self, tcp_addr, udp_addr, max_client=100, max_queueing=5):
        self.max_client = max_client
        self.client_list = {}
        self.client_ids = numpy.random.choice(range(1000, 10000), 100, replace=False)
        self.client_idx = 0

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
                client_socket, addr = self.socket.accept()

                if len(self.client_list) <= self.max_client:
                    given_id = self.client_ids[self.client_idx]
                    client = Client(given_id, addr, client_socket)
                    self.client_list[given_id] = client
                    self.client_idx = (self.client_idx + 1) % len(self.client_ids)
                    logging.info(f"{client.get_name_id()} entered the server.")

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
                logging.info("Server turned off.")
                exit(0)

    def handle_udp(self):
        while True:
            message, addr = self.udp_socket.recvfrom(1024)
            if message.decode() == "getactiveusers":
                activeusers = ""
                for id in self.client_list:
                    activeusers += f"ID:{id},NAME:{self.client_list[id].name};"
                self.udp_socket.sendto(activeusers.encode(), addr)

    def handle_req(self, client: Client):
        client.socket.settimeout(10)
        while client.active:
            try:
                message = client.socket.recv(2048).decode()

                if message == "alive":
                    continue

                elif message == "close":
                    self.client_list.pop(client.id)
                    client.shutdown()
                    logging.info(f"{client.get_name_id()} left the server.")
                    break

                elif (matches := re.match(r"setname:(.+)", message)) is not None:
                    client.set_name(matches.groups()[0])
                    logging.info(f"{client.get_name_id()} changed his/her name to: {client.name}.")

                elif (matches := re.match(r"sendto:(\-?\d+)\smsg:(.+)", message, flags=re.S)) is not None:
                        receiver_id, client_message = matches.groups()

                        if int(receiver_id) == GLOBAL_CHAT_ID:
                            self.send_all(client, client_message)
                            continue

                        target_client = self.client_list[int(receiver_id)]

                        if target_client is not None:
                            target_client.enqueue_message(client_message, client.id)
                            client.socket.send(f"log:Message sent to {target_client.name}#{target_client.id} successfully.".encode())
                            logging.info(f"{client.get_name_id()} sent a message to: {target_client.name}.")

                        else:
                            client.socket.send("log:Specified user doesn't exist.".encode())
            except TimeoutError:
                self.client_list.pop(client.id)
                client.shutdown()
                logging.info(f"{client.get_name_id()} disconnected.")
                break

    def handle_res(self, client: Client):
        client.socket.send(f"setid:{client.id}".encode())
        while client.active:
            if client.has_incoming_messages():
                message, sender_id, is_global = client.dequeue_message()
                sender_name = self.client_list[sender_id].name
                client.socket.send(f"global:{is_global} msgfrom:{sender_id} name:{sender_name} msg:{message}".encode())
            else:
                sleep(2)

    def send_all(self, client, message):
        for client_id in self.client_list:
            if client_id != client.id:
                target_client = self.client_list[client_id]
                target_client.enqueue_message(message, client.id, "1")
        client.socket.send(f"log:Message sent to all successfully".encode())
        logging.info(f"{client.get_name_id()} sent a message globally")

    def refuse(self, client_socket: socket):
        client_socket.send("Server is full! try again later.".encode())
        logging.info(f"A client got refused, due to limit of {self.max_client} clients")
        client_socket.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    server = Server(SERVER_TCP_ADDR, SERVER_UDP_ADDR)
    server.start()