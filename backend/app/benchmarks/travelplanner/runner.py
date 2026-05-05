"""TravelPlanner benchmark runner.

Mirrors `backend/app/benchmarks/runner.py` (the GSM8K/AQuA/MMLU-Pro path) so
the CLI can dispatch on `--benchmark travelplanner` without exposing two
different APIs. The differences from the simple-answer benchmarks:

  - Per-trial outcome is a metric dict (4 metrics) instead of a single bool.
    `correct` is set to `final_pass` for backward compatibility with the
    common BenchmarkAggregate JSON schema.
  - The 5-topology baselines reuse `build_topology()` from the simple runner
    via the `system_hint` override added for this domain.
  - Plan parsing happens here (LLM text → list[dict]).
"""
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ..runner import build_topology  # 5-topology baseline factory (with system_hint param)
from ...engine.topologies import get_executor
from ...models.agent import AgentConfig
from ...models.topology import TopologyConfig

from .dataset import TravelPlannerProblem, load_problems
from .evaluator import evaluate_one
from .parser import parse_plan
from .prompts import SYSTEM_PROMPT, build_user_input


@dataclass
class TravelPlannerTrialRecord:
    task_id: str
    topology_name: str
    correct: bool                       # final_pass (for cross-benchmark JSON compat)
    metrics: dict                       # full 4-metric breakdown
    duration_seconds: float
    message_count: int
    final_output: str
    parsed_plan: Optional[list]         # list[dict] | None (None = delivery failure)
    messages: Optional[list] = None


@dataclass
class TravelPlannerAggregate:
    benchmark: str
    topology_name: str
    n_problems: int
    n_correct: int                          # = sum(final_pass)
    accuracy: float                         # = final_pass_rate over this slice
    delivery_rate: float
    commonsense_pass_rate: float            # macro: 8개 다 통과한 plan 비율
    commonsense_micro_pass_rate: float      # micro: 통과 항목 / 평가 항목 (None 제외)
    hard_pass_rate: float                   # macro: 5개 다 통과한 plan 비율
    hard_micro_pass_rate: float             # micro: 통과 항목 / 평가 항목 (None 제외)
    final_pass_rate: float                  # = accuracy (13개 다 통과 plan 비율)
    total_duration_seconds: float
    trials: list[TravelPlannerTrialRecord] = field(default_factory=list)


async def run_one_with_explicit_topology(
    topology: TopologyConfig,
    agents: list[AgentConfig],
    problem: TravelPlannerProblem,
    save_trace: bool,
    record_topology_name: Optional[str] = None,
) -> TravelPlannerTrialRecord:
    """Phase 2 entry: run a caller-supplied (topology, agents) on one query.

    The participant-built workflow may not have the TravelPlanner system
    prompt baked into agent.instructions; we don't override that here — what
    the participant authored is what gets evaluated.
    """
    agents_dict = {a.id: a for a in agents}
    executor = get_executor(topology.type.value)
    label = record_topology_name or topology.type.value

    user_input = build_user_input(problem.query, problem.reference_information)

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
    plan = parse_plan(final_output)

    query_data = problem.model_dump()
    metrics = evaluate_one(query_data, plan)

    print(
        f"[travelplanner.runner] {label}/{problem.task_id}: "
        f"delivery={metrics['delivery']} cs_macro={metrics['commonsense_pass_macro']} "
        f"hd_macro={metrics['hard_pass_macro']} final={metrics['final_pass']} "
        f"msgs={len(messages)} duration={duration:.1f}s"
    )

    return TravelPlannerTrialRecord(
        task_id=problem.task_id,
        topology_name=label,
        correct=metrics["final_pass"],
        metrics=metrics,
        duration_seconds=round(duration, 3),
        message_count=len(messages),
        final_output=final_output,
        parsed_plan=plan,
        messages=[m.model_dump(mode="json") for m in messages] if save_trace else None,
    )


async def run_one(
    topology_name: str,
    problem: TravelPlannerProblem,
    model: str,
    K: int,
    save_trace: bool,
) -> TravelPlannerTrialRecord:
    """Phase 1 entry: build the named TravelPlanner baseline and run one trial."""
    topology, agents = build_topology(topology_name, model, K, system_hint=SYSTEM_PROMPT)
    return await run_one_with_explicit_topology(
        topology=topology,
        agents=agents,
        problem=problem,
        save_trace=save_trace,
        record_topology_name=topology_name,
    )


async def run_topology_on_benchmark(
    bench_name: str,                    # always "travelplanner" — kept for CLI symmetry
    topology_name: str,
    problems: list[TravelPlannerProblem],
    output_dir: Path,
    model: str,
    K: int,
    save_traces: bool,
) -> TravelPlannerAggregate:
    """Run one topology over a list of TravelPlanner problems and dump results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    agg = TravelPlannerAggregate(
        benchmark=bench_name,
        topology_name=topology_name,
        n_problems=len(problems),
        n_correct=0,
        accuracy=0.0,
        delivery_rate=0.0,
        commonsense_pass_rate=0.0,
        commonsense_micro_pass_rate=0.0,
        hard_pass_rate=0.0,
        hard_micro_pass_rate=0.0,
        final_pass_rate=0.0,
        total_duration_seconds=0.0,
    )

    delivery_count = 0
    cs_count = 0          # macro numerator (8개 다 통과한 plan 수)
    hd_count = 0          # macro numerator (5개 다 통과한 plan 수)
    final_count = 0       # 13개 다 통과한 plan 수

    cs_micro_pass = 0     # commonsense 항목 통과 인스턴스 수
    cs_micro_total = 0    # commonsense 항목 평가 인스턴스 수 (None 제외)
    hd_micro_pass = 0
    hd_micro_total = 0

    for problem in problems:
        record = await run_one(topology_name, problem, model, K, save_traces)
        agg.trials.append(record)
        agg.total_duration_seconds += record.duration_seconds
        m = record.metrics
        delivery_count += int(m["delivery"])
        cs_count += int(m["commonsense_pass_macro"])
        hd_count += int(m["hard_pass_macro"])
        final_count += int(m["final_pass"])

        # Per-item micro accumulation. None means "not applicable for this
        # query" (e.g. hard constraints the user didn't specify) — exclude
        # from both numerator and denominator. Matches eval.py behavior.
        cs_per = m.get("commonsense_per_item") or {}
        for _key, item in cs_per.items():
            passed = item[0] if isinstance(item, list) else item
            if passed is None:
                continue
            cs_micro_total += 1
            cs_micro_pass += int(bool(passed))

        hd_per = m.get("hard_per_item") or {}
        for _key, item in hd_per.items():
            passed = item[0] if isinstance(item, list) else item
            if passed is None:
                continue
            hd_micro_total += 1
            hd_micro_pass += int(bool(passed))

    n = max(agg.n_problems, 1)
    agg.delivery_rate = delivery_count / n
    agg.commonsense_pass_rate = cs_count / n
    agg.hard_pass_rate = hd_count / n
    agg.final_pass_rate = final_count / n
    agg.n_correct = final_count
    agg.accuracy = agg.final_pass_rate
    agg.commonsense_micro_pass_rate = cs_micro_pass / max(cs_micro_total, 1)
    agg.hard_micro_pass_rate = hd_micro_pass / max(hd_micro_total, 1)

    out_path = output_dir / f"results_{topology_name}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(_agg_to_dict(agg), f, indent=2, ensure_ascii=False)
    print(
        f"[travelplanner.runner] {topology_name} done: "
        f"delivery={agg.delivery_rate:.3f}  "
        f"cs_macro={agg.commonsense_pass_rate:.3f}  cs_micro={agg.commonsense_micro_pass_rate:.3f}  "
        f"hd_macro={agg.hard_pass_rate:.3f}  hd_micro={agg.hard_micro_pass_rate:.3f}  "
        f"final={agg.final_pass_rate:.3f}  → {out_path}"
    )
    return agg


def _agg_to_dict(agg: TravelPlannerAggregate) -> dict:
    return {
        **{k: v for k, v in asdict(agg).items() if k != "trials"},
        "trials": [asdict(t) for t in agg.trials],
    }


async def run_benchmark(
    bench_name: str,
    topology_names: list[str],
    problems: list[TravelPlannerProblem],
    output_dir: Path,
    model: str,
    K: int,
    save_traces: bool,
) -> dict[str, TravelPlannerAggregate]:
    """Run multiple topologies sequentially over the same problem set."""
    results: dict[str, TravelPlannerAggregate] = {}
    for name in topology_names:
        results[name] = await run_topology_on_benchmark(
            bench_name, name, problems, output_dir, model, K, save_traces,
        )
    return results
