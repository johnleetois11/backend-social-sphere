from sqlalchemy import Column, Integer, ForeignKey
from app.database.database import Base

class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True)
    idea_id = Column(Integer, ForeignKey("ideas.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    value = Column(Integer)  # +1 or -1