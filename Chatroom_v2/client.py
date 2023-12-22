from time import sleep
from queue import Queue
from threading import Thread
import socket
import re
import logging
import json
from datetime import datetime

from config import *


class Client:
    def __init__(self, name, password, server_tcp_addr):
        self.name = name
        self.password = password
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.sever_addr = server_tcp_addr

        self.command_queue = Queue()
        self.message_queue = Queue()
        self.log_queue = Queue()
        self.history_queue = Queue()

    def enqueue_command(self, command):
        self.command_queue.put(command)

    def dequeue_command(self):
        return self.command_queue.get()

    def has_command(self):
        return not self.command_queue.empty()

    def enqueue_message(self, mtype, sender_name, message):
        if mtype == "message":
            self.message_queue.put((sender_name, message))
        else:
            self.log_queue.put(message)

    def dequeue_message(self, mtype):
        if mtype == "message":
            return self.message_queue.get()
        else:
            return self.log_queue.get()

    def has_messages(self, mtype):
        if mtype == "message":
            return not self.message_queue.empty()
        else:
            return not self.log_queue.empty()
        
    def enqueue_history(self, history):
        self.history_queue.put(history)

    def dequeue_history(self):
        return self.history_queue.get()
    
    def has_history(self):
        return not self.history_queue.empty()

    def connect(self):
        try:
            self.socket.connect(self.sever_addr)
            if self.socket.recv(1024).decode() == "?name":
                self.socket.send(self.name.encode())
            if self.socket.recv(1024).decode() == "?pass":
                self.socket.send(self.password.encode())
            if self.socket.recv(1024).decode() == "reject":
                return False
        except Exception:
            return False
        self.connected = True

        req_thread = Thread(target=self.handle_req)
        req_thread.daemon = True
        res_thread = Thread(target=self.handle_res)
        res_thread.daemon = True

        req_thread.start()
        res_thread.start()

        return True

    def handle_req(self):
        slept = 0
        while self.connected == True:
            try:
                if self.has_command():
                    command= self.dequeue_command()
                    self.socket.send(command.encode())
                    slept = 0
                else:
                    sleep(1)
                    slept += 1
                
                if slept > 5:
                    self.socket.send("alive".encode())
                    slept = 0

            except socket.error:
                self.close()
                return
            
    def handle_res(self):
        while self.connected == True:
            try:
                message = self.socket.recv(2048).decode()
            except OSError:
                self.close()
                return

            if (matches := re.match(r"log:(.+)", message)) is not None:
                self.enqueue_message("log", None, matches.groups()[0])
                
            elif (matches := re.match(r"msgfrom:(.+)\smsg:(.+)", message, flags= re.S)) is not None:
                sender_name, received_message = matches.groups()
                self.enqueue_message("message", sender_name, received_message)

            elif (matches := re.match(r"history:(.+)", message, flags=re.S)) is not None:
                self.enqueue_history(matches.groups()[0])

    def close(self):
        self.connected = False
        try:
            self.socket.send("close".encode())
            self.socket.close()

        except Exception:
            pass


class UI:
    def __init__(self, server_udp_addr):
        self.client = None
        self.username = "[UNKNOWN]"
        self.password = None
        
        self.udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.server_udp_addr = server_udp_addr

    def get_active_users(self):
        try:
            self.udp_socket.sendto("getactiveusers".encode(), self.server_udp_addr)
            self.udp_socket.settimeout(5)
            data, _ = self.udp_socket.recvfrom(2048)
        except socket.error:
            print("Server isn't responding right now. Please try again later.\n")
            return []

        userlist = data.decode().split(";")
        userlist.pop()
        return userlist

    def send_message(self):
        print("Getting a list of active users...")
        userlist = self.get_active_users()

        print("\nActive Users")
        print("------------")

        if len(userlist) == 0:
            print("No active users!")
            return

        print("[G]: Send a message to everyone")
        for i in range(len(userlist)):
            print(f"{i + 1}: {userlist[i]}")
        print("\nType \'G\' to send a message to everyone in the server")
        print("Type a list of comma separated numbers (eg. 1,2,3) to select receivers")
        print("Type \'C\' to cancle:")

        receivers = None
        while True:
            choice = input(">> ")
            if choice == "C":
                return

            elif choice == "G":
                receivers = list(range(len(userlist)))
                break

            elif re.match(r"\d+(,\d+)*", choice):
                index_list = choice.split(",")
                validated = True
                for index in index_list:
                    if int(index) > len(userlist):
                        print("The ID must be within the list!")
                        validated = False
                        break
                        
                if validated:
                    receivers = [int(index) - 1 for index in index_list]
                    break

            else:
                print(f"Incorrect syntax. Make sure you didn't use spaces.")

        print("What is your message? (press \'enter\' twice to send or press \'Ctrl+c\' to cancle):")
        
        message = ""
        state = 0
        while True:
            try:
                buffer = input()
                if len(buffer) == 0 and state == 1:
                    break
                elif len(buffer) != 0:
                    state = 1
                message += buffer + '\n'

            except KeyboardInterrupt:
                return
        message += f"\n[TIME: {datetime.now()}]"

        receivers_names = userlist[receivers[0]]
        for i in range(1, len(receivers)):
            receivers_names += "," + userlist[receivers[i]]
            
        self.client.enqueue_command(f"sendto:{receivers_names} msg:{message}")

    def receive_messages(self):
        print("\nMessages\n------------")
        messages = []
        while self.client.has_messages("message"):
            messages.append(self.client.dequeue_message("message"))

        if len(messages) == 0:
            print ("No new messages.")

        else:
            for sender_name, message in messages:
                print(f"{sender_name}:")
                for line in message.split("\n"):
                    print(f"\t{line}")
                print()

        print("\nServer messages\n------------")
        logs = []
        while self.client.has_messages("log"):
            logs.append(self.client.dequeue_message("log"))
        if len(logs) == 0:
            print("No messages from server.")
        else:
            for message in logs:
                print(f"[SERVER]: {message}")

    def show_history(self):
        print("\nHistory")
        print("------------")
        self.client.enqueue_command("gethistory")
        while not self.client.has_history():
            pass

        history = json.loads(self.client.dequeue_history())

        if len(history) == 0:
            print("No messages here!")
            return

        for name in history:
            print(f"{name}:")
            for message in history[name]:
                for line in message.split("\n"):
                    print(f"\t{line}")
            print("-----\n")

    def set_username(self):
        print("Please enter your name. The name should only contain alphabets, numbers, _, - or dot(.):")
        while True:
            name = input(">> ")
            if re.match(r"^([a-zA-Z0-9]|\-|\_|\.)+$", name):
                return name
            print("Invalid name! try again")
            
    def set_password(self):
        print("Please enter your password. The password should contain 8 or more characters:")
        while True:
            password = input(">> ")
            if len(password) >= 8:
                return password
            print("Invalid password! try again")

    def exit_ui(self):
        print(f"Goodbye, {self.username}!")
        exit(0)

    def main_menu(self):
        print("Welcome to the chatroom!")
        self.username = self.set_username()
        while True:
            print("\n\nMain Menu")
            print("------------")
            print("Please choose an option:")
            print("[0]. Get a list of server's active users")
            print("[1]. Connect to the chatroom")
            print("[2]. Change your name")
            print("[3]. Exit\n")

            option = -1
            while True:
                choice = input(">> ")
                if re.match(r"\d+", choice) is None:
                    print("Please enter a number")
                    continue
                option = int(choice)
                if option < 0 or option > 3:
                    print("Please choose a number between 0 and 3")
                else:
                    break

            if option == 0:
                print("Fetching...")
                active_users = self.get_active_users()
                print("\nActive Users:")
                print("------------")
                if len(active_users) < 1:
                    print("No active users!")
                else:
                    for i in range(len(active_users)):
                        print(f"{i + 1}: {active_users[i]}")

            elif option == 1:
                if self.username is None:
                    print("You haven't set a username yet!")
                    continue

                self.password = self.set_password()
                if self.password is None:
                    print("You didn't set a password, canceling...")
                    continue

                self.client = Client(self.username, self.password, SERVER_TCP_ADDR)
                if self.client.connect():
                    print("You are connected to the server!")
                    try:
                        self.start_chat()
                    except Exception as e:
                        self.client.close()
                    except KeyboardInterrupt:
                        self.client.close()
                else:
                    print("Couldn't connect to the server. Possible reasons:\n"
                          "1. Server is down\n"
                          "2. Your name is not unique\n"
                          "3. Your password is wrong")

            elif option == 2:
                self.username = self.set_username()

            else:
                self.exit_ui()

    def start_chat(self):
        while True:
            print("\n\nChatroom")
            print("------------")
            print("What do you want to do?")
            print("[0]. Refresh")
            print("[1]. Compose a message")
            print("[2]. Show new messages" +\
                ("*" if self.client.has_messages("log") or 
                self.client.has_messages("message") else ""))
            print("[3]. Show history")
            print("[4]. Exit chatroom\n")

            option = -1
            while True:
                choice = input(">> ")
                if re.match(r"\d+", choice) is None:
                    print("Please enter a number")
                    continue
                option = int(choice)
                if option < 0 or option > 4:
                    print("Please choose a number between 0 and 4")
                else:
                    break

            if not self.client.connected:
                print("You got disconnected from the server, please reconnect.")
                self.client.close()
                self.client = None
                break

            if option == 0:
                continue

            elif option == 1:
                self.send_message()

            elif option == 2:
                self.receive_messages()

            elif option == 3:
                self.show_history()

            else:
                self.client.close()
                self.client = None
                break


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    ui = UI(SERVER_UDP_ADDR)
    ui.main_menu()