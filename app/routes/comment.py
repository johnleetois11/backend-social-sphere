from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from app.schemas.comment import CommentCreate
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/comments", tags=["Comments"])


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


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


async def enrich_comment(comment: dict):
    db = get_mongo_db()

    author = None
    user_id = str(comment.get("user_id"))

    if ObjectId.is_valid(user_id):
        author = await db.users.find_one({
            "_id": ObjectId(user_id)
        })

    return {
        "id": str(comment["_id"]),
        "post_id": comment.get("post_id"),
        "user_id": comment.get("user_id"),
        "username": author.get("username") if author else "Unknown",
        "avatar_url": author.get("avatar_url") if author else None,
        "content": comment.get("content"),
        "created_at": serialize_datetime(comment.get("created_at")),
    }


@router.post("/")
async def add_comment(
    data: CommentCreate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    post = await db.posts.find_one({
        "_id": to_object_id(data.post_id, "post ID")
    })

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    group_id = post.get("group_id")

    membership = await is_group_member(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    comment_data = {
        "post_id": data.post_id,
        "group_id": group_id,
        "user_id": user_id,
        "content": data.content,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.comments.insert_one(comment_data)

    await add_points(user_id, group_id, 2)

    created_comment = await db.comments.find_one({
        "_id": result.inserted_id
    })

    return await enrich_comment(created_comment)


@router.get("/{post_id}")
async def get_comments(
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

    comments = await db.comments.find({
        "post_id": post_id
    }).sort("created_at", 1).to_list(length=500)

    return [await enrich_comment(comment) for comment in comments]


@router.delete("/{comment_id}")
async def remove_comment(
    comment_id: str,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    comment = await db.comments.find_one({
        "_id": to_object_id(comment_id, "comment ID")
    })

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your comment")

    await db.comments.delete_one({
        "_id": to_object_id(comment_id, "comment ID")
    })

    return {"message": "Comment deleted"}