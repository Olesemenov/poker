"""Online mode: the host's device runs this server; up to 6 players join by link.

Transport: aiohttp. Guests open  http://<host-ip>:<port>/?room=<code>  in a
browser (served from poker/static) or connect with the mobile client to
ws://<host-ip>:<port>/ws.

Client -> server messages (JSON):
  {"type": "join", "name": "Ann", "pid": "<optional, to reconnect>"}
  {"type": "start"}                                  (host only)
  {"type": "action", "action": "fold|check|call|raise|allin", "amount": 40}
  {"type": "kick", "pid": "..."}                     (host only)
Server -> client:
  {"type": "joined", "pid": "...", "is_host": bool}
  {"type": "state", "state": {...Table.public_state...}, "is_host": bool}
  {"type": "error", "message": "..."}
"""
from __future__ import annotations

import asyncio
import secrets
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aiohttp import WSMsgType, web

from .game import MAX_SEATS, PokerError, Table

STATIC = Path(__file__).parent / "static"


def local_ip() -> str:
    """LAN address of this device (no packets are actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Room:
    def __init__(self, small_blind=10, big_blind=20, start_stack=1000):
        self.code = secrets.token_urlsafe(4)
        self.host_token = secrets.token_urlsafe(16)
        self.start_stack = start_stack
        self.table = Table(small_blind, big_blind, max_seats=MAX_SEATS)
        self.sockets: dict[str, web.WebSocketResponse] = {}
        self.host_pid: Optional[str] = None

    async def broadcast(self) -> None:
        for pid, ws in list(self.sockets.items()):
            if not ws.closed:
                await ws.send_json(
                    {
                        "type": "state",
                        "state": self.table.public_state(pid),
                        "is_host": pid == self.host_pid,
                    }
                )

    async def handle(self, ws, pid: Optional[str], msg: dict, is_host_conn: bool) -> Optional[str]:
        kind = msg.get("type")
        if kind == "join":
            name = str(msg.get("name", "Player"))[:20] or "Player"
            old = msg.get("pid")
            if old and any(p.id == old for p in self.table.players) and old not in self.sockets:
                pid = old  # reconnect
            else:
                pid = secrets.token_hex(4)
                self.table.add_player(pid, name, self.start_stack)
                if is_host_conn:
                    self.host_pid = pid
            self.sockets[pid] = ws
            await ws.send_json({"type": "joined", "pid": pid, "is_host": pid == self.host_pid})
        elif pid is None:
            raise PokerError("join first")
        elif kind == "start":
            if pid != self.host_pid:
                raise PokerError("only the host can start")
            self.table.start_hand()
        elif kind == "action":
            self.table.act(pid, msg.get("action", ""), int(msg.get("amount", 0) or 0))
        elif kind == "kick":
            if pid != self.host_pid:
                raise PokerError("only the host can kick")
            target = msg.get("pid")
            self.table.leave(target)
            old_ws = self.sockets.pop(target, None)
            if old_ws is not None:
                await old_ws.close()
        else:
            raise PokerError("unknown message")
        await self.broadcast()
        return pid


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    room: Room = request.app["room"]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    is_host_conn = request.query.get("host") == room.host_token
    pid: Optional[str] = None
    try:
        async for raw in ws:
            if raw.type != WSMsgType.TEXT:
                continue
            try:
                pid = await room.handle(ws, pid, raw.json(), is_host_conn)
            except (PokerError, ValueError, TypeError) as e:
                await ws.send_json({"type": "error", "message": str(e)})
    finally:
        if pid and room.sockets.get(pid) is ws:
            del room.sockets[pid]
            # keep the seat so the player can reconnect; fold them if it is their turn
            if room.table.phase != "waiting" and room.table.current is not None:
                if room.table.players[room.table.current].id == pid:
                    try:
                        room.table.act(pid, "fold")
                    except PokerError:
                        pass
            await room.broadcast()
    return ws


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


def make_app(room: Room) -> web.Application:
    app = web.Application()
    app["room"] = room
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    return app


@dataclass
class ServerHandle:
    room: Room
    port: int
    loop: asyncio.AbstractEventLoop

    @property
    def guest_url(self) -> str:
        return f"http://{local_ip()}:{self.port}/?room={self.room.code}"

    @property
    def host_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?room={self.room.code}&host={self.room.host_token}"

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)


def start_in_thread(port: int = 8080, **room_kwargs) -> ServerHandle:
    """Start the server on a background thread (used by the mobile app)."""
    room = Room(**room_kwargs)
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def runner():
        asyncio.set_event_loop(loop)
        web_runner = web.AppRunner(make_app(room))
        loop.run_until_complete(web_runner.setup())
        loop.run_until_complete(web.TCPSite(web_runner, "0.0.0.0", port).start())
        ready.set()
        loop.run_forever()

    threading.Thread(target=runner, daemon=True).start()
    ready.wait(10)
    return ServerHandle(room, port, loop)


if __name__ == "__main__":  # run on a PC for development: python -m poker.server
    h = start_in_thread()
    print("Guests:", h.guest_url)
    print("Host:  ", h.host_url)
    threading.Event().wait()
