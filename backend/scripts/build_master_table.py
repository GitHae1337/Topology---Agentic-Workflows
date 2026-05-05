"""
Build master_table.csv: one row per trial (Phase 2) plus one row per Phase 1 baseline.

Joins:
  - Phase 1 results (Log/phase1_humaneval/<dt>/results_<preset>.json)
  - Phase 2 results (backend/data/phase2_results.json)
  - Behavior metrics (backend/data/behavior_metrics.csv) by session_id

Output schema (in order):
  source, preset_or_workflow_id, topology, agent_count,
  participant_id, task_id, session_id,
  n_problems, n_passed, pass_at_1, n_timeouts,
  total_duration_seconds, total_call_count,
  total_input_tokens, total_output_tokens, total_tokens,
  total_edits, undo_count, redo_count,
  first_click_latency_seconds, authoring_duration_seconds,
  distinct_action_types, max_undo_stack_depth

Examples:
    python -m backend.scripts.build_master_table
    python -m backend.scripts.build_master_table --phase1-dir Log/phase1_humaneval/2026-04-28-09-59
"""
import argparse
import csv
import json
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PHASE1_BASE = REPO_ROOT / "Log" / "phase1_humaneval"
DEFAULT_PHASE2 = REPO_ROOT / "backend" / "data" / "phase2_results.json"
DEFAULT_METRICS = REPO_ROOT / "backend" / "data" / "behavior_metrics.csv"
DEFAULT_OUTPUT = REPO_ROOT / "backend" / "data" / "master_table.csv"


COLUMNS = [
    "source",
    "preset_or_workflow_id",
    "topology",
    "agent_count",
    "participant_id",
    "task_id",
    "session_id",
    "n_problems",
    "n_passed",
    "pass_at_1",
    "n_timeouts",
    "total_duration_seconds",
    "total_call_count",
    "total_input_tokens",
    "total_output_tokens",
    "total_tokens",
    "total_edits",
    "undo_count",
    "redo_count",
    "first_click_latency_seconds",
    "authoring_duration_seconds",
    "distinct_action_types",
    "max_undo_stack_depth",
]


def _pick_latest_phase1_dir(base: Path) -> Optional[Path]:
    if not base.exists():
        print(f"[build_master] phase1 base missing: {base}")
        return None
    subdirs = sorted([p for p in base.iterdir() if p.is_dir()])
    if not subdirs:
        print(f"[build_master] no phase1 subdirs in {base}")
        return None
    chosen = subdirs[-1]
    print(f"[build_master] auto-picked latest phase1 dir: {chosen}")
    return chosen


def load_phase1_rows(phase1_dir: Optional[Path]) -> list[dict[str, Any]]:
    """Read each results_<preset>.json and emit a phase1 row per preset."""
    if phase1_dir is None or not phase1_dir.exists():
        print(f"[build_master] no phase1 dir provided/found; skipping phase1 rows")
        return []

    files = sorted(phase1_dir.glob("results_*.json"))
    print(f"[build_master] found {len(files)} phase1 results files in {phase1_dir}")
    rows = []
    for f in files:
        agg = json.loads(f.read_text(encoding="utf-8"))
        preset = agg.get("preset_name", f.stem.replace("results_", ""))
        agent_count = len(agg["trials"][0].get("preset_name", "")) if agg.get("trials") else 0
        # NOTE: phase1 doesn't record agent_count directly; presets always use 3.
        # We hard-code 3 since all 5 baseline presets are 3-agent by design.
        rows.append({
            "source": "phase1",
            "preset_or_workflow_id": preset,
            "topology": preset,
            "agent_count": 3,
            "participant_id": "",
            "task_id": "",
            "session_id": "",
            "n_problems": agg.get("n_problems"),
            "n_passed": agg.get("n_passed"),
            "pass_at_1": agg.get("pass_at_1"),
            "n_timeouts": agg.get("n_timeouts"),
            "total_duration_seconds": agg.get("total_duration_seconds"),
            "total_call_count": agg.get("total_call_count"),
            "total_input_tokens": agg.get("total_input_tokens"),
            "total_output_tokens": agg.get("total_output_tokens"),
            "total_tokens": agg.get("total_tokens"),
            "total_edits": "",
            "undo_count": "",
            "redo_count": "",
            "first_click_latency_seconds": "",
            "authoring_duration_seconds": "",
            "distinct_action_types": "",
            "max_undo_stack_depth": "",
        })
        print(f"[build_master]   phase1 row: {preset} pass@1={agg.get('pass_at_1')}")
    return rows


def load_metrics_lookup(metrics_csv: Path) -> dict[str, dict[str, Any]]:
    """Map session_id → metrics row dict."""
    if not metrics_csv.exists():
        print(f"[build_master] metrics csv missing: {metrics_csv}")
        return {}
    with metrics_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    lookup: dict[str, dict[str, Any]] = {}
    for r in rows:
        sid = r.get("session_id")
        if sid:
            lookup[sid] = r
    print(f"[build_master] loaded metrics for {len(lookup)} sessions")
    return lookup


def load_phase2_rows(phase2_json: Path, metrics_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Read phase2_results.json and emit one row per workflow record, joining metrics."""
    if not phase2_json.exists():
        print(f"[build_master] phase2 json missing: {phase2_json}")
        return []

    payload = json.loads(phase2_json.read_text(encoding="utf-8"))
    records = payload.get("results", [])
    print(f"[build_master] found {len(records)} phase2 records in {phase2_json}")

    rows = []
    for rec in records:
        sid = rec.get("session_id", "")
        m = metrics_lookup.get(sid, {})
        if not m:
            print(f"[build_master]   no metrics for session {sid}; behavior cols blank")
        rows.append({
            "source": "phase2",
            "preset_or_workflow_id": rec.get("workflow_id"),
            "topology": rec.get("topology"),
            "agent_count": rec.get("agent_count"),
            "participant_id": m.get("participant_id", ""),
            "task_id": m.get("task_id", ""),
            "session_id": sid,
            "n_problems": rec.get("n_problems"),
            "n_passed": rec.get("n_passed"),
            "pass_at_1": rec.get("pass_at_1"),
            "n_timeouts": rec.get("n_timeouts"),
            "total_duration_seconds": rec.get("total_duration_seconds"),
            "total_call_count": rec.get("total_call_count"),
            "total_input_tokens": rec.get("total_input_tokens"),
            "total_output_tokens": rec.get("total_output_tokens"),
            "total_tokens": rec.get("total_tokens"),
            "total_edits": m.get("total_edits", ""),
            "undo_count": m.get("undo_count", ""),
            "redo_count": m.get("redo_count", ""),
            "first_click_latency_seconds": m.get("first_click_latency_seconds", ""),
            "authoring_duration_seconds": m.get("session_duration_seconds", ""),
            "distinct_action_types": m.get("distinct_action_types", ""),
            "max_undo_stack_depth": m.get("max_undo_stack_depth", ""),
        })
    return rows


def main(args: argparse.Namespace) -> None:
    phase1_dir = args.phase1_dir or _pick_latest_phase1_dir(args.phase1_base)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics_lookup = load_metrics_lookup(Path(args.metrics))
    phase1_rows = load_phase1_rows(Path(phase1_dir) if phase1_dir else None)
    phase2_rows = load_phase2_rows(Path(args.phase2), metrics_lookup)
    all_rows = phase1_rows + phase2_rows

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in all_rows:
            writer.writerow(r)

    print(
        f"\n[build_master] wrote {len(all_rows)} rows "
        f"(phase1={len(phase1_rows)}, phase2={len(phase2_rows)}) → {output_path}"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build master_table.csv joining phase1, phase2, and behavior metrics")
    p.add_argument("--phase1-base", type=Path, default=DEFAULT_PHASE1_BASE,
                   help=f"phase1 results base dir (default: {DEFAULT_PHASE1_BASE})")
    p.add_argument("--phase1-dir", type=Path, default=None,
                   help="specific phase1 timestamped subdir; if omitted, picks latest")
    p.add_argument("--phase2", type=Path, default=DEFAULT_PHASE2,
                   help=f"phase2_results.json path (default: {DEFAULT_PHASE2})")
    p.add_argument("--metrics", type=Path, default=DEFAULT_METRICS,
                   help=f"behavior_metrics.csv path (default: {DEFAULT_METRICS})")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help=f"output master_table.csv path (default: {DEFAULT_OUTPUT})")
    return p.parse_args()


if __name__ == "__main__":
    main(parse_args())
