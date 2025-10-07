# backend/app/main.py
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from . import models, db
from .auth import require_api_key, verify_hmac
from pydantic import BaseModel, Field, confloat, constr
import asyncio
import os
from datetime import datetime
import json
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Create DB tables
models.Base.metadata.create_all(bind=db.engine)

app = FastAPI(title="IoT Security Dashboard API", version="1.0.0")

# -------------------------
# Validate critical secrets
# -------------------------
def mask_secret(secret: str) -> str:
    return secret[:3] + "***" + secret[-3:] if secret and len(secret) > 6 else "MISSING"

API_KEY = os.getenv("API_KEY")
HMAC_SECRET = os.getenv("HMAC_SECRET")
WS_FRONTEND_TOKEN = (os.getenv("WS_FRONTEND_TOKEN")or "").strip()

print("🔒 Security configuration:")
print(f"  API_KEY............. {mask_secret(API_KEY)}")
print(f"  HMAC_SECRET......... {mask_secret(HMAC_SECRET)}")
print(f"  WS_FRONTEND_TOKEN... {mask_secret(WS_FRONTEND_TOKEN)}")

# -------------------------
# Configure CORS
# -------------------------
origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000")
origins = [o.strip() for o in origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# -------------------------
# Middleware: limit body size
# -------------------------
class LimitBodyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes=1024*50):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) > self.max_bytes:
                    return PlainTextResponse("Payload too large", status_code=413)
            except ValueError:
                pass
        return await call_next(request)

app.add_middleware(LimitBodyMiddleware, max_bytes=int(os.getenv("MAX_BODY_BYTES", "51200")))

# -------------------------
# In-memory rate limiter (simple)
# -------------------------
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "120"))
_rate_store_lock = asyncio.Lock()
_rate_store: Dict[str, List[float]] = {}

async def check_rate_limit(ip: str):
    now = time.time()
    async with _rate_store_lock:
        timestamps = _rate_store.get(ip, [])
        window_start = now - RATE_LIMIT_WINDOW
        timestamps = [t for t in timestamps if t >= window_start]
        if len(timestamps) >= RATE_LIMIT_MAX:
            return False
        timestamps.append(now)
        _rate_store[ip] = timestamps
    return True

# -------------------------
# DB dependency
# -------------------------
def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

# -------------------------
# Input validation models
# -------------------------
class Metrics(BaseModel):
    temperature: confloat(ge=-50, le=200)
    vibration: confloat(ge=0, le=100)

class IngestEvent(BaseModel):
    device_id: constr(min_length=1, max_length=128)
    payload: Dict[str, Any] = Field(default_factory=dict)
    metrics: Metrics | None = None

# -------------------------
# Connection manager
# -------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.frontend_ready: bool = False
        self._lock = asyncio.Lock()
        self._backlog: List[Dict[str, Any]] = []
        self._max_backlog = int(os.getenv("BACKLOG_SIZE", "500"))

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if not self.active_connections:
            self.frontend_ready = False

    async def mark_ready(self):
        async with self._lock:
            self.frontend_ready = True
            if self._backlog and self.active_connections:
                for ev in self._backlog[-self._max_backlog:]:
                    await self._safe_broadcast(ev)
            self._backlog.clear()

    async def broadcast(self, message: Dict[str, Any]):
        if not self.frontend_ready:
            async with self._lock:
                if len(self._backlog) >= self._max_backlog:
                    self._backlog.pop(0)
                self._backlog.append(message)
            return
        await self._safe_broadcast(message)

    async def _safe_broadcast(self, message: Dict[str, Any]):
        stale = []
        for ws in list(self.active_connections):
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)

manager = ConnectionManager()

# -------------------------
# Health endpoints
# -------------------------
@app.get("/healthz")
async def healthz():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}

@app.get("/ready")
async def ready_status():
    return {"ready": manager.frontend_ready}

# -------------------------
# Simulator toggle
# -------------------------
SIMULATION_ACTIVE = True

@app.get("/simulator/state")
async def simulator_state():
    return {"active": SIMULATION_ACTIVE}

@app.post("/simulator/toggle", dependencies=[Depends(require_api_key)])
async def simulator_toggle():
    global SIMULATION_ACTIVE
    SIMULATION_ACTIVE = not SIMULATION_ACTIVE
    return {"active": SIMULATION_ACTIVE}

# -------------------------
# Ingestion endpoint (secured)
# -------------------------
@app.post("/ingest", dependencies=[Depends(require_api_key)])
async def ingest_event(request: Request, database: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not await check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    # Perform HMAC verification (returns True/False)
    from .auth import HMAC_SECRET as AUTH_SECRET
    if AUTH_SECRET:
        import hmac, hashlib
        expected = hmac.new(AUTH_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        evt = IngestEvent(**payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid event structure: {e}")

    db_event = models.Event(device_id=evt.device_id, payload=evt.payload or {"metrics": evt.metrics.dict() if evt.metrics else {}})
    database.add(db_event)
    database.commit()
    database.refresh(db_event)

    event_data = {
        "id": db_event.id,
        "device_id": db_event.device_id,
        "timestamp": db_event.timestamp.isoformat(),
        "payload": db_event.payload,
    }

    await manager.broadcast(event_data)

    # Simple anomaly detection
    try:
        metrics = event_data.get("payload", {}).get("metrics", {})
        temp = float(metrics.get("temperature", 0))
        vib = float(metrics.get("vibration", 0))
        if temp < 18 or temp > 25 or vib > 0.8:
            await manager.broadcast({"type": "anomaly", **event_data})
    except Exception:
        pass

    return {"status": "accepted", "id": db_event.id}

# -------------------------
# Event listing
# -------------------------
@app.get("/events")
def list_events(limit: int = 200, database: Session = Depends(get_db)):
    q = database.query(models.Event).order_by(models.Event.timestamp.desc()).limit(limit).all()
    return [
        {"id": e.id, "device_id": e.device_id, "timestamp": e.timestamp.isoformat(), "payload": e.payload}
        for e in reversed(q)
    ]

# -------------------------
# WebSocket endpoint with token validation
# -------------------------
@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    token = (websocket.query_params.get("token", "")or "").strip()
    expected = (WS_FRONTEND_TOKEN or "").strip()
    print(f"WebSocket connection attempt with token: {token}")
    if expected and token != WS_FRONTEND_TOKEN:
        await websocket.close(code=1008)
        print("WebSocket rejected: invalid or missing token")
        return

    await manager.connect(websocket)
    print("✅ WebSocket client connected")

    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip().lower() == "frontend:ready":
                await manager.mark_ready()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("❌ WebSocket disconnected")
    except Exception as e:
        manager.disconnect(websocket)
        print(f"⚠️ WebSocket error: {e}")
