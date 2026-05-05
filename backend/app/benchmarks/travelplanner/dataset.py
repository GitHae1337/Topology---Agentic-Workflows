"""TravelPlanner dataset loader.

Loads the HuggingFace `osunlp/TravelPlanner` validation split (180 queries) and
caches it as JSONL under `backend/data/travelplanner_validation.jsonl`.

Each row contains the natural-language query + a `reference_information` array
that bundles every candidate flight / accommodation / restaurant / attraction
the model needs to plan with — so no separate database download is required.
"""
import ast
import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DEFAULT_SPLIT = "validation"


class TravelPlannerProblem(BaseModel):
    """One TravelPlanner query record (full row, lossless).

    All upstream HF fields are preserved so the vendored evaluator can read
    annotations / constraints later without a second dataset round-trip.
    """
    task_id: str
    org: str
    dest: str
    days: int
    visiting_city_number: int
    date: str  # stringified list, kept verbatim from upstream
    people_number: int
    budget: Optional[int] = None
    level: str
    query: str
    local_constraint: str  # stringified dict, kept verbatim
    reference_information: list[dict[str, Any]]


def _cache_path(split: str) -> Path:
    return DATA_DIR / f"travelplanner_{split}.jsonl"


def _fetch_split_via_hf_datasets(split: str) -> list[dict]:
    """Pull the requested split via the HuggingFace datasets library."""
    print(f"[travelplanner.dataset] downloading split={split} from osunlp/TravelPlanner")
    from datasets import load_dataset  # local import keeps non-tp paths cheap
    ds = load_dataset("osunlp/TravelPlanner", split, split=split)
    rows: list[dict] = []
    for idx, row in enumerate(ds):
        record = dict(row)
        # Coerce reference_information into a list[dict] regardless of how the
        # upstream loader chose to serialize it. Upstream uses Python repr
        # (single-quoted) so ast.literal_eval is the right parser, not json.
        ref = record.get("reference_information")
        if isinstance(ref, str):
            record["reference_information"] = ast.literal_eval(ref)
        record["task_id"] = f"travelplanner-{idx}"
        rows.append(record)
    print(f"[travelplanner.dataset] fetched {len(rows)} rows")
    return rows


def _write_cache(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[travelplanner.dataset] cached {len(rows)} rows → {path}")


def _read_cache(path: Path) -> list[TravelPlannerProblem]:
    print(f"[travelplanner.dataset] cache hit: {path}")
    out: list[TravelPlannerProblem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(TravelPlannerProblem(**json.loads(line)))
    return out


def load_problems(
    split: str = DEFAULT_SPLIT,
    max_problems: Optional[int] = None,
) -> list[TravelPlannerProblem]:
    """Load TravelPlanner problems for the given split with disk caching.

    First call downloads via the HF datasets library and writes JSONL.
    Subsequent calls read from cache. Pass max_problems to slice the front.
    """
    cache = _cache_path(split)

    if cache.exists():
        problems = _read_cache(cache)
    else:
        rows = _fetch_split_via_hf_datasets(split)
        _write_cache(cache, rows)
        problems = [TravelPlannerProblem(**r) for r in rows]

    if max_problems is not None:
        problems = problems[:max_problems]
    print(f"[travelplanner.dataset] returning {len(problems)} problems (split={split})")
    return problems
