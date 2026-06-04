from sqlalchemy import Column, Integer, String, ForeignKey
from app.database.database import Base

class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    type = Column(String)  # like, heart, etc