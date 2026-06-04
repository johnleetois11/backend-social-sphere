from datetime import datetime
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.schemas.group import GroupCreate, GroupJoin, GroupJoinByCode
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/groups", tags=["Groups"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_group(
    group: dict,
    role: str | None = None,
    member_count: int = 0,
    last_post: dict | None = None,
):
    return {
        "id": str(group["_id"]),
        "name": group.get("name"),
        "description": group.get("description"),
        "purpose": group.get("purpose"),
        "type": group.get("type"),
        "avatar_url": group.get("avatar_url"),
        "invite_code": group.get("invite_code"),
        "owner_id": group.get("owner_id"),
        "created_at": serialize_datetime(group.get("created_at")),
        "role": role,
        "member_count": member_count,
        "last_post_at": serialize_datetime(last_post.get("created_at")) if last_post else None,
        "last_post_preview": (
            last_post.get("content", "")[:80]
            if last_post and last_post.get("content")
            else None
        ),
    }


def generate_invite_code(length: int = 8):
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def to_object_id(id_value: str):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail="Invalid group ID")
    return ObjectId(id_value)


@router.post("/create")
async def create_group_route(
    group: GroupCreate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    invite_code = generate_invite_code()

    while await db.groups.find_one({"invite_code": invite_code}):
        invite_code = generate_invite_code()

    group_data = {
        "name": group.name,
        "description": group.description,
        "purpose": group.purpose,
        "type": group.type,
        "avatar_url": None,
        "invite_code": invite_code,
        "owner_id": user_id,
        "created_at": datetime.utcnow(),
    }

    result = await db.groups.insert_one(group_data)
    group_id = str(result.inserted_id)

    await db.group_members.insert_one({
        "user_id": user_id,
        "group_id": group_id,
        "role": "owner",
        "joined_at": datetime.utcnow(),
    })

    await db.user_points.insert_one({
        "user_id": user_id,
        "group_id": group_id,
        "points": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })

    created_group = await db.groups.find_one({"_id": result.inserted_id})

    return serialize_group(
        created_group,
        role="owner",
        member_count=1,
    )


@router.post("/join")
async def join_group_route(
    data: GroupJoin,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({"_id": to_object_id(data.group_id)})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    existing_member = await db.group_members.find_one({
        "user_id": user_id,
        "group_id": data.group_id,
    })

    if existing_member:
        raise HTTPException(status_code=400, detail="Already a member")

    await db.group_members.insert_one({
        "user_id": user_id,
        "group_id": data.group_id,
        "role": "member",
        "joined_at": datetime.utcnow(),
    })

    existing_points = await db.user_points.find_one({
        "user_id": user_id,
        "group_id": data.group_id,
    })

    if not existing_points:
        await db.user_points.insert_one({
            "user_id": user_id,
            "group_id": data.group_id,
            "points": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

    return {"message": "Joined group"}


@router.post("/join-by-code")
async def join_by_code_route(
    data: GroupJoinByCode,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({"invite_code": data.code})

    if not group:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    group_id = str(group["_id"])

    existing_member = await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })

    if existing_member:
        return {
            "message": "Already a member",
            "group_id": group_id,
            "group_name": group.get("name"),
        }

    await db.group_members.insert_one({
        "user_id": user_id,
        "group_id": group_id,
        "role": "member",
        "joined_at": datetime.utcnow(),
    })

    existing_points = await db.user_points.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })

    if not existing_points:
        await db.user_points.insert_one({
            "user_id": user_id,
            "group_id": group_id,
            "points": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

    return {
        "message": "Joined group",
        "group_id": group_id,
        "group_name": group.get("name"),
    }


@router.get("/my")
async def get_my_groups(user=Depends(get_current_mongo_user)):
    db = get_mongo_db()
    user_id = str(user["_id"])

    memberships = await db.group_members.find({
        "user_id": user_id
    }).to_list(length=100)

    groups = []

    for membership in memberships:
        group_id = membership.get("group_id")

        if not ObjectId.is_valid(group_id):
            continue

        group = await db.groups.find_one({"_id": ObjectId(group_id)})
        if not group:
            continue

        member_count = await db.group_members.count_documents({
            "group_id": group_id
        })

        last_post = await db.posts.find_one(
            {"group_id": group_id},
            sort=[("created_at", -1)]
        )

        groups.append(
            serialize_group(
                group,
                role=membership.get("role"),
                member_count=member_count,
                last_post=last_post,
            )
        )

    return groups