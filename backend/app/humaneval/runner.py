"""
HumanEval Phase 1 runner: orchestrates topology executor x dataset x sandbox.

Output: a list of per-problem TrialRecord and an aggregate summary, written
as JSON to a results directory the caller specifies.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from ..engine.topologies import get_executor
from ..models.topology import TopologyConfig
from ..models.agent import AgentConfig

from .dataset import HumanEvalProblem, load_problems
from .sandbox import run_humaneval_sandbox, SandboxResult
from .cost_tracker import start_collection, stop_collection, UsageBucket


_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(response: str) -> str:
    """Pull the last ```python ... ``` block from a model response. Falls back to the raw text."""
    matches = _CODE_BLOCK_RE.findall(response)
    if matches:
        return matches[-1].strip()
    return response.strip()


@dataclass
class TrialRecord:
    """One topology x one problem outcome."""
    task_id: str
    preset_name: str
    passed: bool
    timed_out: bool
    error_message: str
    final_code: str
    duration_seconds: float
    call_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    message_count: int


@dataclass
class TopologyAggregate:
    """Aggregate stats across all problems for a single topology preset."""
    preset_name: str
    n_problems: int
    n_passed: int
    pass_at_1: float
    n_timeouts: int
    total_duration_seconds: float
    total_call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    trials: list[TrialRecord] = field(default_factory=list)


async def run_topology_on_problem(
    topology: TopologyConfig,
    agents: list[AgentConfig],
    problem: HumanEvalProblem,
    preset_name: str,
) -> TrialRecord:
    """Execute a single (topology, problem) pair end-to-end."""
    print(f"[runner] starting {preset_name} on {problem.task_id}")

    bucket: UsageBucket = start_collection()
    started = time.perf_counter()

    executor = get_executor(topology.type.value)
    agents_dict = {a.id: a for a in agents}

    messages = []
    async for msg in executor.execute(
        topology=topology,
        agents=agents_dict,
        input_message=problem.prompt,
        conversation_history=None,
    ):
        messages.append(msg)

    duration = time.perf_counter() - started
    stop_collection()

    final_response = messages[-1].content if messages else ""
    final_code = extract_code(final_response)

    print(f"[runner] {problem.task_id}: {len(messages)} messages, {bucket.call_count} llm calls, {duration:.1f}s")

    sandbox_result: SandboxResult = run_humaneval_sandbox(
        candidate_code=final_code,
        test_code=problem.test,
        entry_point=problem.entry_point,
    )

    return TrialRecord(
        task_id=problem.task_id,
        preset_name=preset_name,
        passed=sandbox_result.passed,
        timed_out=sandbox_result.timed_out,
        error_message=sandbox_result.error_message,
        final_code=final_code,
        duration_seconds=round(duration, 3),
        call_count=bucket.call_count,
        input_tokens=bucket.total_input_tokens,
        output_tokens=bucket.total_output_tokens,
        total_tokens=bucket.total_tokens,
        message_count=len(messages),
    )


async def run_preset_on_dataset(
    preset_name: str,
    topology: TopologyConfig,
    agents: list[AgentConfig],
    problems: list[HumanEvalProblem],
    output_dir: Path,
    progress_every: int = 1,
) -> TopologyAggregate:
    """Run a single topology preset over the given problems and write JSON results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    aggregate = TopologyAggregate(
        preset_name=preset_name,
        n_problems=len(problems),
        n_passed=0,
        pass_at_1=0.0,
        n_timeouts=0,
        total_duration_seconds=0.0,
        total_call_count=0,
        total_input_tokens=0,
        total_output_tokens=0,
        total_tokens=0,
    )

    for idx, problem in enumerate(problems):
        record = await run_topology_on_problem(topology, agents, problem, preset_name)
        aggregate.trials.append(record)
        aggregate.n_passed += int(record.passed)
        aggregate.n_timeouts += int(record.timed_out)
        aggregate.total_duration_seconds += record.duration_seconds
        aggregate.total_call_count += record.call_count
        aggregate.total_input_tokens += record.input_tokens
        aggregate.total_output_tokens += record.output_tokens
        aggregate.total_tokens += record.total_tokens

        if (idx + 1) % progress_every == 0:
            print(f"[runner] progress {preset_name}: {idx + 1}/{len(problems)} | "
                  f"pass@1={aggregate.n_passed}/{idx + 1} = {aggregate.n_passed / (idx + 1):.3f}")

    aggregate.pass_at_1 = aggregate.n_passed / max(aggregate.n_problems, 1)

    out_path = output_dir / f"results_{preset_name}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(_aggregate_to_dict(aggregate), f, indent=2)
    print(f"[runner] wrote results: {out_path}")

    return aggregate


def _aggregate_to_dict(agg: TopologyAggregate) -> dict:
    """Convert TopologyAggregate to a JSON-serializable dict."""
    return {
        **{k: v for k, v in asdict(agg).items() if k != "trials"},
        "trials": [asdict(t) for t in agg.trials],
    }


async def run_all_presets(
    preset_names: list[str],
    output_dir: Path,
    max_problems: Optional[int] = None,
    model: str = "gpt-4.1",
) -> dict[str, TopologyAggregate]:
    """Top-level entry: run each preset over (a slice of) the HumanEval dataset."""
    from .presets import get_preset

    problems = load_problems()
    if max_problems is not None:
        problems = problems[:max_problems]
    print(f"[runner] loaded {len(problems)} problems")
    print(f"[runner] using model: {model}")

    results: dict[str, TopologyAggregate] = {}
    for name in preset_names:
        topology, agents = get_preset(name, model)
        agg = await run_preset_on_dataset(name, topology, agents, problems, output_dir)
        results[name] = agg
        print(f"[runner] {name} complete: pass@1={agg.pass_at_1:.3f}, total_tokens={agg.total_tokens}")

    return results
