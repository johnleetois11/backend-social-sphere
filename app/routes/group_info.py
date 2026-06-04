from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from bson import ObjectId

from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/groups", tags=["Group Info & Management"])


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None


class RoleUpdate(BaseModel):
    role: str  # admin | member


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def to_object_id(id_value: str):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail="Invalid group ID")
    return ObjectId(id_value)


async def get_membership(user_id: str, group_id: str):
    db = get_mongo_db()

    return await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })


@router.get("/{group_id}/info")
async def get_group_info(
    group_id: str,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    membership = await get_membership(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    group = await db.groups.find_one({"_id": to_object_id(group_id)})

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    memberships = await db.group_members.find({
        "group_id": group_id
    }).to_list(length=500)

    members = []

    for m in memberships:
        member_user_id = m.get("user_id")

        if not ObjectId.is_valid(member_user_id):
            continue

        u = await db.users.find_one({"_id": ObjectId(member_user_id)})

        if u:
            members.append({
                "user_id": str(u["_id"]),
                "username": u.get("username"),
                "full_name": u.get("full_name"),
                "avatar_url": u.get("avatar_url"),
                "role": m.get("role"),
                "joined_at": serialize_datetime(m.get("joined_at")),
            })

    my_role = membership.get("role", "member")
    is_admin = my_role in ("owner", "admin")

    return {
        "id": str(group["_id"]),
        "name": group.get("name"),
        "description": group.get("description"),
        "purpose": group.get("purpose"),
        "type": group.get("type"),
        "avatar_url": group.get("avatar_url"),
        "owner_id": group.get("owner_id"),
        "created_at": serialize_datetime(group.get("created_at")),
        "member_count": len(members),
        "members": members,
        "invite_code": group.get("invite_code") if is_admin else None,
    }


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    data: GroupUpdate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    membership = await get_membership(user_id, group_id)

    if not membership or membership.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can edit group details")

    group = await db.groups.find_one({"_id": to_object_id(group_id)})

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    update_data = {}

    if data.name:
        update_data["name"] = data.name

    if data.description is not None:
        update_data["description"] = data.description

    if data.avatar_url is not None:
        update_data["avatar_url"] = data.avatar_url

    if not update_data:
        return {
            "message": "No changes made",
            "id": group_id,
            "name": group.get("name"),
        }

    update_data["updated_at"] = datetime.utcnow()

    await db.groups.update_one(
        {"_id": to_object_id(group_id)},
        {"$set": update_data},
    )

    updated_group = await db.groups.find_one({"_id": to_object_id(group_id)})

    return {
        "message": "Group updated",
        "id": str(updated_group["_id"]),
        "name": updated_group.get("name"),
    }


@router.put("/{group_id}/members/{target_user_id}/role")
async def update_member_role(
    group_id: str,
    target_user_id: str,
    data: RoleUpdate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    my_membership = await get_membership(user_id, group_id)

    if not my_membership or my_membership.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the group owner can change roles")

    if data.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")

    target = await get_membership(target_user_id, group_id)

    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.get("role") == "owner":
        raise HTTPException(status_code=400, detail="Cannot change owner's role")

    await db.group_members.update_one(
        {
            "user_id": target_user_id,
            "group_id": group_id,
        },
        {
            "$set": {
                "role": data.role,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return {"message": f"Role updated to {data.role}"}


@router.delete("/{group_id}/leave")
async def leave_group(
    group_id: str,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    membership = await get_membership(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=404, detail="Not a member of this group")

    if membership.get("role") == "owner":
        other_admins = await db.group_members.count_documents({
            "group_id": group_id,
            "user_id": {"$ne": user_id},
            "role": {"$in": ["owner", "admin"]},
        })

        if other_admins == 0:
            raise HTTPException(
                status_code=400,
                detail="Transfer ownership before leaving, or delete the group",
            )

    await db.group_members.delete_one({
        "user_id": user_id,
        "group_id": group_id,
    })

    return {"message": "Left group successfully"}