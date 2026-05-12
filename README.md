# TaskFlow — Real-Time Collaborative Task Board
### PDC Project: Parallel & Distributed Computing

A fully-featured real-time collaborative Kanban board demonstrating **Parallel & Distributed Computing** concepts including concurrency, async event handling, distributed messaging via Redis Pub/Sub, and real-time WebSocket communication.

---

## 📁 Project Structure

```
taskboard/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket endpoints
│   ├── connection_manager.py # Concurrent WebSocket state management
│   ├── database.py          # Async SQLite operations (aiosqlite)
│   └── requirements.txt     # Python dependencies
├── frontend/
│   └── index.html           # Full SPA (HTML/CSS/JS, no framework needed)
├── Dockerfile               # Backend container
├── docker-compose.yml       # Full stack: backend + Redis
├── locustfile.py            # Stress testing
└── README.md                # This file
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│  CLIENT LAYER (Browser)                              │
│  ┌──────────┐  WebSocket  ┌──────────┐              │
│  │ User A   │◄───────────►│ User B   │              │
│  └──────────┘             └──────────┘              │
└────────────┬────────────────────┬───────────────────┘
             │ WebSocket /ws/{user}│
┌────────────▼────────────────────▼───────────────────┐
│  APPLICATION LAYER (FastAPI + asyncio)               │
│  ┌─────────────────────────────────────────────────┐ │
│  │  ConnectionManager (concurrent WS connections)  │ │
│  │  REST API: /api/tasks (CRUD operations)         │ │
│  │  Event Publisher → Redis Channel                │ │
│  └──────────────────────┬──────────────────────────┘ │
└─────────────────────────┼───────────────────────────┘
                          │ Pub/Sub
┌─────────────────────────▼───────────────────────────┐
│  DISTRIBUTED LAYER (Redis Pub/Sub)                   │
│  Channel: taskboard:events                           │
│  ┌──────────────────────────────────────────────┐   │
│  │  Publisher ──► [taskboard:events] ──► Sub    │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────┐
│  DATA LAYER (SQLite + aiosqlite)                     │
│  tasks table: id, title, desc, column, color, ...    │
└─────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (Docker — Recommended)

### Prerequisites
- Docker Desktop installed
- Docker Compose available

### Run with one command:

```bash
git clone <your-repo-url>
cd taskboard
docker-compose up --build
```

Open **http://localhost:8000** in multiple browser tabs.

Enter different usernames and collaborate in real time!

---

## 💻 Local Development (Without Docker)

### 1. Start Redis

Option A — Docker:
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

Option B — Install Redis locally:
```bash
# macOS
brew install redis && brew services start redis

# Ubuntu
sudo apt install redis-server && sudo systemctl start redis
```

### 2. Backend Setup

```bash
cd taskboard/backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set environment variables
export REDIS_URL=redis://localhost:6379
export DB_PATH=./taskboard.db

python main.py
# Server running at http://localhost:8000
```

### 3. Open Frontend

The backend serves the frontend at **http://localhost:8000**

Or open `frontend/index.html` directly in browser (set API URL if needed).

---

## 🌐 Free Cloud Deployment

### Option A: Railway (Easiest — ~5 min)

1. Create free account at [railway.app](https://railway.app)
2. Click **New Project → Deploy from GitHub**
3. Connect your GitHub repo
4. Railway auto-detects Dockerfile
5. Add Redis:
   - Click **+ New Service → Database → Redis**
   - Copy the `REDIS_URL` from Redis service settings
6. Set environment variables in backend service:
   ```
   REDIS_URL=<your-redis-url-from-step-5>
   DB_PATH=/data/taskboard.db
   ```
7. Deploy! Railway gives you a public URL.

### Option B: Render (Free Tier)

1. Create account at [render.com](https://render.com)
2. New **Web Service** → connect GitHub repo
3. Settings:
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add **Redis** service (Render has free Redis)
5. Environment variables:
   ```
   REDIS_URL=<render-redis-url>
   DB_PATH=/tmp/taskboard.db
   PORT=10000
   ```
6. Deploy!

### Option C: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

cd taskboard
fly auth login
fly launch          # Follow prompts, name your app
fly redis create    # Create Redis instance
fly secrets set REDIS_URL=<redis-url>
fly deploy
```

### Environment Variables Reference

| Variable    | Default                    | Description              |
|-------------|----------------------------|--------------------------|
| `REDIS_URL` | `redis://localhost:6379`   | Redis connection string  |
| `DB_PATH`   | `./taskboard.db`           | SQLite file path         |
| `PORT`      | `8000`                     | Server port              |

---

## 🧪 Stress Testing Guide

### Install Locust

```bash
pip install locust websocket-client
```

### Run Basic Load Test

```bash
# Start the application first (docker-compose up)

# Then in another terminal:
locust -f locustfile.py --host=http://localhost:8000

# Open http://localhost:8089 in browser
# Set: Number of users = 50, Spawn rate = 5
# Click Start
```

### Stress Test Scenarios

#### Scenario 1: Light load (classroom demo)
- Users: 10
- Spawn rate: 2/second
- Expected: All requests <50ms, 0% errors

#### Scenario 2: Medium load (realistic)
- Users: 50
- Spawn rate: 5/second
- Expected: <100ms avg, <1% errors

#### Scenario 3: Heavy load (stress test)
- Users: 100
- Spawn rate: 10/second
- Expected: WebSocket connections maintained, some slowdown acceptable

### Manual Browser Test (No tools needed)

1. Open 5+ browser tabs to `http://localhost:8000`
2. Use different usernames in each tab
3. Create tasks in one tab → watch them appear in all others
4. Move tasks → all tabs update simultaneously
5. Check the Activity Feed panel for real-time events

### Expected Metrics (Single Server, Docker)

| Concurrent Users | Avg Response | Requests/sec | Error Rate |
|-----------------|-------------|--------------|------------|
| 10              | ~15ms        | ~30 req/s    | 0%         |
| 50              | ~40ms        | ~120 req/s   | <0.1%      |
| 100             | ~80ms        | ~200 req/s   | <1%        |

### How Concurrency is Handled Safely

1. **asyncio event loop**: Single-threaded but handles thousands of concurrent I/O operations via cooperative multitasking
2. **asyncio.Lock** in ConnectionManager: Prevents race conditions when reading/writing the connections dict
3. **asyncio.gather()**: Broadcasts to N clients in parallel (concurrent I/O, not sequential)
4. **Redis Pub/Sub**: Decouples publishers from subscribers; if a subscriber is slow, others aren't affected
5. **aiosqlite**: Non-blocking DB queries; event loop continues serving other requests during DB I/O

---

## 📖 PDC Defense Explanation

### 1. Concurrency
**Definition**: Multiple tasks making progress at the same time.

**In our system**: 100 users can be connected simultaneously via WebSockets. FastAPI uses Python's `asyncio` — a single-threaded event loop that switches between tasks when one is waiting for I/O (network, database). This is called **cooperative multitasking**.

```
User A sends message → event loop handles it
While waiting for Redis → event loop handles User B
While writing to DB    → event loop handles User C
```

**Key code**: `ConnectionManager.broadcast()` uses `asyncio.gather()` to send messages to all N clients concurrently — not one-by-one.

---

### 2. Synchronization
**Definition**: Coordinating access to shared resources to prevent data corruption.

**In our system**: The `_connections` dictionary in `ConnectionManager` is accessed by multiple async coroutines. We use `asyncio.Lock` to ensure only one coroutine modifies it at a time.

```python
async with self._lock:  # Only one coroutine enters this block at a time
    self._connections[client_id] = (websocket, username)
```

Without this lock, two users connecting at the exact same time could corrupt the dict (race condition).

---

### 3. Event-Driven Architecture
**Definition**: System behavior is triggered by events rather than continuous polling.

**In our system**: Instead of clients asking "did anything change?" every second (polling), they receive instant notifications (push). When a task is created:

```
User creates task → FastAPI publishes event → Redis broadcasts → 
All subscribers receive → WebSocket pushes to browsers → UI updates
```

The frontend's `handleServerEvent()` function reacts to typed events: `TASK_CREATED`, `TASK_MOVED`, `USER_JOINED`, etc.

---

### 4. Distributed Messaging (Redis Pub/Sub)
**Definition**: A messaging pattern where publishers send messages to channels, and subscribers receive them — without direct coupling.

**In our system**: Redis acts as a message broker:
- When any backend node processes a change, it **publishes** to `taskboard:events`
- ALL backend nodes have a **subscriber** listening to that channel
- Each subscriber forwards messages to its locally-connected WebSocket clients

**Why this matters for distributed systems**:
- In production, you can run 3 backend servers behind a load balancer
- User A connects to Server 1, User B connects to Server 2
- When A creates a task, Server 1 publishes to Redis
- Server 2's subscriber receives it and notifies User B
- Without Redis, B would never know about A's action!

```
Server 1 (User A connected)       Server 2 (User B connected)
     │                                  │
     ├─ publish("taskboard:events") ──► Redis ──► subscribe()
     │                                  │
     └─ local broadcast to A            └─ local broadcast to B
```

---

### 5. Real-Time Systems
**Definition**: Systems that respond to inputs within guaranteed time bounds.

**In our system**: Updates propagate from one user to all others in under 100ms:
1. User action (drag & drop) → HTTP PATCH request (~5ms)
2. Server processes + publishes to Redis (~2ms)
3. Redis delivers to subscriber (~1ms)
4. WebSocket push to all clients (~2ms)
5. Browser DOM update (~1ms)
**Total: ~11ms typical latency**

This is achieved through:
- Non-blocking I/O (asyncio)
- In-memory message broker (Redis)
- Persistent WebSocket connections (no reconnect overhead)
- Optimistic UI updates (UI updates before server confirms)

---

## 📊 PDC Concepts Summary Table

| Concept | Implementation | Where in Code |
|---------|---------------|---------------|
| Concurrency | asyncio event loop, multiple WS connections | `main.py`, `connection_manager.py` |
| Synchronization | asyncio.Lock on connections dict | `connection_manager.py` line ~25 |
| Event-Driven | WS events: TASK_CREATED, MOVED, etc. | `main.py` → `handleServerEvent()` |
| Distributed Messaging | Redis Pub/Sub on `taskboard:events` | `redis_subscriber()`, `publish_event()` |
| Parallel I/O | asyncio.gather for broadcast | `ConnectionManager.broadcast()` |
| Async DB | aiosqlite non-blocking queries | `database.py` |
| Real-Time Sync | WebSocket push, <100ms latency | `websocket_endpoint()` + frontend WS |

---

## 🛠️ API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | Get all tasks |
| POST | `/api/tasks?username=X` | Create task |
| PUT | `/api/tasks/{id}?username=X` | Update task |
| PATCH | `/api/tasks/{id}/move?username=X` | Move to column |
| DELETE | `/api/tasks/{id}?username=X` | Delete task |
| GET | `/api/stats` | System statistics |
| WS | `/ws/{username}` | WebSocket connection |
| GET | `/docs` | Auto-generated API docs (FastAPI) |

---

## 🔧 Troubleshooting

### "Redis unavailable" message
The system runs in single-node mode without Redis. All features work; just no cross-node distribution. For demo purposes, single-node is fine.

### WebSocket won't connect
- Check that the backend is running: `curl http://localhost:8000/api/stats`
- Check browser console for errors
- Ensure CORS is allowed (it is, by default)

### Tasks not persisting after restart
- If using Docker: check that the SQLite volume is mounted correctly
- The default `DB_PATH` is `./taskboard.db` (relative to backend directory)

### Docker port already in use
```bash
# Change port in docker-compose.yml
ports:
  - "8001:8000"  # Use 8001 instead
```
