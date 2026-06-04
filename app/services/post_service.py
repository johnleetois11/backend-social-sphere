from sqlalchemy.orm import Session
from app.models.post import Post
from app.services.group_utils import is_member
from app.services.points_service import add_points
from fastapi import HTTPException

def create_post(db: Session, user_id: int, data):
    if not is_member(db, user_id, data.group_id):
        raise HTTPException(status_code=403, detail="Not a group member")
         

    post = Post(
        group_id=data.group_id,
        user_id=user_id,
        content=data.content,
        media_url=getattr(data, "media_url", None),
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    add_points(db, user_id, data.group_id, 5)

    return post


def get_group_posts(db: Session, group_id: int, user_id: int):
    if not is_member(db, user_id, group_id):
        return None

    return db.query(Post).filter(Post.group_id == group_id).all()