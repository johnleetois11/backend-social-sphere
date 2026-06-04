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


async def share_group(user_id: str, peer_id: str):
    db = get_mongo_db()

    my_groups = await db.group_members.find({
        "user_id": user_id
    }).to_list(length=500)

    my_group_ids = [m.get("group_id") for m in my_groups]

    if not my_group_ids:
        return False

    peer_membership = await db.group_members.find_one({
        "user_id": peer_id,
        "group_id": {"$in": my_group_ids},
    })

    return peer_membership is not None


@router.websocket("/ws/dm/{peer_id}")
async def dm_chat(websocket: WebSocket, peer_id: str):
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

        if not ObjectId.is_valid(peer_id):
            await websocket.close(code=4004)
            return

        peer = await db.users.find_one({
            "_id": ObjectId(peer_id)
        })

        if not peer:
            await websocket.close(code=4004)
            return

        if not await share_group(user_id, peer_id):
            await websocket.close(code=4003)
            return

        await manager.dm_connect(user_id, peer_id, websocket)

        await manager.dm_send(user_id, peer_id, {
            "type": "presence",
            "user_id": user_id,
            "is_online": True,
        })

        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "message")

                if msg_type == "typing":
                    await manager.set_typing_dm(
                        user_id,
                        peer_id,
                        user.get("username"),
                        data.get("is_typing", False),
                    )

                elif msg_type == "message":
                    content = data.get("content", "").strip()
                    message_type = data.get("message_type", "text")

                    if not content:
                        continue

                    message_data = {
                        "sender_id": user_id,
                        "receiver_id": peer_id,
                        "content": content,
                        "message_type": message_type,
                        "is_read": False,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }

                    result = await db.direct_messages.insert_one(message_data)

                    created_message = await db.direct_messages.find_one({
                        "_id": result.inserted_id
                    })

                    payload_out = {
                        "type": "message",
                        "id": str(created_message["_id"]),
                        "sender_id": user_id,
                        "receiver_id": peer_id,
                        "username": user.get("username"),
                        "avatar_url": user.get("avatar_url"),
                        "content": created_message.get("content"),
                        "message_type": created_message.get("message_type", "text"),
                        "is_read": False,
                        "timestamp": serialize_datetime(created_message.get("created_at")),
                    }

                    await manager.dm_send(user_id, peer_id, payload_out)

                elif msg_type == "seen":
                    await db.direct_messages.update_many(
                        {
                            "sender_id": peer_id,
                            "receiver_id": user_id,
                            "is_read": False,
                        },
                        {
                            "$set": {
                                "is_read": True,
                                "read_at": datetime.utcnow(),
                            }
                        },
                    )

                    await manager.dm_send(user_id, peer_id, {
                        "type": "seen",
                        "by_user_id": user_id,
                    })

            except Exception as e:
                logger.info(f"DM WS loop ended: {e}")
                break

    except Exception as e:
        logger.error(f"DM WS error: {e}")

    finally:
        if user:
            user_id = str(user["_id"])

            manager.dm_disconnect(user_id, peer_id, websocket)

            await manager.dm_send(user_id, peer_id, {
                "type": "presence",
                "user_id": user_id,
                "is_online": False,
            })