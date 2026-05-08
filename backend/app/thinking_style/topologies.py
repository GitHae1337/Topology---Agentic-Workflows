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


def _agent(agent_id: str, name: str, role: str, hint: str, topo_id: str, model: str) -> AgentConfig:
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
def sas_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-sas"
    a1 = _agent(
        "sas-a1", "Solo", "Solo",
        "You are the only agent. Plan the whole trip yourself end-to-end and "
        "output the final plan in the required format.",
        topo_id, model,
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
def independent_preset(model: str = DEFAULT_MODEL, n: int = N_WORKERS) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-independent"
    workers: list[AgentConfig] = []
    for i in range(n):
        workers.append(_agent(
            f"ind-w{i+1}", f"Worker-{i+1}", "Worker",
            f"You are Worker-{i+1} of {n}. You see only the user query (no other "
            f"workers' output). Produce a complete trip plan in the required "
            f"format independently.",
            topo_id, model,
        ))
    aggregator = _agent(
        "ind-agg", "Aggregator", "Aggregator",
        f"You receive the {n} workers' independent plans. Synthesize them into a "
        f"single final plan that satisfies every constraint, in the required "
        f"format. Do not invent items not present in the workers' outputs.",
        topo_id, model,
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
def centralized_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-centralized"
    leader = _agent(
        "cen-leader", "Leader", "Leader",
        "You are the orchestrator. Decompose the trip-planning task into subtasks "
        "and delegate to the members; review their outputs across rounds; finally "
        "synthesize the full plan in the required format.",
        topo_id, model,
    )
    m1 = _agent(
        "cen-m1", "Member-1", "Member",
        "You are Member-1. Handle the subtask the orchestrator assigns you "
        "(e.g. flights/transit). Return findings — not the full plan.",
        topo_id, model,
    )
    m2 = _agent(
        "cen-m2", "Member-2", "Member",
        "You are Member-2. Handle the subtask the orchestrator assigns you "
        "(e.g. accommodation/meals). Return findings — not the full plan.",
        topo_id, model,
    )
    edges = [
        _edge("cen-e1", leader.id, m1.id, EdgeType.BIDIRECTIONAL),
        _edge("cen-e2", leader.id, m2.id, EdgeType.BIDIRECTIONAL),
    ]
    topo = TopologyConfig(
        id=topo_id, type=TopologyType.CENTRALIZED, name="Centralized (PDF)",
        agents=[leader.id, m1.id, m2.id], internal_edges=edges,
        max_turns=3, timeout=300, early_termination=False,
    )
    return topo, [leader, m1, m2]


# ---------------------------------------------------------------------------
# 4. Decentralized — all-to-all debate (reuses MeshExecutor)
# ---------------------------------------------------------------------------
def decentralized_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-decentralized"
    a1 = _agent(
        "dec-a1", "Planner-A", "Member",
        "You are Planner-A. Round 1: propose your own complete plan. Round 2+: "
        "you see all peers' plans, critique them, and produce a refined plan. "
        "Final round: emit the consensus plan in the required format.",
        topo_id, model,
    )
    a2 = _agent(
        "dec-a2", "Planner-B", "Member",
        "You are Planner-B. Round 1: propose your own complete plan. Round 2+: "
        "you see all peers' plans, critique them, and produce a refined plan. "
        "Final round: emit the consensus plan in the required format.",
        topo_id, model,
    )
    a3 = _agent(
        "dec-a3", "Planner-C", "Member",
        "You are Planner-C. Round 1: propose your own complete plan. Round 2+: "
        "you see all peers' plans, critique them, and produce a refined plan. "
        "Final round: emit the consensus plan in the required format.",
        topo_id, model,
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
def hybrid_preset(model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    topo_id = "pdf-hybrid"
    manager = _agent(
        "hyb-mgr", "Manager", "Manager",
        "You are the manager of a hybrid team (orchestrator + lateral peer "
        "channel). Round 1: decompose the task and assign subtasks using lines "
        "like '[ASSIGN:Worker-1] <subtask>' and '[ASSIGN:Worker-2] <subtask>'. "
        "Round 2+: based on the workers' findings, either (a) reassign with "
        "[ASSIGN:...] again, (b) trigger lateral exchange between workers with "
        "'[PEER:Worker-1,Worker-2] <discussion focus>', or (c) finalize by "
        "emitting '[FINAL SYNTHESIS]' followed by the complete plan in the "
        "required output format.",
        topo_id, model,
    )
    w1 = _agent(
        "hyb-w1", "Worker-1", "Worker",
        "You are Worker-1. Execute the manager's [ASSIGN] subtask. When the "
        "manager initiates a [PEER:Worker-1,Worker-2] round, exchange "
        "intermediate findings with Worker-2 to coordinate constraints.",
        topo_id, model,
    )
    w2 = _agent(
        "hyb-w2", "Worker-2", "Worker",
        "You are Worker-2. Execute the manager's [ASSIGN] subtask. When the "
        "manager initiates a [PEER:Worker-1,Worker-2] round, exchange "
        "intermediate findings with Worker-1 to coordinate constraints.",
        topo_id, model,
    )
    edges = [
        _edge("hyb-e1", manager.id, w1.id, EdgeType.BIDIRECTIONAL),
        _edge("hyb-e2", manager.id, w2.id, EdgeType.BIDIRECTIONAL),
        _edge("hyb-e3", w1.id, w2.id, EdgeType.BIDIRECTIONAL),  # lateral peer edge
    ]
    topo = TopologyConfig(
        id=topo_id, type=TopologyType.HIERARCHICAL, name="Hybrid (PDF)",
        agents=[manager.id, w1.id, w2.id], internal_edges=edges,
        max_turns=3, timeout=360, early_termination=False,
    )
    return topo, [manager, w1, w2]


PDF_PRESETS: dict[str, Callable[..., tuple[TopologyConfig, list[AgentConfig]]]] = {
    "sas": sas_preset,
    "independent": independent_preset,
    "centralized": centralized_preset,
    "decentralized": decentralized_preset,
    "hybrid": hybrid_preset,
}


def get_preset(name: str, model: str = DEFAULT_MODEL) -> tuple[TopologyConfig, list[AgentConfig]]:
    """Return (topology, agents) for one of the 5 PDF topology presets."""
    key = name.lower()
    if key not in PDF_PRESETS:
        raise ValueError(f"Unknown PDF preset: {name}. Available: {list(PDF_PRESETS)}")
    return PDF_PRESETS[key](model)
