from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.schemas.channel import ChannelCreate
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/channels", tags=["Channels"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_object_id(id_value: str, label: str = "ID"):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return ObjectId(id_value)


def serialize_channel(channel: dict):
    return {
        "id": str(channel["_id"]),
        "group_id": channel.get("group_id"),
        "name": channel.get("name"),
        "type": channel.get("type"),
        "created_by": channel.get("created_by"),
        "created_at": serialize_datetime(channel.get("created_at")),
        "updated_at": serialize_datetime(channel.get("updated_at")),
    }


async def get_membership(user_id: str, group_id: str):
    db = get_mongo_db()

    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })


@router.post("/")
async def create(
    data: ChannelCreate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    if data.type not in ("text", "announcement"):
        raise HTTPException(
            status_code=400,
            detail="Channel type must be 'text' or 'announcement'",
        )

    group = await db.groups.find_one({
        "_id": to_object_id(data.group_id, "group ID")
    })

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = await get_membership(user_id, data.group_id)

    if not membership or membership.get("role") not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only group owners/admins can create channels",
        )

    existing_channel = await db.channels.find_one({
        "group_id": data.group_id,
        "name": data.name,
    })

    if existing_channel:
        raise HTTPException(
            status_code=400,
            detail="Channel name already exists in this group",
        )

    channel_data = {
        "group_id": data.group_id,
        "name": data.name,
        "type": data.type,
        "created_by": user_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.channels.insert_one(channel_data)

    created_channel = await db.channels.find_one({
        "_id": result.inserted_id
    })

    return serialize_channel(created_channel)


@router.get("/group/{group_id}")
async def get_channels(
    group_id: str,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({
        "_id": to_object_id(group_id, "group ID")
    })

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = await get_membership(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    channels = await db.channels.find({
        "group_id": group_id
    }).sort("created_at", 1).to_list(length=100)

    return [serialize_channel(channel) for channel in channels]