from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from jose import jwt, JWTError
from app.core.config import SECRET_KEY, ALGORITHM
from app.models.message import Message
from app.models.channel import Channel
from app.models.user import User
from app.services.group_utils import is_member

router = APIRouter()

active_connections = {}

def get_current_user_ws(token: str, db: Session):
    if not SECRET_KEY:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore
        user_id = payload.get("user_id")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == user_id).first()
        return user
    except JWTError:
        return None


@router.websocket("/ws/chat/{channel_id}")
async def websocket_chat(websocket: WebSocket, channel_id: int, token: str):
    await websocket.accept()

    db: Session = next(get_db())

    try:
        user = get_current_user_ws(token, db)

        if not user:
            await websocket.close()
            return

        # ✅ GET CHANNEL
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            await websocket.close()
            return

        # ✅ CHECK MEMBERSHIP
        if not is_member(db, user.id, channel.group_id):
            await websocket.close()
            return

        # ✅ STORE CONNECTION
        if channel_id not in active_connections:
            active_connections[channel_id] = []

        active_connections[channel_id].append(websocket)

        while True:
            data = await websocket.receive_text()

            # ✅ SAVE MESSAGE
            message = Message(
                content=data,
                user_id=user.id,
                channel_id=channel_id
            )
            db.add(message)
            db.commit()

            # ✅ BROADCAST
            for connection in active_connections[channel_id]:
                await connection.send_text(
                    f"User {user.id}: {data}"
                )

    except WebSocketDisconnect:
        if channel_id in active_connections and websocket in active_connections[channel_id]:
            active_connections[channel_id].remove(websocket)

        