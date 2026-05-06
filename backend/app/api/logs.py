from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
from pathlib import Path
import json
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# ----- EvaluationPanel self-assessment guide logging (Stage 1) -----
# Two streams written to backend/data/logs/evaluations.jsonl:
#   A. Hidden automatic evaluation snapshot per LLM iteration
#   B. Dimension expand/collapse events from the guide UI
EVAL_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "logs"
EVAL_LOG_PATH = EVAL_LOG_DIR / "evaluations.jsonl"


class GuideAction(BaseModel):
    type: str  # 'expand' | 'collapse'
    dimensionId: str


class EvaluationLogRequest(BaseModel):
    timestamp: str
    sessionId: str
    participantId: str
    taskId: str
    iterationIndex: int
    automaticEvaluation: Optional[Any] = None
    guideAction: Optional[GuideAction] = None


@router.post("/evaluation")
async def log_evaluation(req: EvaluationLogRequest):
    """Append one log row to backend/data/logs/evaluations.jsonl.

    Either automaticEvaluation (Stream A) or guideAction (Stream B) is
    populated per row. Researcher greps by sessionId / participantId for
    post-hoc analysis.
    """
    EVAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = req.model_dump()
    kind = "guide" if req.guideAction else "auto"
    print(f"[logs.evaluation] appending {kind} log: session={req.sessionId} "
          f"iter={req.iterationIndex} task={req.taskId}")
    with EVAL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True}


class TopologyInfo(BaseModel):
    topologyId: str
    topologyName: str
    topologyColor: str


class LogEntry(BaseModel):
    id: str
    agent: str
    content: str
    timestamp: str
    topologyInfo: Optional[TopologyInfo] = None
    agentRole: Optional[str] = None


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str


class SaveLogRequest(BaseModel):
    chatId: str
    workflowName: str
    messages: List[ChatMessage]
    logEntries: List[LogEntry]
    workflowId: Optional[str] = None
    createdAt: str


@router.post("/save")
async def save_log(request: SaveLogRequest):
    """Save chat log to a JSON file in the current session folder."""
    from ..main import SESSION_LOG_PATH

    logger.info(f"Saving chat log: {request.chatId}")
    logger.info(f"Session log path: {SESSION_LOG_PATH}")

    # Construct file path
    filename = f"chat-{request.chatId}.json"
    filepath = os.path.join(SESSION_LOG_PATH, filename)
    logger.info(f"Writing to file: {filepath}")

    # Prepare data
    log_data = {
        "chatId": request.chatId,
        "workflowName": request.workflowName,
        "workflowId": request.workflowId,
        "createdAt": request.createdAt,
        "savedAt": datetime.now().isoformat(),
        "messages": [msg.model_dump() for msg in request.messages],
        "logEntries": [entry.model_dump() for entry in request.logEntries],
    }

    # Write to file - will raise error if fails, no fallback
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Chat log saved successfully: {filepath}")

    return {"success": True, "filepath": filepath}
