import socket

from config import *


class TCPClient:
    def __init__(self, server_addr):
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.server_addr = server_addr

    def force_close(self):
        try:
            self.socket.close()
        except OSError:
            pass

    def start(self):
        self.socket.connect(self.server_addr)
        print("Welcome. Please enter a string or type \'exit server\' to exit.")
        while True:
            string = input("Your string: ")
            if string == "exit server":
                self.socket.send("exit server".encode())
                self.socket.close()
                print("Goodbye!")
                return
            self.socket.send(string.encode())
            response = self.socket.recv(1024).decode()
            print(f"Server's response: {response}")



class UDPClient:
    def __init__(self, server_addr):
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.server_addr = server_addr

    def force_close(self):
        try:
            self.socket.close()
        except OSError:
            pass

    def start(self):
        print("Welcome. Please enter a string.")
        while True:
            string = input("Your string: ")
            self.socket.sendto(string.encode(), self.server_addr)
            response = self.socket.recv(1024).decode()
            print(f"Server's response: {response}")


if __name__ == "__main__":
    try:
        print("What kind of connection do you want to make? [TCP|UDP]")
        conn = ""
        while True:
            conn = input(">> ").upper()
            if conn == "TCP" or conn == "UDP":
                break
            else:
                print("Invalid connection type")

        
        if conn == "TCP":
            try:
                tcpClient = TCPClient(SERVER_TCP_ADDR)
                tcpClient.start()
            except Exception as e:
                tcpClient.force_close()
                print("Something went wrong, exiting.")

        else:
            try:
                udpClient = UDPClient(SERVER_UDP_ADDR)
                udpClient.start()
            except Exception as e:
                udpClient.force_close()
                print("Something went wrong, exiting.")

    except KeyboardInterrupt:
        if conn == "TCP":
            tcpClient.force_close()
        elif conn == "UDP":
            udpClient.force_close()
        print("Goodbye!")
