from pydantic import BaseModel

class VoteCreate(BaseModel):
    idea_id: int
    value: int  # 1 or -1