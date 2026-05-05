from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def _session_dir() -> Path:
    """Resolve the active session log folder set by main.py on startup."""
    from ..main import SESSION_LOG_PATH
    return Path(SESSION_LOG_PATH)


class SessionStartRequest(BaseModel):
    sessionId: str
    participantId: Optional[str] = None
    taskId: Optional[str] = None
    startedAt: str
    userAgent: Optional[str] = None


class EditLogAppendRequest(BaseModel):
    sessionId: str
    timestamp: str
    action: str
    payload: dict[str, Any]
    undoStackDepth: int


class EventRequest(BaseModel):
    sessionId: str
    timestamp: str
    eventType: str
    payload: dict[str, Any] = {}


@router.post("/session-start")
async def session_start(req: SessionStartRequest):
    """Record the beginning of a participant authoring session."""
    session_dir = _session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "type": "session_start",
        "sessionId": req.sessionId,
        "participantId": req.participantId,
        "taskId": req.taskId,
        "startedAt": req.startedAt,
        "userAgent": req.userAgent,
        "serverReceivedAt": datetime.now().isoformat(),
    }

    out_path = session_dir / f"session_{req.sessionId}.json"
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"[edit_log] session_start written: {out_path}")
    return {"success": True, "path": str(out_path)}


@router.post("/append")
async def append_edit(req: EditLogAppendRequest):
    """Append a single structural-edit entry to the session edit-log JSONL."""
    session_dir = _session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)

    line = json.dumps({
        "sessionId": req.sessionId,
        "timestamp": req.timestamp,
        "action": req.action,
        "payload": req.payload,
        "undoStackDepth": req.undoStackDepth,
    }, ensure_ascii=False)

    log_path = session_dir / f"edit_log_{req.sessionId}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    logger.info(f"[edit_log] appended {req.action} to {log_path.name}")
    return {"success": True}


@router.post("/event")
async def append_event(req: EventRequest):
    """Append a non-edit timing event (first click / undo / redo / session end)."""
    session_dir = _session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)

    line = json.dumps({
        "sessionId": req.sessionId,
        "timestamp": req.timestamp,
        "eventType": req.eventType,
        "payload": req.payload,
    }, ensure_ascii=False)

    events_path = session_dir / f"events_{req.sessionId}.jsonl"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    logger.info(f"[edit_log] event {req.eventType} appended to {events_path.name}")
    return {"success": True}
