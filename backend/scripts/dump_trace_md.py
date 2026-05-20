"""Dump every mini_pilot_1 trial into a per-trial markdown file (no truncation).

Input:  backend/data/thinking_styles/mini_pilot_1_<slug>.jsonl   (4 files, 225 rows each)
Output: backend/data/thinking_styles/trace_dump/<slug>/<task>__<style>_to_<topo>__<pass|fail>.md

Each .md contains:
  - meta header (model, task, style, topology, pass/fail, duration, msg count, query)
  - one section per message: '### [N] from -> to' + full content verbatim
  - per_item check breakdown (which commonsense / hard checks were False, with reasons)
  - final_output preview (full)
"""
import argparse
import json
import re
from pathlib import Path

MODELS = [
    ("gpt41mini", "gpt-4.1-mini"),
    ("gpt5mini", "gpt-5-mini"),
    ("gpt52", "gpt-5.2"),
    ("gpt54mini", "gpt-5.4-mini"),
]


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s))


def content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                parts.append(c.get("text") or c.get("content") or json.dumps(c, ensure_ascii=False))
            else:
                parts.append(str(c))
        return "\n".join(parts)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def check_breakdown(per_item: dict) -> tuple:
    """Each per_item entry is [pass_flag, reason]. Return (failed, na, passed)."""
    failed, na, passed = [], [], []
    if not isinstance(per_item, dict):
        return failed, na, passed
    for name, entry in per_item.items():
        if isinstance(entry, list) and len(entry) >= 1:
            flag = entry[0]
            reason = entry[1] if len(entry) > 1 else None
            if flag is False:
                failed.append((name, reason))
            elif flag is None:
                na.append((name, reason))
            else:
                passed.append((name, reason))
    return failed, na, passed


def render_trial(row: dict) -> str:
    out = []
    metrics = row.get("metrics") or {}
    pass_flag = bool(metrics.get("final_pass"))
    out.append(f"# {row.get('task_id')} | style={row.get('style_id')} -> topology={row.get('topology')}")
    out.append("")
    out.append(f"- model: `{row.get('model')}`")
    out.append(f"- final: **{'PASS' if pass_flag else 'FAIL'}**  "
               f"(delivery={metrics.get('delivery')}, "
               f"commonsense_macro={metrics.get('commonsense_pass_macro')}, "
               f"hard_macro={metrics.get('hard_pass_macro')})")
    out.append(f"- duration: {row.get('duration_seconds'):.1f}s  |  message_count: {row.get('message_count')}")
    out.append(f"- temperature: {row.get('temperature')}  |  reasoning_effort: {row.get('reasoning_effort')}")
    out.append(f"- level: {row.get('level')}  |  days: {row.get('days')}")
    out.append("")
    out.append("## Query")
    out.append("")
    q = row.get("query") or ""
    out.append("> " + q.replace("\n", "\n> "))
    out.append("")

    msgs = row.get("messages") or []
    out.append(f"## Trace ({len(msgs)} messages)")
    out.append("")
    if not msgs:
        out.append("_(no messages — single-shot SAS or empty trace)_")
        out.append("")
    for i, m in enumerate(msgs):
        frm = m.get("from_agent") or m.get("role") or m.get("name") or "?"
        to = m.get("to_agent") or ""
        meta = m.get("metadata") or {}
        meta_tail = ""
        if isinstance(meta, dict) and meta:
            keep = {k: v for k, v in meta.items() if k in ("turn", "phase", "round", "stage", "kind", "type")}
            if keep:
                meta_tail = " · " + " ".join(f"{k}={v}" for k, v in keep.items())
        out.append(f"### [{i}] {frm} -> {to}{meta_tail}")
        out.append("")
        out.append(content_to_str(m.get("content")))
        out.append("")

    out.append("## Check breakdown")
    out.append("")
    cs_fail, cs_na, cs_pass = check_breakdown(metrics.get("commonsense_per_item") or {})
    hd_fail, hd_na, hd_pass = check_breakdown(metrics.get("hard_per_item") or {})

    out.append("**Commonsense:**")
    if not cs_fail and not cs_pass and not cs_na:
        out.append("- (no items)")
    else:
        for name, reason in cs_fail:
            out.append(f"- ❌ `{name}` — {reason}")
        for name, reason in cs_pass:
            out.append(f"- ✅ `{name}`")
        for name, reason in cs_na:
            out.append(f"- ➖ `{name}` (N/A)")
    out.append("")
    out.append("**Hard:**")
    if not hd_fail and not hd_pass and not hd_na:
        out.append("- (no items)")
    else:
        for name, reason in hd_fail:
            out.append(f"- ❌ `{name}` — {reason}")
        for name, reason in hd_pass:
            out.append(f"- ✅ `{name}`")
        for name, reason in hd_na:
            out.append(f"- ➖ `{name}` (N/A)")
    out.append("")

    fo = row.get("final_output")
    if fo is not None:
        out.append("## Final output")
        out.append("")
        if isinstance(fo, str):
            out.append("```")
            out.append(fo)
            out.append("```")
        else:
            out.append("```json")
            out.append(json.dumps(fo, ensure_ascii=False, indent=2))
            out.append("```")
        out.append("")

    parsed = row.get("parsed_plan")
    if parsed is not None:
        out.append("## Parsed plan")
        out.append("")
        out.append("```json")
        out.append(json.dumps(parsed, ensure_ascii=False, indent=2))
        out.append("```")
        out.append("")

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="backend/data/thinking_styles")
    ap.add_argument("--out-dir", default="backend/data/thinking_styles/trace_dump")
    ap.add_argument("--model", default=None, help="filter to a single model slug (e.g. gpt52)")
    ap.add_argument("--task-id", default=None)
    ap.add_argument("--style", default=None)
    ap.add_argument("--topology", default=None)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    grand_total = 0
    for slug, label in MODELS:
        if args.model and slug != args.model:
            continue
        path = data_dir / f"mini_pilot_1_{slug}.jsonl"
        if not path.exists():
            print(f"[skip] missing {path}")
            continue
        out_model = out_root / slug
        out_model.mkdir(parents=True, exist_ok=True)
        n_model = 0
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            if args.task_id and row.get("task_id") != args.task_id:
                continue
            if args.style and row.get("style_id") != args.style:
                continue
            if args.topology and row.get("topology") != args.topology:
                continue
            pass_flag = bool((row.get("metrics") or {}).get("final_pass"))
            tag = "pass" if pass_flag else "fail"
            fname = (
                f"{safe(row.get('task_id'))}"
                f"__{safe(row.get('style_id'))}_to_{safe(row.get('topology'))}"
                f"__{tag}.md"
            )
            (out_model / fname).write_text(render_trial(row), encoding="utf-8")
            n_model += 1
        grand_total += n_model
        print(f"[{label:>14}] {n_model} files -> {out_model}")
    print(f"\nTotal: {grand_total} markdown files under {out_root}")


if __name__ == "__main__":
    main()
