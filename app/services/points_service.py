from sqlalchemy.orm import Session
from app.models.user_points import UserPoints

def add_points(db: Session, user_id: int, group_id: int, value: int):
    record = db.query(UserPoints).filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()

    if not record:
        record = UserPoints(
            user_id=user_id,
            group_id=group_id,
            points=0
        )
        db.add(record)

    record.points += value
    db.commit()

    return record