from sqlalchemy.orm import Session
from app.models.event import Event
from app.services.group_utils import is_member
from fastapi import HTTPException

def create_event(db: Session, user_id: int, data):
    if not is_member(...):
        raise HTTPException(status_code=403, detail="Not a group member")

    event = Event(
        group_id=data.group_id,
        title=data.title,
        description=data.description,
        event_date=data.event_date
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return event


def get_events(db: Session, group_id: int, user_id: int):
    if not is_member(db, user_id, group_id):
        return None

    return db.query(Event).filter(Event.group_id == group_id).all()