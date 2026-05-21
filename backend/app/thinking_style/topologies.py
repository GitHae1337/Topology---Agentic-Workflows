"""PDF 5-topology presets for the thinking-style x topology study.

Maps the formal definitions in arXiv:2512.08296 (SAS, Independent, Centralized,
Decentralized, Hybrid) to (TopologyConfig, list[AgentConfig]) pairs that the
matrix runner can hand to existing or new executors.

All agents use the TravelPlanner SYSTEM_PROMPT as a domain prefix, then a
role-specific hint that shapes their behaviour inside the topology. Agent count
is fixed at n=3 workers per Q6 (plus an orchestrator/aggregator where the
topology calls for one).
"""
from typing import Callable

from ..models.topology import TopologyConfig, TopologyType, InternalEdge, EdgeType
from ..models.agent import AgentConfig
from ..benchmarks.travelplanner.prompts import SYSTEM_PROMPT


DEFAULT_MODEL = "gpt-5"
N_WORKERS = 3


def _agent(agent_id: str, name: str, role: str, hint: str, topo_id: str, model: str, temperature: float = 0.7, reasoning_effort: str = "minimal") -> AgentConfig:
    """Compose a TravelPlanner-aware AgentConfig.

    The system prompt = TravelPlanner SYSTEM_PROMPT + a one-paragraph role hint
    that specialises the agent inside its topology.
    """
    instructions = f"{SYSTEM_PROMPT}\n\n[ROLE]\n{hint}"
    return AgentConfig(
        id=agent_id,
        name=name,
        instructions=instructions,
        model=model,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        topology_id=topo_id,
        topology_role=role,
    )


def _edge(edge_id: str, src: str, dst: str, edge_type: EdgeType) -> InternalEdge:
    return InternalEdge(
        id=edge_id,
        **{"from": src, "to": dst, "type": edge_type.value},
    )


# ---------------------------------------------------------------------------
# 1. SAS — single agent, |A|=1, monolithic loop
# ---------------------------------------------------------------------------
def sas_preset(model: str = DEFAULT_MODEL, temperature: float = 0.7, reasoning_effort: str = "minimal") -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-sas"
    a1 = _agent(
        "sas-a1", "Solo", "Solo",
        "You are the only agent. Plan the whole trip yourself end-to-end and "
        "output the final plan in the required format.",
        topo_id, model, temperature, reasoning_effort,
    )
    topo = TopologyConfig(
        id=topo_id, type=TopologyType.SAS, name="SAS (PDF)",
        agents=[a1.id], internal_edges=[],
        max_turns=1, timeout=240, early_termination=False,
        start_agent_id=a1.id,
    )
    return topo, [a1]


# ---------------------------------------------------------------------------
# 2. Independent — N parallel workers, no inter-agent edges, LLM aggregator
# ---------------------------------------------------------------------------
def independent_preset(model: str = DEFAULT_MODEL, n: int = N_WORKERS, temperature: float = 0.7, reasoning_effort: str = "minimal") -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-independent"
    workers: list[AgentConfig] = []
    for i in range(n):
        workers.append(_agent(
            f"ind-w{i+1}", f"Worker-{i+1}", "Worker",
            f"You are Worker-{i+1} of {n}. You see only the user query (no other "
            f"workers' output). Produce a complete trip plan in the required "
            f"format independently.",
            topo_id, model, temperature, reasoning_effort,
        ))
    aggregator = _agent(
        "ind-agg", "Aggregator", "Aggregator",
        f"You receive the {n} workers' independent plans. Synthesize them into a "
        f"single final plan that satisfies every constraint, in the required "
        f"format. Do not invent items not present in the workers' outputs.",
        topo_id, model, temperature, reasoning_effort,
    )

    topo = TopologyConfig(
        id=topo_id, type=TopologyType.INDEPENDENT, name="Independent (PDF)",
        agents=[w.id for w in workers] + [aggregator.id],
        internal_edges=[],
        max_turns=1, timeout=300, early_termination=False,
        start_agent_id=aggregator.id,
    )
    return topo, workers + [aggregator]


# ---------------------------------------------------------------------------
# 3. Centralized — orchestrator-to-workers star (reuses CentralizedExecutor)
# ---------------------------------------------------------------------------
def centralized_preset(model: str = DEFAULT_MODEL, temperature: float = 0.7, reasoning_effort: str = "minimal") -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-centralized"
    leader = _agent(
        "cen-leader", "Leader", "Leader",
        "You are the orchestrator coordinating Member-1, Member-2, Member-3. "
        "Decompose the trip-planning task into focused subtasks and assign "
        "each to a member with '[ASSIGN:Member-i] <subtask>'. Across rounds "
        "you may: (a) refine a member's previous output by reassigning them, "
        "(b) if cross-member context would help, relay one member's findings "
        "to another with a follow-up subtask (e.g., 'Given the flight arrival "
        "at 14:46 from Member-1, find a hotel with check-in available that "
        "afternoon'), (c) request a constraint check across partial results, "
        "or (d) finalize by synthesizing all members' outputs into the "
        "complete plan in the required output format that satisfies all "
        "task constraints. If the synthesized plan violates a constraint, "
        "reassign a refined subtask to the relevant member before finalizing.",
        topo_id, model, temperature, reasoning_effort,
    )
    m1 = _agent(
        "cen-m1", "Member-1", "Member",
        "You are Member-1. Handle the subtask the orchestrator assigns you "
        "and return focused findings for that subtask.",
        topo_id, model, temperature, reasoning_effort,
    )
    m2 = _agent(
        "cen-m2", "Member-2", "Member",
        "You are Member-2. Handle the subtask the orchestrator assigns you "
        "and return focused findings for that subtask.",
        topo_id, model, temperature, reasoning_effort,
    )
    m3 = _agent(
        "cen-m3", "Member-3", "Member",
        "You are Member-3. Handle the subtask the orchestrator assigns you "
        "and return focused findings for that subtask.",
        topo_id, model, temperature, reasoning_effort,
    )
    edges = [
        _edge("cen-e1", leader.id, m1.id, EdgeType.BIDIRECTIONAL),
        _edge("cen-e2", leader.id, m2.id, EdgeType.BIDIRECTIONAL),
        _edge("cen-e3", leader.id, m3.id, EdgeType.BIDIRECTIONAL),
    ]
    topo = TopologyConfig(
        id=topo_id, type=TopologyType.CENTRALIZED, name="Centralized (PDF)",
        agents=[leader.id, m1.id, m2.id, m3.id], internal_edges=edges,
        max_turns=3, timeout=300, early_termination=False,
    )
    return topo, [leader, m1, m2, m3]


# ---------------------------------------------------------------------------
# 4. Decentralized — all-to-all debate (reuses MeshExecutor)
# ---------------------------------------------------------------------------
def decentralized_preset(model: str = DEFAULT_MODEL, temperature: float = 0.7, reasoning_effort: str = "minimal") -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-decentralized"
    a1 = _agent(
        "dec-a1", "Planner-A", "Member",
        "You are Planner-A. Round 1: propose your own complete plan. Round 2+: "
        "you see all peers' plans, critique them, and produce a refined plan. "
        "Final round: emit the consensus plan in the required format.",
        topo_id, model, temperature, reasoning_effort,
    )
    a2 = _agent(
        "dec-a2", "Planner-B", "Member",
        "You are Planner-B. Round 1: propose your own complete plan. Round 2+: "
        "you see all peers' plans, critique them, and produce a refined plan. "
        "Final round: emit the consensus plan in the required format.",
        topo_id, model, temperature, reasoning_effort,
    )
    a3 = _agent(
        "dec-a3", "Planner-C", "Member",
        "You are Planner-C. Round 1: propose your own complete plan. Round 2+: "
        "you see all peers' plans, critique them, and produce a refined plan. "
        "Final round: emit the consensus plan in the required format.",
        topo_id, model, temperature, reasoning_effort,
    )
    edges = [
        _edge("dec-e1", a1.id, a2.id, EdgeType.BIDIRECTIONAL),
        _edge("dec-e2", a1.id, a3.id, EdgeType.BIDIRECTIONAL),
        _edge("dec-e3", a2.id, a3.id, EdgeType.BIDIRECTIONAL),
    ]
    topo = TopologyConfig(
        id=topo_id, type=TopologyType.MESH, name="Decentralized (PDF)",
        agents=[a1.id, a2.id, a3.id], internal_edges=edges,
        max_turns=3, timeout=360, early_termination=False,
        start_agent_id=a1.id,
    )
    return topo, [a1, a2, a3]


# ---------------------------------------------------------------------------
# 5. Hybrid — orchestrator hierarchy + lateral peer edges between workers
# ---------------------------------------------------------------------------
def hybrid_preset(model: str = DEFAULT_MODEL, temperature: float = 0.7, reasoning_effort: str = "minimal") -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-hybrid"
    manager = _agent(
        "hyb-mgr", "Manager", "Manager",
        "You are the manager of a hybrid team coordinating Worker-1, "
        "Worker-2, Worker-3 with a lateral peer channel. Decompose the "
        "trip-planning task into focused subtasks and assign each to a "
        "worker with '[ASSIGN:Worker-i] <subtask>'. Across rounds you may: "
        "(a) refine a worker's previous output by reassigning them, "
        "(b) if cross-worker context would help, relay one worker's "
        "findings to another with a follow-up subtask (e.g., 'Given the "
        "flight arrival at 14:46 from Worker-1, find a hotel with check-in "
        "available that afternoon'), (c) if direct coordination is needed, "
        "trigger lateral exchange between two or more workers with "
        "'[PEER:Worker-i,Worker-j,...] <focus>' (e.g., reconcile flight "
        "arrival with hotel check-in), or (d) finalize with '[FINAL "
        "SYNTHESIS]' followed by the complete plan in the required output "
        "format that satisfies all task constraints. If the synthesized "
        "plan violates a constraint, reassign a refined subtask to the "
        "relevant worker before finalizing.",
        topo_id, model, temperature, reasoning_effort,
    )
    w1 = _agent(
        "hyb-w1", "Worker-1", "Worker",
        "You are Worker-1. Handle the subtask the manager assigns you and "
        "return focused findings for that subtask. When the manager "
        "initiates a [PEER:Worker-i,Worker-j,...] round that lists you, "
        "exchange intermediate findings with the other listed workers to "
        "coordinate constraints.",
        topo_id, model, temperature, reasoning_effort,
    )
    w2 = _agent(
        "hyb-w2", "Worker-2", "Worker",
        "You are Worker-2. Handle the subtask the manager assigns you and "
        "return focused findings for that subtask. When the manager "
        "initiates a [PEER:Worker-i,Worker-j,...] round that lists you, "
        "exchange intermediate findings with the other listed workers to "
        "coordinate constraints.",
        topo_id, model, temperature, reasoning_effort,
    )
    w3 = _agent(
        "hyb-w3", "Worker-3", "Worker",
        "You are Worker-3. Handle the subtask the manager assigns you and "
        "return focused findings for that subtask. When the manager "
        "initiates a [PEER:Worker-i,Worker-j,...] round that lists you, "
        "exchange intermediate findings with the other listed workers to "
        "coordinate constraints.",
        topo_id, model, temperature, reasoning_effort,
    )
    edges = [
        _edge("hyb-e1", manager.id, w1.id, EdgeType.BIDIRECTIONAL),
        _edge("hyb-e2", manager.id, w2.id, EdgeType.BIDIRECTIONAL),
        _edge("hyb-e3", manager.id, w3.id, EdgeType.BIDIRECTIONAL),
        _edge("hyb-e4", w1.id, w2.id, EdgeType.BIDIRECTIONAL),  # lateral peer edges
        _edge("hyb-e5", w1.id, w3.id, EdgeType.BIDIRECTIONAL),
        _edge("hyb-e6", w2.id, w3.id, EdgeType.BIDIRECTIONAL),
    ]
    topo = TopologyConfig(
        id=topo_id, type=TopologyType.HIERARCHICAL, name="Hybrid (PDF)",
        agents=[manager.id, w1.id, w2.id, w3.id], internal_edges=edges,
        max_turns=3, timeout=360, early_termination=False,
    )
    return topo, [manager, w1, w2, w3]


PDF_PRESETS: dict[str, Callable[..., tuple[TopologyConfig, list[AgentConfig]]]] = {
    "sas": sas_preset,
    "independent": independent_preset,
    "centralized": centralized_preset,
    "decentralized": decentralized_preset,
    "hybrid": hybrid_preset,
}


def get_preset(name: str, model: str = DEFAULT_MODEL, temperature: float = 0.7, reasoning_effort: str = "minimal") -> tuple[TopologyConfig, list[AgentConfig]]:
    """Return (topology, agents) for one of the 5 PDF topology presets."""
    key = name.lower()
    if key not in PDF_PRESETS:
        raise ValueError(f"Unknown PDF preset: {name}. Available: {list(PDF_PRESETS)}")
    return PDF_PRESETS[key](model=model, temperature=temperature, reasoning_effort=reasoning_effort)
