"""Run the thinking-style x topology matrix on TravelPlanner.

For every (task, style, topology) cell, override the task's natural-language
query with the participant-authored phrasing, run the matching PDF topology
preset through the executor, evaluate the parsed plan, and append one JSONL
record per trial.

Task selection (pick one — flags are evaluated in this order):
    --task-ids id1,id2,...
    --tasks-file path/with/one_id_per_line.txt
    --filter-level medium --filter-days 3 [--limit N --seed 42]

Use --list-only to print matching task ids without running.

Examples:
    # full 5x5 matrix on a curated set
    python -m backend.scripts.run_thinking_style_matrix \\
        --task-ids travelplanner-0,travelplanner-12 --model gpt-4.1

    # filter + sample 20 tasks
    python -m backend.scripts.run_thinking_style_matrix \\
        --filter-level medium --filter-days 3 --limit 20 --seed 42

    # see candidate tasks before filling prompts.json
    python -m backend.scripts.run_thinking_style_matrix \\
        --filter-level medium --filter-days 3 --list-only
"""
import argparse
import asyncio
import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List

from backend.app.benchmarks.travelplanner.dataset import (
    TravelPlannerProblem,
    load_problems,
)
from backend.app.benchmarks.travelplanner.evaluator import evaluate_one
from backend.app.benchmarks.travelplanner.parser import parse_plan
from backend.app.benchmarks.travelplanner.prompts import build_user_input
from backend.app.engine.topologies import get_executor
from backend.app.thinking_style.loader import (
    DEFAULT_PROMPTS_PATH,
    PromptRecord,
    flatten,
    load_prompts,
)
from backend.app.thinking_style.topologies import PDF_PRESETS, get_preset


DEFAULT_TOPOLOGIES = list(PDF_PRESETS.keys())  # sas, independent, centralized, decentralized, hybrid


_TP_PREFIX = "travelplanner-"


def _parse_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _expand_task_id_token(token: str) -> List[str]:
    """Expand a single --task-ids token. Supports:
        - "12"            -> ["travelplanner-12"]
        - "0-19"          -> ["travelplanner-0", ..., "travelplanner-19"] (inclusive)
        - "travelplanner-7" -> kept verbatim (back-compat)
        - any other string -> kept verbatim (so non-tp datasets still work)
    """
    token = token.strip()
    if not token:
        return []
    if token.startswith(_TP_PREFIX):
        return [token]
    if "-" in token:
        start_s, _, end_s = token.partition("-")
        if start_s.isdigit() and end_s.isdigit():
            start, end = int(start_s), int(end_s)
            if end < start:
                raise ValueError(f"invalid range '{token}': end ({end}) < start ({start})")
            return [f"{_TP_PREFIX}{i}" for i in range(start, end + 1)]
    if token.isdigit():
        return [f"{_TP_PREFIX}{token}"]
    return [token]


def _resolve_task_ids(args, all_problems: List[TravelPlannerProblem]) -> List[str]:
    """Pick task_ids based on CLI args.

    Precedence: --task-ids > --tasks-file > (multi-value) filter+limit.
    Under filter mode, --limit applies PER (level, days) task cell. Passing
    --filter-level=easy,medium,hard --filter-days=3,5,7 sweeps the full 9
    task cells, each contributing up to --limit tasks.
    """
    if args.task_ids:
        out: List[str] = []
        seen: set[str] = set()
        for tok in args.task_ids.split(","):
            for expanded in _expand_task_id_token(tok):
                if expanded not in seen:
                    seen.add(expanded)
                    out.append(expanded)
        return out
    if args.tasks_file:
        return [
            line.strip()
            for line in args.tasks_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    levels: List[str | None] = list(_parse_csv(args.filter_level)) or [None]
    days_raw: List[str | None] = list(_parse_csv(args.filter_days)) or [None]
    days_list: List[int | None] = [int(d) if d is not None else None for d in days_raw]

    selected: list[TravelPlannerProblem] = []
    seen: set[str] = set()
    for lvl in levels:
        for d in days_list:
            cell = list(all_problems)
            if lvl is not None:
                cell = [p for p in cell if p.level == lvl]
            if d is not None:
                cell = [p for p in cell if p.days == d]
            if args.limit and args.limit < len(cell):
                if args.seed is not None:
                    rng = random.Random(args.seed)
                    cell = rng.sample(cell, args.limit)
                else:
                    cell = cell[: args.limit]
            print(
                f"[run_thinking_style_matrix]   task cell (level={lvl}, days={d}): "
                f"{len(cell)} tasks"
            )
            for p in cell:
                if p.task_id not in seen:
                    seen.add(p.task_id)
                    selected.append(p)
    return [p.task_id for p in selected]


async def run_one_trial(
    problem: TravelPlannerProblem,
    record: PromptRecord,
    topology_name: str,
    model: str,
    save_trace: bool,
) -> dict:
    topo, agents = get_preset(topology_name, model=model)
    agents_dict = {a.id: a for a in agents}
    executor = get_executor(topo.type.value)

    user_input = build_user_input(record.query, problem.reference_information)

    started = time.perf_counter()
    messages = []
    async for msg in executor.execute(
        topology=topo,
        agents=agents_dict,
        input_message=user_input,
        conversation_history=None,
    ):
        messages.append(msg)
    duration = time.perf_counter() - started

    final_output = messages[-1].content if messages else ""
    plan = parse_plan(final_output)
    metrics = evaluate_one(problem.model_dump(), plan)

    print(
        f"[run_thinking_style_matrix] {problem.task_id}/{record.style_id}/{topology_name}: "
        f"final_pass={metrics.get('final_pass')} duration={duration:.1f}s msgs={len(messages)}"
    )

    return {
        "task_id": problem.task_id,
        "level": problem.level,
        "days": problem.days,
        "style_id": record.style_id,
        "used_original": record.used_original,
        "topology": topology_name,
        "model": model,
        "query": record.query,
        "duration_seconds": round(duration, 3),
        "message_count": len(messages),
        "metrics": metrics,
        "final_output": final_output,
        "parsed_plan": plan,
        "messages": (
            [m.model_dump(mode="json") for m in messages] if save_trace else None
        ),
    }


async def main_async(args: argparse.Namespace) -> None:
    problems = load_problems(split=args.split)
    by_id = {p.task_id: p for p in problems}

    task_ids = _resolve_task_ids(args, problems)
    print(f"[run_thinking_style_matrix] resolved {len(task_ids)} task_ids")

    if args.list_only:
        for tid in task_ids:
            p = by_id.get(tid)
            if p:
                print(
                    f"  {tid}\tlevel={p.level}\tdays={p.days}\t"
                    f"budget={p.budget}\torg={p.org}\tdest={p.dest}"
                )
            else:
                print(f"  {tid}\t(NOT FOUND in dataset)")
        return

    missing = [tid for tid in task_ids if tid not in by_id]
    if missing:
        raise ValueError(f"task_ids not in dataset: {missing}")
    selected_problems = [by_id[tid] for tid in task_ids]

    pf = load_prompts(args.prompts)
    by_task_style = {(r.task_id, r.style_id): r for r in flatten(pf, selected_problems)}

    topologies = [t.strip().lower() for t in args.topologies.split(",") if t.strip()]
    for t in topologies:
        if t not in PDF_PRESETS:
            raise ValueError(f"unknown topology {t}; valid: {list(PDF_PRESETS)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"[run_thinking_style_matrix] writing → {args.output}")

    plan_to_run: list[tuple[TravelPlannerProblem, PromptRecord, str]] = []
    for problem in selected_problems:
        for style in pf.thinking_styles:
            key = (problem.task_id, style.id)
            if key not in by_task_style:
                print(
                    f"[run_thinking_style_matrix] WARNING: no prompt for "
                    f"task={problem.task_id} style={style.id} — skipping"
                )
                continue
            for topo in topologies:
                plan_to_run.append((problem, by_task_style[key], topo))

    print(f"[run_thinking_style_matrix] total trials: {len(plan_to_run)}")

    with args.output.open("w", encoding="utf-8") as f:
        for i, (problem, record, topo) in enumerate(plan_to_run, 1):
            print(
                f"[run_thinking_style_matrix] [{i}/{len(plan_to_run)}] "
                f"{problem.task_id}/{record.style_id}/{topo}"
            )
            result = await run_one_trial(
                problem=problem,
                record=record,
                topology_name=topo,
                model=args.model,
                save_trace=args.save_trace,
            )
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # task selection
    p.add_argument("--task-ids", type=str, default=None, help="comma-separated task ids")
    p.add_argument("--tasks-file", type=Path, default=None, help="file with one task_id per line")
    p.add_argument(
        "--filter-level",
        type=str,
        default=None,
        help="filter level — single (medium) or csv (easy,medium,hard) for multi-cell sweep",
    )
    p.add_argument(
        "--filter-days",
        type=str,
        default=None,
        help="filter days — single (3) or csv (3,5,7) for multi-cell sweep",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap PER (level, days) cell after filter (sample if --seed given)",
    )
    p.add_argument("--seed", type=int, default=None, help="seed for sampling under --limit")
    p.add_argument("--split", type=str, default="validation")
    p.add_argument("--list-only", action="store_true", help="print matching task ids without running")
    # matrix
    p.add_argument(
        "--topologies",
        type=str,
        default=",".join(DEFAULT_TOPOLOGIES),
        help=f"comma-separated PDF topologies (default: all 5: {DEFAULT_TOPOLOGIES})",
    )
    p.add_argument("--model", type=str, default="gpt-5")
    p.add_argument("--save-trace", action="store_true", help="store full message trace per trial (heavy)")
    # paths
    p.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS_PATH)
    p.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "thinking_styles"
        / f"matrix_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
    )
    args = p.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
