"""Wrap the vendored TravelPlanner evaluators (commonsense + hard) for per-query
evaluation, isolated from the upstream `os.chdir(...)` side effect.

The upstream `evaluation/{commonsense,hard}_constraint.py` modules call
`os.chdir(os.path.dirname(__file__))` at import time so that their relative
DB paths resolve. We snapshot+restore cwd around their import and around
each call to guarantee our own working directory is never mutated.
"""
import ast
import os
import sys
from pathlib import Path
from typing import Optional


REPO_PATH = Path(__file__).resolve().parents[3] / "third_party" / "TravelPlanner"

_cs_eval = None
_hd_eval = None


def _load_evaluators():
    """Lazy-load and cache upstream evaluation functions.

    Importing `evaluation.commonsense_constraint` triggers an os.chdir into
    the upstream evaluation dir. We restore cwd immediately after.
    """
    global _cs_eval, _hd_eval
    if _cs_eval is not None and _hd_eval is not None:
        return _cs_eval, _hd_eval

    if not REPO_PATH.exists():
        raise FileNotFoundError(
            f"TravelPlanner repo not found at {REPO_PATH}. "
            f"Run: git clone https://github.com/OSU-NLP-Group/TravelPlanner.git {REPO_PATH} "
            f"and unzip the database (see README)."
        )

    prev_cwd = os.getcwd()
    if str(REPO_PATH) not in sys.path:
        sys.path.insert(0, str(REPO_PATH))
    print(f"[travelplanner.evaluator] importing upstream evaluators (cwd={prev_cwd})")

    # Note: this triggers `os.chdir(...)` inside the upstream module.
    from evaluation.commonsense_constraint import evaluation as cs_eval
    from evaluation.hard_constraint import evaluation as hd_eval

    os.chdir(prev_cwd)
    print(f"[travelplanner.evaluator] cwd restored to {prev_cwd}")

    _cs_eval = cs_eval
    _hd_eval = hd_eval
    return _cs_eval, _hd_eval


def _normalize_pair(value) -> tuple[Optional[bool], Optional[str]]:
    """Upstream returns each constraint as [bool_or_None, message_or_None]."""
    if not isinstance(value, (list, tuple)) or len(value) < 1:
        return (None, None)
    passed = value[0]
    msg = value[1] if len(value) > 1 else None
    return (passed, msg)


def evaluate_one(query_data: dict, plan: Optional[list[dict]]) -> dict:
    """Run upstream commonsense + hard evaluators on a single parsed plan.

    Mirrors the gating logic in TravelPlanner's eval.py: hard constraints
    are only checked when the commonsense gate keys (`is_not_absent`,
    `is_valid_information_in_sandbox`) both pass.

    Returns a metric dict with both per-item booleans (for downstream micro
    aggregation) and macro pass flags.
    """
    if not plan:
        return {
            "delivery": False,
            "commonsense_pass_macro": False,
            "hard_pass_macro": False,
            "final_pass": False,
            "commonsense_per_item": None,
            "hard_per_item": None,
        }

    # Schema guard: vendored is_reasonable_visiting_city() reads
    # tested_data[i]['current_city'] without an `in` check, so a missing
    # key crashes the whole run with KeyError. Bail out as schema_invalid
    # before the upstream evaluator ever sees the plan.
    days = int(query_data.get("days", len(plan)))
    relevant_days = plan[:days]
    missing = [
        i for i, d in enumerate(relevant_days)
        if not isinstance(d, dict) or "current_city" not in d
    ]
    if missing:
        print(f"[travelplanner.evaluator] schema_invalid: missing 'current_city' in days {missing}")
        return {
            "delivery": True,
            "commonsense_pass_macro": False,
            "hard_pass_macro": False,
            "final_pass": False,
            "commonsense_per_item": {
                "schema_invalid": [False, f"missing 'current_city' in days {missing}"]
            },
            "hard_per_item": None,
        }

    cs_eval, hd_eval = _load_evaluators()

    # Upstream evaluators expect local_constraint as a dict; the HF row
    # serializes it as a Python-repr string. eval.py does the same coercion.
    if isinstance(query_data.get("local_constraint"), str):
        query_data = dict(query_data)  # avoid mutating caller
        query_data["local_constraint"] = ast.literal_eval(query_data["local_constraint"])

    prev_cwd = os.getcwd()
    # Upstream evaluators directly index into plan dicts (e.g. unit['current_city'])
    # and pass values to regex helpers without None-guards. Any LLM plan that
    # diverges from the expected schema can crash them with KeyError/TypeError/
    # AttributeError/IndexError. Treat any such crash as schema_invalid so a
    # single bad plan doesn't kill the whole run.
    try:
        cs_raw = cs_eval(query_data, plan)
        cs = {k: _normalize_pair(v) for k, v in cs_raw.items()}

        gate_ok = bool(cs.get("is_not_absent", (None,))[0]) and bool(
            cs.get("is_valid_information_in_sandbox", (None,))[0]
        )
        if gate_ok:
            hd_raw = hd_eval(query_data, plan)
            hd = {k: _normalize_pair(v) for k, v in hd_raw.items()}
        else:
            hd = None
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as e:
        os.chdir(prev_cwd)
        print(f"[travelplanner.evaluator] schema_invalid (eval crash): {type(e).__name__}: {e}")
        return {
            "delivery": True,
            "commonsense_pass_macro": False,
            "hard_pass_macro": False,
            "final_pass": False,
            "commonsense_per_item": {
                "schema_invalid": [False, f"{type(e).__name__}: {e}"]
            },
            "hard_per_item": None,
        }

    os.chdir(prev_cwd)

    cs_pass = all((p is None) or p for (p, _msg) in cs.values())
    hd_pass = (
        all((p is None) or p for (p, _msg) in hd.values())
        if hd is not None
        else False
    )

    return {
        "delivery": True,
        "commonsense_pass_macro": cs_pass,
        "hard_pass_macro": hd_pass,
        "final_pass": cs_pass and hd_pass,
        "commonsense_per_item": {k: list(v) for k, v in cs.items()},
        "hard_per_item": ({k: list(v) for k, v in hd.items()} if hd else None),
    }
