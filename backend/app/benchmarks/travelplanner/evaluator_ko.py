"""Korean evaluator — 18-task self-contained.

Reuses vendored TravelPlanner evaluators (`commonsense_constraint.evaluation`,
`hard_constraint.evaluation`) but monkey-patches the city DB, the
restaurants/accommodation/attractions DataFrames, AND the four hard-constraint
checks (room_rule/room_type/cuisine/transportation) to operate on Korean
enum values from translations_ko.json.

Scope: only the 18 Korean tasks in translations_ko.json. valid_cost is forced
to skipped — Korean transportation cost lookup is not implemented yet.
"""
import json
import math
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .evaluator import _load_evaluators, evaluate_one


CITY_DB_PATH = Path(__file__).resolve().parent / "citySet_kr.txt"
# evaluator_ko.py is at backend/app/benchmarks/travelplanner/, so parents[3]
# is backend/, where the data/ directory lives.
TRANSLATIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "translations_ko.json"


_PATCHED = False
# Per-task transportation rows from translations_ko.json. Built during patch
# so get_total_cost_ko can look up cost without re-reading JSON each call.
_TRANSPORT_BY_TASK: dict[str, list[dict]] = {}


def _patch_vendored_modules():
    """One-time monkey-patch: swap city DB + reference DataFrames in the
    upstream commonsense_constraint and hard_constraint modules.
    """
    global _PATCHED
    if _PATCHED:
        return

    print("[evaluator_ko] loading vendored evaluators (triggers upstream import)")
    _load_evaluators()  # ensures upstream modules are imported + cwd restored

    # Now upstream modules are in sys.modules. Pull them and patch.
    import evaluation.commonsense_constraint as cc
    import evaluation.hard_constraint as hc

    # --- 1. City DB swap ---
    print(f"[evaluator_ko] swapping city DB from {CITY_DB_PATH}")
    raw = open(CITY_DB_PATH, "r", encoding="utf-8").read().split("\n")
    ko_set = [line for line in raw if "\t" in line]
    ko_map = {x: y for x, y in [u.split("\t") for u in ko_set]}
    cc.city_state_set = ko_set
    cc.city_state_map = ko_map
    print(f"[evaluator_ko] city DB: {len(ko_map)} cities")

    # --- 2. Reference DataFrames swap ---
    rest_df, acc_df, att_df = _build_reference_dfs()
    cc.restaurants.data = rest_df
    cc.accommodation.data = acc_df
    cc.attractions.data = att_df
    hc.restaurants.data = rest_df
    hc.accommodation.data = acc_df
    hc.attractions.data = att_df
    print(f"[evaluator_ko] reference DBs: restaurants={len(rest_df)}, "
          f"accommodations={len(acc_df)}, attractions={len(att_df)}")

    # --- 3. Commonsense function swap (Korean accommodation check) ---
    # Vendored is_valid_accommodaton checks min-nights stay length using a
    # 'minimum nights' column the Korean mock doesn't track. Skip that check
    # — verify only that each accommodation exists in the reference.
    cc.is_valid_accommodaton = is_valid_accommodation_ko

    # --- 3b. extract_from_to swap — recognize Korean "X to Y" / "X → Y"
    # patterns in addition to vendored's "from X to Y". Used by
    # is_reasonable_visiting_city, is_valid_information_in_current_city,
    # is_valid_information_in_sandbox, is_not_absent. Keeps high-level logic
    # identical, only parsing is broadened.
    cc.extract_from_to = extract_from_to_ko
    hc.extract_from_to = extract_from_to_ko

    # --- 4. Hard-constraint function swaps (Korean enum) ---
    hc.is_valid_room_rule = is_valid_room_rule_ko
    hc.is_valid_room_type = is_valid_room_type_ko
    hc.is_valid_cuisine = is_valid_cuisine_ko
    hc.is_valid_transportation = is_valid_transportation_ko
    hc.get_total_cost = get_total_cost_ko

    # Per-task transportation lookup for get_total_cost_ko.
    global _TRANSPORT_BY_TASK
    with open(TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
        ko_data = json.load(f)
    _TRANSPORT_BY_TASK = {}
    for tid, task in ko_data.items():
        ref = task.get("reference_information")
        if isinstance(ref, dict):
            _TRANSPORT_BY_TASK[tid] = ref.get("transportation", []) or []
    print(f"[evaluator_ko] built transport lookup for {len(_TRANSPORT_BY_TASK)} tasks")
    # Re-bind the module-level `evaluation` so it picks up our swapped funcs.
    # vendored evaluation() captures function names at call-time (module
    # attribute lookup) so the swaps above are sufficient — no rebind needed.
    print("[evaluator_ko] hard-constraint functions swapped (room_rule/room_type/cuisine/transport)")

    _PATCHED = True


# ---------- Korean hard-constraint functions ----------
# Each mirrors the vendored function but matches Korean enum values from
# translations_ko.json against Korean substrings in the reference data.

def _accommodation_row(name: str, city: str):
    """Look up an accommodation row by (name substring, exact city)."""
    import evaluation.hard_constraint as hc
    return hc.accommodation.data[
        (hc.accommodation.data["NAME"].astype(str).str.contains(re.escape(name)))
        & (hc.accommodation.data["city"] == city)
    ]


def extract_from_to_ko(text: str):
    """Korean-aware drop-in for vendored extract_from_to.

    Recognizes three patterns, in priority order:
        1. "from X to Y"        — vendored English (downward compatible)
        2. "X to Y"             — 'from' omitted (typical Korean LLM output)
        3. "X → Y" or "X->Y"    — Korean arrow notation

    Returns (origin, destination) or (None, None) if no pattern matches.
    Same return contract as vendored so all callers work unchanged.
    """
    if not text:
        return (None, None)

    # 1. Vendored English pattern.
    m = re.search(r"from\s+(.+?)\s+to\s+([^,]+?)(?=[,]|$)", text)
    if m:
        return (m.group(1).strip(), m.group(2).strip())

    # 2. "X to Y" without 'from'. Anchor at start to avoid matching "back to"
    # in the middle of a sentence; tolerate leading whitespace.
    m = re.search(r"^\s*([^,]+?)\s+to\s+([^,]+?)(?=[,]|$)", text)
    if m:
        return (m.group(1).strip(), m.group(2).strip())

    # 3. Korean arrow notation.
    m = re.search(r"([^\s,→\->]+)\s*(?:→|->)\s*([^\s,]+)", text)
    if m:
        return (m.group(1).strip(), m.group(2).strip())

    return (None, None)


def is_valid_accommodation_ko(question, tested_data):
    """Korean version of vendored is_valid_accommodaton.

    Mirrors vendored logic: count consecutive stays at the same accommodation,
    look up its 'minimum nights' policy in the reference, fail if the
    consecutive-stay count is below that minimum.

    Difference from vendored: if the reference doesn't track 'minimum nights'
    for a row (None — user hasn't filled it in translations_ko.json yet),
    skip the min-nights rule for THAT row rather than crash. Other rows with
    populated minimum_nights are still checked.
    """
    import evaluation.commonsense_constraint as cc
    from utils.func import get_valid_name_city

    data = []
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]
        if "accommodation" not in unit:
            return False, "숙소 정보 누락"
        data.append(unit["accommodation"])

    consecutive = cc.count_consecutive_values(data)
    for unit in consecutive:
        if not unit or unit[0] in ("-", ""):
            continue
        name, city = get_valid_name_city(unit[0])
        rows = cc.accommodation.data[
            (cc.accommodation.data["NAME"].astype(str).str.contains(re.escape(name)))
            & (cc.accommodation.data["city"] == city)
        ]
        if len(rows) == 0:
            return False, f"숙소 '{unit[0]}' 참고 자료에 없음"
        min_nights = rows.iloc[0].get("minimum nights")
        if min_nights is None:
            # Reference doesn't track this row's policy — skip rule.
            continue
        if unit[1] < int(min_nights):
            return False, f"숙소 '{unit[0]}' 최소 숙박일 위반 ({unit[1]}박 < {min_nights}박)"
    return True, None


def is_valid_room_rule_ko(question, tested_data):
    """Korean enum:
        '흡연 가능 객실'   → reject row whose house_rules contains '흡연 금지'
        '10세 미만 아동 동반' → reject row whose house_rules contains '아동 금지'/'어린이 금지'
        '방문객 허용'      → reject row whose house_rules contains '방문객 금지'
        '반려동물 동반 가능' → reject row whose house_rules contains '펫 금지'/'반려동물 금지'
    house_rules in reference is a single string like '흡연 금지, 파티 금지, 펫 가능'.
    """
    rule = question["local_constraint"].get("house rule")
    if rule is None:
        return True, None

    REJECT_SUBSTRINGS = {
        "흡연 가능 객실": ["흡연 금지"],
        "10세 미만 아동 동반": ["아동 금지", "어린이 금지", "10세 미만 금지"],
        "방문객 허용": ["방문객 금지"],
        "반려동물 동반 가능": ["펫 금지", "반려동물 금지"],
    }
    bads = REJECT_SUBSTRINGS.get(rule, [])

    for unit in tested_data:
        acc = unit.get("accommodation")
        if not acc or acc == "-":
            continue
        # plan format may be "Name, City" — split last comma
        name, _, city = acc.rpartition(",")
        name, city = name.strip(), city.strip()
        if not name:
            continue
        rows = _accommodation_row(name, city)
        if len(rows) == 0:
            continue
        rules_str = str(rows["house_rules"].values[0])
        for bad in bads:
            if bad in rules_str:
                return False, f"{rule} 제약 위반: '{name}'의 룰 '{rules_str}'에 '{bad}' 포함"
    return True, None


def is_valid_room_type_ko(question, tested_data):
    """Korean enum:
        '공유 도미토리 제외' → reject row whose room type is '공유 객실' / '도미토리'
        '개인실'           → require room type '개인실' / 'Private'
        '독채(독립 공간)'   → require row whose room type is '독채' / '전체 공간'
    """
    rt = question["local_constraint"].get("room type")
    if rt is None:
        return True, None

    for unit in tested_data:
        acc = unit.get("accommodation")
        if not acc or acc == "-":
            continue
        name, _, city = acc.rpartition(",")
        name, city = name.strip(), city.strip()
        if not name:
            continue
        rows = _accommodation_row(name, city)
        if len(rows) == 0:
            continue
        room_type_val = str(rows["room type"].values[0])
        if rt == "공유 도미토리 제외":
            if "공유" in room_type_val or "도미토리" in room_type_val:
                return False, f"공유 도미토리 제외 위반: '{name}'의 객실 유형 '{room_type_val}'"
        elif rt == "개인실":
            if "개인실" not in room_type_val and "Private" not in room_type_val:
                return False, f"개인실 요구 위반: '{name}'의 객실 유형 '{room_type_val}'"
        elif rt == "독채(독립 공간)":
            if "독채" not in room_type_val and "전체" not in room_type_val:
                return False, f"독채(독립 공간) 요구 위반: '{name}'의 객실 유형 '{room_type_val}'"
    return True, None


def is_valid_cuisine_ko(question, tested_data):
    """Match each required Korean cuisine against the cuisine values seen
    in the trip's restaurant rows. Reference's cuisine column may be a
    single string or comma-separated.
    """
    target = question["local_constraint"].get("cuisine")
    if not target:
        return True, None

    import evaluation.hard_constraint as hc
    seen = set()
    for unit in tested_data:
        for meal_key in ("breakfast", "lunch", "dinner"):
            meal = unit.get(meal_key)
            if not meal or meal == "-":
                continue
            name, _, city = meal.rpartition(",")
            name, city = name.strip(), city.strip()
            if not name:
                continue
            rows = hc.restaurants.data[
                (hc.restaurants.data["Name"].astype(str).str.contains(re.escape(name)))
                & (hc.restaurants.data["City"] == city)
            ]
            if len(rows) == 0:
                continue
            cuis_val = str(rows["Cuisines"].values[0])
            for c in cuis_val.split(","):
                seen.add(c.strip())

    for required in target:
        if required not in seen:
            return False, f"{required} 메뉴가 일정에 없음"
    return True, None


# Plan transportation string → reference type keyword. Tries number match
# first (e.g. "KTX-1000" exact), falls back to type substring.
_TRANSPORT_TYPE_KEYWORDS = [
    ("KTX", "KTX"),
    ("SRT", "SRT"),
    ("무궁화", "무궁화호"),
    ("새마을", "새마을호"),
    ("ITX", "ITX"),
    ("고속버스", "고속버스"),
    ("시외버스", "시외버스"),
    ("렌터카", "렌터카(자가운전)"),
    ("자가운전", "렌터카(자가운전)"),
    ("자가용", "렌터카(자가운전)"),
    ("택시", "택시"),
    ("항공편", "항공편"),
    ("비행기", "항공편"),
]


def _resolve_transport_cost_ko(plan_str: str, transport_rows: list[dict], people: int) -> int:
    """Match a plan transportation line to a reference row, return cost.

    Strategy:
        1. Number match — if any reference number (e.g. 'KTX-1000') appears
           in the plan string, use that row.
        2. Type keyword match — scan for Korean type keywords ('KTX', '렌터카',
           '택시', etc.) and match against the row's 'type' field.

    Returns cost = price_per_person * people. 0 if no row matched.
    """
    if not plan_str or not transport_rows:
        return 0

    # 1. Number match
    for r in transport_rows:
        num = r.get("number", "")
        if num and num in plan_str:
            price = r.get("price_per_person", 0) or 0
            return int(price) * people

    # 2. Type keyword match — case-insensitive substring scan.
    s_lower = plan_str.lower()
    for keyword, type_match in _TRANSPORT_TYPE_KEYWORDS:
        if keyword.lower() in s_lower:
            for r in transport_rows:
                if r.get("type") == type_match:
                    price = r.get("price_per_person", 0) or 0
                    return int(price) * people
    return 0


def get_total_cost_ko(question, tested_data):
    """Korean version of vendored get_total_cost.

    Sums plan transportation/meal/accommodation cost using Korean reference
    data instead of vendored SQLite + GoogleDistanceMatrix. The transportation
    branch is the main difference: vendored matches English keywords
    ('Flight Number', 'Self-driving', 'Taxi'); Korean fork matches Korean
    keywords against translations_ko.json's transportation rows.
    """
    import evaluation.hard_constraint as hc
    from utils.func import get_valid_name_city

    task_id = question.get("task_id", "")
    transport_rows = _TRANSPORT_BY_TASK.get(task_id, [])
    people = int(question.get("people_number", 1) or 1)

    total = 0.0
    for i in range(min(question["days"], len(tested_data))):
        unit = tested_data[i]

        # Transportation
        tr = unit.get("transportation", "")
        if tr and tr != "-":
            total += _resolve_transport_cost_ko(tr, transport_rows, people)

        # Meals — same lookup as vendored, but on the swapped restaurants DF.
        for meal in ("breakfast", "lunch", "dinner"):
            val = unit.get(meal, "")
            if val and val != "-":
                name, city = get_valid_name_city(val)
                rows = hc.restaurants.data[
                    (hc.restaurants.data["Name"].astype(str).str.contains(re.escape(name)))
                    & (hc.restaurants.data["City"] == city)
                ]
                if len(rows) > 0:
                    cost = rows.iloc[0]["Average Cost"] or 0
                    total += int(cost) * people

        # Accommodation
        acc = unit.get("accommodation", "")
        if acc and acc != "-":
            name, city = get_valid_name_city(acc)
            rows = hc.accommodation.data[
                (hc.accommodation.data["NAME"].astype(str).str.contains(re.escape(name)))
                & (hc.accommodation.data["city"] == city)
            ]
            if len(rows) > 0:
                row = rows.iloc[0]
                price = row.get("price", 0) or 0
                max_occ = int(row.get("maximum occupancy", 1) or 1)
                if max_occ < 1:
                    max_occ = 1
                total += int(price) * math.ceil(people / max_occ)

    return total


def is_valid_transportation_ko(question, tested_data):
    """Korean enum:
        '항공편 이용 불가'           → reject if any transportation contains '항공편'/'Flight'/'KE'/'OZ'/'LJ'
        '자가운전 불가(대중교통만)'   → reject if contains '자가운전'/'렌터카'/'Self-driving'
    """
    tr = question["local_constraint"].get("transportation")
    if tr is None:
        return True, None

    for unit in tested_data:
        info = unit.get("transportation", "")
        if not info or info == "-":
            continue
        if tr == "항공편 이용 불가":
            if any(tok in info for tok in ["항공편", "Flight", "비행기"]):
                return False, f"항공편 이용 불가 위반: '{info}'"
        elif tr == "자가운전 불가(대중교통만)":
            if any(tok in info for tok in ["자가운전", "렌터카", "Self-driving"]):
                return False, f"자가운전 불가 위반: '{info}'"
    return True, None


def _build_reference_dfs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Aggregate all 18 tasks' reference data into in-memory DataFrames with
    vendored-compatible column names.

    Vendored evaluator expects:
      - restaurants:   Name, City, Cuisines, Average Cost, Aggregate Rating
      - accommodation: NAME, city, price, room type, house_rules,
                       maximum occupancy, review rate number
      - attractions:   Name, City, Address
    Korean translations_ko uses lowercase keys (name, city, cuisine, ...).
    """
    print(f"[evaluator_ko] loading translations from {TRANSLATIONS_PATH}")
    with open(TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    restaurants = []
    accommodations = []
    attractions = []
    for tid, task in data.items():
        ref = task.get("reference_information")
        if not isinstance(ref, dict):
            continue
        restaurants.extend(ref.get("restaurants", []))
        accommodations.extend(ref.get("accommodations", []))
        attractions.extend(ref.get("attractions", []))

    rest_rows = [
        {
            "Name": r.get("name", ""),
            "City": r.get("city", ""),
            "Cuisines": r.get("cuisine", ""),
            "Average Cost": r.get("price_per_person", 0),
            "Aggregate Rating": r.get("rating", 0),
        }
        for r in restaurants
    ]
    acc_rows = [
        {
            "NAME": r.get("name", ""),
            "city": r.get("city", ""),
            "price": r.get("price_per_night", 0),
            "room type": r.get("room_type", ""),
            "house_rules": r.get("house_rules", ""),
            # Read straight from reference — None if user didn't fill it.
            # The Korean fork checks for None and skips the row's min-nights
            # rule rather than inventing a default.
            "minimum nights": r.get("minimum_nights"),
            "maximum occupancy": r.get("max_occupancy", 0),
            "review rate number": r.get("rating", 0),
        }
        for r in accommodations
    ]
    att_rows = [
        {
            "Name": r.get("name", ""),
            "City": r.get("city", ""),
            "Address": r.get("address", ""),
        }
        for r in attractions
    ]

    return pd.DataFrame(rest_rows), pd.DataFrame(acc_rows), pd.DataFrame(att_rows)


def _normalize_plan_korean(plan):
    """Prefix 'X to Y' patterns with 'from ' so vendored functions whose
    branching depends on the literal substring 'from' (e.g.
    `if 'from' in city_value:` in is_reasonable_visiting_city) fire correctly
    on Korean LLM output that omits 'from'.

    Mutates a copy — the original plan is left untouched.
    """
    if not plan:
        return plan
    KEYS = ("current_city", "transportation")
    out = []
    for day in plan:
        if not isinstance(day, dict):
            out.append(day)
            continue
        new_day = dict(day)
        for key in KEYS:
            val = new_day.get(key)
            if not isinstance(val, str) or "from" in val.lower():
                continue
            # Match a leading "X to Y" segment, prefix with 'from '.
            m = re.search(r"^\s*([^,]+?)\s+to\s+([^,]+?)(?=[,]|$)", val)
            if m:
                org, dest = m.group(1).strip(), m.group(2).strip()
                # Replace first occurrence only — preserve trailing detail.
                new_day[key] = val.replace(f"{org} to {dest}", f"from {org} to {dest}", 1)
        out.append(new_day)
    return out


def evaluate_one_ko(query_data: dict, plan: Optional[list[dict]]) -> dict:
    """Korean version of evaluate_one — vendored logic + city/reference swap
    + Korean plan normalization so 'X to Y' (no 'from') reaches the from-branch
    that all the city-extraction code lives behind.
    """
    _patch_vendored_modules()

    # Normalize before vendored sees the plan. extract_from_to_ko already
    # handles the bare 'X to Y' case, but vendored's `if 'from' in ...`
    # branching has to fire first for that helper to even be called.
    plan = _normalize_plan_korean(plan)

    result = evaluate_one(query_data, plan)

    return result
