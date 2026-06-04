from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    channel_id: str
    content: str = Field(min_length=1, max_length=1000)