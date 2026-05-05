"""Benchmark API for Phase 2-A frontend feedback.

Currently only TravelPlanner is wired. Three endpoints:

  GET  /travelplanner/translations         — list 18 Korean-translated tasks
                                              (ResearcherLanding dropdown)
  GET  /travelplanner/problems/{task_id}   — fetch one cached query
                                              (Korean override applied if matched)
  POST /travelplanner/evaluate             — grade agent's raw output text
                                              and return per-constraint status

The agent's raw output is parsed (Python list-of-dicts in a code fence) and
fed to the upstream commonsense + hard evaluators. The response shape is the
simplified per-constraint dict described in the Phase 2-A plan.
"""
import ast
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..benchmarks.travelplanner.dataset import load_problems
from ..benchmarks.travelplanner.evaluator import evaluate_one
from ..benchmarks.travelplanner.parser import parse_plan


router = APIRouter()


_problems_by_id: Optional[dict[str, Any]] = None
_translations_ko: Optional[dict[str, dict]] = None

TRANSLATIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "translations_ko.json"


def _get_problem(task_id: str):
    """Lazy-load + cache the validation split, then look up by task_id."""
    global _problems_by_id
    if _problems_by_id is None:
        print(f"[api.benchmarks] loading TravelPlanner validation cache")
        problems = load_problems("validation", max_problems=None)
        _problems_by_id = {p.task_id: p for p in problems}
        print(f"[api.benchmarks] cached {len(_problems_by_id)} problems")

    problem = _problems_by_id.get(task_id)
    if problem is None:
        raise HTTPException(
            status_code=404,
            detail=f"task_id {task_id!r} not found in TravelPlanner cache "
                   f"(have {len(_problems_by_id)} entries)",
        )
    return problem


def _load_translations() -> dict[str, dict]:
    """Lazy-load the Korean translation overrides. Cached after first call.

    Per-task fields can be null in the JSON — those are skipped (English
    original kept). reference_information is intentionally null for now.
    """
    global _translations_ko
    if _translations_ko is None:
        print(f"[api.benchmarks] loading translations from {TRANSLATIONS_PATH}")
        if not TRANSLATIONS_PATH.exists():
            print(f"[api.benchmarks] translations file missing — using empty map")
            _translations_ko = {}
        else:
            with TRANSLATIONS_PATH.open("r", encoding="utf-8") as f:
                _translations_ko = json.load(f)
            print(f"[api.benchmarks] loaded {len(_translations_ko)} translation entries")
    return _translations_ko


# Field-by-field override: source dict (translations_ko entry) → keys to copy
# onto the response dict when value is not None. Skips: task_id, level, days,
# people_number, visiting_city_number (schema metadata, identical across langs).
# reference_information stays English (translations_ko has it as null).
_OVERRIDABLE_FIELDS = ("date", "org", "dest", "budget", "local_constraint", "query")


# Korean translations_ko.json stores reference_information as a 4-key dict
# (more natural for the Korean travel domain than the English original's
# 9 separate refs). We expand to the frontend's expected list-of-refs shape
# below. Order matches the English original (attractions → restaurants →
# accommodations → transportation).
_KO_REF_DESCRIPTION = {
    "attractions": "관광지",
    "restaurants": "식당",
    "accommodations": "숙소",
    "transportation": "교통편",
}
_KO_REF_ORDER = ("attractions", "restaurants", "accommodations", "transportation")


def _coerce_ko_reference(ref) -> list[dict]:
    """Convert user-authored Korean reference into the list-of-{Description,
    Content, Records} shape the frontend expects. Accepts:
      - None              → []
      - list (target)     → returned as-is
      - dict (4-key)      → expanded into ordered list
    """
    if ref is None:
        return []
    if isinstance(ref, list):
        return ref
    if not isinstance(ref, dict):
        print(f"[api.benchmarks] unexpected reference type: {type(ref).__name__}")
        return []
    out = []
    for key in _KO_REF_ORDER:
        records = ref.get(key)
        if not isinstance(records, list):
            continue
        out.append({
            "Description": _KO_REF_DESCRIPTION[key],
            "Content": "",
            "Records": records,
        })
    # Future-proof: surface any extra keys we didn't anticipate.
    for key, records in ref.items():
        if key in _KO_REF_DESCRIPTION or not isinstance(records, list):
            continue
        out.append({"Description": key, "Content": "", "Records": records})
    return out


def _apply_translation(out: dict, task_id: str) -> dict:
    """Override English fields with Korean values for matched task_id.

    Modifies `out` in place and returns it. `currency` field added so frontend
    knows whether budget is USD (English) or KRW (Korean override).
    """
    translations = _load_translations()
    ko = translations.get(task_id)
    if ko is None:
        out["currency"] = "USD"
        return out

    overridden = []
    for field in _OVERRIDABLE_FIELDS:
        val = ko.get(field)
        if val is None:
            continue
        if field == "date" and isinstance(val, list):
            # Match English's stringified-list shape so frontend regex still works.
            out[field] = str(val)
        else:
            out[field] = val
        overridden.append(field)

    # reference_information: Korean task ALWAYS overrides (null → empty list,
    # not English fallback). User authored as 4-key dict; coerce to the
    # list-of-refs shape the frontend expects.
    out["reference_information"] = _coerce_ko_reference(ko.get("reference_information"))
    overridden.append("reference_information")

    out["currency"] = "KRW" if "budget" in overridden else "USD"
    print(f"[api.benchmarks] applied Korean override to {task_id}: {overridden}")
    return out


def _try_parse_to_records(content: str) -> Optional[list[dict]]:
    """Best-effort parse of pandas to_string()-style fixed-width text → list[dict].

    The HF dataset stores reference Content as a DataFrame.to_string() snapshot.
    pd.read_fwf re-infers column boundaries from whitespace alignment. On any
    parse failure return None — frontend then falls back to the raw text view.
    Try/except is the right boundary here per CLAUDE.md spirit (parsing
    untrusted external strings) — same justification as parser.py.
    """
    if not isinstance(content, str) or not content.strip():
        return None
    print(f"[api.benchmarks] parsing reference content ({len(content)} chars)")
    import io
    import pandas as pd
    try:
        df = pd.read_fwf(io.StringIO(content))
    except Exception as e:
        print(f"[api.benchmarks] read_fwf failed: {type(e).__name__}: {e}")
        return None
    if df.empty:
        return None
    df = df.where(pd.notna(df), '')
    return df.to_dict('records')


@router.get("/travelplanner/translations")
async def list_travelplanner_translations():
    """Return the list of Korean-translated tasks for the ResearcherLanding
    dropdown. One entry per task with just enough info for the option label.
    """
    translations = _load_translations()
    out = []
    for tid, ko in translations.items():
        out.append({
            "task_id": tid,
            "level": ko.get("level"),
            "days": ko.get("days"),
            "org": ko.get("org"),
            "dest": ko.get("dest"),
        })
    print(f"[api.benchmarks] returning {len(out)} translation entries")
    return out


@router.get("/travelplanner/problems/{task_id}")
async def get_travelplanner_problem(task_id: str):
    """Return one TravelPlanner query record for frontend display.

    If the task_id matches a Korean translation entry, non-null Korean fields
    override the English originals (query/org/dest/budget/local_constraint/date).
    reference_information stays English regardless (translations don't ship
    Korean reference data — LLM still sees English reference).
    """
    problem = _get_problem(task_id)
    out = problem.model_dump()
    # local_constraint comes from the HF row as a Python-repr string.
    # Coerce to a dict so the frontend can read it without ast.literal_eval.
    if isinstance(out.get("local_constraint"), str):
        out["local_constraint"] = ast.literal_eval(out["local_constraint"])

    # Apply Korean override (skips fields where translation is null).
    out = _apply_translation(out, task_id)

    # Augment each reference with structured records so the frontend can
    # render a real <table>. Falls back to None on parse failure → frontend
    # shows the raw <pre> as before.
    # If Records is already supplied (e.g. user-authored Korean reference
    # in translations_ko.json), keep it — don't try to re-parse.
    refs = out.get("reference_information") or []
    for ref in refs:
        if ref.get("Records") is None:
            ref["Records"] = _try_parse_to_records(ref.get("Content", ""))

    return out


class EvaluateRequest(BaseModel):
    task_id: str
    output: str  # the agent's raw final-message text (with code-fenced plan)


_COMMONSENSE_KEYS = (
    "is_reasonable_visiting_city",
    "is_valid_restaurants",
    "is_valid_attractions",
    "is_valid_accommodation",
    "is_valid_transportation",
    "is_valid_information_in_current_city",
    "is_valid_information_in_sandbox",
    "is_not_absent",
)

_HARD_CONSTRAINT_KEYS = (
    "valid_cost",
    "valid_room_rule",
    "valid_cuisine",
    "valid_room_type",
    "valid_transportation",
)


def _status_from_pair(pair) -> dict:
    """Convert one [passed, msg] pair to {status, reason?} dict.

    None passed means "not applicable for this query" (skipped).
    """
    passed = pair[0] if isinstance(pair, (list, tuple)) and len(pair) > 0 else None
    msg = pair[1] if isinstance(pair, (list, tuple)) and len(pair) > 1 else None
    if passed is None:
        return {"status": "skipped", "reason": "해당 제약 미지정"}
    if passed:
        return {"status": "pass"}
    return {"status": "fail", "reason": msg or ""}


def _summarize_eval(eval_result: dict) -> dict:
    """Transform evaluator.evaluate_one output into the frontend's
    simplified per-constraint shape. Always returns all 8 commonsense + 5
    hard slots so the UI can render a fixed-size 13-item list.
    """
    delivered = bool(eval_result.get("delivery"))
    cs_per = eval_result.get("commonsense_per_item")
    hd_per = eval_result.get("hard_per_item")

    if cs_per is None:
        # plan not delivered → commonsense evaluator never ran
        cs = {
            k: {"status": "skipped", "reason": "계획 미생성"}
            for k in _COMMONSENSE_KEYS
        }
    else:
        cs = {k: _status_from_pair(v) for k, v in cs_per.items()}

    if hd_per is None:
        if delivered:
            reason = "공통상식 검증 실패로 하드 제약 미평가"
        else:
            reason = "계획 미생성"
        hd = {k: {"status": "skipped", "reason": reason} for k in _HARD_CONSTRAINT_KEYS}
    else:
        hd = {k: _status_from_pair(v) for k, v in hd_per.items()}

    all_items = list(cs.values()) + list(hd.values())
    passed_count = sum(1 for s in all_items if s["status"] == "pass")
    evaluated_count = sum(1 for s in all_items if s["status"] != "skipped")

    return {
        "delivered": eval_result["delivery"],
        "all_passed": eval_result["final_pass"],
        "passed_count": passed_count,
        "evaluated_count": evaluated_count,
        "constraints": {"commonsense": cs, "hard": hd},
    }


@router.post("/travelplanner/evaluate")
async def evaluate_travelplanner(req: EvaluateRequest):
    """Parse + grade the agent's raw output for one TravelPlanner query.

    Korean tasks (in translations_ko.json) route to evaluator_ko which uses
    the Korean city DB + reference DataFrames + Korean enum hard-constraint
    functions. Other tasks use the vendored English evaluator.
    """
    problem = _get_problem(req.task_id)

    plan = parse_plan(req.output)
    print(f"[api.benchmarks] evaluate task_id={req.task_id} plan_parsed={plan is not None}")

    query_data = problem.model_dump()
    if isinstance(query_data.get("local_constraint"), str):
        query_data["local_constraint"] = ast.literal_eval(query_data["local_constraint"])
    # Apply Korean override so query_data has Korean local_constraint enum
    # values that the Korean evaluator expects.
    query_data = _apply_translation(query_data, req.task_id)

    translations = _load_translations()
    if req.task_id in translations:
        from ..benchmarks.travelplanner.evaluator_ko import evaluate_one_ko
        print(f"[api.benchmarks] using Korean evaluator for {req.task_id}")
        eval_result = evaluate_one_ko(query_data, plan)
    else:
        eval_result = evaluate_one(query_data, plan)

    summary = _summarize_eval(eval_result)
    summary["parsed_plan"] = plan
    return summary
