from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.schemas.event import EventCreate
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/events", tags=["Events"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_object_id(id_value: str, label: str = "ID"):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return ObjectId(id_value)


def serialize_event(event: dict):
    return {
        "id": str(event["_id"]),
        "group_id": event.get("group_id"),
        "title": event.get("title"),
        "description": event.get("description"),
        "event_date": serialize_datetime(event.get("event_date")),
        "created_by": event.get("created_by"),
        "created_at": serialize_datetime(event.get("created_at")),
        "updated_at": serialize_datetime(event.get("updated_at")),
    }


async def get_membership(user_id: str, group_id: str):
    db = get_mongo_db()

    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })


@router.post("/")
async def create(
    data: EventCreate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({
        "_id": to_object_id(data.group_id, "group ID")
    })

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = await get_membership(user_id, data.group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    event_data = {
        "group_id": data.group_id,
        "title": data.title,
        "description": data.description,
        "event_date": data.event_date,
        "created_by": user_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.events.insert_one(event_data)

    created_event = await db.events.find_one({
        "_id": result.inserted_id
    })

    return serialize_event(created_event)


@router.get("/group/{group_id}")
async def get(
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
        raise HTTPException(status_code=403, detail="Access denied")

    events = await db.events.find({
        "group_id": group_id
    }).sort("event_date", 1).to_list(length=200)

    return [serialize_event(event) for event in events]