"""Single Alpaca crypto quote socket, fanned out to the local bots.

Alpaca allows ONE crypto data websocket per account. crypto_run.py and
scalp_run.py both need live quotes, so this process owns the upstream
connection (subscribed to the union of their symbols) and rebroadcasts every
raw message to whoever is connected on ws://127.0.0.1:8765. The bots connect
there instead of to Alpaca and need no auth/subscribe handshake; each ignores
symbols it doesn't trade.

    python feed.py
"""
import asyncio
import json
import logging
import os

import websockets

import config as shared
import crypto_config
import scalp_config

log = logging.getLogger("feed")

UPSTREAM_URL = os.getenv("FEED_UPSTREAM", "wss://stream.data.alpaca.markets/v1beta3/crypto/us")
LOCAL_URL = "ws://127.0.0.1:8765"
LOCAL_HOST, LOCAL_PORT = "127.0.0.1", 8765
SYMBOLS = sorted(set(crypto_config.SYMBOLS) | set(scalp_config.SYMBOLS))

_clients = set()


async def _serve(ws):
    _clients.add(ws)
    log.info("bot connected (%d)", len(_clients))
    try:
        await ws.wait_closed()
    finally:
        _clients.discard(ws)
        log.info("bot disconnected (%d)", len(_clients))


async def _upstream():
    async with websockets.connect(UPSTREAM_URL, max_size=None) as socket:
        await socket.recv()
        await socket.send(json.dumps({"action": "auth", "key": shared.API_KEY, "secret": shared.SECRET_KEY}))
        reply = json.loads(await socket.recv())[0]
        if reply.get("T") == "error":
            raise RuntimeError(f"auth failed: {reply.get('msg')}")
        await socket.send(json.dumps({"action": "subscribe", "quotes": SYMBOLS}))
        reply = json.loads(await socket.recv())[0]
        if reply.get("T") == "error":
            raise RuntimeError(f"subscribe failed: {reply.get('msg')}")
        log.info("upstream subscribed: %s", ",".join(reply.get("quotes", [])))
        async for raw in socket:
            if _clients:
                await asyncio.gather(*(c.send(raw) for c in list(_clients)), return_exceptions=True)


async def main():
    async with websockets.serve(_serve, LOCAL_HOST, LOCAL_PORT):
        log.info("serving bots on %s", LOCAL_URL)
        backoff = 1
        while True:
            try:
                await _upstream()
                backoff = 1
            except Exception as exc:
                log.warning("upstream dropped (%s), retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
