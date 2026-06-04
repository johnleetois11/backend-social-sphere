from fastapi import WebSocket
from typing import Optional


class ConnectionManager:
    def __init__(self):
        # channel_id -> list of (user_id, websocket)
        self.channel_conns: dict[int, list[tuple[int, WebSocket]]] = {}

        # dm_key (frozenset {u1, u2}) -> list of (user_id, websocket)
        self.dm_conns: dict[frozenset, list[tuple[int, WebSocket]]] = {}

        # call signaling: user_id -> websocket
        self.call_conns: dict[int, WebSocket] = {}

        # presence
        self.online_users: set[int] = set()

        # typing: channel_id -> set of user_ids
        self.typing_channel: dict[int, set[int]] = {}

        # typing in DM: dm_key -> set of user_ids
        self.typing_dm: dict[frozenset, set[int]] = {}

    # ── Group channel ───────────────────────────────────────

    async def channel_connect(self, channel_id: int, user_id: int, ws: WebSocket):
        await ws.accept()
        self.channel_conns.setdefault(channel_id, []).append((user_id, ws))
        self.online_users.add(user_id)

    def channel_disconnect(self, channel_id: int, user_id: int, ws: WebSocket):
        conns = self.channel_conns.get(channel_id, [])
        self.channel_conns[channel_id] = [(u, w) for u, w in conns if w is not ws]
        if not self.channel_conns[channel_id]:
            del self.channel_conns[channel_id]
        # Remove from online only if not connected elsewhere
        if not any(
            any(u == user_id for u, _ in lst)
            for lst in self.channel_conns.values()
        ) and not any(
            any(u == user_id for u, _ in lst)
            for lst in self.dm_conns.values()
        ):
            self.online_users.discard(user_id)

    async def channel_broadcast(self, channel_id: int, payload: dict):
        for _, ws in self.channel_conns.get(channel_id, []):
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    # ── Typing – channel ────────────────────────────────────

    async def set_typing_channel(self, channel_id: int, user_id: int, username: str, is_typing: bool):
        bucket = self.typing_channel.setdefault(channel_id, set())
        if is_typing:
            bucket.add(user_id)
        else:
            bucket.discard(user_id)
        await self.channel_broadcast(channel_id, {
            "type": "typing",
            "user_id": user_id,
            "username": username,
            "is_typing": is_typing,
        })

    # ── Direct messages ─────────────────────────────────────

    @staticmethod
    def _dm_key(u1: int, u2: int) -> frozenset:
        return frozenset({u1, u2})

    async def dm_connect(self, user_id: int, peer_id: int, ws: WebSocket):
        await ws.accept()
        key = self._dm_key(user_id, peer_id)
        self.dm_conns.setdefault(key, []).append((user_id, ws))
        self.online_users.add(user_id)

    def dm_disconnect(self, user_id: int, peer_id: int, ws: WebSocket):
        key = self._dm_key(user_id, peer_id)
        conns = self.dm_conns.get(key, [])
        self.dm_conns[key] = [(u, w) for u, w in conns if w is not ws]
        if not self.dm_conns[key]:
            del self.dm_conns[key]
        if not any(
            any(u == user_id for u, _ in lst)
            for lst in {**self.channel_conns, **self.dm_conns}.values()
        ):
            self.online_users.discard(user_id)

    async def dm_send(self, sender_id: int, receiver_id: int, payload: dict):
        key = self._dm_key(sender_id, receiver_id)
        for _, ws in self.dm_conns.get(key, []):
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    async def set_typing_dm(self, user_id: int, peer_id: int, username: str, is_typing: bool):
        key = self._dm_key(user_id, peer_id)
        bucket = self.typing_dm.setdefault(key, set())
        if is_typing:
            bucket.add(user_id)
        else:
            bucket.discard(user_id)
        await self.dm_send(user_id, peer_id, {
            "type": "typing",
            "user_id": user_id,
            "username": username,
            "is_typing": is_typing,
        })

    # ── Call signaling ──────────────────────────────────────

    async def call_connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.call_conns[user_id] = ws

    def call_disconnect(self, user_id: int):
        self.call_conns.pop(user_id, None)

    async def call_send(self, target_user_id: int, payload: dict) -> bool:
        ws = self.call_conns.get(target_user_id)
        if ws:
            try:
                await ws.send_json(payload)
                return True
            except Exception:
                pass
        return False

    def is_online(self, user_id: int) -> bool:
        return user_id in self.online_users


manager = ConnectionManager()
