from app.services.points_service import add_points
from app.models.post import Post
from app.models.comment import Comment
from app.models.user import User
from fastapi import HTTPException

def create_comment(db, user_id, data):
    post = db.query(Post).filter(Post.id == data.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = Comment(
        post_id=data.post_id,
        user_id=user_id,
        content=data.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    add_points(db, user_id, post.group_id, 2)

    author = db.query(User).filter(User.id == user_id).first()
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "user_id": comment.user_id,
        "username": author.username if author else "Unknown",
        "avatar_url": author.avatar_url if author else None,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


def delete_comment(db, user_id, comment_id):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your comment")
    db.delete(comment)
    db.commit()
