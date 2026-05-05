"""Phase 3 — analyze the within-subjects topology study.

Reads:
  --phase0-dir <dir>   Phase 0 (AI baseline) per-topology results JSON
                       (one file per topology). Optional but recommended.
  --phase2-dir <dir>   Phase 2 (human-built) per-workflow results JSON
                       (one file per workflow + summary.json).
  --survey-csv <csv>   Optional Google-Forms export of trial-level survey
                       responses. Required columns: session_id,
                       participant_id, topology, nasa_tlx_total,
                       leppink_intrinsic, leppink_extraneous,
                       leppink_germane, seq, confidence.
                       (Other columns ignored.)

Writes (under --output, default Log/analysis/<datetime>):
  summary.md
  plots/topology_fpr.png         AI vs Human bar
  plots/ai_human_gap.png          per-topology gap
  plots/fail_breakdown.png        which constraints fail most often
  plots/cognitive_load.png        Leppink 3 subscale (if survey-csv)
  plots/cog_load_vs_fpr.png       per-topology scatter (if survey-csv)

Statistics:
  - Within-subjects paired Wilcoxon signed-rank for (A,B) and (B,C) pairs.
    A=hierarchical, B=centralized, C=chain by default; override with --pair.
  - Spearman ρ between cognitive load and FPR per topology (if survey-csv).
"""
import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats


# ---------- I/O ----------

def _load_phase0(phase0_dir: Optional[Path]) -> dict[str, dict]:
    """Load Phase 0 per-topology results. Returns {topology_name: aggregate_dict}."""
    if not phase0_dir or not phase0_dir.exists():
        print(f"[analyze] phase0_dir missing or empty; skipping AI baseline section")
        return {}
    out = {}
    for path in sorted(phase0_dir.glob("results_*.json")):
        with path.open() as f:
            agg = json.load(f)
        topo = agg.get("topology_name", path.stem.replace("results_", ""))
        out[topo] = agg
        print(f"[analyze] phase0 loaded {topo}: final={agg.get('final_pass_rate')}")
    return out


def _load_phase2(phase2_dir: Path) -> list[dict]:
    """Load Phase 2 per-workflow records."""
    if not phase2_dir.exists():
        raise FileNotFoundError(f"phase2_dir not found: {phase2_dir}")
    records = []
    for path in sorted(phase2_dir.glob("results_workflow-*.json")):
        with path.open() as f:
            records.append(json.load(f))
    print(f"[analyze] phase2 loaded {len(records)} workflows")
    return records


def _load_survey(csv_path: Optional[Path]) -> Optional[pd.DataFrame]:
    if not csv_path or not csv_path.exists():
        print(f"[analyze] survey-csv missing; cognitive-load plots skipped")
        return None
    df = pd.read_csv(csv_path)
    print(f"[analyze] survey loaded: {len(df)} rows, cols={list(df.columns)}")
    return df


# ---------- core data shaping ----------

@dataclass
class TrialRow:
    """One participant × topology row, the unit of within-subjects analysis."""
    workflow_id: str
    participant_id: Optional[str]
    topology_label: str
    accuracy: float                      # mean Final Pass Rate over the workflow's evaluated tasks
    duration_seconds: float
    n_problems: int
    n_correct: int
    fail_breakdown: dict = field(default_factory=dict)


def _phase2_to_trial_rows(records: list[dict]) -> list[TrialRow]:
    rows = []
    for r in records:
        rows.append(TrialRow(
            workflow_id=r["workflow_id"],
            participant_id=r.get("participant_id"),
            topology_label=r["topology_label"],
            accuracy=r["accuracy"],
            duration_seconds=r["duration_seconds"],
            n_problems=r["n_problems"],
            n_correct=r["n_correct"],
            fail_breakdown=r.get("fail_breakdown") or {},
        ))
    return rows


def _paired_within_subject(
    rows: list[TrialRow],
    metric_fn,
    topo_a: str,
    topo_b: str,
) -> tuple[list[float], list[float], list[str]]:
    """Build paired arrays: for each participant who has BOTH topologies,
    return (a_values, b_values, participant_ids)."""
    by_pid_topo: dict[tuple[str, str], TrialRow] = {}
    for r in rows:
        if r.participant_id is None:
            continue
        by_pid_topo[(r.participant_id, r.topology_label)] = r

    pids_with_both = sorted({
        pid for (pid, _) in by_pid_topo
        if (pid, topo_a) in by_pid_topo and (pid, topo_b) in by_pid_topo
    })
    a_vals = [metric_fn(by_pid_topo[(pid, topo_a)]) for pid in pids_with_both]
    b_vals = [metric_fn(by_pid_topo[(pid, topo_b)]) for pid in pids_with_both]
    return a_vals, b_vals, pids_with_both


def _wilcoxon(a, b) -> dict:
    """Paired Wilcoxon signed-rank with descriptives."""
    if len(a) < 2 or len(b) < 2:
        return {"n": len(a), "stat": None, "p": None, "median_a": None, "median_b": None,
                "note": "n<2 paired observations; skipping test"}
    res = stats.wilcoxon(a, b)
    return {
        "n": len(a),
        "stat": float(res.statistic),
        "p": float(res.pvalue),
        "median_a": float(pd.Series(a).median()),
        "median_b": float(pd.Series(b).median()),
        "mean_a": float(pd.Series(a).mean()),
        "mean_b": float(pd.Series(b).mean()),
    }


# ---------- plots ----------

def _plot_topology_fpr(phase0: dict, rows: list[TrialRow], out_path: Path):
    topos = sorted(set([r.topology_label for r in rows]) | set(phase0.keys()))
    ai_fpr = [phase0.get(t, {}).get("final_pass_rate", float("nan")) for t in topos]
    human_means = []
    for t in topos:
        hits = [r.accuracy for r in rows if r.topology_label == t]
        human_means.append(sum(hits) / len(hits) if hits else float("nan"))

    x = list(range(len(topos)))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([i - width / 2 for i in x], ai_fpr, width, label="AI baseline")
    ax.bar([i + width / 2 for i in x], human_means, width, label="Human-built (mean)")
    ax.set_xticks(x)
    ax.set_xticklabels(topos)
    ax.set_ylabel("Final Pass Rate")
    ax.set_title("Topology FPR — AI baseline vs Human-built")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_ai_human_gap(phase0: dict, rows: list[TrialRow], out_path: Path):
    topos = sorted(set([r.topology_label for r in rows]) & set(phase0.keys()))
    if not topos:
        print(f"[analyze] no topology overlap between phase0 and phase2; skipping gap plot")
        return
    gaps = []
    for t in topos:
        ai = phase0[t].get("final_pass_rate", 0.0)
        hits = [r.accuracy for r in rows if r.topology_label == t]
        human = sum(hits) / len(hits) if hits else 0.0
        gaps.append(ai - human)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(topos, gaps)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_ylabel("AI FPR – Human FPR")
    ax.set_title("AI–Human Performance Gap per topology")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_fail_breakdown(rows: list[TrialRow], out_path: Path):
    by_topo_constraint: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for k, n in r.fail_breakdown.items():
            by_topo_constraint[r.topology_label][k] += n
    topos = sorted(by_topo_constraint.keys())
    if not topos:
        print(f"[analyze] no fail_breakdown data; skipping plot")
        return
    constraints = sorted({k for d in by_topo_constraint.values() for k in d})
    if not constraints:
        print(f"[analyze] no failures recorded across topologies; skipping plot")
        return

    fig, ax = plt.subplots(figsize=(10, max(4, len(constraints) * 0.35)))
    bottom = [0] * len(constraints)
    for topo in topos:
        vals = [by_topo_constraint[topo].get(k, 0) for k in constraints]
        ax.barh(constraints, vals, left=bottom, label=topo)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xlabel("Total failures across all participants/trials")
    ax.set_title("Constraint-level failure counts (stacked by topology)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_cog_load(survey: pd.DataFrame, out_path: Path):
    needed = {"topology", "leppink_intrinsic", "leppink_extraneous", "leppink_germane"}
    if not needed.issubset(survey.columns):
        print(f"[analyze] survey missing leppink cols; skipping cog-load plot")
        return
    grp = survey.groupby("topology")[["leppink_intrinsic", "leppink_extraneous", "leppink_germane"]].mean()
    fig, ax = plt.subplots(figsize=(8, 4))
    grp.plot(kind="bar", ax=ax)
    ax.set_ylabel("Mean Leppink subscale")
    ax.set_title("Cognitive load by topology (Leppink 3 subscales)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_cog_load_vs_fpr(survey: pd.DataFrame, rows: list[TrialRow], out_path: Path):
    if "session_id" not in survey.columns or "leppink_intrinsic" not in survey.columns:
        print(f"[analyze] survey missing session_id or leppink_intrinsic; skipping scatter")
        return
    # Join survey ↔ rows by session_id (if rows carry session_id; we kept
    # workflow_id but not session_id in TrialRow — use participant+topology).
    # Simpler: aggregate survey by (participant, topology), join by same key.
    if "participant_id" not in survey.columns:
        print(f"[analyze] survey missing participant_id; cannot join")
        return
    survey_g = survey.groupby(["participant_id", "topology"])["leppink_intrinsic"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(8, 5))
    for topo in sorted({r.topology_label for r in rows}):
        xs, ys = [], []
        for r in rows:
            if r.topology_label != topo or r.participant_id is None:
                continue
            match = survey_g[
                (survey_g.participant_id == r.participant_id) & (survey_g.topology == topo)
            ]
            if match.empty:
                continue
            xs.append(float(match.iloc[0].leppink_intrinsic))
            ys.append(r.accuracy)
        if xs:
            ax.scatter(xs, ys, label=topo)
    ax.set_xlabel("Leppink intrinsic load")
    ax.set_ylabel("Final Pass Rate (workflow mean)")
    ax.set_title("Cognitive load (intrinsic) vs FPR per topology")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------- summary writer ----------

def _write_summary(
    out_path: Path,
    args: argparse.Namespace,
    phase0: dict,
    rows: list[TrialRow],
    survey: Optional[pd.DataFrame],
    pair_a_b: tuple[str, str],
    pair_b_c: tuple[str, str],
):
    lines: list[str] = []
    lines.append(f"# Topology study analysis — {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"- phase0_dir: `{args.phase0_dir}`")
    lines.append(f"- phase2_dir: `{args.phase2_dir}`")
    lines.append(f"- survey_csv: `{args.survey_csv}`")
    lines.append(f"- pair (A, B): {pair_a_b}")
    lines.append(f"- pair (B, C): {pair_b_c}")
    lines.append("")

    # Phase 0 baseline table
    lines.append("## Phase 0 — AI baseline (per topology)")
    if phase0:
        lines.append("| topology | n_problems | delivery | cs_macro | hd_macro | final_pass | total_duration_s |")
        lines.append("|---|---|---|---|---|---|---|")
        for t in sorted(phase0.keys()):
            a = phase0[t]
            lines.append(
                f"| {t} | {a.get('n_problems')} | {a.get('delivery_rate', 0):.3f} | "
                f"{a.get('commonsense_pass_rate', 0):.3f} | {a.get('hard_pass_rate', 0):.3f} | "
                f"{a.get('final_pass_rate', 0):.3f} | {a.get('total_duration_seconds', 0):.1f} |"
            )
    else:
        lines.append("(no Phase 0 results loaded)")
    lines.append("")

    # Phase 2 per-topology summary
    lines.append("## Phase 2 — Human-built (per topology)")
    by_topo: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_topo[r.topology_label].append(r.accuracy)
    lines.append("| topology | n_workflows | mean FPR | median FPR |")
    lines.append("|---|---|---|---|")
    for t in sorted(by_topo.keys()):
        accs = by_topo[t]
        lines.append(
            f"| {t} | {len(accs)} | {sum(accs)/len(accs):.3f} | "
            f"{pd.Series(accs).median():.3f} |"
        )
    lines.append("")

    # Within-subjects pair tests on FPR
    lines.append("## Within-subjects paired Wilcoxon")
    for pair in (pair_a_b, pair_b_c):
        lines.append(f"### {pair[0]} vs {pair[1]} — FPR")
        a_vals, b_vals, pids = _paired_within_subject(rows, lambda r: r.accuracy, pair[0], pair[1])
        if not a_vals:
            lines.append(f"- 0 paired participants; skipped.")
            continue
        res = _wilcoxon(a_vals, b_vals)
        lines.append(f"- paired n: {res['n']}")
        lines.append(f"- median {pair[0]}: {res['median_a']:.3f}")
        lines.append(f"- median {pair[1]}: {res['median_b']:.3f}")
        lines.append(f"- W = {res['stat']:.3f}, p = {res['p']:.4f}" if res['stat'] is not None else f"- {res['note']}")

    # Survey-driven analyses
    if survey is not None and "topology" in survey.columns:
        lines.append("")
        lines.append("## Survey-derived metrics (Leppink / NASA-TLX / SEQ)")
        candidate_metrics = [
            "nasa_tlx_total", "leppink_intrinsic", "leppink_extraneous",
            "leppink_germane", "seq", "confidence",
        ]
        for metric in candidate_metrics:
            if metric not in survey.columns:
                continue
            lines.append(f"### {metric}")
            lines.append("| topology | n | mean | median |")
            lines.append("|---|---|---|---|")
            for t in sorted(survey["topology"].dropna().unique()):
                vals = survey[survey.topology == t][metric].dropna()
                if vals.empty:
                    continue
                lines.append(f"| {t} | {len(vals)} | {vals.mean():.3f} | {vals.median():.3f} |")
            lines.append("")
            for pair in (pair_a_b, pair_b_c):
                a = survey[survey.topology == pair[0]].dropna(subset=[metric])
                b = survey[survey.topology == pair[1]].dropna(subset=[metric])
                merge = a.merge(b, on="participant_id", suffixes=("_a", "_b")) \
                    if "participant_id" in survey.columns else None
                if merge is None or merge.empty:
                    continue
                col_a = f"{metric}_a"
                col_b = f"{metric}_b"
                res = _wilcoxon(merge[col_a].tolist(), merge[col_b].tolist())
                lines.append(
                    f"- ({pair[0]} vs {pair[1]}) paired n={res['n']}, "
                    + (f"W={res['stat']:.3f}, p={res['p']:.4f}" if res['stat'] is not None else res['note'])
                )
            lines.append("")

    # Notes
    lines.append("## Notes")
    lines.append("- Wilcoxon signed-rank assumes paired (within-subjects) data; "
                 "drops participants who did not complete both topologies.")
    lines.append("- Phase 0 numbers are the cached AI baseline (no human variance).")
    lines.append("- Cognitive-load survey columns (NASA-TLX/Leppink/SEQ/confidence) "
                 "are pulled from --survey-csv if provided.")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[analyze] wrote {out_path}")


# ---------- main ----------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 3 — analyze topology study results")
    p.add_argument("--phase0-dir", type=Path, default=None,
                   help="Directory of Phase 0 results_<topology>.json files.")
    p.add_argument("--phase2-dir", type=Path, required=True,
                   help="Directory of Phase 2 per-workflow results JSON files.")
    p.add_argument("--survey-csv", type=Path, default=None,
                   help="Google-Forms export with per-trial survey columns.")
    p.add_argument("--pair", nargs=3, metavar=("A", "B", "C"),
                   default=["hierarchical", "centralized", "chain"],
                   help="Top-3 topologies for paired (A,B), (B,C) tests.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output dir (default: Log/analysis/<datetime>).")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    out_dir = args.output or (
        Path(__file__).resolve().parents[2]
        / "Log" / "analysis" / datetime.now().strftime("%Y-%m-%d-%H-%M")
    )
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    print(f"[analyze] output: {out_dir}")

    phase0 = _load_phase0(args.phase0_dir)
    phase2_records = _load_phase2(args.phase2_dir)
    rows = _phase2_to_trial_rows(phase2_records)
    survey = _load_survey(args.survey_csv)

    pair_a_b = (args.pair[0], args.pair[1])
    pair_b_c = (args.pair[1], args.pair[2])

    # Plots
    _plot_topology_fpr(phase0, rows, plots_dir / "topology_fpr.png")
    _plot_ai_human_gap(phase0, rows, plots_dir / "ai_human_gap.png")
    _plot_fail_breakdown(rows, plots_dir / "fail_breakdown.png")
    if survey is not None:
        _plot_cog_load(survey, plots_dir / "cognitive_load.png")
        _plot_cog_load_vs_fpr(survey, rows, plots_dir / "cog_load_vs_fpr.png")

    _write_summary(
        out_dir / "summary.md",
        args, phase0, rows, survey,
        pair_a_b, pair_b_c,
    )

    print(f"\n[analyze] done. Open {out_dir}")


if __name__ == "__main__":
    main()
