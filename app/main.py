from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.limiter import limiter
from app.database.mongodb import connect_to_mongo, close_mongo_connection

from app.routes import (
    auth,
    group,
    post,
    comment,
    reaction,
    channel,
    ws_chat,
    ws_dm,
    ws_call,
    idea,
    task,
    event,
    profile,
    dm,
    group_info,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(title="Social Sphere API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:58642",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:58642",
        "https://backend-social-sphere.onrender.com",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ──────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(group.router)
app.include_router(group_info.router)
app.include_router(post.router)
app.include_router(comment.router)
app.include_router(reaction.router)
app.include_router(channel.router)
app.include_router(ws_chat.router)
app.include_router(ws_dm.router)
app.include_router(ws_call.router)
app.include_router(dm.router)
app.include_router(idea.router)
app.include_router(event.router)
app.include_router(task.router)
app.include_router(profile.router)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.get("/")
def root():
    return {"message": "Social Sphere Backend Running with MongoDB Atlas "}


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests"})