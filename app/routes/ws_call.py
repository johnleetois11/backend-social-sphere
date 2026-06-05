"""
Agora call support.

This file does two things:
1. Generates Agora RTC tokens for authenticated users.
2. Keeps a lightweight WebSocket for call request/accept/reject/end notifications.

Agora handles the actual voice/video connection.
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
    return zlib.crc32(user_id.encode("utf-8")) & 0x7FFFFFFF


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
        logger.error(f"Call token decode error: {e}")
        return None


async def share_group(user_id: str, peer_id: str) -> bool:
    db = get_mongo_db()

    my_groups = await db.group_members.find({"user_id": user_id}).to_list(length=500)
    my_group_ids = [m.get("group_id") for m in my_groups]

    if not my_group_ids:
        return False

    peer_membership = await db.group_members.find_one({
        "user_id": peer_id,
        "group_id": {"$in": my_group_ids},
    })

    return peer_membership is not None


async def is_group_member(user_id: str, group_id: str) -> bool:
    db = get_mongo_db()
    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    }) is not None


async def get_group_member_ids(group_id: str, exclude_user_id: str | None = None) -> list[str]:
    db = get_mongo_db()
    query = {"group_id": group_id}
    if exclude_user_id:
        query["user_id"] = {"$ne": exclude_user_id}

    members = await db.group_members.find(query).to_list(length=1000)
    return [str(m.get("user_id")) for m in members if m.get("user_id")]


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

        target = await db.users.find_one({"_id": ObjectId(data.target_id)})

        if not target:
            raise HTTPException(status_code=404, detail="Target user not found")

        if not await share_group(user_id, data.target_id):
            raise HTTPException(status_code=403, detail="You do not share a group with this user")

    agora_uid = mongo_id_to_agora_uid(user_id)

    current_timestamp = int(time.time())
    privilege_expire_timestamp = current_timestamp + AGORA_TOKEN_EXPIRE_SECONDS
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
    Call notification WebSocket.

    Supported events:
    - call_request
    - call_accept
    - call_reject
    - call_end

    Direct call: send target_id.
    Group call: send group_id. The server broadcasts to group members except caller.
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
                group_id = data.get("group_id")
                channel_name = data.get("channel_name")

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

                if not channel_name:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing channel_name",
                    })
                    continue

                base_payload = {
                    **data,
                    "type": sig_type,
                    "channel_name": channel_name,
                    "from_user_id": user_id,
                    "from_username": user.get("username"),
                    "from_avatar": user.get("avatar_url"),
                    "timestamp": datetime.utcnow().isoformat(),
                }

                # Group call request: broadcast to group members.
                if sig_type == "call_request" and group_id:
                    if not ObjectId.is_valid(str(group_id)):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid group ID",
                        })
                        continue

                    if not await is_group_member(user_id, str(group_id)):
                        await websocket.send_json({
                            "type": "error",
                            "message": "You are not a member of this group",
                        })
                        continue

                    target_user_ids = await get_group_member_ids(str(group_id), exclude_user_id=user_id)
                    sent_count = await manager.call_send_many(target_user_ids, base_payload)

                    await websocket.send_json({
                        "type": "call_request_sent",
                        "sent_count": sent_count,
                        "group_id": group_id,
                        "channel_name": channel_name,
                    })

                    logger.info(
                        f"Agora group call request from {user.get('username')} to group {group_id}, sent {sent_count}"
                    )
                    continue

                # Direct signal: accept/reject/end or one-to-one request.
                if not target_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing target_id or group_id",
                    })
                    continue

                if not ObjectId.is_valid(str(target_id)):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid target user ID",
                    })
                    continue

                target = await db.users.find_one({"_id": ObjectId(str(target_id))})

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

                await manager.call_send(str(target_id), base_payload)

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
