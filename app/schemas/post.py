from pydantic import BaseModel, Field
from typing import Optional


class PostCreate(BaseModel):
    group_id: str
    content: str = Field(min_length=1, max_length=1000)
    media_url: Optional[str] = None


class PostUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)