from threading import Thread
import socket
import logging

from config import *

class Server:
    def __init__(self, tcp_addr, udp_addr):
        self.tcp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.tcp_socket.bind(tcp_addr)

        self.tcp_clients = {}

        self.udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.udp_socket.bind(udp_addr)

    def start(self):
        tcp_handler = Thread(target=self.handle_tcp)
        udp_handler = Thread(target=self.handle_udp)

        tcp_handler.daemon = True
        udp_handler.daemon = True

        tcp_handler.start()
        udp_handler.start()

        try:
            tcp_handler.join()
            udp_handler.join()
        except KeyboardInterrupt:
            logging.info("Shutting down")
            for client in self.tcp_clients:
                self.tcp_clients[client].close()
            self.tcp_socket.close()
            self.udp_socket.close()

    def handle_tcp(self):
        self.tcp_socket.listen(5)
        while True:
            client_socket, addr = self.tcp_socket.accept()
            self.tcp_clients[hash(client_socket)] = client_socket
            logging.info(f"A TCP client connected to the server. Address: {addr}")
            client_handler = Thread(target=self.handle_client, args=[client_socket, addr])
            client_handler.daemon = True
            client_handler.start()

    def handle_client(self, client_socket: socket.socket, addr):
        while True:
            try:
                string = client_socket.recv(1024).decode()
                if string == "exit server":
                    logging.info(f"A client exited. Address: {addr}")
                    client_socket.close()
                    self.tcp_clients.pop(hash(client_socket))
                    return
                if string == "":
                    client_socket.send(",N/A".encode())
                    continue

                codes_list = self.convert_string(string)
                string = "," + self.find_largest_min_repeated(codes_list)
                for code in reversed(codes_list):
                    string = str(code) + string

                client_socket.send(string.encode())

            except socket.error:
                logging.info(f"A client disconnected. Address: {addr}")
                client_socket.close()
                return


    def handle_udp(self):
        while True:
            data, addr = self.udp_socket.recvfrom(1024)
            string = data.decode()
            most_repeated_char = self.find_max_repeated(string).upper()
            self.udp_socket.sendto(f"{string[::-1].upper()},{most_repeated_char}".encode(), addr)

    def find_max_repeated(self, string):
        if len(string) == 0:
            return "N/A"

        words = {}
        for c in string:
            if words.get(c) is None:
                words[c] = 1
            words[c] += 1

        return max(words, key=words.get)

    def find_largest_min_repeated(self, codes_list):
        codes = {}
        for code in codes_list:
            if type(code) is int:
                if codes.get(code) is None:
                    codes[code] = 1

        return str(max(codes))

    def convert_string(self, string):
        codes_list = []
        for c in string:
            ch = c
            if c.isalpha():
                ascii_code = ord(ch.lower())
                ch = (ascii_code - 97) // 2
            codes_list.append(ch)

        return codes_list


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    server = Server(SERVER_TCP_ADDR, SERVER_UDP_ADDR)
    server.start()