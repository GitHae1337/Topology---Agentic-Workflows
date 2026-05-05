"""
Extract per-trial behavior metrics from edit-log JSONL files.

Reads Log/<datetime>/session_*.json (+ matching edit_log_*.jsonl + events_*.jsonl)
and emits one CSV row per trial session for the master_table builder to join.

Output columns:
    session_id, participant_id, task_id, session_started_at,
    total_edits, undo_count, redo_count,
    first_click_latency_seconds, session_duration_seconds,
    distinct_action_types, max_undo_stack_depth

Examples:
    python -m backend.scripts.extract_metrics
    python -m backend.scripts.extract_metrics --log-root Log --output backend/data/behavior_metrics.csv
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


DEFAULT_LOG_ROOT = Path(__file__).resolve().parents[2] / "Log"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "backend" / "data" / "behavior_metrics.csv"


def _parse_iso(ts: str) -> Optional[datetime]:
    """Best-effort ISO parser. Returns None if `ts` is empty/invalid."""
    if not ts:
        return None
    s = ts.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(s)
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts. Returns [] if missing/empty."""
    if not path.exists():
        print(f"[extract_metrics] missing jsonl: {path.name}")
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _seconds_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds(), 3)


def compute_metrics_for_session(
    session_json_path: Path,
) -> Optional[dict[str, Any]]:
    """Given a session_<sid>.json file, return one metric row dict."""
    session_dir = session_json_path.parent
    session_meta = json.loads(session_json_path.read_text(encoding="utf-8"))
    sid = session_meta.get("sessionId")
    if not sid:
        print(f"[extract_metrics] no sessionId in {session_json_path}; skip")
        return None

    started_at = _parse_iso(session_meta.get("startedAt", ""))
    edit_log_path = session_dir / f"edit_log_{sid}.jsonl"
    events_path = session_dir / f"events_{sid}.jsonl"

    edits = _read_jsonl(edit_log_path)
    events = _read_jsonl(events_path)

    total_edits = len(edits)
    distinct_action_types = len({e.get("action") for e in edits if e.get("action")})
    max_undo_stack_depth = max(
        (int(e.get("undoStackDepth", 0)) for e in edits),
        default=0,
    )

    undo_count = sum(1 for ev in events if ev.get("eventType") == "undo")
    redo_count = sum(1 for ev in events if ev.get("eventType") == "redo")

    first_click_ev = next(
        (ev for ev in events if ev.get("eventType") == "first_click"),
        None,
    )
    first_click_latency = _seconds_between(
        started_at,
        _parse_iso(first_click_ev["timestamp"]) if first_click_ev else None,
    )

    session_end_ev = next(
        (ev for ev in events if ev.get("eventType") == "session_end"),
        None,
    )
    if session_end_ev is not None:
        end_ts = _parse_iso(session_end_ev["timestamp"])
    elif edits:
        end_ts = _parse_iso(edits[-1].get("timestamp", ""))
    elif events:
        end_ts = _parse_iso(events[-1].get("timestamp", ""))
    else:
        end_ts = None
    session_duration = _seconds_between(started_at, end_ts)

    row = {
        "session_id": sid,
        "participant_id": session_meta.get("participantId"),
        "task_id": session_meta.get("taskId"),
        "session_started_at": session_meta.get("startedAt"),
        "total_edits": total_edits,
        "undo_count": undo_count,
        "redo_count": redo_count,
        "first_click_latency_seconds": first_click_latency,
        "session_duration_seconds": session_duration,
        "distinct_action_types": distinct_action_types,
        "max_undo_stack_depth": max_undo_stack_depth,
    }
    print(
        f"[extract_metrics] sid={sid[:8]} P={row['participant_id']} task={row['task_id']} "
        f"edits={total_edits} undo={undo_count} dur={session_duration}"
    )
    return row


def collect_all_sessions(log_root: Path) -> list[Path]:
    """Walk log_root/<datetime>/session_*.json files."""
    if not log_root.exists():
        print(f"[extract_metrics] log root missing: {log_root}")
        return []
    paths = sorted(log_root.glob("*/session_*.json"))
    print(f"[extract_metrics] found {len(paths)} session files under {log_root}")
    return paths


COLUMNS = [
    "session_id",
    "participant_id",
    "task_id",
    "session_started_at",
    "total_edits",
    "undo_count",
    "redo_count",
    "first_click_latency_seconds",
    "session_duration_seconds",
    "distinct_action_types",
    "max_undo_stack_depth",
]


def main(args: argparse.Namespace) -> None:
    log_root = Path(args.log_root)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session_paths = collect_all_sessions(log_root)

    rows: list[dict[str, Any]] = []
    for p in session_paths:
        row = compute_metrics_for_session(p)
        if row is not None:
            rows.append(row)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"\n[extract_metrics] wrote {len(rows)} rows → {output_path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract per-trial behavior metrics from edit logs")
    p.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT,
                   help=f"root containing <datetime>/session_*.json (default: {DEFAULT_LOG_ROOT})")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help=f"output CSV path (default: {DEFAULT_OUTPUT})")
    return p.parse_args()


if __name__ == "__main__":
    main(parse_args())
