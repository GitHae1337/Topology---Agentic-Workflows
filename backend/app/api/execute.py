from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from ..models import ExecutionRequest, ExecutionResult, ResumeRequest
from ..engine.graph_orchestrator import GraphOrchestrator, ExecutionContext
from .workflows import get_workflow

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store for paused executions (production should use Redis)
_paused_executions: Dict[str, Dict[str, Any]] = {}


# ---- Korean task reference injection ----

_TRANSLATIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "translations_ko.json"
_translations_cache: Optional[dict] = None


def _load_ko_translations() -> dict:
    global _translations_cache
    if _translations_cache is None:
        if not _TRANSLATIONS_PATH.exists():
            print(f"[execute] translations_ko.json missing at {_TRANSLATIONS_PATH}")
            _translations_cache = {}
        else:
            with _TRANSLATIONS_PATH.open("r", encoding="utf-8") as f:
                _translations_cache = json.load(f)
            print(f"[execute] loaded {len(_translations_cache)} Korean translations")
    return _translations_cache


def _format_records(records: list[dict], fields: list[str]) -> str:
    """Render list of dict as compact bullet lines."""
    out = []
    for r in records:
        parts = [f"{k}={r.get(k, '')}" for k in fields if k in r]
        out.append("- " + ", ".join(parts))
    return "\n".join(out) if out else "- (없음)"


def _build_reference_prompt(task_id: str) -> Optional[str]:
    """If task_id has Korean translation, build a reference prompt the LLM
    can use to ground its plan in Korean names. Returns None for English-only
    tasks so they go through unmodified.
    """
    translations = _load_ko_translations()
    ko = translations.get(task_id)
    if ko is None:
        return None
    ref = ko.get("reference_information")
    if not isinstance(ref, dict):
        return None

    sections = []
    sections.append(
        "## 교통편\n"
        + _format_records(
            ref.get("transportation", []),
            ["type", "carrier", "number", "from", "to", "departure_time", "arrival_time", "price_per_person"],
        )
    )
    sections.append(
        "## 숙소\n"
        + _format_records(
            ref.get("accommodations", []),
            ["name", "city", "price_per_night", "room_type", "house_rules", "max_occupancy"],
        )
    )
    sections.append(
        "## 식당\n"
        + _format_records(
            ref.get("restaurants", []),
            ["name", "city", "cuisine", "price_per_person"],
        )
    )
    sections.append(
        "## 관광지\n"
        + _format_records(
            ref.get("attractions", []),
            ["name", "city", "address", "category"],
        )
    )

    body = "\n\n".join(sections)
    return (
        "[참고 자료 — 일정 작성에 사용할 수 있는 후보 목록. 이름은 그대로 사용할 것]\n\n"
        + body
        + "\n\n[사용자 요청]\n"
    )


@router.post("/{workflow_id}")
async def execute_workflow(workflow_id: str, request: ExecutionRequest):
    """
    Execute a workflow with streaming results via SSE.

    Returns Server-Sent Events with message updates, approval requests, and final result.
    """
    logger.info(f"Execute request for workflow {workflow_id}: {request.input[:100]}...")

    # Get workflow
    workflow = await get_workflow(workflow_id)

    # Create graph orchestrator
    orchestrator = GraphOrchestrator(workflow)

    # If a Korean task is active, prepend its reference data to the input
    # so the LLM grounds its plan in Korean names from translations_ko.json.
    augmented_input = request.input
    if request.task_id:
        ref_prompt = _build_reference_prompt(request.task_id)
        if ref_prompt:
            augmented_input = ref_prompt + request.input
            print(f"[execute] injected Korean reference for task {request.task_id} "
                  f"({len(ref_prompt)} chars)")

    async def event_generator():
        """Generate SSE events from workflow execution."""
        messages = []

        async for message in orchestrator.execute(
            augmented_input,
            request.config_overrides,
            history=request.history,
        ):
            messages.append(message)

            # Check for approval pause
            if message.metadata.get('approval_required'):
                execution_id = message.metadata['execution_id']
                _paused_executions[execution_id] = {
                    'workflow_id': workflow_id,
                    'node_id': message.metadata['node_id'],
                    'context': message.metadata['context'],
                }
                logger.info(f"Execution paused for approval: {execution_id}")

                yield {
                    "event": "approval_required",
                    "data": json.dumps({
                        "type": "approval_required",
                        "data": {
                            "execution_id": execution_id,
                            "node_id": message.metadata['node_id'],
                            "message": message.metadata['message'],
                        }
                    }),
                }
                return  # Stop here, wait for resume

            event_data = {
                "type": "message",
                "data": {
                    "id": message.id,
                    "from": message.from_agent,
                    "to": message.to_agent,
                    "content": message.content,
                    "timestamp": message.timestamp.isoformat(),
                    "metadata": message.metadata,
                }
            }
            yield {
                "event": "message",
                "data": json.dumps(event_data),
            }

        # Send completion event
        logger.info(f"[EXECUTE] Total messages collected: {len(messages)}")
        if messages:
            logger.info(f"[EXECUTE] Last message from: {messages[-1].from_agent}, content length: {len(messages[-1].content)}")
            logger.info(f"[EXECUTE] All message sources: {[m.from_agent for m in messages]}")
        output = messages[-1].content if messages else "No output generated"
        logger.info(f"[EXECUTE] Final output length: {len(output)}")
        complete_data = {
            "type": "complete",
            "data": {
                "output": output,
                "turns_used": len(messages),
                "message_count": len(messages),
            }
        }
        yield {
            "event": "complete",
            "data": json.dumps(complete_data),
        }

    return EventSourceResponse(event_generator())


@router.post("/{workflow_id}/resume")
async def resume_workflow(workflow_id: str, request: ResumeRequest):
    """
    Resume a paused workflow after approval decision.

    The decision determines which branch to follow:
    - "approve" -> port 0 (Approve path)
    - "reject" -> port 1 (Reject path)
    """
    logger.info(f"Resume request for execution {request.execution_id}: {request.decision}")

    paused = _paused_executions.get(request.execution_id)
    if not paused:
        raise HTTPException(status_code=404, detail="Execution not found or already completed")

    if paused['workflow_id'] != workflow_id:
        raise HTTPException(status_code=400, detail="Workflow ID mismatch")

    workflow = await get_workflow(workflow_id)
    orchestrator = GraphOrchestrator(workflow)

    # Determine which port to follow (0 = approve, 1 = reject)
    port = 0 if request.decision == "approve" else 1

    async def event_generator():
        messages = []

        # Get next nodes from the approval node based on decision
        next_nodes = orchestrator._get_next_nodes(paused['node_id'], port=port)
        logger.info(f"Resuming execution, following port {port} to nodes: {next_nodes}")

        # Rebuild context
        saved_context = paused['context']
        context = ExecutionContext(
            workflow_id=workflow_id,
            execution_id=request.execution_id,
            user_input=saved_context.get('user_input', ''),
            current_output=saved_context.get('current_output', ''),
            variables=saved_context.get('variables', {}),
        )

        async for message in orchestrator._execute_nodes(next_nodes, context, {}):
            messages.append(message)

            if message.metadata.get('approval_required'):
                # Another approval node encountered
                new_execution_id = message.metadata['execution_id']
                _paused_executions[new_execution_id] = {
                    'workflow_id': workflow_id,
                    'node_id': message.metadata['node_id'],
                    'context': message.metadata['context'],
                }
                logger.info(f"Execution paused again for approval: {new_execution_id}")

                yield {
                    "event": "approval_required",
                    "data": json.dumps({
                        "type": "approval_required",
                        "data": {
                            "execution_id": new_execution_id,
                            "node_id": message.metadata['node_id'],
                            "message": message.metadata['message'],
                        }
                    }),
                }
                return

            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "message",
                    "data": {
                        "id": message.id,
                        "from": message.from_agent,
                        "to": message.to_agent,
                        "content": message.content,
                        "timestamp": message.timestamp.isoformat(),
                        "metadata": message.metadata,
                    }
                }),
            }

        # Clean up the completed execution
        if request.execution_id in _paused_executions:
            del _paused_executions[request.execution_id]

        output = messages[-1].content if messages else "No output"
        yield {
            "event": "complete",
            "data": json.dumps({
                "type": "complete",
                "data": {
                    "output": output,
                    "turns_used": len(messages),
                    "message_count": len(messages),
                },
            }),
        }

    return EventSourceResponse(event_generator())


@router.post("/{workflow_id}/sync", response_model=ExecutionResult)
async def execute_workflow_sync(workflow_id: str, request: ExecutionRequest):
    """
    Execute a workflow synchronously and return the complete result.

    Use this for non-streaming clients.
    Note: Approval nodes will be auto-approved in sync mode.
    """
    logger.info(f"Sync execute request for workflow {workflow_id}")

    # Get workflow
    workflow = await get_workflow(workflow_id)

    # Create orchestrator
    orchestrator = GraphOrchestrator(workflow)

    # Same Korean reference injection as the streaming endpoint above.
    augmented_input = request.input
    if request.task_id:
        ref_prompt = _build_reference_prompt(request.task_id)
        if ref_prompt:
            augmented_input = ref_prompt + request.input
            print(f"[execute.sync] injected Korean reference for task {request.task_id}")

    # Collect all messages
    messages = []
    async for message in orchestrator.execute(
        augmented_input,
        request.config_overrides,
        history=request.history,
    ):
        messages.append(message)
        # Note: In sync mode, we skip approval pauses

    duration = 0.0  # TODO: Track actual duration
    output = messages[-1].content if messages else "No output generated"

    return ExecutionResult(
        output=output,
        turns_used=len(messages),
        duration_seconds=duration,
        messages=messages,
    )


@router.post("/preview/{workflow_id}")
async def preview_workflow(workflow_id: str, request: ExecutionRequest):
    """
    Preview workflow execution with mock LLM responses.

    Useful for testing workflow structure without using LLM credits.
    """
    logger.info(f"Preview request for workflow {workflow_id}")

    # Get workflow
    workflow = await get_workflow(workflow_id)

    # For preview, return structure info without actually executing
    topology_info = []
    for topo in workflow.topologies:
        agents_in_topo = [a.name for a in workflow.agents if a.topology_id == topo.id]
        topology_info.append({
            "id": topo.id,
            "type": topo.type,
            "name": topo.name,
            "agents": agents_in_topo,
            "edge_count": len(topo.internal_edges),
            "max_turns": topo.max_turns,
            "start_agent": topo.start_agent_id,
        })

    node_info = []
    for node in workflow.nodes:
        node_info.append({
            "id": node.id,
            "type": node.type,
            "name": node.name,
        })

    return {
        "workflow_id": workflow_id,
        "workflow_name": workflow.name,
        "agent_count": len(workflow.agents),
        "topology_count": len(workflow.topologies),
        "node_count": len(workflow.nodes),
        "connection_count": len(workflow.connections),
        "topologies": topology_info,
        "nodes": node_info,
        "preview_mode": True,
        "message": "Preview mode - no LLM calls made",
    }
