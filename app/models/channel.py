from sqlalchemy import Column, Integer, String, ForeignKey
from app.database.database import Base

class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    name = Column(String)
    type = Column(String)  # text / announcement