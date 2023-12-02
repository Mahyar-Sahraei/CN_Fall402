from time import sleep
from queue import Queue
from threading import Thread
import socket
import re
import logging

class Client:
    def __init__(self, name, server_ip, server_port):
        self.name = name
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.sever_addr = (server_ip, server_port)

        self.command_queue = Queue()

        self.message_queue = Queue()
        self.log_queue = Queue()

    def enqueue_command(self, command: str):
        self.command_queue.put(command)

    def dequeue_command(self):
        return self.command_queue.get()

    def has_command(self):
        return not self.command_queue.empty()

    def enqueue_message(self, mtype: str, sender: str, message: str):
        if mtype == "message":
            self.message_queue.put((sender, message))
        else:
            self.log_queue.put((sender, message))

    def dequeue_message(self, mtype: str):
        if mtype == "message":
            return self.message_queue.get()
        else:
            return self.log_queue.get()

    def has_messages(self, mtype: str):
        if mtype == "message":
            return not self.message_queue.empty()
        else:
            return not self.log_queue.empty()

    def connect(self):
        self.socket.connect(self.sever_addr)
        self.socket.send(f"setname:{self.name}".encode())
        self.connected = True

        req_thread = Thread(target=self.handle_req)
        req_thread.daemon = True
        res_thread = Thread(target=self.handle_res)
        res_thread.daemon = True

        req_thread.start()
        res_thread.start()

    def handle_req(self):
        while self.connected == True:
            if self.has_command():
                command= self.dequeue_command()
                self.socket.send(command.encode())
            else:
                sleep(2)

    def handle_res(self):
        while self.connected == True:
            try:
                message = self.socket.recv(2048).decode()
            except OSError:
                self.connected = False
                return

            if (matches := re.match(r"log:(\w+)", message)) is not None:
                self.enqueue_message("log", "[SERVER]", matches.groups()[0])

            elif (matches := re.match(r"msgfrom:(\d+)\sname:(\w+)\smsg:(.+)", message)) is not None:
                sender_id, sender_name, received_message = matches.groups()
                self.enqueue_message("message", f"{sender_name}#{sender_id}", received_message)

    def close(self):
        self.connected = False
        try:
            self.socket.send("close".encode())
            self.socket.close()
        except Exception:
            pass



class UI:
    def __init__(self, server_uip, server_uport):
        self.client = None
        self.username = None
        self.history = {}
        
        self.udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.udp_server_addr = (server_uip, server_uport)

    def get_active_users(self):
        self.udp_socket.sendto("getactiveusers".encode(), self.udp_server_addr)
        data, _ = self.udp_socket.recvfrom(2048)
        userlist = data.decode().split(";")
        userlist.pop()
        return userlist

    def send_message(self):
        print("Getting a list of active users...")
        userlist = self.get_active_users()

        if len(userlist) == 0:
            print("No active users!")
            return

        for i in range(len(userlist)):
            print(f"[{i}]:", userlist[i])
        print("Type the number of the user that you want to send a message to (or type \'c\' to cancle):")

        receiver = -1
        while True:
            choice = input(">> ")
            if choice == "c":
                return
            elif re.match(r"\d+", choice):
                receiver = int(choice)
                if receiver < 0 or receiver >= len(userlist):
                    print("The number must be within the list!")
                else:
                    break
            else:
                print("Your input doesn't look like a number...")

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

        receiver_id = re.match(r"ID:(\d+),NAME:.+", userlist[receiver]).groups()[0]
        self.client.enqueue_command(f"sendto:{receiver_id} msg:{message}")

    def receive_messages(self):
        print("\n\nMessages\n------------")
        messages = []
        while self.client.has_messages("message"):
            messages.append(self.client.dequeue_message("message"))
        if len(messages) == 0:
            print ("No new messages.")
        else:
            for sender, message in messages:
                if self.history.get(sender) is None:
                    self.history[sender] = []
                self.history[sender].append(message)
                print(f"{sender}: {message}")

        print("\n\nServer messages\n------------")
        logs = []
        while self.client.has_messages("log"):
            logs.append(self.client.dequeue_message("log"))
        if len(logs) == 0:
            print("No messages from server.")
        else:
            for sender, message in logs:
                print(f"{sender}: {message}")

    def show_history(self):
        print("Coming soon :)")
        pass

    def exit_ui(self):
        print(f"Goodbye, {self.client.name}!")
        exit(0)

    def main_menu(self):
        print("Welcome to the chatroom! please introduce yourself:")
        self.username = input(">> ")
        print(f"Great, {self.username}! you are now ready to chat with other people.")
        while True:
            print("\n\nMain Menu")
            print("------------")
            print("Please choose an option:")
            print("[0]. Get a list of server's active users")
            print("[1]. Connect to the chatroom")
            print("[2]. Exit\n")

            option = -1
            while True:
                choice = input(">> ")
                if re.match(r"\d+", choice) is None:
                    print("Please enter a number")
                    continue
                option = int(choice)
                if option < 0 or option > 2:
                    print("Please choose a number between 0 and 2")
                else:
                    break

            if option == 0:
                print("Fetching...")
                for user in self.get_active_users():
                    print(user)

            elif option == 1:
                self.client = Client(self.username, "127.0.0.1", 1234)
                self.start_chat()

            else:
                self.exit_ui()


    def start_chat(self):
        self.client.connect()
        print("You are connected to the server!")
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
    ui = UI("127.0.0.1", 4321)
    ui.main_menu()