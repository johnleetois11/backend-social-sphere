from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime
from app.database.database import Base

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    title = Column(String)
    description = Column(String)
    event_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)