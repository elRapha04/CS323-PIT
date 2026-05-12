"""
Real-Time Collaborative Task Board System
Backend: FastAPI + WebSockets + Redis Pub/Sub + SQLite
PDC Concepts: Concurrency, Async Event Handling, Distributed Messaging
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import (
    init_db,
    get_all_tasks,
    create_task,
    update_task,
    delete_task,
    move_task,
    get_task_by_id,
)
from connection_manager import ConnectionManager

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("taskboard")

# ─────────────────────────────────────────────
# Redis configuration
# ─────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_CHANNEL = "taskboard:events"

# ─────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────
manager = ConnectionManager()

redis_pub: Optional[redis.Redis] = None
redis_sub: Optional[redis.Redis] = None


# ─────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pub, redis_sub

    await init_db()
    logger.info("SQLite database initialized")

    try:
        redis_pub = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

        redis_sub = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

        await redis_pub.ping()
        logger.info(f"Connected to Redis at {REDIS_URL}")

        asyncio.create_task(redis_subscriber())
        logger.info("Redis subscriber started")

    except Exception as e:
        logger.warning(f"Redis unavailable ({e}). Running in fallback mode.")
        redis_pub = None
        redis_sub = None

    yield

    if redis_pub:
        await redis_pub.close()
    if redis_sub:
        await redis_sub.close()

    logger.info("Server shutdown complete")


# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────
app = FastAPI(
    title="Real-Time Collaborative Task Board",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/healthz")
async def health_check():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str
    description: str = ""
    column: str = "todo"
    color: str = "#4f8ef7"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class TaskMove(BaseModel):
    column: str


# ─────────────────────────────────────────────
# Redis Pub/Sub
# ─────────────────────────────────────────────
async def redis_subscriber():
    if redis_sub is None:
        return

    pubsub = redis_sub.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)

    logger.info(f"Subscribed to {REDIS_CHANNEL}")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL)


async def publish_event(event: dict):
    payload = json.dumps(event)

    if redis_pub:
        try:
            await redis_pub.publish(REDIS_CHANNEL, payload)
        except Exception as e:
            logger.warning(f"Redis publish failed: {e}")
            await manager.broadcast(payload)
    else:
        await manager.broadcast(payload)


# ─────────────────────────────────────────────
# REST API
# ─────────────────────────────────────────────
@app.get("/api/tasks")
async def list_tasks():
    return {"tasks": await get_all_tasks()}


@app.post("/api/tasks", status_code=201)
async def add_task(task: TaskCreate, username: str = "Anonymous"):
    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    new_task = {
        "id": task_id,
        "title": task.title,
        "description": task.description,
        "column": task.column,
        "color": task.color,
        "created_by": username,
        "created_at": now,
        "updated_at": now,
    }

    await create_task(new_task)

    await publish_event({
        "type": "TASK_CREATED",
        "task": new_task,
        "actor": username,
        "timestamp": now,
    })

    return new_task


@app.put("/api/tasks/{task_id}")
async def edit_task(task_id: str, update: TaskUpdate, username: str = "Anonymous"):
    existing = await get_task_by_id(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    changes = {k: v for k, v in update.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="No changes provided")

    changes["updated_at"] = datetime.utcnow().isoformat()

    updated = await update_task(task_id, changes)

    await publish_event({
        "type": "TASK_UPDATED",
        "task_id": task_id,
        "changes": changes,
        "task": updated,
        "actor": username,
    })

    return updated


@app.patch("/api/tasks/{task_id}/move")
async def move_task_endpoint(task_id: str, move: TaskMove, username: str = "Anonymous"):
    existing = await get_task_by_id(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = await move_task(
        task_id,
        move.column,
        datetime.utcnow().isoformat(),
    )

    await publish_event({
        "type": "TASK_MOVED",
        "task_id": task_id,
        "column": move.column,
        "task": updated,
        "actor": username,
    })

    return updated


@app.delete("/api/tasks/{task_id}")
async def remove_task(task_id: str, username: str = "Anonymous"):
    existing = await get_task_by_id(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    await delete_task(task_id)

    await publish_event({
        "type": "TASK_DELETED",
        "task_id": task_id,
        "actor": username,
    })

    return {"deleted": True}


@app.get("/api/stats")
async def get_stats():
    tasks = await get_all_tasks()

    cols = {"todo": 0, "doing": 0, "done": 0}
    for t in tasks:
        cols[t.get("column", "todo")] += 1

    return {
        "total_tasks": len(tasks),
        "columns": cols,
        "connected_clients": manager.count(),
        "online_users": manager.get_users(),
        "redis_connected": redis_pub is not None,
    }


# ─────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    client_id = str(uuid.uuid4())[:8]

    await manager.connect(websocket, client_id, username)

    await publish_event({
        "type": "USER_JOINED",
        "username": username,
        "client_id": client_id,
        "online_users": manager.get_users(),
    })

    try:
        while True:
            data = await websocket.receive_text()

            try:
                msg = json.loads(data)

                if msg.get("type") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG"}))

                elif msg.get("type") == "CURSOR":
                    await manager.broadcast_except(
                        json.dumps({
                            "type": "CURSOR",
                            "username": username,
                            "x": msg.get("x"),
                            "y": msg.get("y"),
                        }),
                        client_id,
                    )

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(client_id)

        await publish_event({
            "type": "USER_LEFT",
            "username": username,
            "client_id": client_id,
            "online_users": manager.get_users(),
        })


# ─────────────────────────────────────────────
# Frontend serving
# ─────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    async def root():
        return {"status": "running", "docs": "/docs"}


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)