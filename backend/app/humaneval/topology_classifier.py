"""
Auto-classifier for participant-built workflows.

Given a workflow row from workflows.db (the JSON-decoded `data` column plus
the legacy top-level fields), this returns the dominant topology label and
the total number of agent nodes — used by master_table builder to populate
the (topology, agent_count) columns without the researcher manually
labeling each trial.

The 5 valid topology labels are:
    chain, centralized, cycle, hierarchical, mesh

If no topology template was placed on the canvas, returns "none".
"""
from typing import Any

VALID_TOPOLOGIES = {"chain", "centralized", "cycle", "hierarchical", "mesh"}


def _count_agents(workflow_data: dict[str, Any]) -> int:
    """Total number of agent nodes in the workflow.

    We trust workflow_data["agents"] when present (the API canonically
    serializes the agent list there). Fallback to nodes filtered by type.
    """
    agents = workflow_data.get("agents") or []
    if isinstance(agents, list) and len(agents) > 0:
        return len(agents)

    nodes = workflow_data.get("nodes") or []
    return sum(1 for n in nodes if isinstance(n, dict) and n.get("type") == "agent")


def _agents_in_template(template: dict[str, Any]) -> int:
    """Number of agents bound to a given topology template."""
    agents = template.get("agents") or []
    return len(agents) if isinstance(agents, list) else 0


def classify_workflow(workflow_data: dict[str, Any]) -> tuple[str, int]:
    """Return (topology_label, agent_count) for a saved workflow.

    Rules:
      1. agent_count = total agent nodes in the workflow.
      2. If no topology templates → ("none", agent_count)
      3. If exactly one template → (template["type"], agent_count)
      4. If multiple → pick the template with the most agents.

    Unknown / out-of-set type strings collapse to "none" with a warning.
    """
    agent_count = _count_agents(workflow_data)
    templates = workflow_data.get("topologies") or []

    if not templates:
        print(f"[topology_classifier] no templates → none (agents={agent_count})")
        return ("none", agent_count)

    if len(templates) == 1:
        raw_type = (templates[0].get("type") or "").strip().lower()
        label = raw_type if raw_type in VALID_TOPOLOGIES else "none"
        if label == "none":
            print(f"[topology_classifier] unknown template type: {raw_type!r}")
        return (label, agent_count)

    # Multi-template: pick the one with the most agents bound to it.
    dominant = max(templates, key=_agents_in_template)
    raw_type = (dominant.get("type") or "").strip().lower()
    label = raw_type if raw_type in VALID_TOPOLOGIES else "none"
    print(
        f"[topology_classifier] multi-template ({len(templates)}); "
        f"dominant type={raw_type!r}, dominant_agents={_agents_in_template(dominant)}"
    )
    return (label, agent_count)
