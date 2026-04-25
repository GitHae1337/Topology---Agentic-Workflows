from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
import json
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


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
