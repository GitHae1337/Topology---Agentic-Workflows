"""
Phase 1 AI-only baseline topology presets for HumanEval benchmark.

Each preset returns a (TopologyConfig, list[AgentConfig]) pair representing
a fixed, hand-designed baseline configuration. All presets use the same
LLM model and 3 agents to keep cross-topology comparisons controlled.
"""
from typing import Callable

from ..models.topology import TopologyConfig, TopologyType, InternalEdge, EdgeType
from ..models.agent import AgentConfig


DEFAULT_MODEL = "gpt-4.1"


_CODER_HINT = (
    "You are completing a Python function from the HumanEval benchmark. "
    "Output ONLY the completed function body (or full function if needed) "
    "in a single ```python ... ``` code block. Do not include explanations."
)


def _agent(agent_id: str, name: str, role: str, instructions: str, topo_id: str, model: str) -> AgentConfig:
    return AgentConfig(
        id=agent_id,
        name=name,
        instructions=instructions,
        model=model,
        topology_id=topo_id,
        topology_role=role,
    )


def _edge(edge_id: str, src: str, dst: str, edge_type: EdgeType) -> InternalEdge:
    return InternalEdge(
        id=edge_id,
        **{"from": src, "to": dst, "type": edge_type.value},
    )


def chain_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "preset-chain"
    a1 = _agent("chain-a1", "Reader", "Reader",
                f"{_CODER_HINT}\nRead the problem carefully and restate the function spec in 2 sentences before passing to the next agent.",
                topo_id, model)
    a2 = _agent("chain-a2", "Coder", "Coder",
                f"{_CODER_HINT}\nWrite a first complete implementation based on the previous agent's analysis.",
                topo_id, model)
    a3 = _agent("chain-a3", "Reviewer", "Reviewer",
                f"{_CODER_HINT}\nReview the previous implementation for correctness and edge cases. Return the final corrected code.",
                topo_id, model)

    edges = [
        _edge("chain-e1", a1.id, a2.id, EdgeType.UNIDIRECTIONAL),
        _edge("chain-e2", a2.id, a3.id, EdgeType.UNIDIRECTIONAL),
    ]

    topo = TopologyConfig(
        id=topo_id, type=TopologyType.CHAIN, name="Chain (baseline)",
        agents=[a1.id, a2.id, a3.id], internal_edges=edges,
        max_turns=3, timeout=180, early_termination=False,
    )
    return topo, [a1, a2, a3]


def centralized_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "preset-centralized"
    leader = _agent("cen-a1", "Leader", "Leader",
                    f"{_CODER_HINT}\nYou are the leader. Decompose the problem and delegate to two members, then synthesize their outputs into the final code.",
                    topo_id, model)
    m1 = _agent("cen-a2", "Member-1", "Member",
                f"{_CODER_HINT}\nProduce one complete implementation candidate.",
                topo_id, model)
    m2 = _agent("cen-a3", "Member-2", "Member",
                f"{_CODER_HINT}\nProduce a different implementation candidate emphasizing edge-case handling.",
                topo_id, model)

    edges = [
        _edge("cen-e1", leader.id, m1.id, EdgeType.BIDIRECTIONAL),
        _edge("cen-e2", leader.id, m2.id, EdgeType.BIDIRECTIONAL),
    ]

    topo = TopologyConfig(
        id=topo_id, type=TopologyType.CENTRALIZED, name="Centralized (baseline)",
        agents=[leader.id, m1.id, m2.id], internal_edges=edges,
        max_turns=3, timeout=180, early_termination=False,
    )
    return topo, [leader, m1, m2]


def hierarchical_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "preset-hierarchical"
    manager = _agent("hier-a1", "Manager", "Manager",
                     f"{_CODER_HINT}\nYou are the manager. Split the problem into two subtasks and assign one to each worker, then merge their results.",
                     topo_id, model)
    w1 = _agent("hier-a2", "Worker-1", "Worker",
                f"{_CODER_HINT}\nImplement the subtask assigned by the manager (focus on the primary algorithm).",
                topo_id, model)
    w2 = _agent("hier-a3", "Worker-2", "Worker",
                f"{_CODER_HINT}\nImplement the subtask assigned by the manager (focus on input validation / edge cases).",
                topo_id, model)

    edges = [
        _edge("hier-e1", manager.id, w1.id, EdgeType.BIDIRECTIONAL),
        _edge("hier-e2", manager.id, w2.id, EdgeType.BIDIRECTIONAL),
    ]

    topo = TopologyConfig(
        id=topo_id, type=TopologyType.HIERARCHICAL, name="Hierarchical (baseline)",
        agents=[manager.id, w1.id, w2.id], internal_edges=edges,
        max_turns=3, timeout=180, early_termination=False,
    )
    return topo, [manager, w1, w2]


def mesh_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "preset-mesh"
    a1 = _agent("mesh-a1", "Coder-A", "Member",
                f"{_CODER_HINT}\nProvide your candidate implementation. Then critique the candidates from the other agents and propose a merged final.",
                topo_id, model)
    a2 = _agent("mesh-a2", "Coder-B", "Member",
                f"{_CODER_HINT}\nProvide your candidate implementation. Then critique the candidates from the other agents and propose a merged final.",
                topo_id, model)
    a3 = _agent("mesh-a3", "Coder-C", "Member",
                f"{_CODER_HINT}\nProvide your candidate implementation. Then critique the candidates from the other agents and propose a merged final.",
                topo_id, model)

    edges = [
        _edge("mesh-e1", a1.id, a2.id, EdgeType.BIDIRECTIONAL),
        _edge("mesh-e2", a1.id, a3.id, EdgeType.BIDIRECTIONAL),
        _edge("mesh-e3", a2.id, a3.id, EdgeType.BIDIRECTIONAL),
    ]

    topo = TopologyConfig(
        id=topo_id, type=TopologyType.MESH, name="Mesh (baseline)",
        agents=[a1.id, a2.id, a3.id], internal_edges=edges,
        max_turns=3, timeout=240, early_termination=False,
        start_agent_id=a1.id,
    )
    return topo, [a1, a2, a3]


def cycle_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "preset-cycle"
    coder = _agent("cyc-a1", "Coder", "Member",
                   f"{_CODER_HINT}\nRefine the implementation based on the previous critique. If you believe it is correct, prefix your reply with 'TASK COMPLETE:'.",
                   topo_id, model)
    critic = _agent("cyc-a2", "Critic", "Member",
                    f"{_CODER_HINT}\nIdentify bugs / missing edge cases in the current implementation. Then output your suggested fixes as a complete code block.",
                    topo_id, model)
    refiner = _agent("cyc-a3", "Refiner", "Member",
                     f"{_CODER_HINT}\nApply the critic's suggestions and produce an improved implementation.",
                     topo_id, model)

    edges = [
        _edge("cyc-e1", coder.id, critic.id, EdgeType.UNIDIRECTIONAL),
        _edge("cyc-e2", critic.id, refiner.id, EdgeType.UNIDIRECTIONAL),
        _edge("cyc-e3", refiner.id, coder.id, EdgeType.UNIDIRECTIONAL),
    ]

    topo = TopologyConfig(
        id=topo_id, type=TopologyType.CYCLE, name="Cycle (baseline)",
        agents=[coder.id, critic.id, refiner.id], internal_edges=edges,
        max_turns=3, timeout=240, early_termination=True,
        start_agent_id=coder.id,
    )
    return topo, [coder, critic, refiner]


PRESETS: dict[str, Callable[[str], tuple[TopologyConfig, list[AgentConfig]]]] = {
    "chain": chain_preset,
    "centralized": centralized_preset,
    "hierarchical": hierarchical_preset,
    "mesh": mesh_preset,
    "cycle": cycle_preset,
}


def get_preset(name: str, model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    """Return (topology, agents) for a named preset, using the given model on all agents."""
    if name not in PRESETS:
        raise ValueError(f"Unknown preset: {name}. Available: {list(PRESETS)}")
    return PRESETS[name](model)
