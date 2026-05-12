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

# Maximum activity history entries to persist
MAX_HISTORY = 200


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
        # Activity history table — persists events so new joiners see past activity
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                description TEXT NOT NULL,
                icon TEXT NOT NULL,
                color TEXT NOT NULL,
                timestamp TEXT NOT NULL
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


# ─────────────────────────────────────────────
# Activity History
# ─────────────────────────────────────────────

async def append_activity(event_type: str, actor: str, description: str, icon: str, color: str, timestamp: str):
    """Persist one activity entry; prune oldest beyond MAX_HISTORY."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO activity_log (event_type, actor, description, icon, color, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_type, actor, description, icon, color, timestamp),
        )
        # Keep only the latest MAX_HISTORY rows
        await db.execute(
            """DELETE FROM activity_log WHERE id NOT IN (
                SELECT id FROM activity_log ORDER BY id DESC LIMIT ?
            )""",
            (MAX_HISTORY,),
        )
        await db.commit()


async def get_activity_history(limit: int = 50) -> List[Dict]:
    """Fetch recent activity history, oldest first (so client prepends correctly)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT event_type, actor, description, icon, color, timestamp
               FROM activity_log
               ORDER BY id DESC
               LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            # Reverse so oldest is first — client inserts in order
            return [dict(zip(cols, row)) for row in reversed(rows)]
