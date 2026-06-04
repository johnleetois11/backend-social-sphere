from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    group_id: str
    name: str = Field(min_length=1, max_length=100)
    type: str = "text"  # text / announcement