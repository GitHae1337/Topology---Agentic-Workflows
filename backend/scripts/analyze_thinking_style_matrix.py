"""Aggregate the thinking-style x topology matrix into per-cell means.

Reads `matrix_results_*.jsonl` produced by run_thinking_style_matrix and
prints / writes a 5x5 grid of mean metric values for each (style, topology)
pair. Stays deliberately minimal — heavier statistical analysis is left for
the researcher to add after eyeballing the grid.

Usage:
    python -m backend.scripts.analyze_thinking_style_matrix \\
        --input backend/data/thinking_styles/matrix_results_20260508_143015.jsonl
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


METRICS = ["final_pass", "commonsense_pass_macro", "hard_pass_macro", "delivery"]


def _coerce(value) -> float:
    """Coerce per-trial metric value to a float for averaging.

    `final_pass` and `delivery` are bool/0-1; macros are already floats. None
    is treated as 0 — a missing metric counts as a failed trial.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)


def load_records(path: Path) -> List[dict]:
    print(f"[analyze_thinking_style_matrix] reading {path}")
    out: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    print(f"[analyze_thinking_style_matrix] loaded {len(out)} records")
    return out


def aggregate(
    records: List[dict],
) -> Tuple[Dict[Tuple[str, str], Dict[str, float]], List[str], List[str]]:
    """Group by (style_id, topology); return cell -> {metric: mean} + axes."""
    sums: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(
        lambda: {m: 0.0 for m in METRICS}
    )
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    styles: List[str] = []
    topos: List[str] = []
    seen_style = set()
    seen_topo = set()

    for r in records:
        sid = r["style_id"]
        topo = r["topology"]
        if sid not in seen_style:
            seen_style.add(sid)
            styles.append(sid)
        if topo not in seen_topo:
            seen_topo.add(topo)
            topos.append(topo)
        metrics = r.get("metrics") or {}
        for m in METRICS:
            sums[(sid, topo)][m] += _coerce(metrics.get(m))
        counts[(sid, topo)] += 1

    cells: Dict[Tuple[str, str], Dict[str, float]] = {}
    for key, total in sums.items():
        n = counts[key]
        cells[key] = {m: (total[m] / n if n else 0.0) for m in METRICS}
        cells[key]["n"] = n

    styles.sort()
    topos.sort()
    return cells, styles, topos


def group_by_task_cell(records: List[dict]) -> Dict[Tuple[str, int], List[dict]]:
    """Bucket records by (level, days) — the task cell label."""
    buckets: Dict[Tuple[str, int], List[dict]] = defaultdict(list)
    for r in records:
        lvl = r.get("level")
        days = r.get("days")
        if lvl is None or days is None:
            continue
        buckets[(lvl, int(days))].append(r)
    return buckets


def print_grid(
    cells: Dict[Tuple[str, str], Dict[str, float]],
    styles: List[str],
    topos: List[str],
    metric: str,
) -> None:
    print(f"\n=== {metric} (rows=style, cols=topology) ===")
    header = ["style \\ topo"] + topos + ["row_best"]
    print("\t".join(header))
    for sid in styles:
        row_vals = []
        for topo in topos:
            cell = cells.get((sid, topo))
            v = cell[metric] if cell else None
            row_vals.append(v)
        best_idx = max(
            (i for i, v in enumerate(row_vals) if v is not None),
            key=lambda i: row_vals[i],
            default=None,
        )
        cells_str = []
        for i, v in enumerate(row_vals):
            if v is None:
                cells_str.append("-")
            elif i == best_idx:
                cells_str.append(f"*{v:.3f}")
            else:
                cells_str.append(f"{v:.3f}")
        best_label = topos[best_idx] if best_idx is not None else "-"
        print("\t".join([sid] + cells_str + [best_label]))

    col_best = []
    for j, topo in enumerate(topos):
        col_vals = [
            (sid, cells.get((sid, topo), {}).get(metric))
            for sid in styles
        ]
        col_vals = [(s, v) for s, v in col_vals if v is not None]
        if not col_vals:
            col_best.append("-")
            continue
        winner = max(col_vals, key=lambda x: x[1])[0]
        col_best.append(winner)
    print("\t".join(["col_best", *col_best, ""]))


def write_csv(
    cells: Dict[Tuple[str, str], Dict[str, float]],
    styles: List[str],
    topos: List[str],
    output: Path,
    task_cell: Optional[Tuple[str, int]] = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    level_col = task_cell[0] if task_cell else "ALL"
    days_col = task_cell[1] if task_cell else "ALL"
    with output.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_level", "task_days", "style_id", "topology", "n", *METRICS])
        for sid in styles:
            for topo in topos:
                cell = cells.get((sid, topo))
                if not cell:
                    continue
                w.writerow([
                    level_col, days_col, sid, topo, int(cell["n"]),
                    *[f"{cell[m]:.4f}" for m in METRICS],
                ])
    print(f"[analyze_thinking_style_matrix] wrote {output}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="matrix_results_*.jsonl")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output (default: <input_stem>_cells.csv next to input)",
    )
    args = p.parse_args()

    records = load_records(args.input)
    if not records:
        print("[analyze_thinking_style_matrix] no records — nothing to do")
        return

    # ------- per task cell ((level, days) bucket) --------
    buckets = group_by_task_cell(records)
    out_csv = args.output or args.input.with_name(args.input.stem + "_cells.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows_csv: List[List[str]] = [
        ["task_level", "task_days", "style_id", "topology", "n", *METRICS]
    ]

    if buckets:
        for (lvl, days) in sorted(buckets.keys()):
            sub_records = buckets[(lvl, days)]
            print(f"\n########## TASK CELL: level={lvl} days={days}  (records={len(sub_records)}) ##########")
            cells, styles, topos = aggregate(sub_records)
            for m in METRICS:
                print_grid(cells, styles, topos, m)
            for sid in styles:
                for topo in topos:
                    cell = cells.get((sid, topo))
                    if not cell:
                        continue
                    rows_csv.append([
                        lvl, str(days), sid, topo, str(int(cell["n"])),
                        *[f"{cell[m]:.4f}" for m in METRICS],
                    ])

    # ------- overall (ignore task cell) --------
    print(f"\n########## OVERALL (records={len(records)}) ##########")
    cells, styles, topos = aggregate(records)
    for m in METRICS:
        print_grid(cells, styles, topos, m)
    for sid in styles:
        for topo in topos:
            cell = cells.get((sid, topo))
            if not cell:
                continue
            rows_csv.append([
                "ALL", "ALL", sid, topo, str(int(cell["n"])),
                *[f"{cell[m]:.4f}" for m in METRICS],
            ])

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for row in rows_csv:
            w.writerow(row)
    print(f"\n[analyze_thinking_style_matrix] wrote {out_csv}")


if __name__ == "__main__":
    main()
