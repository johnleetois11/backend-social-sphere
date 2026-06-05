from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # MongoDB IDs are strings.
        # channel_id -> list of (user_id, websocket)
        self.channel_conns: dict[str, list[tuple[str, WebSocket]]] = {}

        # dm_key (frozenset {u1, u2}) -> list of (user_id, websocket)
        self.dm_conns: dict[frozenset, list[tuple[str, WebSocket]]] = {}

        # call signaling: user_id -> websocket
        self.call_conns: dict[str, WebSocket] = {}

        # app-wide notifications: user_id -> websocket
        self.notification_conns: dict[str, WebSocket] = {}

        # presence
        self.online_users: set[str] = set()

        # typing: channel_id -> set of user_ids
        self.typing_channel: dict[str, set[str]] = {}

        # typing in DM: dm_key -> set of user_ids
        self.typing_dm: dict[frozenset, set[str]] = {}

    # ── Group channel ───────────────────────────────────────

    async def channel_connect(self, channel_id: str, user_id: str, ws: WebSocket):
        await ws.accept()
        self.channel_conns.setdefault(channel_id, []).append((user_id, ws))
        self.online_users.add(user_id)

    def channel_disconnect(self, channel_id: str, user_id: str, ws: WebSocket):
        conns = self.channel_conns.get(channel_id, [])
        self.channel_conns[channel_id] = [(u, w) for u, w in conns if w is not ws]
        if not self.channel_conns[channel_id]:
            del self.channel_conns[channel_id]

        if not self._user_connected_anywhere(user_id):
            self.online_users.discard(user_id)

    async def channel_broadcast(self, channel_id: str, payload: dict):
        for _, ws in self.channel_conns.get(channel_id, []):
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    # ── App-wide notifications ──────────────────────────────

    async def notification_connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.notification_conns[user_id] = ws
        self.online_users.add(user_id)

    def notification_disconnect(self, user_id: str):
        self.notification_conns.pop(user_id, None)
        if not self._user_connected_anywhere(user_id):
            self.online_users.discard(user_id)

    async def notification_send(self, user_id: str, payload: dict) -> bool:
        ws = self.notification_conns.get(user_id)
        if not ws:
            return False

        try:
            await ws.send_json(payload)
            return True
        except Exception:
            self.notification_disconnect(user_id)
            return False

    # ── Typing – channel ────────────────────────────────────

    async def set_typing_channel(self, channel_id: str, user_id: str, username: str, is_typing: bool):
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
    def _dm_key(u1: str, u2: str) -> frozenset:
        return frozenset({u1, u2})

    async def dm_connect(self, user_id: str, peer_id: str, ws: WebSocket):
        await ws.accept()
        key = self._dm_key(user_id, peer_id)
        self.dm_conns.setdefault(key, []).append((user_id, ws))
        self.online_users.add(user_id)

    def dm_disconnect(self, user_id: str, peer_id: str, ws: WebSocket):
        key = self._dm_key(user_id, peer_id)
        conns = self.dm_conns.get(key, [])
        self.dm_conns[key] = [(u, w) for u, w in conns if w is not ws]
        if key in self.dm_conns and not self.dm_conns[key]:
            del self.dm_conns[key]

        if not self._user_connected_anywhere(user_id):
            self.online_users.discard(user_id)

    async def dm_send(self, sender_id: str, receiver_id: str, payload: dict):
        key = self._dm_key(sender_id, receiver_id)
        for _, ws in self.dm_conns.get(key, []):
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    async def set_typing_dm(self, user_id: str, peer_id: str, username: str, is_typing: bool):
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

    async def call_connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.call_conns[user_id] = ws
        self.online_users.add(user_id)

    def call_disconnect(self, user_id: str):
        self.call_conns.pop(user_id, None)
        if not self._user_connected_anywhere(user_id):
            self.online_users.discard(user_id)

    async def call_send(self, target_user_id: str, payload: dict) -> bool:
        ws = self.call_conns.get(target_user_id)
        if ws:
            try:
                await ws.send_json(payload)
                return True
            except Exception:
                self.call_disconnect(target_user_id)
        return False

    async def call_send_many(self, target_user_ids: list[str], payload: dict) -> int:
        sent_count = 0
        for user_id in target_user_ids:
            if await self.call_send(user_id, payload):
                sent_count += 1
        return sent_count

    def is_online(self, user_id: str) -> bool:
        return user_id in self.online_users

    def _user_connected_anywhere(self, user_id: str) -> bool:
        if user_id in self.call_conns:
            return True
        if user_id in self.notification_conns:
            return True
        if any(any(u == user_id for u, _ in lst) for lst in self.channel_conns.values()):
            return True
        if any(any(u == user_id for u, _ in lst) for lst in self.dm_conns.values()):
            return True
        return False


manager = ConnectionManager()
