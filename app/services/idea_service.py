from sqlalchemy.orm import Session
from app.models.idea import Idea
from app.services.group_utils import is_member
from app.services.points_service import add_points
from fastapi import HTTPException

def create_idea(db: Session, user_id: int, data):
    if not is_member(...):
        raise HTTPException(status_code=403, detail="Not a group member")

    idea = Idea(
        group_id=data.group_id,
        user_id=user_id,
        title=data.title,
        description=data.description
    )

    db.add(idea)
    db.commit()
    db.refresh(idea)

    add_points(db, user_id, data.group_id, 4)

    return idea


def get_group_ideas(db: Session, group_id: int, user_id: int):
    if not is_member(db, user_id, group_id):
        return None

    return db.query(Idea).filter(Idea.group_id == group_id).all()