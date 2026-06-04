import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import MONGODB_URI, MONGODB_DB_NAME

mongo_client = None
mongo_db = None


async def connect_to_mongo():
    global mongo_client, mongo_db

    if not MONGODB_URI:
        raise Exception("MONGODB_URI is missing in .env")

    mongo_client = AsyncIOMotorClient(
        MONGODB_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=10000,
    )

    mongo_db = mongo_client[MONGODB_DB_NAME]

    await mongo_client.admin.command("ping")

    print(f"MongoDB Atlas connected successfully: {MONGODB_DB_NAME}")


async def close_mongo_connection():
    global mongo_client

    if mongo_client:
        mongo_client.close()
        print("MongoDB connection closed")


def get_mongo_db():
    if mongo_db is None:
        raise Exception("MongoDB is not connected")

    return mongo_db