from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.schemas.idea import IdeaCreate
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/ideas", tags=["Ideas"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_object_id(id_value: str, label: str = "ID"):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return ObjectId(id_value)


def serialize_idea(idea: dict):
    return {
        "id": str(idea["_id"]),
        "group_id": idea.get("group_id"),
        "user_id": idea.get("user_id"),
        "username": idea.get("username"),
        "title": idea.get("title"),
        "description": idea.get("description"),
        "status": idea.get("status", "pending"),
        "created_at": serialize_datetime(idea.get("created_at")),
        "updated_at": serialize_datetime(idea.get("updated_at")),
    }


async def get_membership(user_id: str, group_id: str):
    db = get_mongo_db()

    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })


async def add_points(user_id: str, group_id: str, points: int):
    db = get_mongo_db()

    await db.user_points.update_one(
        {
            "user_id": user_id,
            "group_id": group_id,
        },
        {
            "$inc": {"points": points},
            "$set": {"updated_at": datetime.utcnow()},
            "$setOnInsert": {
                "created_at": datetime.utcnow(),
            },
        },
        upsert=True,
    )


@router.post("/")
async def create(
    data: IdeaCreate,
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

    idea_data = {
        "group_id": data.group_id,
        "user_id": user_id,
        "username": user.get("username"),
        "title": data.title,
        "description": data.description,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.ideas.insert_one(idea_data)

    await add_points(user_id, data.group_id, 4)

    created_idea = await db.ideas.find_one({
        "_id": result.inserted_id
    })

    return serialize_idea(created_idea)


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

    ideas = await db.ideas.find({
        "group_id": group_id
    }).sort("created_at", -1).to_list(length=200)

    return [serialize_idea(idea) for idea in ideas]