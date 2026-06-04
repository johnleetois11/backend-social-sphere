from pydantic import BaseModel
from typing import Optional


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    purpose: Optional[str] = None
    type: str = "public"  # public/private/invite


class GroupJoin(BaseModel):
    group_id: str


class GroupJoinByCode(BaseModel):
    code: str