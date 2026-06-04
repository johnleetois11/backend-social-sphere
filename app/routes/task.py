from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.schemas.task import TaskCreate
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_object_id(id_value: str, label: str = "ID"):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return ObjectId(id_value)


def serialize_task(task: dict):
    return {
        "id": str(task["_id"]),
        "group_id": task.get("group_id"),
        "assigned_to": task.get("assigned_to"),
        "assigned_to_username": task.get("assigned_to_username"),
        "title": task.get("title"),
        "description": task.get("description"),
        "status": task.get("status", "pending"),
        "deadline": serialize_datetime(task.get("deadline")),
        "created_by": task.get("created_by"),
        "created_at": serialize_datetime(task.get("created_at")),
        "updated_at": serialize_datetime(task.get("updated_at")),
    }


async def get_membership(user_id: str, group_id: str):
    db = get_mongo_db()

    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })


@router.post("/")
async def create(
    data: TaskCreate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({
        "_id": to_object_id(data.group_id, "group ID")
    })

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    creator_membership = await get_membership(user_id, data.group_id)

    if not creator_membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    assigned_user = await db.users.find_one({
        "_id": to_object_id(data.assigned_to, "assigned user ID")
    })

    if not assigned_user:
        raise HTTPException(status_code=404, detail="Assigned user not found")

    assigned_membership = await get_membership(data.assigned_to, data.group_id)

    if not assigned_membership:
        raise HTTPException(
            status_code=400,
            detail="Assigned user is not a member of this group"
        )

    task_data = {
        "group_id": data.group_id,
        "assigned_to": data.assigned_to,
        "assigned_to_username": assigned_user.get("username"),
        "title": data.title,
        "description": data.description,
        "status": "pending",
        "deadline": data.deadline,
        "created_by": user_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.tasks.insert_one(task_data)

    created_task = await db.tasks.find_one({
        "_id": result.inserted_id
    })

    return serialize_task(created_task)


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

    tasks = await db.tasks.find({
        "group_id": group_id
    }).sort("deadline", 1).to_list(length=200)

    return [serialize_task(task) for task in tasks]