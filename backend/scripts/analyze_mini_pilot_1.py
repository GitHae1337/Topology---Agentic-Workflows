"""Analyze mini_pilot_1 — 4 models, 5x5 (full) + 4x4 (hybrid excluded), 9 tasks/cell.

Two views per model:
  - 5x5 full: cost/scope picture (hybrid included). topology main effect is
    inflated by hybrid's compute-axis effect (duration ~2-8x of the others).
  - 4x4 alignment: hybrid removed so the alignment interaction signal is not
    drowned out by the topology main effect (same rationale as the 90-task
    4x4 pilot).

Runs four tests per view:
  1. Paired Wilcoxon (per-task aligned vs misaligned cell means, alt=greater)
  2. Permutation test (K*K cells reshuffled, diagonal mean p-value)
  3. Per-row max Binomial (n=K, p=1/K, alt=greater)
  4. 2-way ANOVA SS decomposition (Style / Topology / Interaction / Residual)

Output:
  console table (per model, per view)
  backend/data/thinking_styles/analysis_mini_pilot_1/
    summary.md
    tables/{matrix,wilcoxon,binomial,anova_*}_<view>_<model>.csv
    plots/heatmap_<view>_<model>.png
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

STYLE_ORDER_5 = ["sas", "independent", "centralized", "decentralized", "hybrid"]
STYLE_ORDER_4 = ["sas", "independent", "centralized", "decentralized"]

VIEWS = [
    ("5x5", STYLE_ORDER_5),
    ("4x4", STYLE_ORDER_4),
]

MODELS = [
    ("gpt41mini", "gpt-4.1-mini"),
    ("gpt5mini", "gpt-5-mini"),
    ("gpt52", "gpt-5.2"),
    ("gpt54mini", "gpt-5.4-mini"),
]


def load_results(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    df = pd.json_normalize(rows)
    df["pass"] = df["metrics.final_pass"].astype(bool)
    df["delivery"] = df["metrics.delivery"].astype(bool)
    return df


def subset_view(df: pd.DataFrame, style_order: list) -> pd.DataFrame:
    return df[
        df["style_id"].isin(style_order) & df["topology"].isin(style_order)
    ].copy()


def build_matrix(df: pd.DataFrame, style_order: list) -> pd.DataFrame:
    mat = df.groupby(["style_id", "topology"])["pass"].mean().unstack()
    return mat.reindex(index=style_order, columns=style_order)


def paired_wilcoxon(df: pd.DataFrame):
    """Per-task: mean(aligned cells) vs mean(misaligned cells). Signed-rank, greater."""
    df_a = df.assign(aligned=df["style_id"] == df["topology"])
    per_task = (
        df_a.groupby(["task_id", "aligned"])["pass"].mean().unstack()
        .rename(columns={False: "misaligned", True: "aligned"})
        .dropna()
    )
    diff = per_task["aligned"] - per_task["misaligned"]
    # zsplit handles zero-diffs (ties) without dropping them entirely
    if (diff != 0).any():
        w_stat, w_p = stats.wilcoxon(
            diff, alternative="greater", zero_method="zsplit"
        )
    else:
        w_stat, w_p = 0.0, 1.0
    cohen_d = float(diff.mean() / diff.std()) if diff.std() > 0 else float("nan")
    return {
        "n_tasks": int(len(per_task)),
        "aligned_mean": float(per_task["aligned"].mean()),
        "misaligned_mean": float(per_task["misaligned"].mean()),
        "mean_diff": float(diff.mean()),
        "W": float(w_stat),
        "p": float(w_p),
        "cohen_d": cohen_d,
        "per_task": per_task,
    }


def permutation_test(mat: pd.DataFrame, n_permutations: int, rng: np.random.Generator):
    K = mat.shape[0]
    cells_flat = mat.values.flatten()
    actual_diag_mean = float(np.diag(mat.values).mean())
    perm_diag_means = np.zeros(n_permutations)
    for k in range(n_permutations):
        shuffled = rng.permutation(cells_flat).reshape(K, K)
        perm_diag_means[k] = np.diag(shuffled).mean()
    # +1 smoothing avoids exactly-zero p when actual is the most extreme
    p = float(((perm_diag_means >= actual_diag_mean).sum() + 1) / (n_permutations + 1))
    return {
        "actual_diag_mean": actual_diag_mean,
        "null_mean": float(perm_diag_means.mean()),
        "null_std": float(perm_diag_means.std()),
        "p": p,
        "n_perm": n_permutations,
    }


def per_row_max_binomial(mat: pd.DataFrame, style_order: list):
    K = len(style_order)
    rows = []
    n_strict = 0
    n_tied = 0
    for i, s in enumerate(style_order):
        row_vals = mat.loc[s].values
        max_val = row_vals.max()
        diag_val = row_vals[i]
        # strict winner: diagonal cell is the unique argmax (no tie at max)
        n_at_max = int((row_vals == max_val).sum())
        is_strict = bool(diag_val == max_val and n_at_max == 1)
        is_tied = bool(diag_val == max_val)
        if is_strict:
            n_strict += 1
        if is_tied:
            n_tied += 1
        rows.append({
            "style": s,
            "diag_value": float(diag_val),
            "row_max_value": float(max_val),
            "row_argmax_topology": style_order[int(np.argmax(row_vals))],
            "n_cells_at_max": n_at_max,
            "diag_is_strict_winner": is_strict,
            "diag_tied_with_max": is_tied,
        })
    p_strict = float(
        stats.binomtest(n_strict, n=K, p=1.0 / K, alternative="greater").pvalue
    )
    p_tied = float(
        stats.binomtest(n_tied, n=K, p=1.0 / K, alternative="greater").pvalue
    )
    return {
        "per_row": pd.DataFrame(rows),
        "n_strict": n_strict,
        "n_tied": n_tied,
        "K": K,
        "p_null": 1.0 / K,
        "p_strict": p_strict,
        "p_tied": p_tied,
    }


def anova_ss_decomp(mat: pd.DataFrame, df: pd.DataFrame, style_order: list):
    """Two views:
      (a) cell-mean SS (no within-cell variance): Style/Topology/Interaction.
      (b) trial-level SS (includes residual): Style/Topology/Interaction/Residual.
    """
    K = len(style_order)
    # (a) Cell-mean decomposition
    M = mat.values
    grand = float(M.mean())
    row_means = M.mean(axis=1)
    col_means = M.mean(axis=0)
    ss_style_c = float(K * ((row_means - grand) ** 2).sum())
    ss_topo_c = float(K * ((col_means - grand) ** 2).sum())
    additive = grand + (row_means[:, None] - grand) + (col_means[None, :] - grand)
    ss_inter_c = float(((M - additive) ** 2).sum())
    ss_tot_c = float(((M - grand) ** 2).sum())

    # (b) Trial-level decomposition (Type I, balanced design: order does not matter)
    y = df["pass"].astype(float).values
    style_arr = df["style_id"].values
    topo_arr = df["topology"].values
    overall = float(y.mean())
    ss_total_t = float(((y - overall) ** 2).sum())
    # Style main effect
    style_mean = {s: float(y[style_arr == s].mean()) for s in style_order}
    ss_style_t = float(
        sum(((style_mean[s] - overall) ** 2) * (style_arr == s).sum() for s in style_order)
    )
    topo_mean = {t: float(y[topo_arr == t].mean()) for t in style_order}
    ss_topo_t = float(
        sum(((topo_mean[t] - overall) ** 2) * (topo_arr == t).sum() for t in style_order)
    )
    # Interaction = SS(cell) - SS(style) - SS(topology)
    ss_cell_t = 0.0
    for s in style_order:
        for t in style_order:
            mask = (style_arr == s) & (topo_arr == t)
            n_st = int(mask.sum())
            if n_st == 0:
                continue
            mean_st = float(y[mask].mean())
            ss_cell_t += n_st * (mean_st - overall) ** 2
    ss_inter_t = ss_cell_t - ss_style_t - ss_topo_t
    ss_residual_t = ss_total_t - ss_cell_t

    cell_df = pd.DataFrame([
        {"source": "Style (prompt structure)", "SS": ss_style_c, "pct_total": ss_style_c / ss_tot_c * 100},
        {"source": "Topology", "SS": ss_topo_c, "pct_total": ss_topo_c / ss_tot_c * 100},
        {"source": "Interaction (alignment)", "SS": ss_inter_c, "pct_total": ss_inter_c / ss_tot_c * 100},
        {"source": "Total (between cells)", "SS": ss_tot_c, "pct_total": 100.0},
    ])
    trial_df = pd.DataFrame([
        {"source": "Style", "SS": ss_style_t, "pct_total": ss_style_t / ss_total_t * 100},
        {"source": "Topology", "SS": ss_topo_t, "pct_total": ss_topo_t / ss_total_t * 100},
        {"source": "Interaction", "SS": ss_inter_t, "pct_total": ss_inter_t / ss_total_t * 100},
        {"source": "Residual (within cell)", "SS": ss_residual_t, "pct_total": ss_residual_t / ss_total_t * 100},
        {"source": "Total", "SS": ss_total_t, "pct_total": 100.0},
    ])
    return {
        "cell_df": cell_df,
        "trial_df": trial_df,
        "cell_pct": {
            "style": ss_style_c / ss_tot_c * 100,
            "topology": ss_topo_c / ss_tot_c * 100,
            "interaction": ss_inter_c / ss_tot_c * 100,
        },
        "trial_pct": {
            "style": ss_style_t / ss_total_t * 100,
            "topology": ss_topo_t / ss_total_t * 100,
            "interaction": ss_inter_t / ss_total_t * 100,
            "residual": ss_residual_t / ss_total_t * 100,
        },
    }


def draw_heatmap(mat: pd.DataFrame, style_order: list, view_label: str,
                 model_label: str, out_path: Path, n_tasks: int):
    K = len(style_order)
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    vmax_raw = mat.values.max()
    im = ax.imshow(mat.values, cmap="YlOrRd", vmin=0, vmax=max(vmax_raw, 0.4))
    ax.set_xticks(range(K))
    ax.set_yticks(range(K))
    ax.set_xticklabels(style_order, rotation=20)
    ax.set_yticklabels(style_order)
    ax.set_xlabel("topology (executor)")
    ax.set_ylabel("style_id (prompt structure)")
    ax.set_title(
        f"pass@1 — {view_label} matrix ({model_label}, {n_tasks} tasks/cell)"
    )
    for i in range(K):
        for j in range(K):
            v = mat.values[i, j]
            ax.text(
                j, i, f"{v:.3f}",
                ha="center", va="center",
                color="black" if v < vmax_raw * 0.55 else "white",
                fontweight="bold" if i == j else "normal",
            )
    plt.colorbar(im, ax=ax, label="pass@1")
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    plt.close()


def analyze_one_view(df_view: pd.DataFrame, style_order: list, view_label: str,
                     model_label: str, out_dir: Path,
                     n_permutations: int, seed: int) -> dict:
    print(f"\n----- {model_label} | {view_label} -----")
    print(f"[view] trials={len(df_view)} tasks={df_view['task_id'].nunique()} "
          f"cells={len(style_order)}x{len(style_order)}")

    mat = build_matrix(df_view, style_order)
    mat.to_csv(out_dir / "tables" / f"matrix_{view_label}_{model_label}.csv")
    print(f"[matrix] {view_label} pass@1:")
    print(mat.round(3))

    # 1. Wilcoxon
    w = paired_wilcoxon(df_view)
    print(f"[wilcoxon] n_tasks={w['n_tasks']} aligned={w['aligned_mean']:.3f} "
          f"misaligned={w['misaligned_mean']:.3f} diff={w['mean_diff']:+.3f} "
          f"W={w['W']:.1f} p={w['p']:.4g} d={w['cohen_d']:.3f}")
    w["per_task"].to_csv(
        out_dir / "tables" / f"wilcoxon_per_task_{view_label}_{model_label}.csv"
    )

    # 2. Permutation
    rng = np.random.default_rng(seed)
    p = permutation_test(mat, n_permutations, rng)
    print(f"[permutation] actual_diag={p['actual_diag_mean']:.4f} "
          f"null={p['null_mean']:.4f}+/-{p['null_std']:.4f} "
          f"p={p['p']:.4g} (n_perm={p['n_perm']})")

    # 3. Per-row max binomial
    b = per_row_max_binomial(mat, style_order)
    print(f"[binomial] strict_wins={b['n_strict']}/{b['K']} p={b['p_strict']:.4g} | "
          f"tied_or_wins={b['n_tied']}/{b['K']} p={b['p_tied']:.4g} "
          f"(null p={b['p_null']:.2f})")
    b["per_row"].to_csv(
        out_dir / "tables" / f"binomial_per_row_{view_label}_{model_label}.csv",
        index=False,
    )

    # 4. ANOVA SS
    a = anova_ss_decomp(mat, df_view, style_order)
    print("[anova / cell-mean view]")
    print(a["cell_df"].round(4).to_string(index=False))
    print("[anova / trial-level view incl. residual]")
    print(a["trial_df"].round(4).to_string(index=False))
    a["cell_df"].to_csv(
        out_dir / "tables" / f"anova_cell_{view_label}_{model_label}.csv", index=False
    )
    a["trial_df"].to_csv(
        out_dir / "tables" / f"anova_trial_{view_label}_{model_label}.csv", index=False
    )

    draw_heatmap(
        mat, style_order, view_label, model_label,
        out_dir / "plots" / f"heatmap_{view_label}_{model_label}.png",
        n_tasks=df_view["task_id"].nunique(),
    )

    return {
        "view": view_label,
        "n_trials": int(len(df_view)),
        "n_tasks": int(df_view["task_id"].nunique()),
        "matrix": mat,
        "wilcoxon": w,
        "permutation": p,
        "binomial": b,
        "anova": a,
    }


def analyze_one_model(jsonl_path: Path, model_label: str, out_dir: Path,
                      n_permutations: int, seed: int) -> dict:
    print(f"\n========== {model_label} ==========")
    df = load_results(jsonl_path)
    print(f"[load] trials={len(df)} tasks={df['task_id'].nunique()} "
          f"styles={df['style_id'].nunique()} topologies={df['topology'].nunique()}")

    by_view = {}
    for view_label, style_order in VIEWS:
        df_view = subset_view(df, style_order)
        by_view[view_label] = analyze_one_view(
            df_view, style_order, view_label, model_label, out_dir,
            n_permutations, seed,
        )

    return {"model": model_label, "n_trials_full": int(len(df)), "views": by_view}


def _summary_row(model: str, v: dict) -> str:
    w = v["wilcoxon"]; p = v["permutation"]; b = v["binomial"]; t = v["anova"]["trial_pct"]
    return (
        f"| {model} | {w['aligned_mean']:.3f} | {w['misaligned_mean']:.3f} | "
        f"{w['mean_diff']:+.3f} | {w['p']:.4g} | {p['p']:.4g} | "
        f"{b['n_strict']}/{b['K']} (p={b['p_strict']:.3g}) | "
        f"{b['n_tied']}/{b['K']} (p={b['p_tied']:.3g}) | "
        f"{t['style']:.1f}% | {t['topology']:.1f}% | "
        f"{t['interaction']:.1f}% | {t['residual']:.1f}% |"
    )


def _view_block(v: dict, model: str) -> list:
    lines = []
    view = v["view"]
    lines.append(f"### {view} — pass@1 matrix ({v['n_tasks']} tasks/cell)\n")
    lines.append("```")
    lines.append(v["matrix"].round(3).to_string())
    lines.append("```")
    lines.append(f"![heatmap](plots/heatmap_{view}_{model}.png)\n")
    w = v["wilcoxon"]
    lines.append(f"#### {view} — Paired Wilcoxon (aligned vs misaligned, per task)\n")
    lines.append(f"- n_tasks = {w['n_tasks']}")
    lines.append(f"- aligned mean = {w['aligned_mean']:.3f}, misaligned mean = {w['misaligned_mean']:.3f}")
    lines.append(f"- mean diff = {w['mean_diff']:+.3f}, Cohen d = {w['cohen_d']:.3f}")
    lines.append(f"- W = {w['W']:.2f}, p (one-sided, greater) = **{w['p']:.4g}**\n")
    p = v["permutation"]
    K = v["binomial"]["K"]
    lines.append(f"#### {view} — Permutation test ({K*K} cells reshuffled)\n")
    lines.append(f"- actual diagonal mean = {p['actual_diag_mean']:.4f}")
    lines.append(f"- null diagonal mean = {p['null_mean']:.4f} ± {p['null_std']:.4f}")
    lines.append(f"- p (one-sided) = **{p['p']:.4g}** (n_perm = {p['n_perm']})\n")
    b = v["binomial"]
    lines.append(f"#### {view} — Per-row max (Binomial)\n")
    lines.append(f"- strict wins (unique argmax on diagonal): {b['n_strict']}/{b['K']}, p = **{b['p_strict']:.4g}**")
    lines.append(f"- tied-or-wins (diagonal tied with max): {b['n_tied']}/{b['K']}, p = **{b['p_tied']:.4g}**")
    lines.append(f"- null: p_per_row = {b['p_null']:.2f}\n")
    lines.append("```")
    lines.append(b["per_row"].round(3).to_string(index=False))
    lines.append("```\n")
    lines.append(f"#### {view} — 2-way ANOVA SS decomposition\n")
    lines.append("Cell-mean view (between-cell variation only):\n")
    lines.append("```")
    lines.append(v["anova"]["cell_df"].round(4).to_string(index=False))
    lines.append("```\n")
    lines.append("Trial-level view (includes within-cell residual):\n")
    lines.append("```")
    lines.append(v["anova"]["trial_df"].round(4).to_string(index=False))
    lines.append("```\n")
    return lines


def write_summary(results: list, out_dir: Path):
    lines = []
    lines.append("# mini_pilot_1 — 4 models × {5×5 (full), 4×4 (hybrid excluded)}\n")
    lines.append("Per cell: 9 task replicates. Tasks: 9 TravelPlanner items.\n")
    lines.append("Metric: `final_pass` (binary).\n")
    lines.append("5×5 = full scope (hybrid included). 4×4 = alignment view (hybrid removed).\n")
    lines.append("")
    header = (
        "| model | aligned | misaligned | diff | Wilcoxon p | Perm p | "
        "Binom (strict) | Binom (tied) | SS%: style | topo | inter | resid |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|---|---|"
    for view_label, _ in VIEWS:
        lines.append(f"## Cross-model summary — {view_label}\n")
        lines.append(header)
        lines.append(sep)
        for r in results:
            lines.append(_summary_row(r["model"], r["views"][view_label]))
        lines.append("")
    for r in results:
        m = r["model"]
        lines.append(f"\n## {m}\n")
        for view_label, _ in VIEWS:
            lines.extend(_view_block(r["views"][view_label], m))
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[write] summary.md -> {out_dir / 'summary.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data-dir",
        default="backend/data/thinking_styles",
        help="dir containing mini_pilot_1_*.jsonl",
    )
    ap.add_argument(
        "--out-dir",
        default="backend/data/thinking_styles/analysis_mini_pilot_1",
    )
    ap.add_argument("--n-permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    (out_dir / "plots").mkdir(parents=True, exist_ok=True)

    results = []
    for slug, label in MODELS:
        path = data_dir / f"mini_pilot_1_{slug}.jsonl"
        if not path.exists():
            print(f"[skip] missing {path}")
            continue
        r = analyze_one_model(path, label, out_dir, args.n_permutations, args.seed)
        results.append(r)

    write_summary(results, out_dir)


if __name__ == "__main__":
    main()
