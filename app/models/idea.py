from sqlalchemy import Column, Integer, String, ForeignKey
from app.database.database import Base

class Idea(Base):
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    description = Column(String)
    status = Column(String, default="pending")  # pending/approved/implemented