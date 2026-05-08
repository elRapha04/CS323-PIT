"""
Connection Manager — PDC Concept: Concurrent WebSocket State Management
Manages all active WebSocket connections with thread-safe operations using asyncio locks.
"""

import asyncio
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("taskboard.connections")


class ConnectionManager:
    """
    Manages concurrent WebSocket connections.

    PDC Concepts:
    - Concurrency: Multiple clients connected simultaneously
    - Synchronization: asyncio.Lock prevents race conditions when
      modifying the shared connections dict
    - Broadcast: Fan-out pattern — one event → all N clients
    """

    def __init__(self):
        # Maps client_id -> (WebSocket, username)
        self._connections: Dict[str, tuple] = {}
        # Lock prevents concurrent modification of _connections
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str, username: str):
        """Accept connection and register it."""
        await websocket.accept()
        async with self._lock:
            self._connections[client_id] = (websocket, username)
        logger.info(f"Registered client {client_id} ({username}). Active: {len(self._connections)}")

    def disconnect(self, client_id: str):
        """Remove a disconnected client (sync, called from exception handler)."""
        self._connections.pop(client_id, None)
        logger.info(f"Removed client {client_id}. Active: {len(self._connections)}")

    async def broadcast(self, message: str):
        """
        Send message to ALL connected clients concurrently.

        PDC: Uses asyncio.gather() to send to all clients in parallel —
        a key concurrency pattern. Dead connections are removed.
        """
        if not self._connections:
            return

        async with self._lock:
            clients = list(self._connections.items())

        dead_clients = []
        tasks = []

        for client_id, (ws, username) in clients:
            tasks.append(self._safe_send(client_id, ws, message, dead_clients))

        # Send to all clients concurrently (parallel I/O)
        await asyncio.gather(*tasks, return_exceptions=True)

        # Clean up dead connections
        if dead_clients:
            async with self._lock:
                for cid in dead_clients:
                    self._connections.pop(cid, None)
            logger.info(f"Cleaned up {len(dead_clients)} dead connections")

    async def broadcast_except(self, message: str, exclude_client_id: str):
        """Broadcast to all clients except one (e.g., cursor updates)."""
        async with self._lock:
            clients = [(cid, ws, uname) for cid, (ws, uname) in self._connections.items()
                       if cid != exclude_client_id]

        dead_clients = []
        tasks = [self._safe_send(cid, ws, message, dead_clients) for cid, ws, _ in clients]
        await asyncio.gather(*tasks, return_exceptions=True)

        if dead_clients:
            async with self._lock:
                for cid in dead_clients:
                    self._connections.pop(cid, None)

    async def _safe_send(self, client_id: str, ws: WebSocket, message: str, dead: list):
        """Send with error handling; mark dead connections."""
        try:
            await ws.send_text(message)
        except Exception as e:
            logger.debug(f"Failed to send to {client_id}: {e}")
            dead.append(client_id)

    def count(self) -> int:
        """Current number of connected clients."""
        return len(self._connections)

    def get_users(self) -> List[str]:
        """List of currently connected usernames."""
        return list({uname for _, (_, uname) in self._connections.items()})
