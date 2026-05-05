"""
3-level statistical analysis of AI baseline vs human-built MAS workflows.

Reads master_table.csv (built by build_master_table.py) and produces:

  - analysis_summary.md   — Mann-Whitney U / Wilcoxon / Spearman tables
  - plots/pass_at_1_per_topology.png    — phase1 vs phase2 means per topology
  - plots/behavior_correlations.png     — scatter: pass@1 vs behavior metrics
  - plots/per_participant_strip.png     — pass@1 distribution per participant

Statistical tests:
  Aggregate    — Mann-Whitney U on pass@1: phase1 group vs phase2 group
  Topology     — Mann-Whitney U per of 5 topologies
  Participant  — Wilcoxon signed-rank on (phase2 - phase1) paired by topology
  Correlations — Spearman rho on phase2: pass@1 vs (duration, edits, undo, n_agents)

Empty / single-group data is gracefully skipped with print logs.
"""
import argparse
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")  # headless / no GUI
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "backend" / "data" / "master_table.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "backend" / "data" / "analysis"

TOPOLOGIES = ["chain", "centralized", "cycle", "hierarchical", "mesh"]


def _load_master(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        print(f"[analyze_gap] master table missing: {path}")
        return None
    df = pd.read_csv(path)
    print(f"[analyze_gap] loaded {len(df)} rows from {path}")
    if df.empty:
        print(f"[analyze_gap] master table is empty")
        return df
    return df


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    p1 = df[df["source"] == "phase1"].copy()
    p2 = df[df["source"] == "phase2"].copy()
    print(f"[analyze_gap] phase1 rows={len(p1)}, phase2 rows={len(p2)}")
    return p1, p2


def aggregate_test(p1: pd.DataFrame, p2: pd.DataFrame) -> list[str]:
    """Mann-Whitney U on overall pass@1."""
    lines = ["## Aggregate (overall AI vs human)\n"]
    a, b = p1["pass_at_1"].dropna(), p2["pass_at_1"].dropna()
    if len(a) < 1 or len(b) < 1:
        lines.append(f"- skipped: phase1 n={len(a)}, phase2 n={len(b)}")
        return lines

    lines.append(f"- phase1 n={len(a)}, mean={a.mean():.3f}, median={a.median():.3f}")
    lines.append(f"- phase2 n={len(b)}, mean={b.mean():.3f}, median={b.median():.3f}")

    if len(a) >= 1 and len(b) >= 1:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        lines.append(f"- Mann-Whitney U: U={u:.2f}, p={p:.4f}")
    return lines


def per_topology_test(p1: pd.DataFrame, p2: pd.DataFrame) -> list[str]:
    """Mann-Whitney U for each of 5 topologies."""
    lines = ["\n## Per topology (Mann-Whitney U on pass@1)\n"]
    lines.append("| topology | phase1 n | phase1 mean | phase2 n | phase2 mean | U | p |")
    lines.append("|---|---|---|---|---|---|---|")
    for t in TOPOLOGIES:
        a = p1[p1["topology"] == t]["pass_at_1"].dropna()
        b = p2[p2["topology"] == t]["pass_at_1"].dropna()
        if len(a) < 1 or len(b) < 1:
            lines.append(f"| {t} | {len(a)} | {a.mean() if len(a) else '—':.3} | {len(b)} | {b.mean() if len(b) else '—':.3} | — | — |")
            continue
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        lines.append(f"| {t} | {len(a)} | {a.mean():.3f} | {len(b)} | {b.mean():.3f} | {u:.2f} | {p:.4f} |")
    return lines


def participant_paired_test(p1: pd.DataFrame, p2: pd.DataFrame) -> list[str]:
    """
    Wilcoxon signed-rank on (phase2 - phase1) pairs, paired by topology.
    For each phase2 row, we look up the phase1 baseline for the same topology
    and compute the diff. With N=10 participants × ~5 topologies = ~50 pairs.
    """
    lines = ["\n## Participant level (Wilcoxon signed-rank)\n"]
    if p2.empty:
        lines.append("- skipped: phase2 empty")
        return lines

    p1_lookup = p1.set_index("topology")["pass_at_1"].to_dict() if not p1.empty else {}
    if not p1_lookup:
        lines.append("- skipped: no phase1 baseline to pair against")
        return lines

    diffs = []
    for _, row in p2.iterrows():
        t = row["topology"]
        if t in p1_lookup:
            diffs.append(row["pass_at_1"] - p1_lookup[t])
    if len(diffs) < 2:
        lines.append(f"- skipped: only {len(diffs)} paired observations (need ≥2)")
        return lines

    arr = np.array(diffs)
    if np.all(arr == 0):
        lines.append(f"- skipped: all diffs are 0 (Wilcoxon undefined)")
        return lines

    w, p = stats.wilcoxon(arr)
    lines.append(f"- n_pairs={len(arr)}, mean_diff={arr.mean():+.3f}, median_diff={np.median(arr):+.3f}")
    lines.append(f"- Wilcoxon: W={w:.2f}, p={p:.4f}")
    return lines


def correlation_test(p2: pd.DataFrame) -> list[str]:
    """Spearman rho between pass@1 and behavior metrics on phase2 rows."""
    lines = ["\n## Behavior correlations (Spearman rho, phase2 only)\n"]
    if p2.empty:
        lines.append("- skipped: phase2 empty")
        return lines

    targets = [
        ("authoring_duration_seconds", "authoring duration"),
        ("total_edits", "total edits"),
        ("undo_count", "undo count"),
        ("agent_count", "agent count"),
    ]
    lines.append("| metric | n | rho | p |")
    lines.append("|---|---|---|---|")
    for col, label in targets:
        if col not in p2.columns:
            lines.append(f"| {label} | — | — | — |")
            continue
        sub = p2[[col, "pass_at_1"]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < 3:
            lines.append(f"| {label} | {len(sub)} | — | — |  (need n≥3)")
            continue
        rho, p = stats.spearmanr(sub[col], sub["pass_at_1"])
        lines.append(f"| {label} | {len(sub)} | {rho:+.3f} | {p:.4f} |")
    return lines


# ---------- plotting ----------

def plot_pass_at_1_per_topology(p1: pd.DataFrame, p2: pd.DataFrame, out_path: Path) -> None:
    means_p1 = [p1[p1["topology"] == t]["pass_at_1"].mean() for t in TOPOLOGIES]
    means_p2 = [p2[p2["topology"] == t]["pass_at_1"].mean() for t in TOPOLOGIES]
    means_p1 = [0 if pd.isna(x) else x for x in means_p1]
    means_p2 = [0 if pd.isna(x) else x for x in means_p2]

    x = np.arange(len(TOPOLOGIES))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, means_p1, width, label="Phase 1 (AI baseline)", color="#5b8def")
    ax.bar(x + width / 2, means_p2, width, label="Phase 2 (human-built)", color="#ef8d5b")
    ax.set_xticks(x)
    ax.set_xticklabels(TOPOLOGIES)
    ax.set_ylabel("pass@1")
    ax.set_ylim(0, 1)
    ax.set_title("HumanEval pass@1: AI baseline vs human-built per topology")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"[analyze_gap] wrote plot {out_path}")


def plot_behavior_correlations(p2: pd.DataFrame, out_path: Path) -> None:
    if p2.empty:
        print(f"[analyze_gap] skip behavior plot: phase2 empty")
        return

    targets = [
        ("authoring_duration_seconds", "Authoring duration (s)"),
        ("total_edits", "Total edits"),
        ("undo_count", "Undo count"),
        ("agent_count", "Agent count"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for ax, (col, label) in zip(axes.flat, targets):
        if col not in p2.columns:
            ax.set_title(f"{label} (column missing)")
            continue
        sub = p2[[col, "pass_at_1"]].apply(pd.to_numeric, errors="coerce").dropna()
        if sub.empty:
            ax.set_title(f"{label} (no data)")
            continue
        ax.scatter(sub[col], sub["pass_at_1"], alpha=0.7, color="#ef8d5b")
        ax.set_xlabel(label)
        ax.set_ylabel("pass@1")
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)
    fig.suptitle("Phase 2: pass@1 vs behavior metrics")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"[analyze_gap] wrote plot {out_path}")


def plot_per_participant_strip(p2: pd.DataFrame, out_path: Path) -> None:
    if p2.empty or "participant_id" not in p2.columns:
        print(f"[analyze_gap] skip participant plot: phase2 empty or no participant_id")
        return
    sub = p2.dropna(subset=["participant_id", "pass_at_1"])
    sub = sub[sub["participant_id"].astype(str).str.len() > 0]
    if sub.empty:
        print(f"[analyze_gap] skip participant plot: no participant rows")
        return

    participants = sorted(sub["participant_id"].unique())
    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(participants)), 5))
    rng = np.random.default_rng(42)
    for i, pid in enumerate(participants):
        vals = sub[sub["participant_id"] == pid]["pass_at_1"].values
        jitter = rng.uniform(-0.1, 0.1, size=len(vals))
        ax.scatter(np.full(len(vals), i) + jitter, vals, alpha=0.7, color="#ef8d5b")
    ax.set_xticks(range(len(participants)))
    ax.set_xticklabels(participants, rotation=30)
    ax.set_ylabel("pass@1")
    ax.set_ylim(0, 1)
    ax.set_title("Phase 2: per-participant pass@1 distribution")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"[analyze_gap] wrote plot {out_path}")


def main(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    df = _load_master(Path(args.input))
    if df is None or df.empty:
        print(f"[analyze_gap] aborting: no data")
        return

    p1, p2 = _split(df)

    summary_lines = ["# AI–Human Gap Analysis\n"]
    summary_lines.extend(aggregate_test(p1, p2))
    summary_lines.extend(per_topology_test(p1, p2))
    summary_lines.extend(participant_paired_test(p1, p2))
    summary_lines.extend(correlation_test(p2))

    summary_path = out_dir / "analysis_summary.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"\n[analyze_gap] wrote summary {summary_path}")

    plot_pass_at_1_per_topology(p1, p2, plots_dir / "pass_at_1_per_topology.png")
    plot_behavior_correlations(p2, plots_dir / "behavior_correlations.png")
    plot_per_participant_strip(p2, plots_dir / "per_participant_strip.png")

    print("\n=== analysis_summary.md ===")
    print(summary_path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="3-level AI vs human gap analysis on master_table.csv")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                   help=f"master_table.csv path (default: {DEFAULT_INPUT})")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                   help=f"output dir for summary + plots/ (default: {DEFAULT_OUTPUT_DIR})")
    return p.parse_args()


if __name__ == "__main__":
    main(parse_args())
