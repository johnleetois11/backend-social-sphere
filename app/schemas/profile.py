from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    hobbies: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class OwnProfileResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    hobbies: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberProfileResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    role: str
    points: int
    rank: int
    joined_group_at: datetime
    badges: List[str]


class GroupStatsResponse(BaseModel):
    group_id: int
    group_name: str
    role: str
    points: int
    rank: int
    badges: List[str]
    joined_at: datetime


class LoginActivityResponse(BaseModel):
    id: int
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
