"""Parse a TravelPlanner plan (list[dict]) out of an LLM's natural-language reply.

Strategies, in order:
  1. Fenced code block ```python ... ``` or ```json ... ```
  2. Bare list-of-dicts span starting with '[{' and ending with '}]'

Returns None if no valid plan list is recoverable. The vendored evaluator
treats None as "delivery failure" (Delivery Rate = 0 for that trial).
"""
import ast
import json
import re
from typing import Optional


_FENCE_RE = re.compile(r"```(?:python|json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)
_BARE_LIST_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.DOTALL)


def _is_list_of_dicts(value) -> bool:
    if not isinstance(value, list):
        return False
    # Empty dicts are allowed (padding). Reject if any non-dict item present.
    return all(isinstance(item, dict) for item in value)


def _try_parse(span: str) -> Optional[list[dict]]:
    """Attempt ast.literal_eval first (handles Python repr / single quotes),
    then json.loads. Both can fail on LLM output — try/except is the right
    boundary here per CLAUDE.md spirit (parsing untrusted external strings).
    """
    print(f"[travelplanner.parser] trying to parse {len(span)} chars")
    parsed = None
    try:
        parsed = ast.literal_eval(span)
    except (SyntaxError, ValueError) as e:
        print(f"[travelplanner.parser] ast.literal_eval failed: {type(e).__name__}: {e}")
    if parsed is None:
        try:
            parsed = json.loads(span)
        except json.JSONDecodeError as e:
            print(f"[travelplanner.parser] json.loads failed: {e}")
            return None
    if _is_list_of_dicts(parsed):
        return parsed
    print(f"[travelplanner.parser] parsed but not list[dict]: type={type(parsed).__name__}")
    return None


def parse_plan(text: str) -> Optional[list[dict]]:
    """Extract the final plan from agent output text.

    Returns:
        list[dict] or None. Padding empty dicts ({}) are preserved in-place
        — the upstream evaluator expects length 7 padding for trips < 7 days.
    """
    if not text:
        return None

    # 1. Markdown fenced block — pick the LAST one (final answer convention)
    fences = _FENCE_RE.findall(text)
    if fences:
        candidate = fences[-1].strip()
        plan = _try_parse(candidate)
        if plan is not None:
            return plan

    # 2. Bare list-of-dicts span
    span = _BARE_LIST_RE.search(text)
    if span:
        plan = _try_parse(span.group(0))
        if plan is not None:
            return plan

    print("[travelplanner.parser] no parseable plan found")
    return None
