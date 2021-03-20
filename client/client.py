import asyncio
import websockets
import json
import sys
import time

# creating a client class
class Client():
    def __init__(self, uri):
        # initialising variables needed in this class
        # uri is the address of the server
        # id is used to keep track of packets sent to the server
        # packet is the for the message is sent to the server
        # receive_message is the received message from the server
        self.uri = uri
        self.game_states = ["You tied!", "You won!", "You lost!"]
        self.id = 0
        self.packet = {"id": self.id,
                        "msg": ""}
        self.receive_message = ""

    # function used to connect to the server
    async def connect(self):
        self.connection = await websockets.client.connect(self.uri)
        # if the connection is succesfull, the player is asked for their desired username (cant be empty)
        if self.connection.open:
            print("Connected")
            while True:
                msg = input("Username: ")
                if msg == "":
                    print("username can not be empty")
                else:
                    await self.sendMessage(msg)
                    break
            #return the connection
            return self.connection

    # function for the gameloop
    async def gameLoop(self, connection):
        # simple variable used to print the messages just once, instead of each loop
        i=0
        while True:
            # waits for message from the server, if no message received in 0.1 seconds then move on
            try:
                await asyncio.wait_for(self.recv_message(connection),timeout=0.1)
            except asyncio.TimeoutError:
                pass
            
            # if the game is played and a result iss received, print it and go back to main loop
            if self.receive_message in self.game_states:
                print("\n" + self.receive_message)
                await self.sendMessage("ready")
                await self.recv_message(connection)
            # if game is started, wait for users action
            elif self.receive_message == "Game begins, pick rock, paper or scissors":
                msg = input(self.receive_message+": ")
                i = 0
                if msg == "exit":
                    await self.connection.close()
                try:
                    await self.sendMessage(msg)
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed")
                    break
                await self.recv_message(connection)
            # when player connects, this block is shown, also shown after 'rank', 'ping' and finished game state
            elif self.receive_message == "connected":
                print("\nType 'play' to play a game of Rock-Paper-Scissors")
                print("Type 'exit' to exit the game")
                print("Type 'rank' to see your rank")
                print("Type 'ping' to measure the connection")
                msg = input("")
                i = 0
                if msg == "exit":
                    await self.connection.close()
                    break
                elif msg == "rank":
                    await self.get_rank(connection)
                elif msg == "ping":
                    await self.pingpong(connection)
                else:
                    try:
                        await self.sendMessage(msg)
                    except websockets.exceptions.ConnectionClosed:
                        print("Connection closed")
                        break
                await self.recv_message(connection)
            # prints messages for "waiting a player" and "waiting for other players move"
            else:
                if i == 0:
                    print(self.receive_message)
                    i = 1
        
    # function to parse the 'rank' messafe from the server, prints the rank if one is sent, return to main loop after
    async def get_rank(self,connection):
        await self.sendMessage("rank")
        await self.recv_message(connection)
        try:
            rank = float(self.receive_message.split("rank:")[1])
        except ValueError:
            print(self.receive_message.split("rank:")[1])
        else:
            print(f"Your current ranking points: {rank:.2f}")
            await self.sendMessage("ready")

    # function to set the receive_message to the received message from the server
    async def recv_message(self, connection):
        self.receive_message = await connection.recv()

    # function for the connection testing
    # sends ping to server with an id
    # waits for response and measures how much time was spent
    # also measures if the received messages id is the same as the one sent, if not the packet is lost
    # prints the round trip time after each ping
    # finally prints packets sent, received and lost
    # also prints minimum, maximum and average latency for the pings
    async def pingpong(self, connection):
        l_min = None
        l_max = 0.0
        l_all = 0
        prev_id = -1
        packets_lost = 0
        for i in range(5):
            start = time.time()
            await self.sendMessage("ping")
            msg = await connection.recv()
            end = time.time()
            elapsed = end - start

            msg = json.loads(msg)
            if prev_id - msg["id"] != -1:
                packets_lost += 1
            if i == 0:
                l_min = elapsed
                l_max = elapsed
            elif elapsed > l_max:
                l_max = elapsed
            elif elapsed < l_min:
                l_min = elapsed
            l_all += elapsed
            prev_id += 1
            print(f"round trip time: {elapsed * 1000:.02f} ms")

            await asyncio.sleep(0.1)

        l_avg = l_all / 5
        print(f"\nPackets: Sent = 5, Received = {5-packets_lost}, Lost = {packets_lost} ({packets_lost / 5 * 100:.2f}% loss)")
        print(f"Round trip time")
        print(f"    Minimum: {l_min * 1000:.02f} ms, maximum: {l_max * 1000:.02f} ms, average: {l_avg * 1000:.02f} ms")

        await self.sendMessage("ready")

    # sends a message to the server, format is seen in class __ini__ function
    async def sendMessage(self, message):
        self.packet["id"] = self.id
        self.packet["msg"] = message
        self.id += 1
        await self.connection.send(json.dumps(self.packet))

# expects the server address as command line argument
# if address provided, tries to connect to it and start the game loop
def main(argv):
    try:
        uri = f"ws://{argv[0]}:6789"
    except IndexError:
        print("include server address as command line argument")
        print("for example:")
        print("python client.py localhost")
    else:
        client = Client(uri)
        loop = asyncio.get_event_loop()
        connection = loop.run_until_complete(client.connect())
        tasks = [
            asyncio.ensure_future(client.gameLoop(connection))
        ]
        loop.run_until_complete(asyncio.wait(tasks))

if __name__ == "__main__":
    main(sys.argv[1:])
