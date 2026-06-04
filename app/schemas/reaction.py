from pydantic import BaseModel


class ReactionCreate(BaseModel):
    post_id: str
    type: str = "like"