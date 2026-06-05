from pydantic import BaseModel, Field
from typing import Optional


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    purpose: Optional[str] = None
    type: str = "public"  # public/private/invite
    category: str = Field(default="friends")  # friends/family/school


class GroupJoin(BaseModel):
    group_id: str


class GroupJoinByCode(BaseModel):
    code: str
