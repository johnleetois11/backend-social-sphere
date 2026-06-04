from typing import Optional, List
from datetime import datetime

from fastapi import HTTPException
from bson import ObjectId

from app.database.mongodb import get_mongo_db
from app.core.security import verify_password, hash_password


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def to_object_id(id_value: str):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail="Invalid ID")
    return ObjectId(id_value)


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_user(user: dict):
    if not user:
        return None

    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "birthdate": user.get("birthdate"),
        "gender": user.get("gender"),
        "mobile": user.get("mobile"),
        "address": user.get("address"),
        "facebook_link": user.get("facebook_link"),
        "hobbies": user.get("hobbies"),
        "bio": user.get("bio"),
        "avatar_url": user.get("avatar_url"),
        "created_at": serialize_datetime(user.get("created_at")),
    }


# ──────────────────────────────────────────────
# Badge & rank helpers
# ──────────────────────────────────────────────

def compute_badges(points: int) -> List[str]:
    badges = []

    if points >= 0:
        badges.append("New Member")
    if points >= 50:
        badges.append("Contributor")
    if points >= 100:
        badges.append("Active Member")
    if points >= 300:
        badges.append("Star Member")
    if points >= 500:
        badges.append("Legend")

    return badges


async def compute_rank(user_id: str, group_id: str) -> int:
    db = get_mongo_db()

    rec = await db.user_points.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })

    if not rec:
        return 0

    higher = await db.user_points.count_documents({
        "group_id": group_id,
        "points": {"$gt": rec.get("points", 0)},
    })

    return higher + 1


# ──────────────────────────────────────────────
# Profile CRUD
# ──────────────────────────────────────────────

async def get_own_profile(user_id: str):
    db = get_mongo_db()

    user = await db.users.find_one({"_id": to_object_id(user_id)})

    return serialize_user(user)


async def update_profile(user_id: str, data):
    db = get_mongo_db()

    user = await db.users.find_one({"_id": to_object_id(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = {}

    if data.username and data.username != user.get("username"):
        taken = await db.users.find_one({
            "username": data.username,
            "_id": {"$ne": to_object_id(user_id)},
        })

        if taken:
            raise HTTPException(status_code=400, detail="Username already taken")

        update_data["username"] = data.username

    if data.full_name is not None:
        update_data["full_name"] = data.full_name
    if data.bio is not None:
        update_data["bio"] = data.bio
    if data.avatar_url is not None:
        update_data["avatar_url"] = data.avatar_url
    if data.hobbies is not None:
        update_data["hobbies"] = data.hobbies

    if not update_data:
        return serialize_user(user)

    update_data["updated_at"] = datetime.utcnow()

    await db.users.update_one(
        {"_id": to_object_id(user_id)},
        {"$set": update_data},
    )

    updated_user = await db.users.find_one({"_id": to_object_id(user_id)})

    return serialize_user(updated_user)


async def change_password(user_id: str, current_password: str, new_password: str):
    db = get_mongo_db()

    user = await db.users.find_one({"_id": to_object_id(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    await db.users.update_one(
        {"_id": to_object_id(user_id)},
        {
            "$set": {
                "password_hash": hash_password(new_password),
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return True


async def delete_account(user_id: str):
    db = get_mongo_db()

    await db.login_activity.delete_many({"user_id": user_id})
    await db.user_points.delete_many({"user_id": user_id})
    await db.group_members.delete_many({"user_id": user_id})
    await db.users.delete_one({"_id": to_object_id(user_id)})

    return True


# ──────────────────────────────────────────────
# Group-restricted member profile
# ──────────────────────────────────────────────

async def get_member_profile(viewer_id: str, target_id: str, group_id: str):
    db = get_mongo_db()

    viewer_membership = await db.group_members.find_one({
        "user_id": viewer_id,
        "group_id": group_id,
    })

    if not viewer_membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")

    target_membership = await db.group_members.find_one({
        "user_id": target_id,
        "group_id": group_id,
    })

    if not target_membership:
        raise HTTPException(status_code=404, detail="Member not found in this group")

    target = await db.users.find_one({"_id": to_object_id(target_id)})

    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    rec = await db.user_points.find_one({
        "user_id": target_id,
        "group_id": group_id,
    })

    points = rec.get("points", 0) if rec else 0

    return {
        "id": str(target["_id"]),
        "username": target.get("username"),
        "full_name": target.get("full_name"),
        "bio": target.get("bio"),
        "avatar_url": target.get("avatar_url"),
        "created_at": serialize_datetime(target.get("created_at")),
        "role": target_membership.get("role"),
        "points": points,
        "rank": await compute_rank(target_id, group_id),
        "joined_group_at": serialize_datetime(target_membership.get("joined_at")),
        "badges": compute_badges(points),
    }


# ──────────────────────────────────────────────
# Group engagement stats for own profile
# ──────────────────────────────────────────────

async def get_my_group_stats(user_id: str):
    db = get_mongo_db()

    memberships = await db.group_members.find({"user_id": user_id}).to_list(length=100)

    stats = []

    for membership in memberships:
        group_id = membership.get("group_id")

        group = None

        if ObjectId.is_valid(str(group_id)):
            group = await db.groups.find_one({"_id": ObjectId(str(group_id))})

        if not group:
            group = await db.groups.find_one({"id": group_id})

        if not group:
            continue

        rec = await db.user_points.find_one({
            "user_id": user_id,
            "group_id": str(group_id),
        })

        points = rec.get("points", 0) if rec else 0

        stats.append({
            "group_id": str(group.get("_id", group_id)),
            "group_name": group.get("name"),
            "role": membership.get("role"),
            "points": points,
            "rank": await compute_rank(user_id, str(group_id)),
            "badges": compute_badges(points),
            "joined_at": serialize_datetime(membership.get("joined_at")),
        })

    return stats


# ──────────────────────────────────────────────
# Login activity
# ──────────────────────────────────────────────

async def record_login(user_id: str, ip_address: Optional[str] = None):
    db = get_mongo_db()

    activity = {
        "user_id": user_id,
        "ip_address": ip_address,
        "created_at": datetime.utcnow(),
    }

    result = await db.login_activity.insert_one(activity)

    activity["id"] = str(result.inserted_id)
    activity["created_at"] = activity["created_at"].isoformat()

    return activity


async def get_login_activity(user_id: str, limit: int = 10):
    db = get_mongo_db()

    activities = await db.login_activity.find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)

    return [
        {
            "id": str(activity["_id"]),
            "user_id": activity.get("user_id"),
            "email": activity.get("email"),
            "ip_address": activity.get("ip_address"),
            "created_at": serialize_datetime(activity.get("created_at")),
        }
        for activity in activities
    ]