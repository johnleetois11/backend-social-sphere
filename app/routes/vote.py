from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.schemas.vote import VoteCreate
from app.services.vote_service import vote_idea
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/votes", tags=["Votes"])

@router.post("/")
def vote(data: VoteCreate, db: Session = Depends(get_db), user = Depends(get_current_user)):
    return vote_idea(db, user.id, data)