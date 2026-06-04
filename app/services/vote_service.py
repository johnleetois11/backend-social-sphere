from sqlalchemy.orm import Session
from app.models.vote import Vote
from app.services.points_service import add_points
from app.models.idea import Idea


def vote_idea(db: Session, user_id: int, data):
    existing = db.query(Vote).filter_by(
        idea_id=data.idea_id,
        user_id=user_id
    ).first()

    if existing:
        existing.value = data.value
        db.commit()
        return existing

    vote = Vote(
        idea_id=data.idea_id,
        user_id=user_id,
        value=data.value
    )

    db.add(vote)
    db.commit()

    idea = db.query(Idea).filter(Idea.id == data.idea_id).first()

    add_points(db, user_id, idea.group_id, 1)
    return vote