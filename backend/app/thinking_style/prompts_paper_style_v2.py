"""Variant v2 of paper-style prompts.

Overrides 4 constants from v1 (prompts_paper_style) to maximize the leverage
of the user-side styled query on centralized / hybrid / decentralized
topologies. All other constants are re-exported from v1 unchanged.

Activate via env var:
    PROMPT_VARIANT=v2 python -m backend.scripts.run_thinking_style_matrix ...

Rationale (see paper-style notes):
  - Centralized: R1 planning already faithful to user structure, but R2 coord
    and R3 synthesis drift in v1. v2 adds a one-line reminder at the end of
    both to maintain the user's decomposition.
  - Hybrid: in v1 the Manager autonomously decides ACTION 1 (per-agent guidance)
    vs ACTION 2 (PEER lateral exchange). v2 ties that decision explicitly to
    keywords in the user's request so PEER fires when the user asks for
    cross-coordination and is suppressed when the user asks for independent /
    sequential work.
  - Decentralized: in v1 each planner has a fixed strategy
    (systematic / broad / backward) baked in, overriding any angles the user
    enumerates. v2 replaces the fixed strategies with "take the i-th
    perspective the user mentions" so the planners' debate angles inherit
    from the user's stated angles.
"""
from .prompts_paper_style import *  # noqa: F401, F403
from .prompts_paper_style import (
    ORCHESTRATOR_COORDINATION_USER as _V1_COORD,
    ORCHESTRATOR_SYNTHESIS_USER as _V1_SYNTH,
)


# ---------------------------------------------------------------------------
# Centralized — reinforce user decomposition fidelity at R2 + R3
# ---------------------------------------------------------------------------

ORCHESTRATOR_COORDINATION_USER = _V1_COORD.rstrip() + """

Maintain alignment with the user's stated organization — each agent's role should remain consistent with the part of the user's request it was originally assigned to."""


ORCHESTRATOR_SYNTHESIS_USER = _V1_SYNTH.rstrip() + """

Preserve the user's intended decomposition pattern in the final plan — the structure of the final plan should reflect how the user organized the task."""


# ---------------------------------------------------------------------------
# Hybrid — tie ACTION 1 / ACTION 2 (PEER) decision to user query keywords
# ---------------------------------------------------------------------------

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
You have TWO actions available for this turn — pick whichever fits the user's stated organization:

  ACTION 1 — Give {agent_id} specific guidance for their next step (1-3 sentences).

  ACTION 2 — Trigger a lateral peer exchange so {agent_id} can reconcile directly with another worker BEFORE refining. End your message with a single line on its own:
      [PEER:Worker-i,Worker-j] <focus of the exchange>

Tie ACTION 1 vs ACTION 2 to the user's request:
- If the user's request emphasizes lateral coordination (e.g., 'coordinate directly', 'cross-dependent constraints', 'reconcile', 'cross-check') — strongly prefer ACTION 2 [PEER].
- If the user's request emphasizes independent or sequential work (e.g., 'fully independent', 'pipeline', 'sequentially', 'no parallel work') — prefer ACTION 1 and avoid PEER.
- If neither is clearly indicated, default to ACTION 1.

Choose ONE action. No JSON, just the message — with the [PEER:...] trailer at the end if you choose ACTION 2."""


# ---------------------------------------------------------------------------
# Decentralized — derive planner perspectives from user's stated angles
# ---------------------------------------------------------------------------

DECENTRALIZED_PLANNER_STRATEGIES = [
    "Take the first perspective the user mentions in their request. If no specific angle is stated, prioritize a cost / efficiency lens.",
    "Take the second perspective the user mentions in their request. If no second angle is stated, prioritize a feasibility / schedule lens.",
    "Take the third perspective the user mentions in their request. If no third angle is stated, prioritize a rule-safety / constraint-satisfaction lens.",
]
