from app.services.points_service import add_points
from app.models.post import Post
from app.models.reaction import Reaction
from app.models.user import User
from fastapi import HTTPException

def toggle_reaction(db, user_id, post_id, reaction_type="like"):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = db.query(Reaction).filter_by(
        user_id=user_id, post_id=post_id, type=reaction_type
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return {"liked": False}
    else:
        reaction = Reaction(user_id=user_id, post_id=post_id, type=reaction_type)
        db.add(reaction)
        db.commit()
        add_points(db, user_id, post.group_id, 1)
        return {"liked": True}


def get_likers(db, post_id):
    reactions = db.query(Reaction).filter_by(post_id=post_id, type="like").all()
    result = []
    for r in reactions:
        u = db.query(User).filter(User.id == r.user_id).first()
        if u:
            result.append({"user_id": u.id, "username": u.username, "avatar_url": u.avatar_url})
    return result
