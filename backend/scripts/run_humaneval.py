"""
CLI entry for the HumanEval Phase 1 AI-only benchmark.

Examples:
  # Single topology, first 5 problems (smoke test)
  python -m backend.scripts.run_humaneval --presets chain --max-problems 5

  # All 5 baseline topologies, all 164 problems
  python -m backend.scripts.run_humaneval --presets chain centralized hierarchical mesh cycle

  # Custom output directory
  python -m backend.scripts.run_humaneval --presets chain --output ./Log/phase1_smoke
"""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from backend.app.humaneval.runner import run_all_presets
from backend.app.humaneval.presets import PRESETS


DEFAULT_OUTPUT_BASE = Path(__file__).resolve().parents[2] / "Log" / "phase1_humaneval"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HumanEval Phase 1 baseline benchmark")
    parser.add_argument(
        "--presets", nargs="+", default=list(PRESETS.keys()),
        help=f"Topology preset name(s). Available: {list(PRESETS.keys())}",
    )
    parser.add_argument(
        "--max-problems", type=int, default=None,
        help="Limit to first N HumanEval problems (default: all 164).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output directory for results JSON (default: Log/phase1_humaneval/<timestamp>).",
    )
    parser.add_argument(
        "--model", type=str, default="gpt-4.1",
        help="LLM model used by every agent across all presets (default: gpt-4.1). e.g. gpt-4.1, gpt-5.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    output_dir = args.output or (DEFAULT_OUTPUT_BASE / datetime.now().strftime("%Y-%m-%d-%H-%M"))
    print(f"[run_humaneval] presets={args.presets}, model={args.model}, max_problems={args.max_problems}, output={output_dir}")

    results = asyncio.run(
        run_all_presets(
            preset_names=args.presets,
            output_dir=output_dir,
            max_problems=args.max_problems,
            model=args.model,
        )
    )

    print("\n=== Phase 1 Summary ===")
    for name, agg in results.items():
        print(f"  {name:>14}: pass@1={agg.pass_at_1:.3f}  "
              f"({agg.n_passed}/{agg.n_problems})  "
              f"total_tokens={agg.total_tokens:,}  "
              f"timeouts={agg.n_timeouts}")
    print(f"\nResults written to: {output_dir}")


if __name__ == "__main__":
    main()
