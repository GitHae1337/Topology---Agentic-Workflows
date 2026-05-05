"""Generic benchmark runner: 5-topology baselines × N problems.

Topology baselines are defined inline (no humaneval/presets dependency) so
the only domain-specific bits are dataset loading and answer extraction.

Per-trial output: TrialRecord. Per-(benchmark × topology) output:
    Log/benchmarks/<bench>/<datetime>/results_<topology>.json
"""
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ..engine.topologies import get_executor
from ..models.agent import AgentConfig
from ..models.topology import EdgeType, InternalEdge, TopologyConfig, TopologyType

from .datasets import BenchmarkProblem
from .extractors import EXTRACTORS, FORMAT_HINTS, score


GENERIC_AGENT_HINT = (
    "You are a careful reasoning agent. Solve the given problem step by step "
    "with brief justification, then state the final answer in the requested "
    "format. Always preserve any '#### ...' final-answer line."
)


@dataclass
class TrialRecord:
    """One topology × one problem outcome."""
    task_id: str
    topology_name: str
    expected: str
    extracted: Optional[str]
    correct: bool
    duration_seconds: float
    message_count: int
    final_output: str
    messages: Optional[list] = None  # populated only when save_traces=True


@dataclass
class BenchmarkAggregate:
    """Aggregate stats for one (benchmark, topology) pair."""
    benchmark: str
    topology_name: str
    n_problems: int
    n_correct: int
    accuracy: float
    total_duration_seconds: float
    trials: list[TrialRecord] = field(default_factory=list)


# ---------- topology baselines (3-agent each, K = topology.max_turns) ----------

def _agent(aid: str, name: str, role: Optional[str], instr: str, topo_id: str, model: str) -> AgentConfig:
    return AgentConfig(
        id=aid, name=name, instructions=instr, model=model,
        topology_id=topo_id, topology_role=role,
    )


def _edge(eid: str, src: str, dst: str, etype: EdgeType) -> InternalEdge:
    return InternalEdge(id=eid, **{"from": src, "to": dst, "type": etype.value})


def build_topology(
    name: str,
    model: str,
    K: int,
    system_hint: str = GENERIC_AGENT_HINT,
) -> tuple[TopologyConfig, list[AgentConfig]]:
    """Return (topology, agents) for the named 5-topology baseline.

    system_hint is the per-agent system instruction. Defaults to the generic
    GSM8K/AQuA/MMLU-Pro reasoning hint; benchmarks that need a different
    output format (e.g. TravelPlanner's strict plan schema) pass their own.
    """
    topo_id = f"bench-{name}"

    if name == "chain":
        agents = [
            _agent("ag1", "Solver1", None, system_hint, topo_id, model),
            _agent("ag2", "Solver2", None, system_hint, topo_id, model),
            _agent("ag3", "Solver3", None, system_hint, topo_id, model),
        ]
        edges = [
            _edge("e1", "ag1", "ag2", EdgeType.UNIDIRECTIONAL),
            _edge("e2", "ag2", "ag3", EdgeType.UNIDIRECTIONAL),
        ]
        return TopologyConfig(
            id=topo_id, type=TopologyType.CHAIN, name="Chain",
            agents=["ag1", "ag2", "ag3"], internal_edges=edges,
            max_turns=K, timeout=300, early_termination=False,
        ), agents

    if name == "centralized":
        agents = [
            _agent("ag1", "Leader", "Leader",
                   system_hint + " You orchestrate sub-agents.", topo_id, model),
            _agent("ag2", "Member-1", "Member", system_hint, topo_id, model),
            _agent("ag3", "Member-2", "Member", system_hint, topo_id, model),
        ]
        edges = [
            _edge("e1", "ag1", "ag2", EdgeType.BIDIRECTIONAL),
            _edge("e2", "ag1", "ag3", EdgeType.BIDIRECTIONAL),
        ]
        return TopologyConfig(
            id=topo_id, type=TopologyType.CENTRALIZED, name="Centralized",
            agents=["ag1", "ag2", "ag3"], internal_edges=edges,
            max_turns=K, timeout=300, early_termination=False,
        ), agents

    if name == "hierarchical":
        agents = [
            _agent("ag1", "Manager", "Manager",
                   system_hint + " You manage workers.", topo_id, model),
            _agent("ag2", "Worker-1", "Worker", system_hint, topo_id, model),
            _agent("ag3", "Worker-2", "Worker", system_hint, topo_id, model),
        ]
        edges = [
            _edge("e1", "ag1", "ag2", EdgeType.BIDIRECTIONAL),
            _edge("e2", "ag1", "ag3", EdgeType.BIDIRECTIONAL),
        ]
        return TopologyConfig(
            id=topo_id, type=TopologyType.HIERARCHICAL, name="Hierarchical",
            agents=["ag1", "ag2", "ag3"], internal_edges=edges,
            max_turns=K, timeout=300, early_termination=False,
        ), agents

    if name == "mesh":
        agents = [
            _agent(f"ag{i}", f"Solver{i}", "Member", system_hint, topo_id, model)
            for i in range(1, 4)
        ]
        edges = [
            _edge("e1", "ag1", "ag2", EdgeType.BIDIRECTIONAL),
            _edge("e2", "ag2", "ag3", EdgeType.BIDIRECTIONAL),
            _edge("e3", "ag1", "ag3", EdgeType.BIDIRECTIONAL),
        ]
        return TopologyConfig(
            id=topo_id, type=TopologyType.MESH, name="Mesh",
            agents=["ag1", "ag2", "ag3"], internal_edges=edges,
            max_turns=K, timeout=300, early_termination=False,
            start_agent_id="ag1",
        ), agents

    if name == "cycle":
        agents = [
            _agent("ag1", "Coder", "Member",
                   system_hint + " Produce or refine the candidate solution.", topo_id, model),
            _agent("ag2", "Critic", "Member",
                   system_hint + " Critique gaps and edge cases.", topo_id, model),
            _agent("ag3", "Refiner", "Member",
                   system_hint + " Apply the critique and refine.", topo_id, model),
        ]
        edges = [
            _edge("e1", "ag1", "ag2", EdgeType.UNIDIRECTIONAL),
            _edge("e2", "ag2", "ag3", EdgeType.UNIDIRECTIONAL),
            _edge("e3", "ag3", "ag1", EdgeType.UNIDIRECTIONAL),
        ]
        return TopologyConfig(
            id=topo_id, type=TopologyType.CYCLE, name="Cycle",
            agents=["ag1", "ag2", "ag3"], internal_edges=edges,
            max_turns=K, timeout=300, early_termination=False,
            start_agent_id="ag1",
        ), agents

    raise ValueError(f"Unknown topology: {name}")


# ---------- core run loop ----------

async def run_one_with_explicit_topology(
    bench_name: str,
    topology: TopologyConfig,
    agents: list[AgentConfig],
    problem: BenchmarkProblem,
    save_trace: bool,
    record_topology_name: Optional[str] = None,
) -> TrialRecord:
    """Run one trial against a caller-supplied (topology, agents).

    Used by Phase 2: workflow_adapter pulls a participant-built workflow out
    of workflows.db and feeds it here. record_topology_name is the label that
    goes into the TrialRecord (defaults to topology.type.value so Phase 2
    records can be grouped by classifier label).
    """
    agents_dict = {a.id: a for a in agents}
    executor = get_executor(topology.type.value)
    label = record_topology_name or topology.type.value

    user_input = f"{problem.question}\n\n{FORMAT_HINTS[bench_name]}"

    started = time.perf_counter()
    messages = []
    async for msg in executor.execute(
        topology=topology,
        agents=agents_dict,
        input_message=user_input,
        conversation_history=None,
    ):
        messages.append(msg)
    duration = time.perf_counter() - started

    final_output = messages[-1].content if messages else ""
    extracted = EXTRACTORS[bench_name](final_output)
    correct = score(extracted, problem.answer)

    print(f"[runner] {label}/{problem.task_id}: "
          f"correct={correct}  extracted={extracted!r}  expected={problem.answer!r}  "
          f"msgs={len(messages)}  duration={duration:.1f}s")

    return TrialRecord(
        task_id=problem.task_id,
        topology_name=label,
        expected=problem.answer,
        extracted=extracted,
        correct=correct,
        duration_seconds=round(duration, 3),
        message_count=len(messages),
        final_output=final_output,
        messages=[m.model_dump(mode="json") for m in messages] if save_trace else None,
    )


async def run_one(
    bench_name: str,
    topology_name: str,
    problem: BenchmarkProblem,
    model: str,
    K: int,
    save_trace: bool,
) -> TrialRecord:
    """Phase 1 entry: build the named 5-topology baseline and run one trial."""
    topology, agents = build_topology(topology_name, model, K)
    return await run_one_with_explicit_topology(
        bench_name=bench_name,
        topology=topology,
        agents=agents,
        problem=problem,
        save_trace=save_trace,
        record_topology_name=topology_name,
    )


async def run_topology_on_benchmark(
    bench_name: str,
    topology_name: str,
    problems: list[BenchmarkProblem],
    output_dir: Path,
    model: str,
    K: int,
    save_traces: bool,
) -> BenchmarkAggregate:
    """Run one topology over a list of problems and dump JSON results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    agg = BenchmarkAggregate(
        benchmark=bench_name,
        topology_name=topology_name,
        n_problems=len(problems),
        n_correct=0,
        accuracy=0.0,
        total_duration_seconds=0.0,
    )

    for problem in problems:
        record = await run_one(bench_name, topology_name, problem, model, K, save_traces)
        agg.trials.append(record)
        agg.n_correct += int(record.correct)
        agg.total_duration_seconds += record.duration_seconds

    agg.accuracy = agg.n_correct / max(agg.n_problems, 1)

    out_path = output_dir / f"results_{topology_name}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(_agg_to_dict(agg), f, indent=2, ensure_ascii=False)
    print(f"[runner] {topology_name} done: "
          f"{agg.n_correct}/{agg.n_problems} = {agg.accuracy:.3f} → {out_path}")

    return agg


def _agg_to_dict(agg: BenchmarkAggregate) -> dict:
    return {
        **{k: v for k, v in asdict(agg).items() if k != "trials"},
        "trials": [asdict(t) for t in agg.trials],
    }


async def run_benchmark(
    bench_name: str,
    topology_names: list[str],
    problems: list[BenchmarkProblem],
    output_dir: Path,
    model: str,
    K: int,
    save_traces: bool,
) -> dict[str, BenchmarkAggregate]:
    """Run multiple topologies sequentially over the same problem set."""
    results: dict[str, BenchmarkAggregate] = {}
    for name in topology_names:
        results[name] = await run_topology_on_benchmark(
            bench_name, name, problems, output_dir, model, K, save_traces,
        )
    return results
