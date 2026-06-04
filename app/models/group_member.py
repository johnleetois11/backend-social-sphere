from sqlalchemy import Column, Integer, ForeignKey, String, DateTime
from datetime import datetime
from app.database.database import Base

class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))
    role = Column(String, default="member")  # owner/admin/mod/member
    joined_at = Column(DateTime, default=datetime.utcnow)