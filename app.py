#!/usr/bin/env python

import asyncio
import itertools
import json
import os
import secrets
import signal
import websockets

from connect4 import Connect4, PLAYER1, PLAYER2

JOIN = {}
WATCH = {}

async def error(websocket, messaage):
    event = {
        "type": "error",
        "message": messaage
    }
    await websocket.send(json.dumps(event))

async def init(websocket):

    game = Connect4()
    connected = {websocket}

    join_key = secrets.token_urlsafe(3)
    JOIN[join_key] = game, connected

    watch_key = secrets.token_urlsafe(3)
    WATCH[join_key] = game, connected

    try:
        event = {
            'type': 'init',
            'join': join_key,
            'watch': watch_key,
        }
        await websocket.send(json.dumps(event))
        await play(websocket, game, PLAYER1, connected)
    finally:
        del JOIN[join_key]

async def join(websocket, join_key):
    try:
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not found.")
        return

    connected.add(websocket)
    try:
        await play(websocket, game, PLAYER2, connected)
    finally:
        connected.remove(websocket)

async def play(websocket, game, player, connected):
    while True:
        async for message in websocket:
            event = json.loads(message)
            assert event['type'] == 'play'
            column = event['column']

            try:
                row = game.play(player, column)
            except RuntimeError as e:
                await error(websocket, str(e))
                continue

            event = {
                'type': 'play',
                'player': player,
                'column': column,
                'row': row
            }

            websockets.broadcast(connected, json.dumps(event))

            if game.winner is not None:
                event = {
                    'type': 'win',
                    'player': game.winner
                }
                websockets.broadcast(connected, json.dumps(event))
                break;


async def watch(websocket, watch_key):
    
    try:
        game, connected = WATCH[watch_key]
    except KeyError:
        await error(websocket, "Game not found.")
        return

    connected.add(websocket)
    try:
        await replay_moves(game, websocket)
        await websocket.wait_closed()
    finally:
        connected.remove(websocket)

async def replay_moves(game, websocket):
    for player, column, row in game.moves.copy():
        event = {
            'type': 'play',
            'player': player,
            'column': column,
            'row': row
        }
        await websocket.send(json.dumps(event))



async def handler(websocket):
    message = await websocket.recv()
    event = json.loads(message)
    assert event["type"] == "init"

    if "join" in event:
        await join(websocket, event["join"])
    elif "watch" in event:
        await watch(websocket, event["watch"])
    else:
        await init(websocket)
                        

async def main():

    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    port = int(os.environ.get('PORT', "8001"))

    async with websockets.serve(handler, "", port):
        await stop


if __name__ == "__main__":
    asyncio.run(main())