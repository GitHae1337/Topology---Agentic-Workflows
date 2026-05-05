"""CLI for Phase 2 evaluation: run participant-built workflows on benchmarks.

Workflow:
  1. Read workflows.db, pick rows with session_id (= saved during a trial).
  2. For each row, adapt to (TopologyConfig, agents, label) via classifier.
       Skip rows that aren't runnable (label='none' or <2 agents).
  3. For each runnable workflow × N benchmark problems, run one trial each.
  4. Per-workflow result JSON + cross-workflow summary JSON.

Examples:
  # Dry-run: just classify and print, no LLM calls
  python -m backend.scripts.run_phase2_benchmarks \
      --benchmark gsm8k --dry-run

  # One participant on TravelPlanner, 5 queries, fairness model override
  python -m backend.scripts.run_phase2_benchmarks \
      --benchmark travelplanner --participant P01 \
      --max-problems 5 --override-model gpt-4.1

  # Specific workflow only (smoke)
  python -m backend.scripts.run_phase2_benchmarks \
      --benchmark gsm8k --workflow-id workflow-abc12345 \
      --task-ids gsm8k-0
"""
import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load OPENAI_API_KEY from backend/.env. find_dotenv walks up from this file.
load_dotenv()

from backend.app.benchmarks.workflow_adapter import (
    adapt_workflow_to_topology,
    build_participant_session_map,
    iter_phase2_workflows,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "backend" / "workflows.db"
DEFAULT_LOG_ROOT = REPO_ROOT / "Log"
DEFAULT_OUTPUT_BASE = REPO_ROOT / "Log" / "phase2_benchmarks"

# Disabled: gsm8k / aqua / mmlu_pro. Re-enable by extending this list.
BENCHMARK_CHOICES = ["travelplanner"]


@dataclass
class WorkflowEvalRecord:
    """Per-workflow result; one of these is dumped per evaluable row."""
    workflow_id: str
    workflow_name: str
    session_id: Optional[str]
    participant_id: Optional[str]
    topology_label: str
    agent_count: int
    benchmark: str
    n_problems: int
    n_correct: int
    accuracy: float
    duration_seconds: float
    trials: list = field(default_factory=list)
    # Phase 2 spec: per-constraint fail count across trials.
    fail_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class Phase2Summary:
    benchmark: str
    K: int
    n_workflows_in_db: int
    n_evaluated: int
    n_skipped: int
    skip_reasons: dict[str, int] = field(default_factory=dict)
    by_topology: dict[str, dict] = field(default_factory=dict)
    by_participant: dict[str, dict] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2 evaluation: participant workflows × benchmark")
    p.add_argument("--benchmark", required=True, choices=BENCHMARK_CHOICES)
    p.add_argument("--participant", default=None,
                   help="Filter to one participant_id (joined via Log session_*.json).")
    p.add_argument("--workflow-id", default=None,
                   help="Filter to one workflow id (e.g. workflow-abc12345).")
    p.add_argument("--max-problems", type=int, default=None,
                   help="Slice front of benchmark (ignored when --task-ids).")
    p.add_argument("--task-ids", nargs="+", default=None,
                   help="Run only these task_ids (e.g. gsm8k-5 gsm8k-10).")
    p.add_argument("--rounds", type=int, default=None,
                   help="Override topology.max_turns (default: keep what participant set).")
    p.add_argument("--model", default="gpt-4.1",
                   help="Default agent model when an agent has none. Default gpt-4.1.")
    p.add_argument("--override-model", default=None,
                   help="Force every agent.model = M (fairness comparison).")
    p.add_argument("--no-traces", action="store_true",
                   help="Skip per-message trace dump.")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Classify and report, but don't run any trials.")
    return p.parse_args()


def _load_problems(args):
    """Pick the right loader based on benchmark, apply task-ids/max-problems filter.

    Currently only TravelPlanner is supported. The simple-answer branch is
    commented below for future re-enablement.
    """
    from backend.app.benchmarks.travelplanner.dataset import load_problems as load
    # Disabled: simple-answer benchmark loader.
    # if args.benchmark == "travelplanner":
    #     from backend.app.benchmarks.travelplanner.dataset import load_problems as load
    # else:
    #     from backend.app.benchmarks.datasets import load_problems as load

    if args.task_ids:
        all_problems = load(max_problems=None)
        # Disabled: load(args.benchmark, max_problems=None) when benchmark != travelplanner
        wanted = set(args.task_ids)
        problems = [p for p in all_problems if p.task_id in wanted]
        missing = wanted - {p.task_id for p in problems}
        if missing:
            sample = [p.task_id for p in all_problems[:5]]
            raise SystemExit(f"task_ids not found: {sorted(missing)}. Sample: {sample}")
        print(f"[run_phase2] filtered to {len(problems)} problems by --task-ids")
        return problems

    return load(max_problems=args.max_problems)
    # Disabled: return load(args.benchmark, max_problems=args.max_problems)


def _maybe_apply_overrides(topology, agents, args):
    """Apply --rounds and --override-model if requested. Returns (topology, agents)."""
    if args.rounds is not None and topology.max_turns != args.rounds:
        # Pydantic v2: model_copy with update
        topology = topology.model_copy(update={"max_turns": args.rounds})
        print(f"[run_phase2] override max_turns → {args.rounds}")

    if args.override_model:
        agents = [a.model_copy(update={"model": args.override_model}) for a in agents]
        print(f"[run_phase2] override model → {args.override_model} for all {len(agents)} agents")
    else:
        # Replace any blank model with the default
        agents = [
            (a if a.model else a.model_copy(update={"model": args.model}))
            for a in agents
        ]
    return topology, agents


# Disabled: simple-answer trial runner (gsm8k / aqua / mmlu_pro). Kept for
# future re-enablement; currently unreachable because BENCHMARK_CHOICES only
# allows travelplanner.
# async def _run_one_trial_simple(bench_name, topology, agents, problem, save_trace, label):
#     from backend.app.benchmarks.runner import run_one_with_explicit_topology
#     return await run_one_with_explicit_topology(
#         bench_name=bench_name,
#         topology=topology,
#         agents=agents,
#         problem=problem,
#         save_trace=save_trace,
#         record_topology_name=label,
#     )


async def _run_one_trial_tp(topology, agents, problem, save_trace, label):
    from backend.app.benchmarks.travelplanner.runner import run_one_with_explicit_topology
    return await run_one_with_explicit_topology(
        topology=topology,
        agents=agents,
        problem=problem,
        save_trace=save_trace,
        record_topology_name=label,
    )


# Constraint key catalogs — used by _simplify_tp_trial below.
_COMMONSENSE_KEYS = (
    "is_reasonable_visiting_city",
    "is_valid_restaurants",
    "is_valid_attractions",
    "is_valid_accommodation",
    "is_valid_transportation",
    "is_valid_information_in_current_city",
    "is_valid_information_in_sandbox",
    "is_not_absent",
)
_HARD_KEYS = (
    "valid_cost",
    "valid_room_rule",
    "valid_cuisine",
    "valid_room_type",
    "valid_transportation",
)


def _status_from_pair(pair) -> dict:
    """[bool|None, msg|None] → {status, reason?}."""
    passed = pair[0] if isinstance(pair, (list, tuple)) and len(pair) > 0 else None
    msg = pair[1] if isinstance(pair, (list, tuple)) and len(pair) > 1 else None
    if passed is None:
        return {"status": "skipped", "reason": "not specified in query"}
    if passed:
        return {"status": "pass"}
    return {"status": "fail", "reason": msg or ""}


def _simplify_tp_trial(trial_dict: dict) -> dict:
    """Phase 2 trial JSON simplification — drop macro/micro stats, expose
    each of the 13 constraints as {status, reason?}.

    Always emits all 8 commonsense + 5 hard slots so downstream analysis can
    iterate without missing-key checks. Plan-not-delivered → all 13 slots
    are 'skipped' with reason 'plan not delivered'.
    """
    metrics = trial_dict.get("metrics") or {}
    delivered = bool(metrics.get("delivery"))

    cs_per = metrics.get("commonsense_per_item")
    if cs_per is None:
        cs = {k: {"status": "skipped", "reason": "plan not delivered"} for k in _COMMONSENSE_KEYS}
    else:
        cs = {k: _status_from_pair(cs_per.get(k, [None, None])) for k in _COMMONSENSE_KEYS}

    hd_per = metrics.get("hard_per_item")
    if hd_per is None:
        reason = "commonsense gate failed; hard not evaluated" if delivered else "plan not delivered"
        hd = {k: {"status": "skipped", "reason": reason} for k in _HARD_KEYS}
    else:
        hd = {k: _status_from_pair(hd_per.get(k, [None, None])) for k in _HARD_KEYS}

    all_items = list(cs.values()) + list(hd.values())
    passed_count = sum(1 for s in all_items if s["status"] == "pass")
    evaluated_count = sum(1 for s in all_items if s["status"] != "skipped")

    return {
        "task_id": trial_dict.get("task_id"),
        "topology_name": trial_dict.get("topology_name"),
        "all_passed": bool(metrics.get("final_pass")),
        "passed_count": passed_count,
        "evaluated_count": evaluated_count,
        "constraints": {"commonsense": cs, "hard": hd},
        "duration_seconds": trial_dict.get("duration_seconds"),
        "message_count": trial_dict.get("message_count"),
        "final_output": trial_dict.get("final_output"),
        "parsed_plan": trial_dict.get("parsed_plan"),
        "messages": trial_dict.get("messages"),
    }


def _build_fail_breakdown(simplified_trials: list[dict]) -> dict[str, int]:
    """Across all of a workflow's trials, count how many times each constraint
    key appeared as 'fail'. Helps the participant see which rules they trip
    most often."""
    counts: dict[str, int] = {}
    for t in simplified_trials:
        for category in ("commonsense", "hard"):
            for k, v in t["constraints"][category].items():
                if v["status"] == "fail":
                    counts[k] = counts.get(k, 0) + 1
    return counts


async def _evaluate_workflow(args, row, problems, save_trace, sid_to_pid):
    """Adapt one workflow row, run all problems, return WorkflowEvalRecord or None."""
    adapted = adapt_workflow_to_topology(row.data)
    if adapted is None:
        return None, "label_none_or_few_agents"

    topology, agents, label, agent_count = adapted
    topology, agents = _maybe_apply_overrides(topology, agents, args)
    pid = sid_to_pid.get(row.session_id) if row.session_id else None

    if args.dry_run:
        print(f"[dry-run] {row.id} pid={pid} label={label} agents={agent_count} K={topology.max_turns}")
        return WorkflowEvalRecord(
            workflow_id=row.id,
            workflow_name=row.name,
            session_id=row.session_id,
            participant_id=pid,
            topology_label=label,
            agent_count=agent_count,
            benchmark=args.benchmark,
            n_problems=0, n_correct=0, accuracy=0.0, duration_seconds=0.0,
            trials=[],
        ), None

    print(f"[run_phase2] evaluating {row.id} pid={pid} label={label} on {len(problems)} problems")

    trials = []
    n_correct = 0
    duration = 0.0
    for problem in problems:
        # Only TravelPlanner is wired for now. Simple-answer branch disabled.
        trial = await _run_one_trial_tp(topology, agents, problem, save_trace, label)
        # Disabled:
        # if args.benchmark == "travelplanner":
        #     trial = await _run_one_trial_tp(topology, agents, problem, save_trace, label)
        # else:
        #     trial = await _run_one_trial_simple(args.benchmark, topology, agents, problem, save_trace, label)
        trials.append(trial)
        n_correct += int(trial.correct)
        duration += trial.duration_seconds

    # Simplify each trial to the 13-constraint status form (Phase 2 spec).
    simplified_trials = [_simplify_tp_trial(asdict(t)) for t in trials]
    fail_breakdown = _build_fail_breakdown(simplified_trials)

    record = WorkflowEvalRecord(
        workflow_id=row.id,
        workflow_name=row.name,
        session_id=row.session_id,
        participant_id=pid,
        topology_label=label,
        agent_count=agent_count,
        benchmark=args.benchmark,
        n_problems=len(problems),
        n_correct=n_correct,
        accuracy=n_correct / max(len(problems), 1),
        duration_seconds=round(duration, 3),
        trials=simplified_trials,
        fail_breakdown=fail_breakdown,
    )
    return record, None


def _write_record(output_dir: Path, record: WorkflowEvalRecord) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"results_{record.workflow_id}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(asdict(record), f, indent=2, ensure_ascii=False)
    return out


def _build_summary(args, records, n_in_db, skipped_reasons) -> Phase2Summary:
    by_topology: dict[str, dict] = {}
    by_participant: dict[str, dict] = {}
    for r in records:
        if r.n_problems == 0:
            continue  # dry-run
        bt = by_topology.setdefault(r.topology_label, {"n_workflows": 0, "accuracies": []})
        bt["n_workflows"] += 1
        bt["accuracies"].append(r.accuracy)
        if r.participant_id:
            bp = by_participant.setdefault(r.participant_id, {"n_workflows": 0, "accuracies": []})
            bp["n_workflows"] += 1
            bp["accuracies"].append(r.accuracy)

    for d in (by_topology, by_participant):
        for k, v in d.items():
            accs = v.pop("accuracies")
            v["mean_accuracy"] = sum(accs) / max(len(accs), 1)

    return Phase2Summary(
        benchmark=args.benchmark,
        K=args.rounds if args.rounds is not None else -1,
        n_workflows_in_db=n_in_db,
        n_evaluated=sum(1 for r in records if r.n_problems > 0),
        n_skipped=sum(skipped_reasons.values()),
        skip_reasons=skipped_reasons,
        by_topology=by_topology,
        by_participant=by_participant,
    )


async def main_async(args):
    save_traces = not args.no_traces
    output_dir = args.output or (
        DEFAULT_OUTPUT_BASE / args.benchmark / datetime.now().strftime("%Y-%m-%d-%H-%M")
    )
    print(f"[run_phase2] benchmark={args.benchmark} output={output_dir} dry_run={args.dry_run}")

    sid_to_pid = build_participant_session_map(args.log_root)

    rows = list(iter_phase2_workflows(args.db))
    n_in_db = len(rows)

    if args.workflow_id:
        rows = [r for r in rows if r.id == args.workflow_id]
        print(f"[run_phase2] workflow-id filter: {len(rows)} of {n_in_db}")
    if args.participant:
        rows = [
            r for r in rows
            if r.session_id and sid_to_pid.get(r.session_id) == args.participant
        ]
        print(f"[run_phase2] participant filter ({args.participant}): {len(rows)} rows")

    if not rows:
        print(f"[run_phase2] no rows after filters; nothing to do")
        return

    problems = [] if args.dry_run else _load_problems(args)
    if not args.dry_run:
        print(f"[run_phase2] loaded {len(problems)} problems")

    records: list[WorkflowEvalRecord] = []
    skipped_reasons: dict[str, int] = {}
    for row in rows:
        record, skip_reason = await _evaluate_workflow(args, row, problems, save_traces, sid_to_pid)
        if record is None:
            skipped_reasons[skip_reason] = skipped_reasons.get(skip_reason, 0) + 1
            continue
        records.append(record)
        if not args.dry_run:
            out = _write_record(output_dir, record)
            print(f"[run_phase2] wrote {out}")

    summary = _build_summary(args, records, n_in_db, skipped_reasons)
    if not args.dry_run:
        sum_path = output_dir / "summary.json"
        sum_path.parent.mkdir(parents=True, exist_ok=True)
        with sum_path.open("w", encoding="utf-8") as f:
            json.dump(asdict(summary), f, indent=2, ensure_ascii=False)
        print(f"[run_phase2] wrote {sum_path}")

    print(f"\n=== Phase 2 Summary ({args.benchmark}) ===")
    print(f"  workflows in DB: {summary.n_workflows_in_db}")
    print(f"  evaluated: {summary.n_evaluated}, skipped: {summary.n_skipped}")
    if summary.skip_reasons:
        print(f"  skip reasons: {summary.skip_reasons}")
    if summary.by_topology:
        print(f"  by topology:")
        for label, stats in summary.by_topology.items():
            print(f"    {label:>14}: n={stats['n_workflows']:3d}  mean_acc={stats['mean_accuracy']:.3f}")
    if summary.by_participant:
        print(f"  by participant:")
        for pid, stats in summary.by_participant.items():
            print(f"    {pid:>14}: n={stats['n_workflows']:3d}  mean_acc={stats['mean_accuracy']:.3f}")


def main():
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
