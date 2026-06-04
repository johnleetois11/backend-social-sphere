from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class EventCreate(BaseModel):
    group_id: str
    title: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None
    event_date: datetime