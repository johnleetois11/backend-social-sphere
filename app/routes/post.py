from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId

from app.schemas.post import PostCreate, PostUpdate
from app.database.mongodb import get_mongo_db
from app.core.mongo_dependencies import get_current_mongo_user
from app.core.limiter import limiter

router = APIRouter(prefix="/posts", tags=["Posts"])


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

    membership = await db.group_members.find_one({
        "user_id": user_id,
        "group_id": group_id,
    })

    return membership


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


async def enrich_post(post: dict, current_user_id: str):
    db = get_mongo_db()

    author = None

    if ObjectId.is_valid(str(post.get("user_id"))):
        author = await db.users.find_one({
            "_id": ObjectId(str(post.get("user_id")))
        })

    reactions = await db.reactions.find({
        "post_id": str(post["_id"]),
        "type": "like",
    }).to_list(length=500)

    comment_count = await db.comments.count_documents({
        "post_id": str(post["_id"])
    })

    likers = []
    is_liked = False

    for reaction in reactions:
        reaction_user_id = str(reaction.get("user_id"))

        if reaction_user_id == current_user_id:
            is_liked = True

        liker = None

        if ObjectId.is_valid(reaction_user_id):
            liker = await db.users.find_one({
                "_id": ObjectId(reaction_user_id)
            })

        if liker:
            likers.append({
                "user_id": str(liker["_id"]),
                "username": liker.get("username"),
                "avatar_url": liker.get("avatar_url"),
            })

    return {
        "id": str(post["_id"]),
        "group_id": post.get("group_id"),
        "user_id": post.get("user_id"),
        "username": author.get("username") if author else "Unknown",
        "avatar_url": author.get("avatar_url") if author else None,
        "content": post.get("content"),
        "media_url": post.get("media_url"),
        "is_pinned": post.get("is_pinned", False),
        "created_at": serialize_datetime(post.get("created_at")),
        "like_count": len(reactions),
        "is_liked_by_me": is_liked,
        "likers": likers,
        "comment_count": comment_count,
    }


@router.post("/")
@limiter.limit("10/minute")
async def create(
    request: Request,
    data: PostCreate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({
        "_id": to_object_id(data.group_id, "group ID")
    })

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = await is_group_member(user_id, data.group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Not a group member")

    post_data = {
        "group_id": data.group_id,
        "user_id": user_id,
        "content": data.content,
        "media_url": data.media_url,
        "is_pinned": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.posts.insert_one(post_data)

    await add_points(user_id, data.group_id, 5)

    created_post = await db.posts.find_one({
        "_id": result.inserted_id
    })

    return await enrich_post(created_post, user_id)


@router.get("/group/{group_id}")
async def get_posts(
    group_id: str,
    skip: int = 0,
    limit: int = 20,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    group = await db.groups.find_one({
        "_id": to_object_id(group_id, "group ID")
    })

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = await is_group_member(user_id, group_id)

    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    posts = await db.posts.find({
        "group_id": group_id
    }).sort([
        ("is_pinned", -1),
        ("created_at", -1),
    ]).skip(skip).limit(limit).to_list(length=limit)

    return [await enrich_post(post, user_id) for post in posts]


@router.patch("/{post_id}")
async def edit_post(
    post_id: str,
    data: PostUpdate,
    user=Depends(get_current_mongo_user),
):
    db = get_mongo_db()
    user_id = str(user["_id"])

    post = await db.posts.find_one({
        "_id": to_object_id(post_id, "post ID")
    })

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not your post")

    await db.posts.update_one(
        {"_id": to_object_id(post_id, "post ID")},
        {
            "$set": {
                "content": data.content,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    updated_post = await db.posts.find_one({
        "_id": to_object_id(post_id, "post ID")
    })

    return await enrich_post(updated_post, user_id)


@router.delete("/{post_id}")
async def delete_post(
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
    is_admin = membership and membership.get("role") in ("owner", "admin")

    if post.get("user_id") != user_id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.comments.delete_many({
        "post_id": post_id
    })

    await db.reactions.delete_many({
        "post_id": post_id
    })

    await db.posts.delete_one({
        "_id": to_object_id(post_id, "post ID")
    })

    return {"message": "Post deleted"}


@router.patch("/{post_id}/pin")
async def pin_post(
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

    if not membership or membership.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can pin posts")

    new_pin_status = not post.get("is_pinned", False)

    await db.posts.update_one(
        {"_id": to_object_id(post_id, "post ID")},
        {
            "$set": {
                "is_pinned": new_pin_status,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return {"is_pinned": new_pin_status}