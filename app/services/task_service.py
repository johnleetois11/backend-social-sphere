from sqlalchemy.orm import Session
from app.models.task import Task
from app.services.group_utils import is_member
from fastapi import HTTPException

def create_task(db: Session, user_id: int, data):
    if not is_member(...):
        raise HTTPException(status_code=403, detail="Not a group member")

    task = Task(
        group_id=data.group_id,
        assigned_to=data.assigned_to,
        title=data.title,
        description=data.description,
        deadline=data.deadline
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return task


def get_tasks(db: Session, group_id: int, user_id: int):
    if not is_member(db, user_id, group_id):
        return None

    return db.query(Task).filter(Task.group_id == group_id).all()