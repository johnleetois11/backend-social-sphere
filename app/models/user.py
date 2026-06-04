from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    full_name = Column(String)
    birthdate = Column(String)
    gender = Column(String)
    mobile = Column(String)
    address = Column(String)
    facebook_link = Column(String)
    hobbies = Column(String)
    bio = Column(String)