from time import sleep
from queue import Queue
from threading import Thread
import socket
import re
import logging

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

    def has_incoming_messages(self):
        return not self.message_queue.empty()

    def enqueue_message(self, message, sender_id):
        self.message_queue.put((message, sender_id))

    def dequeue_message(self):
        return self.message_queue.get()

    def shutdown(self):
        self.active = False
        self.socket.close()


class Server:
    def __init__(self, ip, port, uip, uport, max_client=100, max_queueing=5):
        self.max_client = max_client
        self.client_list = {}
        self.inc_client_id = 0

        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.socket.bind((ip, port))

        self.udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.udp_socket.bind((uip, uport))

    def is_socket_alive(self, client_socket):
        try:
            data = client_socket.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
            if len(data) == 0:
                return False
        except BlockingIOError:
            return True
        except ConnectionResetError:
            return False
        except Exception as e:
            return False
        return True

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
                    client = Client(self.inc_client_id, addr, client_socket)
                    self.client_list[self.inc_client_id] = client
                    self.inc_client_id += 1
                    logging.log(logging.INFO, f"Client: {client.id} entered the server.")

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
                logging.log(logging.INFO, "Server turned off.")
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

                if message == "close":
                    self.client_list.pop(client.id)
                    client.shutdown()
                    logging.log(logging.INFO, f"Client: {client.id} left the server.")
                    break

                elif (matches := re.match(r"setname:(.+)", message)) is not None:
                    client.set_name(matches.groups()[0])
                    logging.log(logging.INFO, f"Client: {client.id} changed his/her name to: {client.name}.")

                elif (matches := re.match(r"sendto:(\d+)\smsg:(.+)", message)) is not None:
                        id = int(matches.groups()[0])
                        client_message = matches.groups()[1]

                        target_client = self.client_list[id]

                        if target_client is not None:
                            target_client.enqueue_message(client_message, client.id)
                            client.socket.send(f"log:Message sent to {target_client.name}#{target_client.id} successfully.".encode())
                            logging.log(logging.INFO, f"Client: {client.id} sent a message to: {target_client.name}.")

                        else:
                            client.socket.send("log:Specified user doesn't exist.".encode())
            except TimeoutError:
                if self.is_socket_alive(client.socket):
                    continue
                else:
                    self.client_list.pop(client.id)
                    client.shutdown()
                    logging.log(logging.INFO, f"Client: {client.id} disconnected.")
                    break

    def handle_res(self, client: Client):
        while client.active:
            if client.has_incoming_messages():
                message, sender_id = client.dequeue_message()
                sender_name = self.client_list[sender_id].name
                client.socket.send(f"msgfrom:{sender_id} name:{sender_name} msg:{message}".encode())
                logging.log(logging.INFO, f"Client: {client.id} received a message from {sender_id}")
            else:
                sleep(2)
            

    def refuse(self, client_socket: socket):
        client_socket.send("Server is full! try again later.".encode())
        logging.log(logging.INFO, f"A client got refused, due to limit of {self.max_client} clients")
        client_socket.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    server = Server("127.0.0.1", 1234, "127.0.0.1", 4321)
    server.start()