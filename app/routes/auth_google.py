from datetime import datetime, timedelta
import json
import os
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, initialize_app, _apps
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database.mongodb import get_mongo_db

router = APIRouter(prefix="/auth", tags=["Google Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def init_firebase_admin():
    if _apps:
        return

    service_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    service_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if service_json:
        data = json.loads(service_json)
        cred = credentials.Certificate(data)
        initialize_app(cred)
        return

    if service_path:
        cred = credentials.Certificate(service_path)
        initialize_app(cred)
        return

    # Works only if the environment has Google Application Default Credentials.
    initialize_app()


init_firebase_admin()


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=10)


class GoogleCompleteRegistrationRequest(BaseModel):
    id_token: str = Field(min_length=10)
    username: str = Field(min_length=1, max_length=50)
    full_name: Optional[str] = None
    birthdate: Optional[str] = None
    gender: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    facebook_link: Optional[str] = None
    hobbies: Optional[str] = None
    bio: Optional[str] = None


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "exp": expire,
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def serialize_user(user: dict):
    return {
        "id": str(user["_id"]),
        "_id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "avatar_url": user.get("avatar_url"),
        "auth_provider": user.get("auth_provider", "password"),
        "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
    }


def make_username_from_email(email: str) -> str:
    base = email.split("@")[0]
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch == "_")
    return cleaned or "google_user"


async def unique_username(base_username: str) -> str:
    db = get_mongo_db()
    candidate = base_username
    count = 1

    while await db.users.find_one({"username": candidate}):
        count += 1
        candidate = f"{base_username}{count}"

    return candidate


async def verify_google_token(id_token: str) -> dict:
    try:
        decoded = firebase_auth.verify_id_token(id_token)

        email = decoded.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email")

        return decoded
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase ID token: {e}")


@router.post("/google-login")
async def google_login(data: GoogleLoginRequest):
    db = get_mongo_db()

    decoded = await verify_google_token(data.id_token)

    email = decoded.get("email")
    firebase_uid = decoded.get("uid")
    full_name = decoded.get("name") or ""
    picture = decoded.get("picture")

    existing = await db.users.find_one({"email": email})

    if existing:
        # Link existing Mongo user to Firebase UID when missing.
        update_data = {
            "firebase_uid": firebase_uid,
            "auth_provider": existing.get("auth_provider", "google"),
            "updated_at": datetime.utcnow(),
        }

        if picture and not existing.get("avatar_url"):
            update_data["avatar_url"] = picture

        await db.users.update_one(
            {"_id": existing["_id"]},
            {"$set": update_data},
        )

        token = create_access_token(str(existing["_id"]))

        return {
            "access_token": token,
            "token_type": "bearer",
            "needs_registration": False,
            "user": serialize_user(existing),
        }

    suggested_username = await unique_username(make_username_from_email(email))

    return {
        "needs_registration": True,
        "google": {
            "email": email,
            "firebase_uid": firebase_uid,
            "full_name": full_name,
            "avatar_url": picture,
            "username": suggested_username,
        },
    }


@router.post("/google-register-complete")
async def google_register_complete(data: GoogleCompleteRegistrationRequest):
    db = get_mongo_db()

    decoded = await verify_google_token(data.id_token)

    email = decoded.get("email")
    firebase_uid = decoded.get("uid")
    google_name = decoded.get("name") or ""
    picture = decoded.get("picture")

    existing = await db.users.find_one({"email": email})

    if existing:
        token = create_access_token(str(existing["_id"]))
        return {
            "access_token": token,
            "token_type": "bearer",
            "needs_registration": False,
            "user": serialize_user(existing),
        }

    username = data.username.strip()
    if await db.users.find_one({"username": username}):
        username = await unique_username(username)

    # No password is needed for Google users. We still store a locked random hash
    # so old code that expects password_hash will not break.
    locked_password_hash = pwd_context.hash(f"GOOGLE_ONLY_{firebase_uid}_{ObjectId()}")

    user_data = {
        "username": username,
        "email": email,
        "password_hash": locked_password_hash,
        "full_name": data.full_name or google_name,
        "birthdate": data.birthdate,
        "gender": data.gender,
        "mobile": data.mobile,
        "address": data.address,
        "facebook_link": data.facebook_link,
        "hobbies": data.hobbies,
        "bio": data.bio,
        "avatar_url": picture,
        "firebase_uid": firebase_uid,
        "auth_provider": "google",
        "email_verified": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.users.insert_one(user_data)

    created = await db.users.find_one({"_id": result.inserted_id})

    token = create_access_token(str(result.inserted_id))

    return {
        "access_token": token,
        "token_type": "bearer",
        "needs_registration": False,
        "user": serialize_user(created),
    }
