"""Paper-style prompt templates for centralized + hybrid topologies.

4-stage flow per trial:
  R1: orchestrator planning           -> JSON {subtasks: [{agent_id, objective, focus}]}
  R1: sub-agent work + summarize       -> findings (no plan)
  R2: orchestrator coordination (xN)   -> per-agent guidance string
  R2: sub-agent refine + summarize     -> updated findings
  R3: orchestrator synthesis           -> final plan (the only place with output schema)

Hybrid variant lets the manager append `[PEER:Worker-i,Worker-j] <focus>` to
a coordination guidance; executor parses it and runs a lateral exchange call
on those two workers before their next refine.
"""

ORCHESTRATOR_BASE_SYSTEM = """You are a lead agent who orchestrates a team of travel-planning sub-agents.

You coordinate multiple sub-agents to build one travel plan. Your responsibilities:
1. PLANNING: Read the user's request and turn it into subtasks for your sub-agents.
2. COORDINATION: Give each sub-agent guidance each round based on their progress and the rest of the team's findings.
3. DECISION-MAKING: Decide when the team has enough to assemble the final plan.
4. SYNTHESIS: Combine the sub-agents' findings into one final plan in the required output format.

You have full visibility across all sub-agents and their findings.

Build the plan using ONLY the candidate flights, restaurants, accommodations and attractions in the reference information. Do not invent any names, IDs, or prices.

{task_instance}"""


SUB_AGENT_BASE_SYSTEM = """You are a travel-planning sub-agent.

You work as part of a team. Given guidance from the lead agent, work through your assigned part. Use ONLY the candidate flights, restaurants, accommodations and attractions in the reference information. Do not invent names, IDs, or prices.

Stay within your assigned objective; report what you find rather than producing the whole plan.

Reference data available to you:
{task_instance}"""


ORCHESTRATOR_PLANNING_USER = """Create a plan to work on this task.

The user's request above describes how they want the work organized. Translate the organization in their request into subtasks as faithfully as you can, using the roles and channels available to you. Map each part of the user's stated structure to a subtask.

Create exactly {num_agents} subtasks. Each subtask must be specific and focused.

Return ONLY a JSON object with this structure:
{{
    "subtasks": [
        {{
            "agent_id": "agent_1",
            "objective": "Specific objective for this sub-agent",
            "focus": "The part of the user's stated structure this agent covers"
        }}
    ],
    "reasoning": "For each subtask, state which part of the user's request it came from"
}}"""


ORCHESTRATOR_COORDINATION_USER = """ORCHESTRATOR COORDINATION TASK:

CURRENT SITUATION:
- Round: {round_num}
- Agent: {agent_id}
- Agent's objective: {agent_objective}
- Agent's focus: {agent_strategy}

AGENT'S PROGRESS:
{agent_findings_summary}

TEAM CONTEXT:
{team_context}

COORDINATION TASK:
Based on this agent's progress and the team context, give {agent_id} specific guidance for their next step.

Consider:
- Is the agent making progress on its objective?
- Are its findings usable for the final plan (valid candidates, prices, room rules, no duplicate restaurants or attractions across the team)?
- Do its findings conflict with another agent's (budget overrun, schedule clash, same restaurant picked twice)?
- Should it keep exploring, narrow down, change approach, or wrap up?

Give one clear, actionable message (2-3 sentences max). No JSON, just the message."""


# Hybrid variant: PEER is a first-class action, not an optional trailer.
ORCHESTRATOR_COORDINATION_USER_HYBRID = """ORCHESTRATOR COORDINATION TASK:

CURRENT SITUATION:
- Round: {round_num}
- Agent: {agent_id}
- Agent's objective: {agent_objective}
- Agent's focus: {agent_strategy}

AGENT'S PROGRESS:
{agent_findings_summary}

TEAM CONTEXT:
{team_context}

COORDINATION TASK:
You have TWO actions available for this turn — pick whichever fits the situation best:

  ACTION 1 — Give {agent_id} specific guidance for their next step (1-3 sentences).

  ACTION 2 — Trigger a lateral peer exchange so {agent_id} can reconcile directly with another worker BEFORE refining. End your message with a single line on its own:
      [PEER:Worker-i,Worker-j] <focus of the exchange>
    Use this when two workers' findings need direct alignment — timing conflicts (flight arrival vs hotel check-in), budget allocation across categories, hard-constraint cross-checks, conflicting picks (same restaurant chosen twice), etc.

Consider:
- Is the agent making progress on its objective?
- Are its findings consistent with other agents' findings? (If two agents are in tension or duplicating work, ACTION 2 is often the right move.)
- Should it explore more, narrow down, or coordinate laterally?

Choose ONE action. No JSON, just the message — with the [PEER:...] trailer at the end if you choose ACTION 2."""


ORCHESTRATOR_SYNTHESIS_USER = """SYNTHESIS TASK:
Your team has gathered the findings below. Assemble them into one final travel plan.

{all_findings}

SYNTHESIS INSTRUCTIONS:
- Use ONLY items that appear in the team's findings and the reference information. Do not invent names, IDs, or prices.
- Across the whole trip, no restaurant may appear in more than one meal slot, and no attraction may appear on more than one day. The same accommodation across consecutive nights is expected.
- The chosen accommodation must satisfy every house rule and the minimum-nights rule from the user's request.
- Total cost (transportation + accommodation x nights + every meal) must not exceed the user's budget. If over, swap in cheaper items from the findings before finalizing.
- If the user's request listed required cuisines, every one must appear at least once.

Return the final plan as a Python list of dicts, one dict per day, padded with empty dicts {{}} to length 7. Days are 1-indexed.
Each non-empty day-dict must contain these keys:
  'days' (int), 'current_city' (str: 'CityX' or 'from CityX to CityY'),
  'transportation' (str: 'Flight Number: F..., from X to Y, Departure Time: HH:MM, Arrival Time: HH:MM' / 'Self-driving, ...' / '-'),
  'breakfast', 'lunch', 'dinner' (str: 'Restaurant Name, City' or '-'),
  'attraction' (str: 'Name, City;Name, City;' or '-'),
  'accommodation' (str: 'Hotel Name, City' or '-')

Wrap the plan in a ```python ... ``` code block so it can be parsed automatically. Output only the code block."""


SUB_AGENT_START_USER = """To start, here is your objective and guidance from the lead agent.
Objective:
{orchestrator_objective}
Focus:
{orchestrator_focus}

Work on your objective using the reference information available to you in the system instructions.

Then summarize your findings to be most useful to your team. Include the candidates you found with their relevant attributes (flight numbers and times and per-person price; accommodation name, price-per-night, room type, house rules, max occupancy, minimum nights; restaurant name and city; attraction name and city), what you confirmed, and any conclusions. Do not assemble the final plan."""


SUB_AGENT_COORDINATION_USER = """Round {round_num} guidance from the lead agent:
{orchestrator_guidance}

Your previous findings:
{previous_findings}
{peer_section}
Continue working on your objective and summarize your updated findings. Include candidates with their relevant attributes and any conclusions. Do not assemble the final plan."""


SUB_AGENT_PEER_USER = """You are in a lateral peer exchange with {peer_agent_id}.

The lead agent's instruction for this exchange:
{peer_focus}

Your current findings:
{own_findings}

{peer_agent_id}'s current findings:
{peer_findings}

Discuss with {peer_agent_id} based on the lead agent's instruction. Report what you reconcile or refine in your findings. Do not assemble the final plan."""


# ============================================================================
# Independent topology (paper-style framing; output schema preserved per agent)
# ============================================================================
# `{{...}}` are doubled so .format(task_instance=...) leaves them intact.
# SAS topology is NOT updated here — its preset stays on the legacy framing.

_TRAVEL_PLAN_OUTPUT_SCHEMA = """OUTPUT FORMAT (strict, machine-evaluated):
Return a Python list of dicts, one dict per day. Days are 1-indexed. Pad the list with empty dicts {{}} so the total length is exactly 7 (3-day trip → 3 day-dicts + 4 empty dicts).

Each non-empty day-dict MUST contain these keys:
  - 'days': int (1..N)
  - 'current_city': str  ('CityX' for in-city days, or 'from CityX to CityY' for travel days)
  - 'transportation': str  (e.g. 'Flight Number: F1234567, from X to Y, Departure Time: HH:MM, Arrival Time: HH:MM' / 'Self-driving, from X to Y, duration: ..., distance: ..., cost: ...' / '-')
  - 'breakfast', 'lunch', 'dinner': 'Restaurant Name, City' or '-'
  - 'attraction': 'Name1, City;Name2, City;' or '-'  (semicolons separate; trailing semicolon ok)
  - 'accommodation': 'Hotel Name, City' or '-'

Rules:
- Use '-' for fields not applicable (e.g. transportation '-' on in-city days; meals '-' after returning to origin).
- All names must be exact substrings of what appears in the reference data.
- A restaurant may appear in at most one meal slot across the entire trip; an attraction may appear in at most one day.
- Total cost (transportation + accommodation x nights + meals) must not exceed the query's budget.
- The accommodation must satisfy every house rule and the minimum-nights rule from the query.
- If the query lists required cuisines, every one of them must appear at least once in the meals you pick.

Wrap the final plan in a ```python ... ``` code block so it can be parsed automatically."""


INDEPENDENT_WORKER_BASE_SYSTEM = """You are an intelligent travel-planning agent.

You work as Independent Worker-{worker_index} of {num_workers} — no coordination with other workers, just solve the task end-to-end yourself. Use ONLY the candidate flights, restaurants, accommodations and attractions in the reference information. Do not invent any names, IDs, or prices.

""" + _TRAVEL_PLAN_OUTPUT_SCHEMA + """

{task_instance}"""


INDEPENDENT_WORKER_START_USER = """Objective: Solve the task completely on your own.
Focus: Independent worker {worker_index}.
Begin!"""


INDEPENDENT_AGGREGATOR_BASE_SYSTEM = """You are an aggregator that combines independent agents' plans.

You receive {num_workers} workers' independent plans. Synthesize them into one final plan that satisfies every constraint. Use ONLY items present in workers' outputs and the reference information. Do not invent any names, IDs, or prices.

""" + _TRAVEL_PLAN_OUTPUT_SCHEMA + """

{task_instance}"""


INDEPENDENT_AGGREGATOR_SYNTHESIS_USER = """Worker plans:
{worker_plans_block}

Synthesize the workers' plans into one final plan in the required output format. Resolve disagreements yourself; do not invent items absent from all workers' outputs."""


# ============================================================================
# Chain topology (paper-style framing; output schema only at the final agent)
# ============================================================================
# Chain executor (chain.py) calls agents sequentially: Agent-1 -> Agent-2 ->
# Agent-3, K=1 round, passing each agent's output to the next via the user
# message. The executor also appends a "Round X/K. You are agent i/N..."
# position info to the system prompt at call time. No {task_instance}
# placeholder is needed here — the user message already carries the full task.

CHAIN_AGENT_BASE_SYSTEM = """You are an intelligent travel-planning agent participating in a sequential pipeline.

Build on or refine the previous agent's output and pass your work to the next agent. Use ONLY the candidate flights, restaurants, accommodations and attractions in the reference information. Do not invent any names, IDs, or prices.

You do not need to produce the final formatted plan — that is the last agent's job. Focus on partial findings, candidate sets, constraint checks, or draft itineraries that the next agent can build on."""


CHAIN_FINAL_AGENT_SYSTEM = """You are the final agent in a sequential travel-planning pipeline.

Take the previous agent's draft and finalize it into the required output format. Use ONLY the candidate flights, restaurants, accommodations and attractions in the reference information. Do not invent any names, IDs, or prices.

""" + _TRAVEL_PLAN_OUTPUT_SCHEMA


# ============================================================================
# Decentralized topology (paper-style round structure + LLM final synthesis)
# ============================================================================
# Paper (Du et al. 2023 / ybkim95 agent-scaling) round mechanism is mirrored:
#   - 3 planners with DISTINCT strategies
#   - R1: independent candidate answer
#   - R2..d: each agent sees ONLY the previous round's peer answers
#     (not cumulative) and may defend / refine / replace
#   - No mid-debate consensus early-termination check
# Aggregation differs from paper: paper uses mechanical majority voting on
# identical-string match, which degenerates on TravelPlanner (plans are never
# identical strings). We keep an LLM-level synthesis call by the start agent
# (Planner-A) as the final aggregation.
#
# Each planner produces a complete plan, so the output schema lives in their
# system prompt. MeshExecutor passes the full task in the user message of each
# round, so {task_instance} placeholder is NOT used here.

DECENTRALIZED_PLANNER_BASE_SYSTEM = """You are an intelligent travel-planning agent participating in a multi-agent debate.

You work alongside 2 other planners. Each round you produce a complete trip plan; in later rounds you also see your peers' answers from the previous round and may defend / refine / replace your own answer. After the last debate round, a deterministic majority vote across the agents' final answers selects the system output.

Use ONLY the candidate flights, restaurants, accommodations and attractions in the reference information. Do not invent any names, IDs, or prices.

""" + _TRAVEL_PLAN_OUTPUT_SCHEMA + """

YOUR DEBATE STRATEGY:
{planner_strategy}"""


# Three distinct strategies cycled across N peer planners (paper sec. 6.1).
DECENTRALIZED_PLANNER_STRATEGIES = [
    "Analyze the problem systematically and produce a complete solution.",
    "Explore the problem broadly, identify the root cause, then solve it.",
    "Focus on the target outcome and work backwards to a solution.",
]


DECENTRALIZED_R1_USER = """Round 1: produce your best candidate answer to the task independently. Submit your final answer for this round when ready."""


DECENTRALIZED_R2PLUS_USER = """Debate round {round_num} of {max_rounds}.

Below are your peers' answers from the previous round. Read them carefully. Identify points where you agree, points where they erred, and points where you missed something. Then produce your updated final answer for this round. You may defend your previous answer, refine it, or replace it.

{peer_context}

Produce your updated final answer now."""


DECENTRALIZED_FINAL_SYNTHESIS_USER = """The debate has concluded after {n_rounds} round(s).

Below are all planners' final answers:

{all_final_answers_block}

Synthesize ONE final plan from these answers. Identify points of agreement to retain, resolve points of disagreement using the strongest arguments, and use ONLY items present in the planners' answers and the reference information. Return the final plan in the required output format."""
