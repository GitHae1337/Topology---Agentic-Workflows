"""Benchmark dataset loaders for GSM8K / AQuA / MMLU-Pro.

Pulls test rows from HuggingFace datasets-server REST API and caches them as
JSONL under backend/data/<bench>_test.jsonl. Subsequent runs hit disk only.

The unified record shape is BenchmarkProblem(task_id, question, answer):
    - GSM8K answer:    integer string parsed out of '#### N' suffix
    - AQuA answer:     'A' | 'B' | 'C' | 'D' | 'E'
    - MMLU-Pro answer: 'A'..'J'
"""
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel


DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# datasets-server caps `length` at 100 per call. For spot-checks 100 is plenty;
# expand via pagination later if a benchmark needs a wider sample.
HF_FETCH_CAP = 100


class BenchmarkProblem(BaseModel):
    """One benchmark question with its canonical expected answer."""
    task_id: str
    question: str
    answer: str


def _hf_url(dataset: str, config: str, split: str, offset: int, length: int) -> str:
    qs = urllib.parse.urlencode({
        "dataset": dataset,
        "config": config,
        "split": split,
        "offset": offset,
        "length": length,
    })
    return f"https://datasets-server.huggingface.co/rows?{qs}"


def _fetch_rows(dataset: str, config: str, split: str, n: int) -> list[dict]:
    """Fetch up to n rows from HuggingFace datasets-server."""
    url = _hf_url(dataset, config, split, 0, min(n, HF_FETCH_CAP))
    print(f"[datasets] GET {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        body = json.loads(resp.read().decode())
    rows = body.get("rows", [])
    print(f"[datasets] got {len(rows)} rows")
    return rows


def _format_gsm8k(row: dict) -> dict:
    r = row["row"]
    a_full = r["answer"]
    m = re.search(r"####\s*(.+)", a_full)
    answer = m.group(1).strip() if m else a_full.strip()
    return {
        "task_id": f"gsm8k-{row['row_idx']}",
        "question": r["question"],
        "answer": answer,
    }


def _format_aqua(row: dict) -> dict:
    r = row["row"]
    options_str = "\n".join(r["options"])
    return {
        "task_id": f"aqua-{row['row_idx']}",
        "question": f"{r['question']}\n\nOptions:\n{options_str}",
        "answer": r["correct"].strip().upper(),
    }


def _format_mmlu_pro(row: dict) -> dict:
    r = row["row"]
    letters = "ABCDEFGHIJ"
    options_str = "\n".join(f"{letters[i]}) {opt}" for i, opt in enumerate(r["options"]))
    qid = r.get("question_id", row["row_idx"])
    return {
        "task_id": f"mmlu_pro-{qid}",
        "question": f"{r['question']}\n\nOptions:\n{options_str}",
        "answer": r["answer"].strip().upper(),
    }


DATASET_CONFIG: dict[str, dict] = {
    "gsm8k":    {"dataset": "openai/gsm8k",       "config": "main",    "split": "test", "format": _format_gsm8k},
    "aqua":     {"dataset": "deepmind/aqua_rat",  "config": "raw",     "split": "test", "format": _format_aqua},
    "mmlu_pro": {"dataset": "TIGER-Lab/MMLU-Pro", "config": "default", "split": "test", "format": _format_mmlu_pro},
}


def _cache_path(bench_name: str) -> Path:
    return DATA_DIR / f"{bench_name}_test.jsonl"


def _write_cache(path: Path, problems: list[BenchmarkProblem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for p in problems:
            f.write(p.model_dump_json() + "\n")
    print(f"[datasets] cached {len(problems)} problems → {path}")


def _read_cache(path: Path) -> list[BenchmarkProblem]:
    print(f"[datasets] cache hit: {path}")
    out: list[BenchmarkProblem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(BenchmarkProblem(**json.loads(line)))
    return out


def load_problems(bench_name: str, max_problems: Optional[int] = None) -> list[BenchmarkProblem]:
    """Load benchmark problems with disk caching.

    First call hits HuggingFace datasets-server and writes a JSONL cache.
    Subsequent calls read from cache. Pass max_problems to slice the front of
    the list for spot-checks.
    """
    if bench_name not in DATASET_CONFIG:
        raise ValueError(f"Unknown benchmark: {bench_name}. Available: {list(DATASET_CONFIG)}")

    cfg = DATASET_CONFIG[bench_name]
    cache = _cache_path(bench_name)

    if cache.exists():
        problems = _read_cache(cache)
    else:
        rows = _fetch_rows(cfg["dataset"], cfg["config"], cfg["split"], HF_FETCH_CAP)
        problems = [BenchmarkProblem(**cfg["format"](r)) for r in rows]
        _write_cache(cache, problems)

    if max_problems is not None:
        problems = problems[:max_problems]
    print(f"[datasets] returning {len(problems)} {bench_name} problems")
    return problems
