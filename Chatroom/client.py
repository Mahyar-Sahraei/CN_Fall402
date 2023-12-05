from time import sleep
from queue import Queue
from threading import Thread
import socket
import re
import logging

from config import *


class Client:
    def __init__(self, name, server_tcp_addr):
        self.name = name
        self.id = -1
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.sever_addr = server_tcp_addr

        self.command_queue = Queue()

        self.message_queue = Queue()
        self.log_queue = Queue()

    def enqueue_command(self, command):
        self.command_queue.put(command)

    def dequeue_command(self):
        return self.command_queue.get()

    def has_command(self):
        return not self.command_queue.empty()

    def enqueue_message(self, mtype, is_global, sender_name, sender_id, message):
        if mtype == "message":
            self.message_queue.put((is_global, sender_name, sender_id, message))
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

    def connect(self):
        try:
            self.socket.connect(self.sever_addr)
            self.socket.send(f"setname:{self.name}".encode())
        except Exception as e:
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

            except OSError:
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
                self.enqueue_message("log", None, None, None, matches.groups()[0])

            elif (matches := re.match(r"setid:(\d+)", message)) is not None:
                self.id = int(matches.groups()[0])
                
            elif (matches := re.match(r"global:(\d)\smsgfrom:(\d+)\sname:(\w+)\smsg:(.+)", message, flags= re.S)) is not None:
                globalflag, sender_id, sender_name, received_message = matches.groups()
                self.enqueue_message("message", globalflag, sender_name, sender_id, received_message)

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
        self.history = {
            "[GLOBAL]": {}
        }
        self.names = {}
        
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

        fmt_userlist = []
        for i in range(len(userlist)):
            user_id, user_name = re.match(r"ID:(\d+),NAME:(.+)", userlist[i]).groups()
            fmt_userlist.append((user_id, user_name))

        return fmt_userlist

    def send_message(self):
        print("Getting a list of active users...")
        userlist = self.get_active_users()

        print("\nActive Users")
        print("------------")

        if len(userlist) == 0:
            print("No active users!")
            return

        print("[G]: Send a message to everyone")
        for user in userlist:
            print(f"[{user[0]}]: {user[1]}")
        print("\nType \'G\' to send a message to everyone in the server")
        print("Or type the [ID] of the user that you want to send a message to")
        print("And If you want to cancle, type \'C\':")

        receiver_id = None
        while True:
            choice = input(">> ")
            if choice == "C":
                return

            elif choice == "G":
                receiver_id = GLOBAL_CHAT_ID
                break

            elif re.match(r"\d+", choice):
                valid_user = False
                for user in userlist:
                    if user[0] == choice:
                        valid_user = True
                        break
                if valid_user:
                    receiver_id = int(choice)
                    break
                else:
                    print("The ID must be within the list!")

            else:
                print(f"{choice} doesn't look like a valid option...")

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

        self.client.enqueue_command(f"sendto:{receiver_id} msg:{message}")

    def receive_messages(self):
        print("\nMessages\n------------")
        messages = []
        while self.client.has_messages("message"):
            messages.append(self.client.dequeue_message("message"))

        if len(messages) == 0:
            print ("No new messages.")

        else:
            for is_global, sender_name, sender_id, message in messages:
                if self.names.get(sender_id) is None:
                    self.names[sender_id] = sender_name

                if is_global == "1":
                    if self.history["[GLOBAL]"].get(sender_id) is None:
                        self.history["[GLOBAL]"][sender_id] = []
                    self.history["[GLOBAL]"][sender_id].append(message)

                else: 
                    if self.history.get(sender_id) is None:
                        self.history[sender_id] = []
                    self.history[sender_id].append(message)

                print(f"{sender_name}#{sender_id}{'[GLOBALL]:' if is_global == '1' else ':'}")
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

        if len(self.history) == 1 and len(self.history["[GLOBAL]"]) == 0:
            print("No messages here!")
            return

        if len(self.history["[GLOBAL]"]) != 0:
            print("@Global_Messages")
        for sender_id in self.history:
            if sender_id != "[GLOBAL]":
                print(f"@{self.names[sender_id]}#{sender_id}")



        print("\nChoose one of the users (by ID) to view their message history,")
        print("Or view global chats by typing G,")
        print("And type \'C\' if you want to cancle:")

        sender_id = None
        while True:
            choice = input(">> ")

            if choice == "C":
                return

            elif choice == "G":
                if len(self.history["[GLOBAL]"]) != 0:
                    sender_id = "[GLOBAL]"
                    break
                else:
                    print("You have no public messages yet.")
            
            elif re.match("(\d+)", choice):
                valid_sender = False
                for sender in self.history:
                    if sender == choice:
                        valid_sender = True
                        break

                if valid_sender:
                    sender_id = choice
                    break

                else:
                    print("The ID must be within the list!")

            else:
                print(f"{choice} doesn't look like a valid option...")

        if sender_id == "[GLOBAL]":
            for client_id in self.history["[GLOBAL]"]:
                print(f"\n\n{self.names[client_id]}#{client_id}")
                print("------------")
                for message in self.history["[GLOBAL]"][client_id]:
                    for line in message.split("\n"):
                        print(f"\t{line}")
                    print("------")

        else:
            print(f"\n\n{self.names[sender_id]}#{sender_id}")
            print("------------")
            for message in self.history[sender_id]:
                for line in message.split("\n"):
                    print(f"\t{line}")
                print("------")

    def change_username(self):
        print("Please enter your name. The name should only contain alphabets, numbers, _, - or dot(.):")
        while True:
            name = input(">> ")
            try:
                if re.match(r"^([a-zA-Z0-9]|\-|\_|\.)+$", name):
                    self.username = name
                    print(f"Your name set to {self.username} successfully.")
                    return
                print("Invalid name! try again")
            except KeyboardInterrupt:
                return

    def exit_ui(self):
        print(f"Goodbye, {self.username}!")
        exit(0)

    def main_menu(self):
        print("Welcome to the chatroom!")
        self.change_username()
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
                    for user in active_users:
                        print(f"[{user[0]}]: {user[1]}")

            elif option == 1:
                self.client = Client(self.username, SERVER_TCP_ADDR)
                if self.client.connect():
                    print("You are connected to the server!")
                    try:
                        self.start_chat()
                    except Exception as e:
                        self.client.close()
                    except KeyboardInterrupt:
                        self.client.close()
                else:
                    print("Couldn't connect to the server. Please try again")

            elif option == 2:
                self.change_username()

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
            print("[3]. See messages from specified user")
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