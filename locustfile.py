"""
Locust Stress Test for Real-Time Collaborative Task Board
Run: locust -f locustfile.py --host=http://localhost:8000

PDC Testing: Simulates concurrent users to test:
- Parallel WebSocket connections
- Concurrent API requests
- System behavior under load
- Redis Pub/Sub throughput
"""

import json
import random
import string
import time
import uuid
from locust import HttpUser, TaskSet, task, between, events
import websocket
import threading


COLORS = ["#5b7fff", "#f5a623", "#2dd87a", "#ff4d6a", "#c47aff"]
COLUMNS = ["todo", "doing", "done"]

SAMPLE_TASKS = [
    "Implement user authentication",
    "Fix navigation bug",
    "Write unit tests",
    "Deploy to staging",
    "Code review PR #42",
    "Update documentation",
    "Optimize database queries",
    "Design new landing page",
    "Set up CI/CD pipeline",
    "Refactor API layer",
]


def random_username():
    return "User_" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))


class TaskBoardUser(HttpUser):
    """
    Simulates a real user:
    1. Fetches the board state
    2. Creates tasks
    3. Moves tasks between columns
    4. Edits tasks
    5. Deletes tasks
    Maintains a WebSocket connection throughout.
    """

    wait_time = between(1, 4)  # Think time between actions

    def on_start(self):
        """Called when a user starts. Opens WebSocket connection."""
        self.username = random_username()
        self.created_task_ids = []
        self.ws_connected = False

        # Open WebSocket in a background thread
        ws_url = self.host.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += f"/ws/{self.username}"

        try:
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_ws_open,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close,
            )
            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()
            time.sleep(0.5)  # Wait for connection
        except Exception as e:
            print(f"WS connection failed for {self.username}: {e}")

    def _on_ws_open(self, ws):
        self.ws_connected = True

    def _on_ws_message(self, ws, message):
        try:
            event = json.loads(message)
            # Count WebSocket messages as successful requests
            events.request.fire(
                request_type="WebSocket",
                name=f"Event:{event.get('type', 'unknown')}",
                response_time=0,
                response_length=len(message),
                exception=None,
                context={},
            )
        except Exception:
            pass

    def _on_ws_error(self, ws, error):
        self.ws_connected = False

    def _on_ws_close(self, ws, close_status_code, close_msg):
        self.ws_connected = False

    def on_stop(self):
        """Close WebSocket when user leaves."""
        if hasattr(self, 'ws'):
            try:
                self.ws.close()
            except Exception:
                pass

    @task(3)
    def view_board(self):
        """Fetch all tasks (most common action)."""
        with self.client.get("/api/tasks", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(2)
    def create_task(self):
        """Create a new task."""
        title = random.choice(SAMPLE_TASKS) + f" #{random.randint(1, 99)}"
        payload = {
            "title": title,
            "description": f"Created by {self.username} during load test",
            "column": random.choice(COLUMNS),
            "color": random.choice(COLORS),
        }
        with self.client.post(
            f"/api/tasks?username={self.username}",
            json=payload,
            catch_response=True
        ) as response:
            if response.status_code == 201:
                data = response.json()
                self.created_task_ids.append(data["id"])
                response.success()
            else:
                response.failure(f"Got {response.status_code}: {response.text[:100]}")

    @task(2)
    def move_task(self):
        """Move a task to a random column."""
        if not self.created_task_ids:
            return
        task_id = random.choice(self.created_task_ids)
        target_col = random.choice(COLUMNS)

        with self.client.patch(
            f"/api/tasks/{task_id}/move?username={self.username}",
            json={"column": target_col},
            catch_response=True,
            name="/api/tasks/[id]/move",
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(1)
    def edit_task(self):
        """Edit a task's title."""
        if not self.created_task_ids:
            return
        task_id = random.choice(self.created_task_ids)
        new_title = random.choice(SAMPLE_TASKS) + f" [edited #{random.randint(1, 99)}]"

        with self.client.put(
            f"/api/tasks/{task_id}?username={self.username}",
            json={"title": new_title},
            catch_response=True,
            name="/api/tasks/[id]",
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(1)
    def delete_task(self):
        """Delete a task created by this user."""
        if len(self.created_task_ids) < 2:
            return
        task_id = self.created_task_ids.pop(0)

        with self.client.delete(
            f"/api/tasks/{task_id}?username={self.username}",
            catch_response=True,
            name="/api/tasks/[id] DELETE",
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(1)
    def check_stats(self):
        """Check system stats."""
        with self.client.get("/api/stats", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got {response.status_code}")

    @task(1)
    def send_ws_ping(self):
        """Send WebSocket ping."""
        if self.ws_connected and hasattr(self, 'ws'):
            try:
                self.ws.send(json.dumps({"type": "PING"}))
            except Exception:
                pass
