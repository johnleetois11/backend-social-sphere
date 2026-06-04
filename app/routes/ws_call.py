"""
Agora call support.

This file does two things:
1. Generates Agora RTC tokens for authenticated users.
2. Keeps a lightweight WebSocket for call request/accept/reject/end notifications.

Agora handles the actual voice/video connection.
We do not need raw WebRTC offer/answer/ice_candidate handling anymore.
"""

from datetime import datetime
import logging
import time
import zlib

from fastapi import APIRouter, WebSocket, Depends, HTTPException
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from bson import ObjectId
from agora_token_builder import RtcTokenBuilder

from app.services.ws_manager import manager
from app.database.mongodb import get_mongo_db
from app.core.config import (
    SECRET_KEY,
    ALGORITHM,
    AGORA_APP_ID,
    AGORA_APP_CERTIFICATE,
    AGORA_TOKEN_EXPIRE_SECONDS,
)
from app.core.mongo_dependencies import get_current_mongo_user

logger = logging.getLogger(__name__)
router = APIRouter()


class AgoraTokenRequest(BaseModel):
    channel_name: str = Field(min_length=1, max_length=64)
    target_id: str | None = None


def mongo_id_to_agora_uid(user_id: str) -> int:
    """
    Agora RTC UID should be a number.
    MongoDB user ID is a string, so we convert it to a stable numeric UID.
    """
    return zlib.crc32(user_id.encode("utf-8")) & 0x7FFFFFFF


async def get_user_from_token(token: str):
    if token.startswith("Bearer "):
        token = token.replace("Bearer ", "").strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Your new MongoDB auth token uses "sub".
        # Old token may use "user_id", so we support both.
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
        logger.error(f"Call token decode error: {e}")
        return None


async def share_group(user_id: str, peer_id: str) -> bool:
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


@router.post("/calls/agora-token")
async def generate_agora_token(
    data: AgoraTokenRequest,
    user=Depends(get_current_mongo_user),
):
    if not AGORA_APP_ID:
        raise HTTPException(status_code=500, detail="AGORA_APP_ID is missing")

    if not AGORA_APP_CERTIFICATE:
        raise HTTPException(status_code=500, detail="AGORA_APP_CERTIFICATE is missing")

    db = get_mongo_db()
    user_id = str(user["_id"])

    if data.target_id:
        if not ObjectId.is_valid(data.target_id):
            raise HTTPException(status_code=400, detail="Invalid target user ID")

        target = await db.users.find_one({
            "_id": ObjectId(data.target_id)
        })

        if not target:
            raise HTTPException(status_code=404, detail="Target user not found")

        if not await share_group(user_id, data.target_id):
            raise HTTPException(
                status_code=403,
                detail="You do not share a group with this user"
            )

    agora_uid = mongo_id_to_agora_uid(user_id)

    current_timestamp = int(time.time())
    privilege_expire_timestamp = current_timestamp + AGORA_TOKEN_EXPIRE_SECONDS

    # 1 = publisher role
    role = 1

    token = RtcTokenBuilder.buildTokenWithUid(
        AGORA_APP_ID,
        AGORA_APP_CERTIFICATE,
        data.channel_name,
        agora_uid,
        role,
        privilege_expire_timestamp,
    )

    return {
        "app_id": AGORA_APP_ID,
        "token": token,
        "channel_name": data.channel_name,
        "uid": agora_uid,
        "expires_at": privilege_expire_timestamp,
    }


@router.websocket("/ws/call")
async def call_signaling(websocket: WebSocket):
    """
    This WebSocket is now only for call notification events:
    - call_request
    - call_accept
    - call_reject
    - call_end

    Do not send offer/answer/ice_candidate anymore when using Agora.
    """
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

        await manager.call_connect(user_id, websocket)

        logger.info(f"User {user.get('username')} connected to Agora call signaling")

        while True:
            try:
                data = await websocket.receive_json()

                sig_type = data.get("type")
                target_id = data.get("target_id")
                channel_name = data.get("channel_name")

                if not target_id:
                    continue

                if not ObjectId.is_valid(str(target_id)):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid target user ID",
                    })
                    continue

                target = await db.users.find_one({
                    "_id": ObjectId(str(target_id))
                })

                if not target:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Target user not found",
                    })
                    continue

                if not await share_group(user_id, str(target_id)):
                    await websocket.send_json({
                        "type": "error",
                        "message": "You do not share a group with this user",
                    })
                    continue

                allowed_types = {
                    "call_request",
                    "call_accept",
                    "call_reject",
                    "call_end",
                }

                if sig_type not in allowed_types:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid call signal type",
                    })
                    continue

                await manager.call_send(str(target_id), {
                    **data,
                    "type": sig_type,
                    "channel_name": channel_name,
                    "from_user_id": user_id,
                    "from_username": user.get("username"),
                    "from_avatar": user.get("avatar_url"),
                    "timestamp": datetime.utcnow().isoformat(),
                })

                logger.info(
                    f"Agora call signal '{sig_type}' from {user.get('username')} to {target_id}"
                )

            except Exception as e:
                logger.info(f"Agora call WS loop ended: {e}")
                break

    except Exception as e:
        logger.error(f"Agora call WS error: {e}")

    finally:
        if user:
            user_id = str(user["_id"])
            manager.call_disconnect(user_id)