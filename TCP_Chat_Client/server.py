import queue
import re
import socket
from threading import Thread

class Client:
    def __init__(self, identifier: int, addr: tuple[str, int], socket: socket):
        self.id = identifier
        self.addr = addr
        self.socket = socket
        self.message_queue = queue.Queue(maxsize=100)
        self.name = "Unknown"

    def set_name(self, name):
        self.name = name

    def queue_message(self, message, sender_id):
        self.message_queue.put((message, sender_id))

class Server:
    def __init__(self, ip, port, max_client=100, max_queueing=5):
        self.address = (ip, port)
        self.max_client = max_client
        self.client_list = {}
        self.inc_client_id = 0
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.socket.bind(self.address)

    def start(self):
        self.socket.listen(5)
        while True:
            client_socket, addr = self.socket.accept()

            if len(self.client_list) <= self.max_client:
                client = Client(self.inc_client_id, addr, client_socket)
                self.client_list[id] = client
                thread = threading.Thread(target=self.handle, args=[client])
                thread.start()

            else:
                self.refuse(client_socket)

    def handle(self, client: Client):
        client.socket.send(
            '''Welcome to the server!
            '''.encode()
        )
        while True:
            message = client.socket.recv(2048).decode()

            if message == "close":
                client.socket.send("Goodbye!".encode())
                client.socket.close()
                break

            elif message == "get_client_list":
                info = "Active Users:\n"
                for id in self.client_list:
                    info += f"ID: {self.client_list[id].id}, NAME: {self.client_list[id].name}\n"
                client.socket.send(info.encode())

            elif message.split(":")[0] == "set_name":
                parsed_message = message.split(":")
                if len(parsed_message) != 2:
                    client.socket.send("The name isn't specified correctly".encode())
                else:
                    client.set_name(parsed_message[1])

            else:
                matches = re.match(r"sendto:(\d+)\smsg:(\w+)", message)
                if matches is not None:
                    id = int(matches[0])
                    client_message = matches[1]

                    target_client = self.client_list[id]

                    if target_client is not None:
                        target_client.queue_message(client_message, client.id)
                        client.socket.send(f"Message sent to {target_client.id}:{target_client.name} successfully.".encode())

                    else:
                        client.socket.send("Specified user doesn't exist.".encode())

            

    def refuse(self, client_socket: socket):
        client_socket.send("Server is full! try again later.".encode())
        client_socket.close()