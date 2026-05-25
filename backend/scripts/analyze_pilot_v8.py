"""
Analyze pilot_v8_full_gpt54mini_temp1.jsonl
- 180 task × 5 style × 4 topology = 3600 trial
- 4×4 view (decentralized style row 제외; topology side는 이미 4개)
- 4 difficulty conditions (easy / medium / hard / all)
- 4-test per condition: Wilcoxon / Permutation / Per-row max / 2-way ANOVA
- 4 heatmaps (4×4) with common vmin/vmax
"""

import json
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

ROOT = Path("/Users/joseph423/Kitae/Research/Topology/code")
SRC = ROOT / "backend/data/thinking_styles/pilot_v8_full_gpt54mini_temp1.jsonl"
OUT = ROOT / "backend/data/thinking_styles/analysis_v8_full_180"
TABLES = OUT / "tables"
PLOTS = OUT / "plots"
TABLES.mkdir(parents=True, exist_ok=True)
PLOTS.mkdir(parents=True, exist_ok=True)

# 4x4 view labels (decentralized style row excluded; topology already 4)
STYLES = ["sas", "independent", "centralized", "hybrid"]
TOPOS  = ["sas", "independent", "centralized", "hybrid"]
RNG = np.random.default_rng(42)
N_PERM = 100_000


def _partial_credit(m: dict) -> float:
    """Per-item micro pass rate across commonsense + hard, excluding nulls.
    Matches runner.py:186-200 definition."""
    passed = 0
    total = 0
    for kind in ("commonsense_per_item", "hard_per_item"):
        per = m.get(kind) or {}
        for _k, item in per.items():
            v = item[0] if isinstance(item, list) else item
            if v is None:
                continue
            total += 1
            if bool(v):
                passed += 1
    return passed / total if total else 0.0


def load() -> pd.DataFrame:
    rows = []
    with open(SRC) as f:
        for line in f:
            d = json.loads(line)
            rows.append({
                "task_id": d["task_id"],
                "level": d["level"],
                "days": d["days"],
                "style_id": d["style_id"],
                "topology": d["topology"],
                "final_pass": int(bool(d["metrics"]["final_pass"])),
                "partial_credit": _partial_credit(d["metrics"]),
            })
    return pd.DataFrame(rows)


def cell_mean_matrix(df: pd.DataFrame, metric: str = "final_pass") -> pd.DataFrame:
    """4x4 matrix of mean(metric), rows=style, cols=topology."""
    sub = df[df["style_id"].isin(STYLES) & df["topology"].isin(TOPOS)]
    m = (
        sub.groupby(["style_id", "topology"])[metric]
        .mean()
        .unstack("topology")
        .reindex(index=STYLES, columns=TOPOS)
    )
    return m


def wilcoxon_per_task(df: pd.DataFrame, metric: str = "final_pass") -> tuple[pd.DataFrame, dict]:
    """Per-task: aligned-cell mean (4 diag) vs misaligned-cell mean (12 off-diag).
    Returns per-task df and summary dict."""
    sub = df[df["style_id"].isin(STYLES) & df["topology"].isin(TOPOS)].copy()
    sub["aligned"] = sub["style_id"] == sub["topology"]
    g = (
        sub.groupby(["task_id", "level", "days", "aligned"])[metric]
        .mean()
        .unstack("aligned")
    )
    g = g.rename(columns={False: "misaligned_mean", True: "aligned_mean"}).reset_index()
    g["diff"] = g["aligned_mean"] - g["misaligned_mean"]
    g = g.dropna(subset=["aligned_mean", "misaligned_mean"])

    diffs = g["diff"].values
    nonzero = diffs[diffs != 0]
    if len(nonzero) >= 1:
        w_stat, p = stats.wilcoxon(g["aligned_mean"], g["misaligned_mean"], zero_method="wilcox")
        # Cohen's d on paired diffs
        sd = diffs.std(ddof=1)
        d_eff = float(diffs.mean() / sd) if sd > 0 else float("nan")
    else:
        w_stat, p, d_eff = float("nan"), float("nan"), float("nan")
    summary = {
        "n": int(len(g)),
        "aligned_mean": float(g["aligned_mean"].mean()),
        "misaligned_mean": float(g["misaligned_mean"].mean()),
        "diff": float(diffs.mean()),
        "W": float(w_stat),
        "p": float(p),
        "cohen_d": d_eff,
    }
    return g, summary


def permutation_test(M: pd.DataFrame) -> dict:
    """Random-relabel diagonal mean test on 4x4 cell-mean matrix."""
    vals = M.values.flatten()
    K = M.shape[0]
    diag_actual = float(np.mean([M.iloc[i, i] for i in range(K)]))
    perm_diag = np.empty(N_PERM)
    for i in range(N_PERM):
        RNG.shuffle(vals)
        perm_diag[i] = vals.reshape(K, K).diagonal().mean()
    p = float((perm_diag >= diag_actual).sum() / N_PERM)
    return {
        "diag_mean": diag_actual,
        "perm_mean": float(perm_diag.mean()),
        "perm_sd": float(perm_diag.std(ddof=1)),
        "p": p,
    }


def per_row_max(M: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    K = M.shape[0]
    rows = []
    winners = 0
    for s in STYLES:
        row = M.loc[s]
        winner = row.idxmax()
        diag = row[s]
        rows.append({"style": s, "diag_pass": diag, "winner": winner, "winner_pass": row.max(), "aligned_winner": winner == s})
        if winner == s:
            winners += 1
    p = float(stats.binomtest(winners, K, p=1 / K, alternative="greater").pvalue)
    df = pd.DataFrame(rows)
    return df, {"winners": int(winners), "K": int(K), "p": p}


def anova_ss(M: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """2-way ANOVA SS decomposition on cell-mean matrix."""
    K = M.shape[0]
    grand = float(M.values.mean())
    row_means = M.mean(axis=1).values
    col_means = M.mean(axis=0).values
    ss_total = float(((M.values - grand) ** 2).sum())
    ss_row = float(K * ((row_means - grand) ** 2).sum())
    ss_col = float(K * ((col_means - grand) ** 2).sum())
    ss_inter = ss_total - ss_row - ss_col
    rows = [
        {"source": "Style (prompt structure)", "SS": ss_row, "pct_total": 100 * ss_row / ss_total if ss_total else 0},
        {"source": "Topology", "SS": ss_col, "pct_total": 100 * ss_col / ss_total if ss_total else 0},
        {"source": "Interaction", "SS": ss_inter, "pct_total": 100 * ss_inter / ss_total if ss_total else 0},
        {"source": "Total", "SS": ss_total, "pct_total": 100.0},
    ]
    df = pd.DataFrame(rows)
    summary = {
        "style_pct": rows[0]["pct_total"],
        "topology_pct": rows[1]["pct_total"],
        "interaction_pct": rows[2]["pct_total"],
    }
    return df, summary


def heatmap(M: pd.DataFrame, title: str, out: Path, vmin: float, vmax: float, cbar_label: str = "pass@1 (final_pass)"):
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    im = ax.imshow(M.values, cmap="YlOrRd", vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(TOPOS)))
    ax.set_yticks(range(len(STYLES)))
    ax.set_xticklabels(TOPOS, rotation=20)
    ax.set_yticklabels(STYLES)
    ax.set_xlabel("Topology")
    ax.set_ylabel("Prompt style")
    ax.set_title(title)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M.values[i, j]
            text_color = "white" if v > (vmin + vmax) / 1.6 else "black"
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", color=text_color, fontsize=10)
    # Highlight diagonal cells
    for i, s in enumerate(STYLES):
        if s in TOPOS:
            j = TOPOS.index(s)
            ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="black", lw=2))
    fig.colorbar(im, ax=ax, label=cbar_label)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def run_condition(name: str, df_subset: pd.DataFrame, metric: str = "final_pass", suffix: str = "") -> dict:
    """Run 4-test on one (condition, metric). suffix is appended to filenames
    ('' for final_pass, '_partial' for partial credit)."""
    M = cell_mean_matrix(df_subset, metric)
    M.to_csv(TABLES / f"cell_mean{suffix}_{name}.csv", index_label="style")

    wilcoxon_df, wilcoxon_sum = wilcoxon_per_task(df_subset, metric)
    wilcoxon_df.to_csv(TABLES / f"wilcoxon{suffix}_{name}.csv", index=False)

    perm_sum = permutation_test(M)

    row_df, row_sum = per_row_max(M)
    row_df.to_csv(TABLES / f"per_row_max{suffix}_{name}.csv", index=False)

    anova_df, anova_sum = anova_ss(M)
    anova_df.to_csv(TABLES / f"anova{suffix}_{name}.csv", index=False)

    return {
        "condition": name,
        "metric": metric,
        "n_task": wilcoxon_sum["n"],
        "M": M,
        "wilcoxon": wilcoxon_sum,
        "perm": perm_sum,
        "row_max": row_sum,
        "anova": anova_sum,
    }


def main():
    df = load()
    print(f"Loaded {len(df)} rows. Levels: {df['level'].value_counts().to_dict()}")

    conditions = {
        "easy":   df[df["level"] == "easy"],
        "medium": df[df["level"] == "medium"],
        "hard":   df[df["level"] == "hard"],
        "all":    df,
    }

    # Run BOTH final_pass and partial_credit analyses (parallel)
    all_results = {}
    all_matrices = {}
    for metric, suffix, label in [
        ("final_pass", "", "pass@1 (final_pass)"),
        ("partial_credit", "_partial", "partial credit (per-item)"),
    ]:
        print(f"\n{'#'*70}\n# METRIC: {metric}\n{'#'*70}")
        results = {}
        matrices = {}
        for name, sub in conditions.items():
            print(f"\n=== {metric} / {name} (n_trial={len(sub)}) ===")
            r = run_condition(name, sub, metric=metric, suffix=suffix)
            results[name] = r
            matrices[name] = r["M"]
            print(f"  cell-mean:\n{r['M'].round(3).to_string()}")
            print(f"  wilcoxon: aligned={r['wilcoxon']['aligned_mean']:.4f}, misaligned={r['wilcoxon']['misaligned_mean']:.4f}, diff={r['wilcoxon']['diff']:+.4f}, p={r['wilcoxon']['p']:.4f}, d={r['wilcoxon']['cohen_d']:.3f}, n={r['wilcoxon']['n']}")
            print(f"  perm: diag={r['perm']['diag_mean']:.4f}, p={r['perm']['p']:.4f}")
            print(f"  row-max: {r['row_max']['winners']}/{r['row_max']['K']}, p={r['row_max']['p']:.4f}")
            print(f"  anova: style={r['anova']['style_pct']:.1f}%, topo={r['anova']['topology_pct']:.1f}%, interaction={r['anova']['interaction_pct']:.1f}%")

        # Permutation summary table
        perm_rows = [
            {"condition": n, "diag_mean": r["perm"]["diag_mean"], "perm_mean": r["perm"]["perm_mean"],
             "perm_sd": r["perm"]["perm_sd"], "p": r["perm"]["p"]}
            for n, r in results.items()
        ]
        pd.DataFrame(perm_rows).to_csv(TABLES / f"permutation{suffix}_summary.csv", index=False)

        # Heatmaps with common vmin/vmax across 4 conditions per metric
        vmin = min(M.values.min() for M in matrices.values())
        vmax = max(M.values.max() for M in matrices.values())
        print(f"\nHeatmap{suffix} vmin={vmin:.3f}, vmax={vmax:.3f}")
        for name, M in matrices.items():
            title = f"pilot_v8 4×4 — {metric} — {name} (n={results[name]['n_task']})"
            heatmap(M, title, PLOTS / f"heatmap{suffix}_{name}.png", vmin=vmin, vmax=vmax, cbar_label=label)

        # 4-test summary table
        summary_rows = []
        for name, r in results.items():
            summary_rows.append({
                "condition": name, "n_task": r["n_task"],
                "aligned_mean": r["wilcoxon"]["aligned_mean"],
                "misaligned_mean": r["wilcoxon"]["misaligned_mean"],
                "diff": r["wilcoxon"]["diff"],
                "cohen_d": r["wilcoxon"]["cohen_d"],
                "wilcoxon_W": r["wilcoxon"]["W"],
                "wilcoxon_p": r["wilcoxon"]["p"],
                "perm_p": r["perm"]["p"],
                "row_max_winners": r["row_max"]["winners"],
                "row_max_p": r["row_max"]["p"],
                "anova_style_pct": r["anova"]["style_pct"],
                "anova_topology_pct": r["anova"]["topology_pct"],
                "anova_interaction_pct": r["anova"]["interaction_pct"],
            })
        pd.DataFrame(summary_rows).to_csv(TABLES / f"summary_4test{suffix}.csv", index=False)

        all_results[metric] = results
        all_matrices[metric] = matrices

    # Write summary.md (both metrics)
    write_summary_md(all_results, all_matrices)
    print(f"\nWrote: {OUT}")


def fmt_p(p: float) -> str:
    if p < 0.001:
        return "**<0.001**"
    s = f"{p:.4f}"
    return f"**{s}**" if p < 0.05 else s


def _metric_section(metric_label: str, results: dict, matrices: dict) -> list[str]:
    lines = []
    lines.append(f"## [{metric_label}] 4-test 종합")
    lines.append("")
    lines.append("| Condition | n | aligned | misaligned | diff | d | Wilcoxon p | Perm p | row-max | ANOVA inter% |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for name in ["easy", "medium", "hard", "all"]:
        r = results[name]
        w = r["wilcoxon"]; p_perm = r["perm"]["p"]; rm = r["row_max"]; an = r["anova"]
        lines.append(
            f"| **{name}** | {w['n']} | {w['aligned_mean']:.4f} | {w['misaligned_mean']:.4f} | {w['diff']:+.4f} | {w['cohen_d']:+.3f} | {fmt_p(w['p'])} | {fmt_p(p_perm)} | {rm['winners']}/{rm['K']} ({fmt_p(rm['p'])}) | {an['interaction_pct']:.1f}% |"
        )
    lines.append("")
    lines.append(f"### [{metric_label}] Cell-mean matrix (4×4)")
    lines.append("")
    for name in ["easy", "medium", "hard", "all"]:
        lines.append(f"#### {name} (n_task={results[name]['n_task']})")
        lines.append("```")
        lines.append(matrices[name].round(4).to_string())
        lines.append("```")
        wins = []
        for s in STYLES:
            row = matrices[name].loc[s]
            wins.append(f"{s}→{row.idxmax()}({row.max():.3f})")
        lines.append("Row winner: " + " · ".join(wins))
        lines.append("")
    lines.append(f"### [{metric_label}] 한 줄 해석")
    lines.append("")
    for name in ["easy", "medium", "hard", "all"]:
        r = results[name]
        w = r["wilcoxon"]; p_perm = r["perm"]["p"]; rm = r["row_max"]; an = r["anova"]
        sig_w = "✅" if w["p"] < 0.05 else ("⚠" if w["p"] < 0.1 else "✗")
        sig_p = "✅" if p_perm < 0.05 else ("⚠" if p_perm < 0.1 else "✗")
        sig_r = "✅" if rm["p"] < 0.05 else ("⚠" if rm["p"] < 0.1 else "✗")
        lines.append(
            f"- **{name}**: Wilcoxon p={w['p']:.4f} (d={w['cohen_d']:+.2f}) {sig_w} · Perm p={p_perm:.4f} {sig_p} · row-max {rm['winners']}/{rm['K']} (p={rm['p']:.4f}) {sig_r} · ANOVA interaction={an['interaction_pct']:.1f}%"
        )
    lines.append("")
    return lines


def write_summary_md(all_results: dict, all_matrices: dict):
    lines = []
    lines.append("# pilot_v8_full — 4×4 Prompt-Structure × Topology Analysis (n=180 task)")
    lines.append("")
    lines.append("**Source**: `pilot_v8_full_gpt54mini_temp1.jsonl` (3600 trial = 180 task × 5 style × 4 topology, gpt-5.4-mini, temp 1.0, v6 setup).")
    lines.append("")
    lines.append("**View**: 4×4 (SAS + independent + centralized + hybrid; **decentralized style row 제외**, topology side 이미 4개). 16 cell × 4 difficulty condition (easy/medium/hard/all).")
    lines.append("")
    lines.append("**Metrics**:")
    lines.append("- `final_pass` — TravelPlanner full-pass rate (binary per trial; strictest)")
    lines.append("- `partial_credit` — per-item micro pass rate (commonsense 8 + hard 5 items, None=N/A 제외; matches `runner.py:186-200`)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.extend(_metric_section("final_pass", all_results["final_pass"], all_matrices["final_pass"]))
    lines.append("---")
    lines.append("")
    lines.extend(_metric_section("partial_credit", all_results["partial_credit"], all_matrices["partial_credit"]))
    lines.append("---")
    lines.append("")
    lines.append("## Files")
    lines.append("- `tables/cell_mean[_partial]_{condition}.csv` — 4×4 cell mean")
    lines.append("- `tables/wilcoxon[_partial]_{condition}.csv` — per-task paired aligned vs misaligned")
    lines.append("- `tables/per_row_max[_partial]_{condition}.csv` — winner topology per row")
    lines.append("- `tables/anova[_partial]_{condition}.csv` — SS decomposition")
    lines.append("- `tables/permutation[_partial]_summary.csv` — perm test p per condition")
    lines.append("- `tables/summary_4test[_partial].csv` — 4 condition × 4-test full numbers")
    lines.append("- `plots/heatmap[_partial]_{condition}.png` — 4×4 heatmap (common vmin/vmax per metric)")
    (OUT / "summary.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
