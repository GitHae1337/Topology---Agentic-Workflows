"""
workflows.db row → (TopologyConfig, list[AgentConfig], label, agent_count) 변환.

Phase 1의 get_preset()이 반환하던 것과 같은 형태로, runner.py의
run_preset_on_dataset()을 그대로 재사용할 수 있게 한다.

label="none"이거나 dominant template의 agent <2개면 None을 돌려준다.
"""
from typing import Any, Optional

from ..models.topology import TopologyConfig
from ..models.agent import AgentConfig
from .topology_classifier import classify_workflow, VALID_TOPOLOGIES


def _pick_dominant_template(templates: list[dict]) -> Optional[dict]:
    """가장 많은 agent가 바인딩된 template 선택."""
    if not templates:
        return None
    if len(templates) == 1:
        return templates[0]
    return max(templates, key=lambda t: len(t.get("agents") or []))


def adapt_workflow_to_topology(
    workflow_data: dict[str, Any],
) -> Optional[tuple[TopologyConfig, list[AgentConfig], str, int]]:
    """
    workflows.db의 JSON-decoded data dict를 받아 평가 가능한 형태로 반환.
    runnable이 아니면 None.
    """
    label, agent_count = classify_workflow(workflow_data)
    print(f"[adapter] classified: label={label}, agent_count={agent_count}")

    if label not in VALID_TOPOLOGIES:
        print(f"[adapter] skip: label={label!r} not runnable")
        return None

    templates = workflow_data.get("topologies") or []
    dominant = _pick_dominant_template(templates)
    if dominant is None:
        print(f"[adapter] skip: no dominant template")
        return None

    bound_agent_ids = set(dominant.get("agents") or [])
    if len(bound_agent_ids) < 2:
        print(f"[adapter] skip: dominant template has <2 agents ({len(bound_agent_ids)})")
        return None

    all_agents = workflow_data.get("agents") or []
    filtered_agents = [
        a for a in all_agents
        if isinstance(a, dict) and a.get("id") in bound_agent_ids
    ]
    print(
        f"[adapter] dominant: type={dominant.get('type')}, "
        f"bound={len(bound_agent_ids)}, resolved={len(filtered_agents)}"
    )

    if len(filtered_agents) < 2:
        print(f"[adapter] skip: only {len(filtered_agents)} agent dicts resolved")
        return None

    topo = TopologyConfig(**dominant)
    agents = [AgentConfig(**a) for a in filtered_agents]
    return (topo, agents, label, agent_count)
