import logging

from fastapi import APIRouter, WebSocket
from jose import jwt, JWTError
from bson import ObjectId

from app.services.ws_manager import manager
from app.database.mongodb import get_mongo_db
from app.core.config import SECRET_KEY, ALGORITHM

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_user_from_token(token: str):
    if token.startswith("Bearer "):
        token = token.replace("Bearer ", "").strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub") or payload.get("user_id")

        if not user_id or not ObjectId.is_valid(str(user_id)):
            return None

        db = get_mongo_db()
        return await db.users.find_one({"_id": ObjectId(str(user_id))})

    except JWTError:
        return None
    except Exception as e:
        logger.error(f"Notification token decode error: {e}")
        return None


@router.websocket("/ws/notifications")
async def notifications(websocket: WebSocket):
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=4001)
        return

    user = None

    try:
        user = await get_user_from_token(token)

        if not user:
            await websocket.close(code=4001)
            return

        user_id = str(user["_id"])
        await manager.notification_connect(user_id, websocket)

        await websocket.send_json({
            "type": "notification_ready",
            "user_id": user_id,
            "username": user.get("username"),
        })

        while True:
            # Keep the socket alive. Client may send ping/heartbeat.
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except Exception as e:
        logger.info(f"Notification WS ended: {e}")

    finally:
        if user:
            manager.notification_disconnect(str(user["_id"]))
