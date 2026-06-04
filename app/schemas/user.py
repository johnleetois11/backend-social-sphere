from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    full_name: Optional[str] = None
    birthdate: Optional[str] = None
    gender: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    facebook_link: Optional[str] = None
    hobbies: Optional[str] = None
    bio: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)