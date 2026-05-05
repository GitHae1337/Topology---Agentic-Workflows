"""Phase 2 helpers: turn participant-built workflows into evaluable inputs.

Three concerns combined in one module:

  1. classify_workflow(data) → (label, agent_count)
     Auto-classifier identical to humaneval/topology_classifier.py.
     Picks the dominant topology template (or "none" if no template / unknown).

  2. adapt_workflow_to_topology(data) → (TopologyConfig, agents, label, count) | None
     Turn a workflows.db `data` JSON into the same (TopologyConfig, agents)
     pair our Phase 1 build_topology() returns, so the same runners can
     consume both AI presets and human-built workflows.

  3. iter_phase2_workflows(db_path) + build_participant_session_map(log_root)
     Pull rows that came from researcher-led trials (session_id IS NOT NULL)
     and join them to participant_id by scanning the Log/ folders the
     edit_log API writes.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional

from ..models.topology import TopologyConfig
from ..models.agent import AgentConfig


VALID_TOPOLOGIES = {"chain", "centralized", "cycle", "hierarchical", "mesh"}


# -------------------------- classifier --------------------------

def _count_agents(workflow_data: dict[str, Any]) -> int:
    """Total number of agent nodes in the workflow."""
    agents = workflow_data.get("agents") or []
    if isinstance(agents, list) and len(agents) > 0:
        return len(agents)
    nodes = workflow_data.get("nodes") or []
    return sum(1 for n in nodes if isinstance(n, dict) and n.get("type") == "agent")


def _agents_in_template(template: dict[str, Any]) -> int:
    agents = template.get("agents") or []
    return len(agents) if isinstance(agents, list) else 0


def classify_workflow(workflow_data: dict[str, Any]) -> tuple[str, int]:
    """Return (topology_label, agent_count) for a saved workflow.

    Rules:
      - 0 templates → ("none", agent_count)
      - 1 template → (template["type"], agent_count)
      - >1 templates → dominant by agent count
      - unknown type → "none"
    """
    agent_count = _count_agents(workflow_data)
    templates = workflow_data.get("topologies") or []

    if not templates:
        print(f"[workflow_adapter] no templates → none (agents={agent_count})")
        return ("none", agent_count)

    if len(templates) == 1:
        raw_type = (templates[0].get("type") or "").strip().lower()
        label = raw_type if raw_type in VALID_TOPOLOGIES else "none"
        if label == "none":
            print(f"[workflow_adapter] unknown template type: {raw_type!r}")
        return (label, agent_count)

    dominant = max(templates, key=_agents_in_template)
    raw_type = (dominant.get("type") or "").strip().lower()
    label = raw_type if raw_type in VALID_TOPOLOGIES else "none"
    print(
        f"[workflow_adapter] multi-template ({len(templates)}); "
        f"dominant={raw_type!r}, dominant_agents={_agents_in_template(dominant)}"
    )
    return (label, agent_count)


# -------------------------- adapter --------------------------

def _pick_dominant_template(templates: list[dict]) -> Optional[dict]:
    if not templates:
        return None
    if len(templates) == 1:
        return templates[0]
    return max(templates, key=lambda t: len(t.get("agents") or []))


def adapt_workflow_to_topology(
    workflow_data: dict[str, Any],
) -> Optional[tuple[TopologyConfig, list[AgentConfig], str, int]]:
    """workflows.db 'data' JSON → evaluable (topology, agents, label, count).

    Returns None if the workflow is not runnable: classifier returned 'none',
    no dominant template found, fewer than 2 agents bound to dominant
    template, or fewer than 2 actual agent dicts resolvable.
    """
    label, agent_count = classify_workflow(workflow_data)
    print(f"[workflow_adapter] classified: label={label}, agent_count={agent_count}")

    if label not in VALID_TOPOLOGIES:
        print(f"[workflow_adapter] skip: label={label!r} not runnable")
        return None

    templates = workflow_data.get("topologies") or []
    dominant = _pick_dominant_template(templates)
    if dominant is None:
        print(f"[workflow_adapter] skip: no dominant template")
        return None

    bound_agent_ids = set(dominant.get("agents") or [])
    if len(bound_agent_ids) < 2:
        print(f"[workflow_adapter] skip: dominant template has <2 agents ({len(bound_agent_ids)})")
        return None

    all_agents = workflow_data.get("agents") or []
    filtered_agents = [
        a for a in all_agents
        if isinstance(a, dict) and a.get("id") in bound_agent_ids
    ]
    print(
        f"[workflow_adapter] dominant: type={dominant.get('type')}, "
        f"bound={len(bound_agent_ids)}, resolved={len(filtered_agents)}"
    )
    if len(filtered_agents) < 2:
        print(f"[workflow_adapter] skip: only {len(filtered_agents)} agent dicts resolved")
        return None

    topo = TopologyConfig(**dominant)
    agents = [AgentConfig(**a) for a in filtered_agents]
    return (topo, agents, label, agent_count)


# -------------------------- DB row generator --------------------------

class WorkflowRow:
    """Lightweight container for one workflows.db row."""
    __slots__ = ("id", "name", "session_id", "data", "created_at")

    def __init__(self, id: str, name: str, session_id: Optional[str], data: dict, created_at: str):
        self.id = id
        self.name = name
        self.session_id = session_id
        self.data = data
        self.created_at = created_at


def iter_phase2_workflows(db_path: Path) -> Iterator[WorkflowRow]:
    """Yield workflows.db rows where session_id IS NOT NULL (i.e. saved during a trial)."""
    if not db_path.exists():
        raise FileNotFoundError(f"workflows.db not found at {db_path}")
    print(f"[workflow_adapter] reading {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, session_id, data, created_at FROM workflows "
        "WHERE session_id IS NOT NULL ORDER BY created_at ASC"
    )
    rows = cur.fetchall()
    conn.close()
    print(f"[workflow_adapter] found {len(rows)} workflows with session_id")

    for r in rows:
        data = json.loads(r["data"])
        yield WorkflowRow(
            id=r["id"],
            name=r["name"],
            session_id=r["session_id"],
            data=data,
            created_at=r["created_at"],
        )


# -------------------------- session → participant join --------------------------

def build_participant_session_map(log_root: Path) -> dict[str, str]:
    """Scan Log/<datetime>/session_<sid>.json and return {session_id: participant_id}.

    Newer files win on duplicate sessionId (mtime sort). participantId may be
    None if the researcher panel didn't capture it; in that case the entry is
    skipped so callers can detect 'unknown participant' explicitly.
    """
    if not log_root.exists():
        print(f"[workflow_adapter] log_root {log_root} doesn't exist; empty map")
        return {}

    candidates = sorted(
        log_root.glob("*/session_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    print(f"[workflow_adapter] scanning {len(candidates)} session_*.json files under {log_root}")

    out: dict[str, str] = {}
    for path in candidates:
        with path.open("r", encoding="utf-8") as f:
            record = json.load(f)
        sid = record.get("sessionId")
        pid = record.get("participantId")
        if not sid or not pid:
            continue
        out[sid] = pid

    print(f"[workflow_adapter] mapped {len(out)} session→participant pairs")
    return out
