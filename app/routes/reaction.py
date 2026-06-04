from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/reactions", tags=["Reactions"])


def to_object_id(id_value: str, label: str = "ID"):
    if not ObjectId.is_valid(id_value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return ObjectId(id_value)


async def is_group_member(user_id: str, group_id: str):
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


@router.post("/toggle/{post_id}")
async def toggle(
    post_id: str,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])
    reaction_type = "like"

    post = await db.posts.find_one({
        "_id": to_object_id(post_id, "post ID")
    })

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    group_id = post.get("group_id")

    membership = await is_group_member(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    existing = await db.reactions.find_one({
        "user_id": user_id,
        "post_id": post_id,
        "type": reaction_type,
    })

    if existing:
        await db.reactions.delete_one({
            "_id": existing["_id"]
        })

        return {
            "liked": False,
            "post_id": post_id,
        }

    reaction_data = {
        "user_id": user_id,
        "post_id": post_id,
        "group_id": group_id,
        "type": reaction_type,
        "created_at": datetime.utcnow(),
    }

    await db.reactions.insert_one(reaction_data)

    await add_points(user_id, group_id, 1)

    return {
        "liked": True,
        "post_id": post_id,
    }


@router.get("/{post_id}/likers")
async def likers(
    post_id: str,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    post = await db.posts.find_one({
        "_id": to_object_id(post_id, "post ID")
    })

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    group_id = post.get("group_id")

    membership = await is_group_member(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    reactions = await db.reactions.find({
        "post_id": post_id,
        "type": "like",
    }).to_list(length=500)

    result = []

    for reaction in reactions:
        reaction_user_id = str(reaction.get("user_id"))

        if not ObjectId.is_valid(reaction_user_id):
            continue

        liker = await db.users.find_one({
            "_id": ObjectId(reaction_user_id)
        })

        if liker:
            result.append({
                "user_id": str(liker["_id"]),
                "username": liker.get("username"),
                "avatar_url": liker.get("avatar_url"),
            })

    return result