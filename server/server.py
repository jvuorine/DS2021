import asyncio
import json
import websockets
import math
from pymongo import MongoClient, errors


DOMAIN = 'host.docker.internal'
PORT = 27017
AVAILABLE_MOVES = ["rock", "paper", "scissors"]
USERS = set()
usernames = {}

'''user_rank_details = {
    "name": "",
    "rank": 400
}'''

GAME = set()
MOVES = {}

'''try:
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

print(database_names)'''

client = MongoClient()

db = client.ranks
user = db.user

async def register_move(websocket, move):
    MOVES.update({websocket: move})

async def add_username(websocket, username):
    usernames.update({websocket:username})

async def clear_moves():
    MOVES.clear()

async def clear_game():
    GAME.clear()

async def register(websocket):
    USERS.add(websocket)


async def unregister(websocket):
    USERS.remove(websocket)

async def register_to_play(websocket, name):
    if not user.find_one({"name": name}):
        user_rank_details = {
            "name": name,
            "rank": 1000
        }
        user.insert_one(user_rank_details)
    GAME.add(websocket)


async def unregister_from_play(websocket):
    GAME.remove(websocket)

def probability(rank1, rank2):
    return 1 / (1 + math.pow(10,(rank1 - rank2) / 400))

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
    
    pr1 = probability(p1_rank, p2_rank)
    pr2 = probability(p2_rank, p1_rank)

    if winner == p1:
        p1_rank = p1_rank + 50 * (1-pr1)
        p2_rank = p2_rank + 50 * (-pr2)
    elif winner == p2:
        p1_rank = p1_rank + (-pr1)
        p2_rank = p2_rank + (1-pr2)

    user.update_one({"name": p1_name}, {"$set": {"rank": p1_rank}})
    user.update_one({"name": p2_name}, {"$set": {"rank": p2_rank}})
    print(p1_rank, p2_rank)

    return winner

async def gamestate():
    print("hello there")
    winner = evaluate_winner()
    await clear_moves()
    print(MOVES)
    print(winner)
    for player in GAME:
        if winner == "tie":
            await player.send("You tied!")
        elif winner == player:
            await player.send("You won!")
        else:
            await player.send("You lost!")
    await clear_game()


async def counter(websocket, path):
    await register(websocket)
    pong_id = 0
    try:
        message = await websocket.recv()
        username = json.loads(message)["msg"]
        await add_username(websocket, username)
        await websocket.send("connected")
    except Exception as e:
        print(e)
    else:
        while True:
            try:
                async for message in websocket:
                    id, message = json.loads(message).values()
                    print(id, message)
                    if message == "play":
                        await register_to_play(websocket, username)
                    elif message == "cancel":
                        await unregister_from_play(websocket)
                        await websocket.send("connected")
                    elif message == "ping":
                        await websocket.send(json.dumps({"id": pong_id, "msg": "pong"}))
                        pong_id += 1
                    elif message == "rank":
                        print("ye ay we are herer")
                        try:
                            rank = user.find_one({"name":username})["rank"]
                        except Exception as e:
                            print(e)
                            await websocket.send(f"rank:You have not played a game yet!")
                        else:
                            await websocket.send(f"rank:{rank}")
                    elif message == "ready":
                        await websocket.send("connected")
                        pong_id = 0
                    if len(GAME) == 0 and message != "ping" and message != "rank":
                        await websocket.send("connected")
                    elif len(GAME) == 2:
                        if message.lower() in AVAILABLE_MOVES:
                            await register_move(websocket, message)
                        elif len(MOVES) == 0:
                            for player in GAME:
                                await player.send("Game begins, pick rock, paper or scissors")
                        if len(MOVES) == 2:
                            await gamestate()
                        elif len(MOVES) == 1:
                            await websocket.send("Waiting for other players move")
                    elif websocket in GAME:
                        await websocket.send("Waiting for other player")

                    print(len(GAME))
                    print(len(MOVES))
                    print(GAME)

            finally:
                print('asdasdasd')
                for socket in GAME:
                    try:
                        await socket.send("The other player left, waiting for a new player")
                    except websockets.exceptions.ConnectionClosedOK:
                        pass
                    except Exception:
                        pass
                try:
                    await unregister_from_play(websocket)
                except Exception:
                    pass
                await unregister(websocket)
                clear_moves()
                print(len(GAME))
                break


if __name__ == "__main__":
    start_server = websockets.serve(counter, "0.0.0.0", 6789)
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
