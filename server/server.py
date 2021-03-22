import asyncio
import json
import websockets
import math
from pymongo import MongoClient, errors

# defining global variables
# DOMAIN is the address of the database
# PORT is the port of the database
# AVAILABLE_MOVES are the moves the player can pick if in a game
# USERS is a set of users connected to the server
# usernames is a dictionary of the connected users usernames
# GAME is a set of players connected to a game
# MOVES is dictionary of players username and thei move in a game
DOMAIN = 'host.docker.internal'
PORT = 27017
AVAILABLE_MOVES = ["rock", "paper", "scissors"]
USERS = set()
usernames = {}
GAME = set()
MOVES = {}

# try to connect to a database server, if cannot connect, host a local database
try:
    client = MongoClient(
            host = [ str(DOMAIN) + ":" + str(PORT) ],
            serverSelectionTimeoutMS = 3000, # 3 second timeout
        )
    print ("server version:", client.server_info()["version"])
    database_names = client.list_database_names()
except errors.ServerSelectionTimeoutError as err:
    client = None
    database_names = []
    print ("pymongo ERROR:", err)
    client = MongoClient()

# create a database and collection for the users and their ranks
db = client.ranks
user = db.user

# helper functions to register users to the server and also register their moves
# also function to unregister players and clear the MOVES dictionary
async def register(websocket):
    USERS.add(websocket)

async def unregister(websocket):
    USERS.remove(websocket)

async def register_move(websocket, move):
    MOVES.update({websocket: move})

async def add_username(websocket, username):
    usernames.update({websocket:username})

async def clear_moves():
    MOVES.clear()

async def clear_game():
    GAME.clear()

# function to register user to a game, if their username is not in the database add it and set their rank to default value of 1000
async def register_to_play(websocket, name):
    if not user.find_one({"name": name}):
        user_rank_details = {
            "name": name,
            "rank": 1000
        }
        user.insert_one(user_rank_details)
    GAME.add(websocket)

# function to unregister a player from game
async def unregister_from_play(websocket):
    GAME.remove(websocket)

# function to calculate probability of a player winning a game based on their current rank,
# used in the calculation of points won or lost by a user
def probability(rank1, rank2):
    return 1 / (1 + math.pow(10,(rank1 - rank2) / 400))

# evaluates the winner in the game of rock.paper-scissors
# also calculates the points gained or lost by a player using the ELO formula
# updates the ranks to the database
def evaluate_winner():
    p1, p2 = MOVES.keys()
    p1_move, p2_move = MOVES.values()
    p1_name = usernames[p1]
    p2_name = usernames[p2]
    p1_rank = user.find_one({"name": p1_name})["rank"]
    p2_rank = user.find_one({"name": p2_name})["rank"]
    print(p1,p2,p1_move,p2_move, p1_rank, p2_rank)
    winner = None
    if p1_move == p2_move:
        winner = "tie"
    elif p1_move == "rock":
        if p2_move == "scissors":
            winner = p1
        else:
            winner = p2
    elif p1_move == "scissors":
        if p2_move == "paper":
            winner = p1
        else:
            winner = p2
    elif p1_move == "paper":
        if p2_move == "rock":
            winner = p1
        else:
            winner = p2
    
    # calculating probabilities for the elo algorithm
    pr1 = probability(p1_rank, p2_rank)
    pr2 = probability(p2_rank, p1_rank)

    # update ranks depending on the outcome
    if winner == p1:
        p1_rank = p1_rank + 50 * (1-pr1)
        p2_rank = p2_rank + 50 * (-pr2)
    elif winner == p2:
        p1_rank = p1_rank + (-pr1)
        p2_rank = p2_rank + (1-pr2)

    user.update_one({"name": p1_name}, {"$set": {"rank": p1_rank}})
    user.update_one({"name": p2_name}, {"$set": {"rank": p2_rank}})

    return winner

# sends messages to the players after a game
# clears the MOVES dictionary
async def gamestate():
    winner = evaluate_winner()
    await clear_moves()
    for player in GAME:
        if winner == "tie":
            await player.send("You tied!")
        elif winner == player:
            await player.send("You won!")
        else:
            await player.send("You lost!")
    await clear_game()

# main connection loop for a client
async def counter(websocket, path):
    # register socket to the server
    # set pong_id to 0, used in the packet loss tests
    await register(websocket)
    pong_id = 0
    # waits for the users username and adds it to the usernames dictionary
    # if connection is failed, print the exception server-side
    try:
        message = await websocket.recv()
        username = json.loads(message)["msg"]
        await add_username(websocket, username)
        await websocket.send("connected")
    except Exception as e:
        print(e)
    # if everything ok with the connection, goes into the main loop
    else:
        try:
            # wait for messages from the client
            async for message in websocket:
                id, message = json.loads(message).values()
                # if the message is 'play' and GAME has less than 2 players add the player to the game
                # if game full, send message to the client
                if message == "play":
                    if len(GAME) < 2:
                        await register_to_play(websocket, username)
                    else:
                        await websocket.send("Game is full, wait until it finishes")
                # if the message is 'ping', send 'pong' the the client with id that increases, client then compares this id to the sent 'ping' id and measures if packets were lost
                elif message == "ping":
                    await websocket.send(json.dumps({"id": pong_id, "msg": "pong"}))
                    pong_id += 1
                # if message 'rank', find the plauer from the database and send the rank to the player
                # if player not in the database, send informing message
                elif message == "rank":
                    try:
                        rank = user.find_one({"name":username})["rank"]
                    except Exception as e:
                        print(e)
                        await websocket.send(f"rank:You have not played a game yet!")
                    else:
                        await websocket.send(f"rank:{rank}")
                # if message ready, reset the client to the default loop
                elif message == "ready":
                    await websocket.send("connected")
                    pong_id = 0
                # if the are 0 players in the game, send the client to the default loop
                if len(GAME) == 0 and message != "ping" and message != "rank":
                    await websocket.send("connected")
                # if the client is in GAME and there are 2 players in GAME, start the game
                # wait for the players moves and evaluate winner
                elif len(GAME) == 2 and websocket in GAME:
                    if message.lower() in AVAILABLE_MOVES:
                        await register_move(websocket, message)
                    elif len(MOVES) == 0:
                        for player in GAME:
                            await player.send("Game begins, pick rock, paper or scissors")
                    if len(MOVES) == 2:
                        await gamestate()
                    elif len(MOVES) == 1:
                        await websocket.send("Waiting for other players move")
                # if the player is the only one in GAME then wait for other player
                elif websocket in GAME:
                    await websocket.send("Waiting for other player")
        
        except Exception as e:
            print(e)

        # after loop, show who disconnected
        # unregister the client from GAME, USERS and clear MOVES
        finally:
            print(f"{websocket} disconnected")
            try:
                await unregister_from_play(websocket)
            except Exception:
                pass
            await unregister(websocket)
            await clear_moves()

# start the server
if __name__ == "__main__":
    start_server = websockets.serve(counter, "0.0.0.0", 6789)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
