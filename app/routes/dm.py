from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/dm", tags=["Direct Messages"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_object_id(id_value: str, label: str = "ID"):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return ObjectId(id_value)


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


async def serialize_dm_message(message: dict):
    return {
        "id": str(message["_id"]),
        "sender_id": message.get("sender_id"),
        "receiver_id": message.get("receiver_id"),
        "content": message.get("content"),
        "message_type": message.get("message_type", "text"),
        "is_read": message.get("is_read", False),
        "created_at": serialize_datetime(message.get("created_at")),
    }


@router.get("/conversations")
async def get_conversations(user=Depends(get_current_mongo_user)):
    db = get_mongo_db()
    user_id = str(user["_id"])

    messages = await db.direct_messages.find({
        "$or": [
            {"sender_id": user_id},
            {"receiver_id": user_id},
        ]
    }).sort("created_at", -1).to_list(length=1000)

    conversations = {}

    for message in messages:
        sender_id = message.get("sender_id")
        receiver_id = message.get("receiver_id")

        peer_id = receiver_id if sender_id == user_id else sender_id

        if peer_id not in conversations:
            peer = None

            if ObjectId.is_valid(peer_id):
                peer = await db.users.find_one({
                    "_id": ObjectId(peer_id)
                })

            unread_count = await db.direct_messages.count_documents({
                "sender_id": peer_id,
                "receiver_id": user_id,
                "is_read": False,
            })

            conversations[peer_id] = {
                "peer_id": peer_id,
                "username": peer.get("username") if peer else "Unknown",
                "full_name": peer.get("full_name") if peer else None,
                "avatar_url": peer.get("avatar_url") if peer else None,
                "last_message": message.get("content"),
                "last_message_type": message.get("message_type", "text"),
                "last_message_at": serialize_datetime(message.get("created_at")),
                "unread_count": unread_count,
            }

    return list(conversations.values())


@router.get("/history/{peer_id}")
async def get_history(
    peer_id: str,
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    peer = await db.users.find_one({
        "_id": to_object_id(peer_id, "peer ID")
    })

    if not peer:
        raise HTTPException(status_code=404, detail="Peer user not found")

    if not await share_group(user_id, peer_id):
        raise HTTPException(status_code=403, detail="You do not share a group with this user")

    messages = await db.direct_messages.find({
        "$or": [
            {
                "sender_id": user_id,
                "receiver_id": peer_id,
            },
            {
                "sender_id": peer_id,
                "receiver_id": user_id,
            },
        ]
    }).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)

    messages.reverse()

    return [await serialize_dm_message(message) for message in messages]