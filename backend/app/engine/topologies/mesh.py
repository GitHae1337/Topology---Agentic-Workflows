"""Paper-style MeshExecutor (decentralized topology).

Round mechanism mirrors Du et al. 2023 / ybkim95 agent-scaling:
  R1     — each planner produces an independent candidate answer (parallel)
  R2..d  — each planner sees ONLY the previous round's peer answers
           (not cumulative) and may defend / refine / replace its answer
  No mid-debate consensus early-termination check.

Final aggregation differs from the paper: paper uses mechanical majority
voting on identical-string match, which degenerates on TravelPlanner since
plans are essentially never identical strings. We use an LLM-level synthesis
call by the start agent (Planner-A) to combine the final-round answers into
a single plan. The system-prompt level "deterministic vote selects output"
phrasing remains for the planners — only the executor diverges here.

Per trial calls: N × max_rounds debate + 1 synthesis. With N=3, max_rounds=3
that's 10 calls.
"""
from typing import Dict, List, AsyncGenerator, Tuple
import asyncio
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage
from ...thinking_style.prompts_paper_style import (
    DECENTRALIZED_R1_USER,
    DECENTRALIZED_R2PLUS_USER,
    DECENTRALIZED_FINAL_SYNTHESIS_USER,
)

logger = logging.getLogger(__name__)


class MeshExecutor(BaseTopologyExecutor):
    """Paper-style decentralized debate with LLM-level final synthesis."""

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting mesh (paper-style) execution with {len(agents)} agents")

        agent_list: List[AgentConfig] = [agents[aid] for aid in topology.agents if aid in agents]
        if len(agent_list) < 2:
            yield self.create_message("system", "user", "Error: Mesh needs at least 2 agents")
            return
        if not topology.start_agent_id or topology.start_agent_id not in agents:
            yield self.create_message("system", "user", "Error: Mesh needs a valid start_agent_id")
            return

        max_rounds = topology.max_turns
        # round_responses[round_num] = {agent_id: response_string}
        round_responses: List[Dict[str, str]] = []

        # ===================== Round 1: independent candidates =====================
        logger.info(f"Round 1 / {max_rounds}: independent candidates")
        r1_user = DECENTRALIZED_R1_USER

        async def r1_one(agent: AgentConfig) -> Tuple[str, str]:
            # The full task (reference + styled query) is in input_message; we wrap
            # it the same way chain/sas do: as the user's "Original task:" prefix.
            user_msg = self.format_user_prompt_with_task(input_message, r1_user)
            resp = await self.call_agent(agent, [LLMMessage(role="user", content=user_msg)])
            return agent.id, resp

        r1_results = await asyncio.gather(*[r1_one(a) for a in agent_list])
        r1_responses: Dict[str, str] = dict(r1_results)
        round_responses.append(r1_responses)
        for aid, resp in r1_responses.items():
            yield self.create_message(
                agents[aid].name, "all", resp,
                {"round": 1, "type": "initial"},
            )

        # ===================== Round 2..d: peer-aware refine ======================
        for r in range(2, max_rounds + 1):
            logger.info(f"Round {r} / {max_rounds}: peer-aware refine")
            prev_round = round_responses[-1]

            async def rN_one(agent: AgentConfig) -> Tuple[str, str]:
                # Previous-round-only peer context (paper sec. 6.1).
                peer_blocks = []
                for other in agent_list:
                    if other.id == agent.id:
                        continue
                    ans = prev_round.get(other.id, "")
                    if not ans:
                        continue
                    peer_blocks.append(
                        f"--- Peer answer from {other.name} (round {r - 1}) ---\n{ans}"
                    )
                peer_context = "\n\n".join(peer_blocks) if peer_blocks else "(no peer responses available)"
                round_msg = DECENTRALIZED_R2PLUS_USER.format(
                    round_num=r, max_rounds=max_rounds, peer_context=peer_context,
                )
                user_msg = self.format_user_prompt_with_task(input_message, round_msg)
                resp = await self.call_agent(agent, [LLMMessage(role="user", content=user_msg)])
                return agent.id, resp

            rN_results = await asyncio.gather(*[rN_one(a) for a in agent_list])
            this_round: Dict[str, str] = dict(rN_results)
            round_responses.append(this_round)
            for aid, resp in this_round.items():
                yield self.create_message(
                    agents[aid].name, "all", resp,
                    {"round": r, "type": "debate"},
                )

        # ===================== Final aggregation: LLM synthesis ===================
        start_agent = agents[topology.start_agent_id]
        final_round = round_responses[-1]
        # Build the final-answers block in canonical agent-list order.
        all_final_block = "\n\n".join(
            f"=== {a.name} (final, round {len(round_responses)}) ===\n{final_round.get(a.id, '(no final answer)')}"
            for a in agent_list
        )
        synthesis_user = DECENTRALIZED_FINAL_SYNTHESIS_USER.format(
            n_rounds=len(round_responses),
            all_final_answers_block=all_final_block,
        )
        synthesis_input = self.format_user_prompt_with_task(input_message, synthesis_user)
        final = await self.call_agent(
            start_agent, [LLMMessage(role="user", content=synthesis_input)]
        )
        yield self.create_message(
            start_agent.name, "output", final,
            {"round": max_rounds, "type": "final_synthesis"},
        )
        logger.info(f"Mesh (paper-style) execution complete: {max_rounds} debate rounds + 1 synthesis")
