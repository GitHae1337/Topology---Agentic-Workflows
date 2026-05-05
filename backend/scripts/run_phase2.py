"""
Phase 2 evaluator: workflows.db의 trial workflow를 HumanEval에 돌려서
phase2_results.json으로 저장.

각 row → adapter → run_preset_on_dataset → 집계.

Examples:
  # 모든 trial workflow를 HumanEval 5문제로 smoke test
  python -m backend.scripts.run_phase2 --max-problems 5

  # gpt-4.1로 model을 통일해서 fair comparison
  python -m backend.scripts.run_phase2 --override-model gpt-4.1

  # 사용자 지정 출력 위치
  python -m backend.scripts.run_phase2 --output backend/data/phase2_smoke.json --max-problems 5
"""
import argparse
import asyncio
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.app.humaneval.runner import run_preset_on_dataset
from backend.app.humaneval.workflow_adapter import adapt_workflow_to_topology
from backend.app.humaneval.dataset import load_problems


DEFAULT_DB = Path(__file__).resolve().parents[2] / "backend" / "workflows.db"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "backend" / "data" / "phase2_results.json"


def fetch_trial_workflows(db_path: str) -> list[dict]:
    """workflows.db에서 session_id가 있는 row만 읽어서 dict 리스트로 반환."""
    print(f"[run_phase2] reading {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, name, data, session_id, created_at, updated_at "
        "FROM workflows WHERE session_id IS NOT NULL "
        "ORDER BY created_at"
    )
    rows = []
    for r in cur.fetchall():
        rows.append({
            "id": r["id"],
            "name": r["name"],
            "session_id": r["session_id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "data": json.loads(r["data"]),
        })
    conn.close()
    print(f"[run_phase2] found {len(rows)} trial workflows")
    return rows


def _override_agent_models(agents: list, model: str) -> None:
    """모든 agent의 model 필드를 override (fair comparison용)."""
    for a in agents:
        a.model = model


async def evaluate_one(
    workflow_row: dict,
    problems: list,
    output_dir: Path,
    override_model: Optional[str],
) -> Optional[dict]:
    workflow_id = workflow_row["id"]
    print(f"\n[run_phase2] === workflow {workflow_id} ({workflow_row['name']}) ===")

    adapted = adapt_workflow_to_topology(workflow_row["data"])
    if adapted is None:
        print(f"[run_phase2] skip {workflow_id}: not runnable")
        return None

    topology, agents, label, agent_count = adapted

    if override_model is not None:
        _override_agent_models(agents, override_model)
        print(f"[run_phase2] overrode all agent.model → {override_model}")

    preset_name = f"{workflow_id}_{label}"
    print(f"[run_phase2] running {preset_name}: label={label}, agents={agent_count}")

    aggregate = await run_preset_on_dataset(
        preset_name=preset_name,
        topology=topology,
        agents=agents,
        problems=problems,
        output_dir=output_dir,
    )

    return {
        "workflow_id": workflow_id,
        "workflow_name": workflow_row["name"],
        "session_id": workflow_row["session_id"],
        "created_at": workflow_row["created_at"],
        "topology": label,
        "agent_count": agent_count,
        "n_problems": aggregate.n_problems,
        "n_passed": aggregate.n_passed,
        "pass_at_1": aggregate.pass_at_1,
        "n_timeouts": aggregate.n_timeouts,
        "total_duration_seconds": aggregate.total_duration_seconds,
        "total_call_count": aggregate.total_call_count,
        "total_input_tokens": aggregate.total_input_tokens,
        "total_output_tokens": aggregate.total_output_tokens,
        "total_tokens": aggregate.total_tokens,
        "trials": [asdict(t) for t in aggregate.trials],
    }


async def main_async(args: argparse.Namespace) -> None:
    output_path = Path(args.output)
    output_dir = output_path.parent / output_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[run_phase2] output={output_path}, per-workflow JSONs in {output_dir}")

    rows = fetch_trial_workflows(str(args.db))
    if not rows:
        print("[run_phase2] no trial workflows; aborting")
        return

    problems = load_problems()
    if args.max_problems is not None:
        problems = problems[: args.max_problems]
    print(f"[run_phase2] evaluating {len(rows)} workflows on {len(problems)} problems")
    if args.override_model:
        print(f"[run_phase2] override-model={args.override_model} (will replace every agent.model)")
    else:
        print(f"[run_phase2] using each workflow's saved agent.model values")

    results = []
    skipped = 0
    for row in rows:
        record = await evaluate_one(row, problems, output_dir, args.override_model)
        if record is None:
            skipped += 1
        else:
            results.append(record)

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "n_workflows_total": len(rows),
        "n_workflows_evaluated": len(results),
        "n_workflows_skipped": skipped,
        "n_problems": len(problems),
        "override_model": args.override_model,
        "results": results,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[run_phase2] === Summary ===")
    print(f"  evaluated={len(results)}, skipped={skipped}, total_rows={len(rows)}")
    for r in results:
        print(f"  {r['workflow_id']:>20} ({r['topology']:>11}, n={r['agent_count']}): "
              f"pass@1={r['pass_at_1']:.3f} ({r['n_passed']}/{r['n_problems']})  "
              f"tokens={r['total_tokens']:,}")
    print(f"\n[run_phase2] wrote {output_path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2 — evaluate participant workflows on HumanEval")
    p.add_argument("--db", type=Path, default=DEFAULT_DB,
                   help=f"workflows.db path (default: {DEFAULT_DB})")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help=f"output JSON path (default: {DEFAULT_OUTPUT})")
    p.add_argument("--max-problems", type=int, default=None,
                   help="limit HumanEval problems (default: all 164)")
    p.add_argument("--override-model", type=str, default=None,
                   help="if set, replace every agent.model with this value")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
