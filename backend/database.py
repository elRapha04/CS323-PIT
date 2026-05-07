"""
Database Layer — SQLite with aiosqlite for async non-blocking I/O
PDC Concept: Async I/O ensures the event loop is never blocked by DB queries
"""

import json
import logging
import os
from typing import Dict, List, Optional

import aiosqlite

logger = logging.getLogger("taskboard.db")

DB_PATH = os.getenv("DB_PATH", "./taskboard.db")


async def init_db():
    """Initialize SQLite schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                column TEXT NOT NULL DEFAULT 'todo',
                color TEXT DEFAULT '#4f8ef7',
                created_by TEXT DEFAULT 'Anonymous',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info(f"Database initialized at {DB_PATH}")


def _row_to_dict(row, cursor) -> Dict:
    """Convert aiosqlite row to dict using column names."""
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


async def get_all_tasks() -> List[Dict]:
    """Fetch all tasks ordered by creation time."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM tasks ORDER BY created_at ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_dict(row, cursor) for row in rows]


async def get_task_by_id(task_id: str) -> Optional[Dict]:
    """Fetch a single task by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_dict(row, cursor)
    return None


async def create_task(task: Dict) -> Dict:
    """Insert a new task."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO tasks (id, title, description, column, color, created_by, created_at, updated_at)
               VALUES (:id, :title, :description, :column, :color, :created_by, :created_at, :updated_at)""",
            task,
        )
        await db.commit()
    logger.debug(f"Task created: {task['id']}")
    return task


async def update_task(task_id: str, changes: Dict) -> Optional[Dict]:
    """Update specific fields of a task."""
    # Build dynamic SET clause
    set_parts = ", ".join(f"{k} = ?" for k in changes.keys())
    values = list(changes.values()) + [task_id]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE tasks SET {set_parts} WHERE id = ?",
            values,
        )
        await db.commit()

    return await get_task_by_id(task_id)


async def move_task(task_id: str, column: str, updated_at: str) -> Optional[Dict]:
    """Move task to a different column."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET `column` = ?, updated_at = ? WHERE id = ?",
            (column, updated_at, task_id),
        )
        await db.commit()
    return await get_task_by_id(task_id)


async def delete_task(task_id: str) -> bool:
    """Delete a task by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return cursor.rowcount > 0
