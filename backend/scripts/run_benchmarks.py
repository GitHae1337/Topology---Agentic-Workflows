"""CLI entry for TravelPlanner benchmark runs.

NOTE: GSM8K / AQuA / MMLU-Pro paths are dormant (commented out below). The
underlying modules (`benchmarks/datasets.py`, `extractors.py`, `runner.py`)
are kept intact because TravelPlanner reuses `build_topology` / 5-topology
baselines from `benchmarks/runner.py`.

Examples:
  # Smallest spot-check: 1 TravelPlanner query, chain only, K=1
  python -m backend.scripts.run_benchmarks \
      --benchmark travelplanner --topologies chain \
      --task-ids travelplanner-0 --rounds 1

  # 5 topology comparison on one query
  python -m backend.scripts.run_benchmarks \
      --benchmark travelplanner \
      --topologies chain centralized hierarchical mesh cycle \
      --task-ids travelplanner-0
"""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load OPENAI_API_KEY from backend/.env (find_dotenv searches upward from this file).
load_dotenv()

# Disabled: simple single-answer benchmarks (kept for module reuse only).
# from backend.app.benchmarks.datasets import DATASET_CONFIG, load_problems
# from backend.app.benchmarks.runner import run_benchmark


DEFAULT_OUTPUT_BASE = Path(__file__).resolve().parents[2] / "Log" / "benchmarks"
TOPOLOGY_CHOICES = ["chain", "centralized", "hierarchical", "mesh", "cycle"]
# Disabled: gsm8k / aqua / mmlu_pro. Re-enable by restoring the import above
# and replacing the line below with: list(DATASET_CONFIG.keys()) + ["travelplanner"]
BENCHMARK_CHOICES = ["travelplanner"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TravelPlanner benchmark runner")
    p.add_argument(
        "--benchmark", required=True, choices=BENCHMARK_CHOICES,
        help="Benchmark to run (one).",
    )
    p.add_argument(
        "--topologies", nargs="+", default=TOPOLOGY_CHOICES, choices=TOPOLOGY_CHOICES,
        help=f"Topology baselines (multi). Default: all five.",
    )
    p.add_argument(
        "--max-problems", type=int, default=None,
        help="Limit to first N problems (default: all cached, currently up to 100). "
             "Ignored when --task-ids is given.",
    )
    p.add_argument(
        "--task-ids", nargs="+", default=None,
        help="Run only the specified task_ids (e.g. 'gsm8k-5 gsm8k-10'). "
             "Takes precedence over --max-problems.",
    )
    p.add_argument(
        "--model", type=str, default="gpt-4.1",
        help="LLM model used by every agent (default: gpt-4.1).",
    )
    p.add_argument(
        "--rounds", type=int, default=3,
        help="K rounds (max_turns) for each topology. Default: 3 (G-Designer paper setting).",
    )
    p.add_argument(
        "--no-traces", action="store_true",
        help="Skip per-message trace dump in results JSON (smaller files). "
             "Traces are saved by default; pass this to opt out.",
    )
    p.add_argument(
        "--output", type=Path, default=None,
        help="Output directory (default: Log/benchmarks/<bench>/<datetime>).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    output_dir = args.output or (
        DEFAULT_OUTPUT_BASE / args.benchmark / datetime.now().strftime("%Y-%m-%d-%H-%M")
    )
    save_traces = not args.no_traces
    print(
        f"[run_benchmarks] benchmark={args.benchmark} "
        f"topologies={args.topologies} max_problems={args.max_problems} "
        f"task_ids={args.task_ids} "
        f"K={args.rounds} model={args.model} save_traces={save_traces} "
        f"output={output_dir}"
    )

    # Only TravelPlanner is supported for now. The simple-answer benchmarks
    # (gsm8k/aqua/mmlu_pro) are dormant — see commented branch below to
    # re-enable.
    from backend.app.benchmarks.travelplanner.dataset import load_problems as tp_load
    from backend.app.benchmarks.travelplanner.runner import run_benchmark as tp_run

    if args.task_ids:
        all_problems = tp_load(max_problems=None)
        wanted = set(args.task_ids)
        problems = [p for p in all_problems if p.task_id in wanted]
        missing = wanted - {p.task_id for p in problems}
        if missing:
            sample = [p.task_id for p in all_problems[:5]]
            raise SystemExit(
                f"[run_benchmarks] task_ids not found: {sorted(missing)}. "
                f"Cache size={len(all_problems)}. Sample: {sample}"
            )
        print(f"[run_benchmarks] filtered to {len(problems)} problems by --task-ids")
    else:
        problems = tp_load(max_problems=args.max_problems)

    results = asyncio.run(
        tp_run(
            bench_name=args.benchmark,
            topology_names=args.topologies,
            problems=problems,
            output_dir=output_dir,
            model=args.model,
            K=args.rounds,
            save_traces=save_traces,
        )
    )

    # ----- Disabled: simple-answer benchmark dispatch (gsm8k / aqua / mmlu_pro)
    # Restore by reinstating the imports at top of file and uncommenting:
    # if args.benchmark == "travelplanner":
    #     ... (the tp branch above) ...
    # else:
    #     if args.task_ids:
    #         all_problems = load_problems(args.benchmark, max_problems=None)
    #         wanted = set(args.task_ids)
    #         problems = [p for p in all_problems if p.task_id in wanted]
    #         missing = wanted - {p.task_id for p in problems}
    #         if missing:
    #             sample = [p.task_id for p in all_problems[:5]]
    #             raise SystemExit(
    #                 f"[run_benchmarks] task_ids not found: {sorted(missing)}. "
    #                 f"Cache size={len(all_problems)}. Sample: {sample}"
    #             )
    #         print(f"[run_benchmarks] filtered to {len(problems)} problems by --task-ids")
    #     else:
    #         problems = load_problems(args.benchmark, max_problems=args.max_problems)
    #     results = asyncio.run(
    #         run_benchmark(
    #             bench_name=args.benchmark,
    #             topology_names=args.topologies,
    #             problems=problems,
    #             output_dir=output_dir,
    #             model=args.model,
    #             K=args.rounds,
    #             save_traces=save_traces,
    #         )
    #     )

    print(f"\n=== {args.benchmark.upper()} Summary (K={args.rounds}) ===")
    for name, agg in results.items():
        print(
            f"  {name:>14}: acc={agg.accuracy:.3f}  "
            f"({agg.n_correct}/{agg.n_problems})  "
            f"duration={agg.total_duration_seconds:.1f}s"
        )
    print(f"\nResults written to: {output_dir}")


if __name__ == "__main__":
    main()
