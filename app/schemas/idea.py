from pydantic import BaseModel, Field
from typing import Optional


class IdeaCreate(BaseModel):
    group_id: str
    title: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None