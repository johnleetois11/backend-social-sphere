from datetime import datetime
import logging

from fastapi import APIRouter, WebSocket
from jose import jwt, JWTError
from bson import ObjectId

from app.services.ws_manager import manager
from app.database.mongodb import get_mongo_db
from app.core.config import SECRET_KEY, ALGORITHM

logger = logging.getLogger(__name__)
router = APIRouter()


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def get_user_from_token(token: str):
    if token.startswith("Bearer "):
        token = token.replace("Bearer ", "").strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # New MongoDB auth token uses "sub"
        user_id = payload.get("sub") or payload.get("user_id")

        if not user_id or not ObjectId.is_valid(str(user_id)):
            return None

        db = get_mongo_db()

        user = await db.users.find_one({
            "_id": ObjectId(str(user_id))
        })

        return user

    except JWTError:
        return None
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        return None


async def is_group_member(user_id: str, group_id: str):
    db = get_mongo_db()

    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })


@router.websocket("/ws/chat/{channel_id}")
async def chat(websocket: WebSocket, channel_id: str):
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001)
        return

    user = None

    try:
        db = get_mongo_db()

        user = await get_user_from_token(token)

        if not user:
            await websocket.close(code=4001)
            return

        user_id = str(user["_id"])

        if not ObjectId.is_valid(channel_id):
            await websocket.close(code=4004)
            return

        channel = await db.channels.find_one({
            "_id": ObjectId(channel_id)
        })

        if not channel:
            await websocket.close(code=4004)
            return

        group_id = channel.get("group_id")

        membership = await is_group_member(user_id, group_id)

        if not membership:
            await websocket.close(code=4003)
            return

        await manager.channel_connect(channel_id, user_id, websocket)

        await manager.channel_broadcast(channel_id, {
            "type": "presence",
            "user_id": user_id,
            "username": user.get("username"),
            "is_online": True,
        })

        # Send message history, oldest to newest
        history = await db.messages.find({
            "channel_id": channel_id
        }).sort("created_at", 1).limit(50).to_list(length=50)

        for message in history:
            sender = None
            sender_id = str(message.get("user_id"))

            if ObjectId.is_valid(sender_id):
                sender = await db.users.find_one({
                    "_id": ObjectId(sender_id)
                })

            await websocket.send_json({
                "type": "history",
                "id": str(message["_id"]),
                "user_id": sender_id,
                "username": sender.get("username") if sender else "Unknown",
                "avatar_url": sender.get("avatar_url") if sender else None,
                "content": message.get("content"),
                "message_type": message.get("message_type", "text"),
                "timestamp": serialize_datetime(message.get("created_at")),
            })

        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "typing":
                    await manager.set_typing_channel(
                        channel_id,
                        user_id,
                        user.get("username"),
                        data.get("is_typing", False),
                    )

                elif msg_type == "message":
                    content = data.get("content", "").strip()
                    message_type = data.get("message_type", "text")

                    if not content:
                        continue

                    message_data = {
                        "channel_id": channel_id,
                        "group_id": group_id,
                        "user_id": user_id,
                        "content": content,
                        "message_type": message_type,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }

                    result = await db.messages.insert_one(message_data)

                    created_message = await db.messages.find_one({
                        "_id": result.inserted_id
                    })

                    await manager.channel_broadcast(channel_id, {
                        "type": "message",
                        "id": str(created_message["_id"]),
                        "user_id": user_id,
                        "username": user.get("username"),
                        "avatar_url": user.get("avatar_url"),
                        "content": created_message.get("content"),
                        "message_type": created_message.get("message_type", "text"),
                        "timestamp": serialize_datetime(created_message.get("created_at")),
                    })

                elif msg_type == "seen":
                    await manager.channel_broadcast(channel_id, {
                        "type": "seen",
                        "user_id": user_id,
                        "username": user.get("username"),
                    })

            except Exception as e:
                logger.info(f"Channel WS loop ended: {e}")
                break

    except Exception as e:
        logger.error(f"Channel WS error: {e}")

    finally:
        if user:
            user_id = str(user["_id"])

            manager.channel_disconnect(channel_id, user_id, websocket)

            await manager.channel_broadcast(channel_id, {
                "type": "presence",
                "user_id": user_id,
                "username": user.get("username"),
                "is_online": False,
            })