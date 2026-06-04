from sqlalchemy import Column, Integer, ForeignKey
from app.database.database import Base

class UserPoints(Base):
    __tablename__ = "user_points"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))
    points = Column(Integer, default=0)