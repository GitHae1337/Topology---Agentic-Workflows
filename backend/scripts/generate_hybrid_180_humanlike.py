"""Generate human-like hybrid queries for all 180 TravelPlanner tasks.

Reads task metadata (org, dest, days, party size, budget, constraints) and
produces per-task hybrid queries that mirror the style of the 30 user-authored
examples in prompts_hybrid_authoring.xlsx. Each query:
  - Opens with a 1-sentence summary of the trip (route, days, party, budget, constraint)
  - Frames the work as 3 parallel sub-planners (transit / lodging / meals & attractions)
  - Spells out 2 specific cross-dependencies (transit↔lodging, lodging↔meals)
    tailored to the task's constraints (multi-city day-split, room rule,
    cuisine matching, group seating, tight budget, etc.)
  - Limits the lead's role to subtask assignment + final assembly
  - Appends the original TravelPlanner question

Output: backend/data/thinking_styles/prompts_v5_hybrid_180human.json
(same shape as prompts_v5.json, only the 'hybrid' query field changes for all 180 tasks)
"""
import json
import random
from ast import literal_eval
from pathlib import Path

ROOT = Path("/Users/joseph423/Kitae/Research/Topology/code")
TP_PATH = ROOT / "backend/data/travelplanner_validation.jsonl"
V5_PATH = ROOT / "backend/data/thinking_styles/prompts_v5.json"
OUT_PATH = ROOT / "backend/data/thinking_styles/prompts_v5_hybrid_180human.json"


def party_clause(n: int) -> str:
    if n == 1:
        return "solo"
    if n == 2:
        return "2-person"
    return f"group of {n}"


def constraint_text(local_constraint: dict) -> tuple[str, str]:
    """Returns (opening_constraint_phrase, dependency_focus).
       opening_constraint_phrase is appended to opening, e.g. ', entire rooms required'.
       dependency_focus is woven into a dependency, e.g. 'whether the chosen entire-room option leaves enough'.
    """
    if not local_constraint:
        return "", ""
    house_rule = local_constraint.get("house rule")
    cuisine = local_constraint.get("cuisine")
    room_type = local_constraint.get("room type")
    transp = local_constraint.get("transportation")

    parts = []
    dep_focus = ""
    if room_type:
        parts.append(f"{room_type} accommodations required")
        dep_focus = f"which {room_type} option fits the party size and budget"
    if house_rule:
        rule_map = {
            "smoking": "smoking-allowed",
            "visitors": "visitor-friendly",
            "parties": "party-allowed",
            "pets": "pet-friendly",
            "children": "no-children-restriction",
        }
        rule_text = rule_map.get(house_rule, f"{house_rule}-allowed")
        parts.append(rule_text + " accommodations required")
        dep_focus = f"which {rule_text} accommodation works for the party"
    if cuisine:
        if isinstance(cuisine, str):
            try:
                cuisine = literal_eval(cuisine)
            except Exception:
                cuisine = [cuisine]
        if isinstance(cuisine, list):
            cuisine_str = " and ".join(cuisine)
        else:
            cuisine_str = str(cuisine)
        parts.append(f"{cuisine_str} cuisines wanted")
        dep_focus = f"which neighborhoods have {cuisine_str} options near the chosen stay"
    if transp:
        parts.append(f"transportation preference: {transp}")
    if not parts:
        return "", ""
    return ", " + ", ".join(parts), dep_focus


def transit_lodging_clause(task: dict) -> str:
    cities = task["visiting_city_number"]
    party = party_clause(task["people_number"])
    if cities > 1:
        return (
            f"transit and lodging have to settle the day-split between the {cities} "
            f"{task['dest']} cities together (and therefore how many nights each city's stay needs)"
        )
    # single-city trip — focus on check-in fit
    if party == "solo":
        party_phrase = "a solo traveler"
    elif "group of" in party:
        party_phrase = f"a {party}"
    else:
        party_phrase = f"a {party} party"
    return (
        f"transit and lodging have to agree on whether the flight times fit "
        f"the chosen accommodation's check-in window for {party_phrase}"
    )


def lodging_meals_clause(task: dict, dep_focus: str) -> str:
    cities = task["visiting_city_number"]
    party = task["people_number"]
    pieces = []
    if dep_focus:
        # Constraint-driven dependency
        if cities > 1:
            return (
                f"lodging and meals have to align on which neighborhoods in each city anchor "
                f"the chosen stays so the meal and attraction picks match what's actually nearby, "
                f"including {dep_focus}"
            )
        return (
            f"lodging and meals have to coordinate on {dep_focus} and which neighborhood "
            f"the chosen stay anchors so the meal and attraction picks remain reachable"
        )
    # No constraint — generic neighborhood / group-size dependency
    if party >= 5:
        return (
            f"lodging and meals have to coordinate on which restaurants and attractions near "
            f"the chosen stay can actually accommodate a party of {party}"
        )
    if cities > 1:
        return (
            f"lodging and meals have to align on which clusters in each city anchor the daily "
            f"plans so the meal and attraction picks fit the chosen stays"
        )
    return (
        f"lodging and meals have to align on which neighborhood the chosen stay anchors "
        f"so daily meals and attractions are reachable within budget"
    )


_OPENING_TEMPLATES = [
    "{summary}. Please run this as three parallel sub-planners (transit, lodging, meals & attractions) coordinating directly with each other.",
    "I want this planned as three parallel specialists working together rather than one planner doing everything — transit, lodging, meals & attractions running in parallel with direct peer exchange. {summary}.",
    "{summary} — the sub-parts have real interplay so I'd like three parallel sub-planners (transit / lodging / meals & attractions) talking to each other directly rather than through a single lead.",
    "Plan this as three parallel sub-planners — transit, lodging, meals & attractions — running side by side and reconciling cross-dependencies among themselves. {summary}.",
]


def build_summary(task: dict, cons_open: str) -> str:
    party_n = task["people_number"]
    party_s = party_clause(party_n)
    days = task["days"]
    org, dest = task["org"], task["dest"]
    budget = task["budget"]
    cities = task["visiting_city_number"]
    if cities > 1:
        route = f"{org}→{dest} trip across {cities} cities"
    else:
        route = f"{org}→{dest} trip"
    summary = f"This is a {days}-day {party_s} {route} on ${budget:,}{cons_open}"
    return summary


def make_hybrid_query(task: dict, rng: random.Random) -> str:
    cons_open, dep_focus = constraint_text(task.get("local_constraint") or {})
    summary = build_summary(task, cons_open)
    opening_tpl = rng.choice(_OPENING_TEMPLATES)
    opening = opening_tpl.format(summary=summary)

    dep1 = transit_lodging_clause(task)
    dep2 = lodging_meals_clause(task, dep_focus)

    lead_clause = "Lead only assigns the subtasks and assembles the final plan; the cross-cut values get locked between the workers themselves."

    body = f"{opening}\n\nSpecifically: {dep1}, and {dep2}.\n\n{lead_clause}"
    # Append original task query (preserves v5 convention: prefix + original question)
    body += "\n\n" + task["query"]
    return body


def parse_local_constraint(s):
    if isinstance(s, dict):
        return s
    if not s:
        return {}
    try:
        return literal_eval(s) if isinstance(s, str) else dict(s)
    except Exception:
        return {}


def main():
    tasks = []
    with open(TP_PATH) as f:
        for line in f:
            d = json.loads(line)
            d["local_constraint"] = parse_local_constraint(d.get("local_constraint"))
            tasks.append(d)
    print(f"Loaded {len(tasks)} tasks")

    with open(V5_PATH) as f:
        prompts = json.load(f)
    tasks_by_id = {t["task_id"]: t for t in prompts["tasks"]}

    rng = random.Random(42)
    # Stable rotation by task_id index
    for i, t in enumerate(tasks):
        new_q = make_hybrid_query(t, rng)
        if t["task_id"] not in tasks_by_id:
            print(f"WARN: task {t['task_id']} not in prompts_v5; skipping")
            continue
        tasks_by_id[t["task_id"]]["queries"]["hybrid"] = new_q

    with open(OUT_PATH, "w") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_PATH}")

    # Show 3 examples (one per level, with varied constraint)
    print("\n=== examples ===")
    for tid in ["travelplanner-3", "travelplanner-66", "travelplanner-135"]:
        q = tasks_by_id[tid]["queries"]["hybrid"]
        print(f"\n--- {tid} ---")
        print(q)


if __name__ == "__main__":
    main()
