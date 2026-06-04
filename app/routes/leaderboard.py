from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user_points import UserPoints
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])

@router.get("/{group_id}")
def get_leaderboard(group_id: int, db: Session = Depends(get_db), user = Depends(get_current_user)):
    leaderboard = db.query(UserPoints)\
        .filter(UserPoints.group_id == group_id)\
        .order_by(UserPoints.points.desc())\
        .all()

    return leaderboard