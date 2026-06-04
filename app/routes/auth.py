from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext

from app.schemas.user import UserCreate, LoginSchema
from app.database.mongodb import get_mongo_db
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.mongo_dependencies import get_current_mongo_user

router = APIRouter(prefix="/auth", tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print("PASSWORD VERIFY ERROR:", repr(e))
        return False


def create_access_token(data: dict) -> str:
    try:
        expire_minutes = int(ACCESS_TOKEN_EXPIRE_MINUTES)
    except Exception:
        expire_minutes = 60

    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "birthdate": user.get("birthdate"),
        "gender": user.get("gender"),
        "mobile": user.get("mobile"),
        "address": user.get("address"),
        "facebook_link": user.get("facebook_link"),
        "hobbies": user.get("hobbies"),
        "bio": user.get("bio"),
        "avatar_url": user.get("avatar_url"),
        "created_at": serialize_datetime(user.get("created_at")),
    }


async def authenticate_user(email: str, password: str):
    db = get_mongo_db()

    email = email.lower().strip()

    user = await db.users.find_one({"email": email})

    if not user:
        return None

    stored_hash = user.get("password_hash") or user.get("hashed_password")

    if not stored_hash:
        print("LOGIN ERROR: User has no password_hash or hashed_password")
        return None

    if not verify_password(password, stored_hash):
        return None

    return user


@router.post("/register")
async def register(user: UserCreate):
    db = get_mongo_db()

    email = user.email.lower().strip()
    username = user.username.strip()

    existing_user = await db.users.find_one({
        "$or": [
            {"email": email},
            {"username": username},
        ]
    })

    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password is too long. Please use 72 bytes or fewer.",
        )

    password_hash = hash_password(user.password)

    user_data = {
        "username": username,
        "email": email,

        # Save both for compatibility
        "password_hash": password_hash,
        "hashed_password": password_hash,

        "avatar_url": None,
        "created_at": datetime.utcnow(),

        "full_name": user.full_name,
        "birthdate": user.birthdate,
        "gender": user.gender,
        "mobile": user.mobile,
        "address": user.address,
        "facebook_link": user.facebook_link,
        "hobbies": user.hobbies,
        "bio": user.bio,
    }

    result = await db.users.insert_one(user_data)

    created_user = await db.users.find_one({"_id": result.inserted_id})

    return {
        "message": "User created successfully",
        "user": serialize_user(created_user),
    }


@router.post("/login")
async def login(request: Request, user: LoginSchema):
    try:
        db_user = await authenticate_user(user.email, user.password)

        if not db_user:
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
            )

        access_token = create_access_token({
            "sub": str(db_user["_id"]),
            "email": db_user["email"],
        })

        # Do not let login activity logging break login
        try:
            db = get_mongo_db()
            ip_address = request.client.host if request.client else None

            await db.login_activity.insert_one({
                "user_id": str(db_user["_id"]),
                "email": db_user["email"],
                "ip_address": ip_address,
                "created_at": datetime.utcnow(),
            })

        except Exception as activity_error:
            print("LOGIN ACTIVITY ERROR:", repr(activity_error))

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    except HTTPException:
        raise

    except Exception as e:
        print("LOGIN CRASH ERROR:", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Login crashed: {type(e).__name__}: {str(e)}",
        )


@router.post("/token")
async def login_for_swagger(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    db_user = await authenticate_user(form_data.username, form_data.password)

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token({
        "sub": str(db_user["_id"]),
        "email": db_user["email"],
    })

    try:
        db = get_mongo_db()
        ip_address = request.client.host if request.client else None

        await db.login_activity.insert_one({
            "user_id": str(db_user["_id"]),
            "email": db_user["email"],
            "ip_address": ip_address,
            "created_at": datetime.utcnow(),
        })

    except Exception as activity_error:
        print("LOGIN ACTIVITY ERROR:", repr(activity_error))

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(current_user=Depends(get_current_mongo_user)):
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user=Depends(get_current_mongo_user)):
    return serialize_user(current_user)