from typing import Dict, List, AsyncGenerator, Tuple
import asyncio
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class MeshExecutor(BaseTopologyExecutor):
    """
    Mesh (Fully Connected) topology executor.

    Behavior:
    1. Round 1: All agents receive the task simultaneously (parallel) and produce initial responses
    2. Round 2+: All agents see ALL previous responses (including their own) with cumulative history
    3. Repeat until consensus, early termination, or max rounds reached
    4. Final: Majority voting/synthesis across all agents' final outputs
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting mesh (debate) execution with {len(agents)} agents")

        if not topology.start_agent_id:
            logger.error("No start agent specified for mesh topology")
            yield self.create_message("system", "user", "Error: Start agent not specified")
            return

        agent_list = [agents.get(aid) for aid in topology.agents if agents.get(aid)]
        if len(agent_list) < 2:
            logger.error("Mesh topology requires at least 2 agents")
            yield self.create_message("system", "user", "Error: Need at least 2 agents")
            return

        logger.info(f"Agents: {[a.name for a in agent_list]}")

        # Use max_turns directly as max_rounds for Mesh topology
        max_rounds = topology.max_turns
        current_round = 0

        # Cumulative history: list of round responses
        all_rounds_history: List[Dict[str, str]] = []

        # ============================================================
        # Round 1: All agents receive the same task in parallel
        # ============================================================
        current_round += 1
        logger.info(f"Starting debate round {current_round}")

        async def get_initial_response(agent: AgentConfig) -> Tuple[str, str]:
            """Get initial response from an agent."""
            prompt = f"""You are participating in a multi-agent debate/discussion.

Topic/Task: {input_message}

This is Round 1. Provide your initial perspective, analysis, or solution. Be thorough but concise."""

            response = await self.call_agent(agent, [LLMMessage(role="user", content=prompt)])
            return agent.id, response

        # Execute all agents in parallel
        initial_tasks = [get_initial_response(agent) for agent in agent_list]
        initial_results = await asyncio.gather(*initial_tasks)

        # Store round 1 responses
        round_responses: Dict[str, str] = {}
        for agent_id, response in initial_results:
            round_responses[agent_id] = response
            agent = agents.get(agent_id)
            yield self.create_message(agent.name, "all", response, {"round": current_round, "type": "initial"})

        all_rounds_history.append(round_responses.copy())

        # ============================================================
        # Round 2+: Debate rounds with full visibility and cumulative history
        # ============================================================
        while current_round < max_rounds:
            current_round += 1
            logger.info(f"Starting debate round {current_round}")

            # Build cumulative history text from ALL previous rounds
            history_text = self._build_cumulative_history(all_rounds_history, agents)

            async def get_debate_response(agent: AgentConfig) -> Tuple[str, str]:
                """Get debate response from an agent with full history visibility."""
                prompt = f"""You are participating in a multi-agent debate/discussion.

Topic/Task: {input_message}

This is Round {current_round}. Here is the complete history of all previous rounds:

{history_text}

Based on all perspectives shared so far:
1. Consider points you agree or disagree with
2. Refine your position if needed
3. Provide your updated response

If you believe consensus has been reached, start your response with "CONSENSUS REACHED:" followed by the agreed conclusion."""

                response = await self.call_agent(agent, [LLMMessage(role="user", content=prompt)])
                return agent.id, response

            # Execute all agents in parallel
            debate_tasks = [get_debate_response(agent) for agent in agent_list]
            debate_results = await asyncio.gather(*debate_tasks)

            # Store this round's responses
            new_responses: Dict[str, str] = {}
            for agent_id, response in debate_results:
                new_responses[agent_id] = response
                agent = agents.get(agent_id)
                yield self.create_message(agent.name, "all", response, {"round": current_round, "type": "debate"})

            # Accumulate history
            all_rounds_history.append(new_responses.copy())
            round_responses = new_responses

            # Check for consensus (majority of agents indicate consensus)
            consensus_count = sum(1 for r in round_responses.values() if "CONSENSUS REACHED" in r.upper())
            if consensus_count >= len(agent_list) // 2 + 1:
                logger.info(f"Consensus reached at round {current_round}")
                break

            # Check for early termination
            if topology.early_termination:
                if all(self.check_early_termination(r) for r in round_responses.values()):
                    logger.info(f"Early termination at round {current_round}")
                    break

        # ============================================================
        # Final: Majority voting / synthesis
        # ============================================================
        start_agent = agents.get(topology.start_agent_id)
        if start_agent:
            # Format all final outputs for majority voting
            final_outputs_text = "\n\n".join([
                f"[{agents.get(aid).name}]: {resp}"
                for aid, resp in round_responses.items()
                if agents.get(aid)
            ])

            synthesis_prompt = f"""The debate has concluded after {current_round} rounds.

Original Task: {input_message}

Here are all agents' final positions:

{final_outputs_text}

Your task:
1. Identify the majority answer or common consensus among the agents
2. If there's clear agreement, state the agreed answer
3. If there are differences, synthesize the best answer based on the strongest arguments

Provide the final answer that best represents the collective conclusion."""

            synthesis = await self.call_agent(
                start_agent,
                [LLMMessage(role="user", content=synthesis_prompt)],
            )

            yield self.create_message(
                start_agent.name,
                "output",
                synthesis,
                {"round": current_round, "type": "majority_voting"}
            )

        logger.info(f"Mesh execution completed in {current_round} rounds")

    def _build_cumulative_history(
        self,
        all_rounds_history: List[Dict[str, str]],
        agents: Dict[str, AgentConfig]
    ) -> str:
        """Build a formatted string of cumulative history from all rounds."""
        history_parts = []

        for round_num, round_responses in enumerate(all_rounds_history, start=1):
            round_text = f"=== Round {round_num} ==="
            for agent_id, response in round_responses.items():
                agent = agents.get(agent_id)
                if agent:
                    round_text += f"\n[{agent.name}]: {response}"
            history_parts.append(round_text)

        return "\n\n".join(history_parts)
