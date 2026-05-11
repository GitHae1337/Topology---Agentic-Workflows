"""Analyze thinking-style x topology matrix results.

Reads a results jsonl produced by run_thinking_style_matrix.py and writes
analysis_summary.md plus plots/ and tables/ under the output directory.

Sections:
  A. Alignment hypothesis (5x5 heatmap, paired Wilcoxon, per-pair effect)
  B. Difficulty moderator (level x days subgroup analysis)
  C. Failure mode (3-stage decomposition + per-hard-constraint rate)
  D. Cost (duration / msg per topology, cost-quality scatter)
  E. Off-diagonal asymmetry (M[i,j] vs M[j,i])
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

STYLE_ORDER = ["sas", "independent", "centralized", "decentralized", "hybrid"]
TOPOLOGY_ORDER = STYLE_ORDER  # same set; matrix uses identical ordering


def load_results(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    df = pd.json_normalize(rows)
    df["pass"] = df["metrics.final_pass"].astype(bool)
    df["delivery"] = df["metrics.delivery"].astype(bool)
    df["cs_pass"] = df["metrics.commonsense_pass_macro"].astype(bool)
    df["hd_pass"] = df["metrics.hard_pass_macro"].astype(bool)
    return df


def section_a_alignment(df: pd.DataFrame, out_dir: Path) -> dict:
    mat = df.groupby(["style_id", "topology"])["pass"].mean().unstack()
    mat = mat.reindex(index=STYLE_ORDER, columns=TOPOLOGY_ORDER)

    fig, ax = plt.subplots(figsize=(7.5, 6))
    im = ax.imshow(mat.values, cmap="YlOrRd", vmin=0, vmax=max(mat.values.max(), 0.5))
    ax.set_xticks(range(5))
    ax.set_yticks(range(5))
    ax.set_xticklabels(TOPOLOGY_ORDER, rotation=20)
    ax.set_yticklabels(STYLE_ORDER)
    ax.set_xlabel("topology (executor)")
    ax.set_ylabel("style_id (query phrasing)")
    ax.set_title("pass@1 — 5×5 alignment matrix (n=90 tasks per cell)")
    vmax = mat.values.max()
    for i in range(5):
        for j in range(5):
            v = mat.values[i, j]
            ax.text(
                j, i, f"{v:.2f}",
                ha="center", va="center",
                color="black" if v < vmax * 0.55 else "white",
                fontweight="bold" if i == j else "normal",
            )
    plt.colorbar(im, ax=ax, label="pass@1")
    plt.tight_layout()
    plt.savefig(out_dir / "plots" / "pass_at_1_heatmap.png", dpi=120)
    plt.close()

    mat.to_csv(out_dir / "tables" / "pass_at_1_matrix.csv")

    style_marginal = (
        df.groupby("style_id")["pass"].agg(["mean", "count"]).reindex(STYLE_ORDER)
    )
    topo_marginal = (
        df.groupby("topology")["pass"].agg(["mean", "count"]).reindex(TOPOLOGY_ORDER)
    )
    style_marginal.to_csv(out_dir / "tables" / "style_marginal.csv")
    topo_marginal.to_csv(out_dir / "tables" / "topology_marginal.csv")

    df_a = df.assign(aligned=df["style_id"] == df["topology"])
    per_task = (
        df_a.groupby(["task_id", "aligned"])["pass"].mean().unstack()
        .rename(columns={False: "misaligned", True: "aligned"})
        .dropna()
    )
    diff = per_task["aligned"] - per_task["misaligned"]
    w_stat, w_p = stats.wilcoxon(diff, alternative="greater")
    cohen_d = float(diff.mean() / diff.std()) if diff.std() > 0 else float("nan")

    diag_rows = []
    for s in STYLE_ORDER:
        aligned_cell = mat.loc[s, s]
        off_diag_row = mat.drop(columns=s).loc[s].mean()
        diag_rows.append(
            {
                "pair": s,
                "aligned": aligned_cell,
                "off_diag_mean": off_diag_row,
                "diff": aligned_cell - off_diag_row,
            }
        )
    diag = pd.DataFrame(diag_rows)
    diag.to_csv(out_dir / "tables" / "alignment_per_pair.csv", index=False)

    return {
        "matrix": mat,
        "style_marginal": style_marginal,
        "topo_marginal": topo_marginal,
        "wilcoxon_stat": float(w_stat),
        "wilcoxon_p": float(w_p),
        "cohen_d": cohen_d,
        "aligned_mean": float(per_task["aligned"].mean()),
        "misaligned_mean": float(per_task["misaligned"].mean()),
        "diag_pairs": diag,
        "n_paired_tasks": int(len(per_task)),
    }


def section_b_difficulty(df: pd.DataFrame, out_dir: Path) -> dict:
    df_b = df.assign(aligned=df["style_id"] == df["topology"])

    cell_agg = (
        df_b.groupby(["level", "days", "aligned"])["pass"].mean().unstack()
        .rename(columns={False: "misaligned", True: "aligned"})
    )
    cell_agg["diff"] = cell_agg["aligned"] - cell_agg["misaligned"]

    level_agg = (
        df_b.groupby(["level", "aligned"])["pass"].mean().unstack()
        .rename(columns={False: "misaligned", True: "aligned"})
        .reindex(["easy", "medium", "hard"])
    )
    level_agg["diff"] = level_agg["aligned"] - level_agg["misaligned"]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(level_agg))
    width = 0.36
    ax.bar(x - width / 2, level_agg["misaligned"], width, label="misaligned (n=20 cells/task)", color="#888")
    ax.bar(x + width / 2, level_agg["aligned"], width, label="aligned (n=5 cells/task)", color="#d6604d")
    ax.set_xticks(x)
    ax.set_xticklabels(level_agg.index)
    ax.set_ylabel("pass@1")
    ax.set_title("Alignment effect by difficulty level")
    ax.legend()
    ax.set_ylim(0, 1)
    for i, lvl in enumerate(level_agg.index):
        ax.text(i - width / 2, level_agg.loc[lvl, "misaligned"] + 0.02,
                f"{level_agg.loc[lvl, 'misaligned']:.2f}", ha="center", fontsize=9)
        ax.text(i + width / 2, level_agg.loc[lvl, "aligned"] + 0.02,
                f"{level_agg.loc[lvl, 'aligned']:.2f}", ha="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(out_dir / "plots" / "alignment_by_level.png", dpi=120)
    plt.close()

    cell_agg.to_csv(out_dir / "tables" / "alignment_by_cell.csv")
    level_agg.to_csv(out_dir / "tables" / "alignment_by_level.csv")

    return {"cell_agg": cell_agg, "level_agg": level_agg}


def _fail_reason(row: pd.Series) -> str:
    if not row["delivery"]:
        return "no_plan"
    if not row["cs_pass"]:
        return "commonsense_fail"
    if not row["hd_pass"]:
        return "hard_constraint_fail"
    return "passed"


def section_c_failure(df: pd.DataFrame, out_dir: Path) -> dict:
    df_c = df.copy()
    df_c["fail_reason"] = df_c.apply(_fail_reason, axis=1)

    fail_order = ["passed", "hard_constraint_fail", "commonsense_fail", "no_plan"]
    topo_fail = (
        df_c.groupby(["topology", "fail_reason"]).size().unstack(fill_value=0)
        .reindex(index=TOPOLOGY_ORDER)
    )
    for col in fail_order:
        if col not in topo_fail.columns:
            topo_fail[col] = 0
    topo_fail = topo_fail[fail_order]
    topo_fail_pct = topo_fail.div(topo_fail.sum(axis=1), axis=0) * 100

    colors = {
        "passed": "#5aae61",
        "hard_constraint_fail": "#f4a582",
        "commonsense_fail": "#d6604d",
        "no_plan": "#404040",
    }
    fig, ax = plt.subplots(figsize=(9, 5))
    bottom = np.zeros(len(topo_fail_pct))
    for col in fail_order:
        vals = topo_fail_pct[col].values
        ax.bar(range(len(topo_fail_pct)), vals, bottom=bottom, label=col, color=colors[col])
        bottom += vals
    ax.set_xticks(range(len(topo_fail_pct)))
    ax.set_xticklabels(topo_fail_pct.index)
    ax.set_ylabel("% of trials")
    ax.set_title("Failure mode decomposition by topology")
    ax.legend(loc="lower right", framealpha=0.9)
    plt.tight_layout()
    plt.savefig(out_dir / "plots" / "failure_mode_by_topology.png", dpi=120)
    plt.close()

    topo_fail.to_csv(out_dir / "tables" / "failure_mode_count.csv")
    topo_fail_pct.to_csv(out_dir / "tables" / "failure_mode_pct.csv")

    hard_keys = [
        "valid_cuisine",
        "valid_room_rule",
        "valid_transportation",
        "valid_room_type",
        "valid_cost",
    ]
    parts = []
    for k in hard_keys:
        col = f"metrics.hard_per_item.{k}"
        if col not in df_c.columns:
            continue
        sub = df_c[df_c[col].apply(lambda v: isinstance(v, list))][["topology", col]].copy()
        sub["passed"] = sub[col].apply(lambda v: bool(v[0]) if v[0] is not None else True)
        sub["constraint"] = k
        parts.append(sub[["topology", "constraint", "passed"]])
    cdf = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["topology", "constraint", "passed"]
    )
    constraint_pass = (
        cdf.groupby(["topology", "constraint"])["passed"].mean().unstack()
        .reindex(index=TOPOLOGY_ORDER)
    )
    constraint_n = (
        cdf.groupby(["topology", "constraint"]).size().unstack().reindex(index=TOPOLOGY_ORDER)
    )
    constraint_pass.to_csv(out_dir / "tables" / "hard_constraint_pass_rate.csv")
    constraint_n.to_csv(out_dir / "tables" / "hard_constraint_n.csv")

    return {
        "topo_fail": topo_fail,
        "topo_fail_pct": topo_fail_pct,
        "constraint_pass": constraint_pass,
        "constraint_n": constraint_n,
    }


def section_d_cost(df: pd.DataFrame, out_dir: Path) -> dict:
    cost = df.groupby("topology").agg(
        pass_at_1=("pass", "mean"),
        duration_mean=("duration_seconds", "mean"),
        duration_median=("duration_seconds", "median"),
        msg_count_mean=("message_count", "mean"),
    ).reindex(TOPOLOGY_ORDER)
    cost["pass_per_second"] = cost["pass_at_1"] / cost["duration_mean"]
    cost.to_csv(out_dir / "tables" / "cost_per_topology.csv")

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    for color, t in zip(palette, TOPOLOGY_ORDER):
        sub = cost.loc[t]
        ax.scatter(sub["duration_mean"], sub["pass_at_1"], s=220, color=color, edgecolor="black")
        ax.annotate(
            t,
            (sub["duration_mean"], sub["pass_at_1"]),
            xytext=(8, 6),
            textcoords="offset points",
            fontsize=11,
            fontweight="bold",
        )
    ax.set_xlabel("mean duration per trial (s)")
    ax.set_ylabel("pass@1")
    ax.set_title("Cost-quality tradeoff per topology")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "plots" / "cost_quality.png", dpi=120)
    plt.close()

    return {"cost": cost}


def section_e_asymmetry(mat: pd.DataFrame, out_dir: Path) -> dict:
    rows = []
    for i, s_i in enumerate(STYLE_ORDER):
        for j, s_j in enumerate(STYLE_ORDER):
            if i < j:
                ij = mat.loc[s_i, s_j]
                ji = mat.loc[s_j, s_i]
                rows.append(
                    {
                        "pair": f"{s_i} ↔ {s_j}",
                        "style_i_topo_j": ij,
                        "style_j_topo_i": ji,
                        "abs_diff": abs(ij - ji),
                    }
                )
    asym_df = pd.DataFrame(rows).sort_values("abs_diff", ascending=False).reset_index(drop=True)
    asym_df.to_csv(out_dir / "tables" / "off_diagonal_asymmetry.csv", index=False)
    return {"asym_df": asym_df}


def write_summary(out_dir: Path, results: dict, n_total: int, n_tasks: int) -> None:
    a = results["alignment"]
    b = results["difficulty"]
    c = results["failure"]
    d = results["cost"]
    e = results["asymmetry"]

    overall_pass = (n_total - results["n_failed"]) / n_total * 100

    md = []
    md.append("# Thinking-style × Topology Analysis\n")
    md.append(f"- N trials: **{n_total}**\n")
    md.append(f"- N tasks: **{n_tasks}** (90 task pilot, 9 difficulty cells × 10 tasks)\n")
    md.append(f"- Overall pass@1: **{overall_pass:.2f}%**\n")
    md.append(f"- Styles: {', '.join(STYLE_ORDER)}\n")
    md.append(f"- Topologies: {', '.join(TOPOLOGY_ORDER)}\n\n")

    md.append("## A. Alignment hypothesis\n")
    md.append("### A.1 5×5 pass@1 matrix (rows = style, cols = topology)\n")
    md.append("```\n" + a["matrix"].to_string(float_format="%.3f") + "\n```\n")
    md.append("![heatmap](plots/pass_at_1_heatmap.png)\n\n")

    md.append("### A.2 Marginal effects\n")
    md.append("**Style (query phrasing) main effect:**\n")
    md.append("```\n" + a["style_marginal"].to_string(float_format="%.3f") + "\n```\n")
    md.append("**Topology (executor) main effect:**\n")
    md.append("```\n" + a["topo_marginal"].to_string(float_format="%.3f") + "\n```\n\n")

    md.append("### A.3 Diagonal vs off-diagonal — paired Wilcoxon (per-task)\n")
    md.append(f"- aligned mean (per-task pass@1): **{a['aligned_mean']:.4f}**\n")
    md.append(f"- misaligned mean (per-task pass@1): **{a['misaligned_mean']:.4f}**\n")
    md.append(f"- mean diff (aligned − misaligned): **{a['aligned_mean'] - a['misaligned_mean']:+.4f}**\n")
    md.append(
        f"- Wilcoxon W = {a['wilcoxon_stat']:.1f}, "
        f"p = {a['wilcoxon_p']:.4g} (one-sided H1: aligned > misaligned)\n"
    )
    md.append(f"- Cohen's d (per-task diff): {a['cohen_d']:.3f}\n")
    md.append(f"- N paired tasks: {a['n_paired_tasks']}\n\n")

    md.append("### A.4 Per-pair alignment effect (diagonal cell vs row off-diagonal mean)\n")
    md.append("```\n" + a["diag_pairs"].to_string(index=False, float_format="%.3f") + "\n```\n\n")

    md.append("## B. Difficulty moderator\n")
    md.append("### B.1 by level\n")
    md.append("```\n" + b["level_agg"].to_string(float_format="%.3f") + "\n```\n")
    md.append("![alignment by level](plots/alignment_by_level.png)\n\n")
    md.append("### B.2 by 9-cell (level × days)\n")
    md.append("```\n" + b["cell_agg"].to_string(float_format="%.3f") + "\n```\n\n")

    md.append("## C. Failure mode\n")
    md.append("### C.1 Per-topology distribution (% of trials)\n")
    md.append("```\n" + c["topo_fail_pct"].to_string(float_format="%.2f") + "\n```\n")
    md.append("![failure mode](plots/failure_mode_by_topology.png)\n\n")
    md.append(
        "### C.2 Hard-constraint pass rate per topology "
        "(conditional on commonsense gate passing — denominator below)\n"
    )
    md.append("**Pass rate:**\n")
    md.append("```\n" + c["constraint_pass"].to_string(float_format="%.3f") + "\n```\n")
    md.append("**Sample size (n):**\n")
    md.append("```\n" + c["constraint_n"].to_string() + "\n```\n\n")

    md.append("## D. Cost\n")
    md.append("```\n" + d["cost"].to_string(float_format="%.3f") + "\n```\n")
    md.append("![cost-quality](plots/cost_quality.png)\n\n")

    md.append("## E. Off-diagonal asymmetry\n")
    md.append(
        "Pairs (i, j) where M[i, j] = pass@1(style_i, topology_j) and the transpose, "
        "sorted by |diff|.\n\n"
    )
    md.append("```\n" + e["asym_df"].to_string(index=False, float_format="%.3f") + "\n```\n")

    (out_dir / "analysis_summary.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "thinking_styles"
        / "results_9cell_10each.jsonl",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "thinking_styles" / "analysis",
    )
    args = p.parse_args()

    out_dir = args.out_dir
    (out_dir / "plots").mkdir(parents=True, exist_ok=True)
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)

    df = load_results(args.input)
    n_tasks = df["task_id"].nunique()
    print(f"[analyze_thinking_style] loaded {len(df)} trials, {n_tasks} tasks")

    print("[analyze_thinking_style] section A: alignment")
    a = section_a_alignment(df, out_dir)
    print("[analyze_thinking_style] section B: difficulty moderator")
    b = section_b_difficulty(df, out_dir)
    print("[analyze_thinking_style] section C: failure mode")
    c = section_c_failure(df, out_dir)
    print("[analyze_thinking_style] section D: cost")
    d = section_d_cost(df, out_dir)
    print("[analyze_thinking_style] section E: asymmetry")
    e = section_e_asymmetry(a["matrix"], out_dir)

    n_failed = int((~df["pass"]).sum())
    write_summary(
        out_dir,
        {"alignment": a, "difficulty": b, "failure": c, "cost": d, "asymmetry": e, "n_failed": n_failed},
        n_total=len(df),
        n_tasks=n_tasks,
    )
    print(f"[analyze_thinking_style] done → {out_dir / 'analysis_summary.md'}")


if __name__ == "__main__":
    main()
