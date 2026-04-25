from typing import Dict, List, Set, AsyncGenerator, Tuple
import asyncio
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class P2PExecutor(BaseTopologyExecutor):
    """
    Peer-to-Peer (P2P) topology executor with ring/graph structure.

    Behavior:
    1. Round 1: All agents receive the same task and produce initial responses in parallel
    2. Round 2+: Each agent sees ONLY their adjacent agents' responses (based on internal edges)
    3. Information propagates through the network over synchronized rounds
    4. Final: Majority voting / synthesis of all final outputs
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting P2P execution with {len(agents)} agents")

        if not topology.start_agent_id:
            logger.error("No start agent specified for P2P topology")
            yield self.create_message("system", "user", "Error: Start agent not specified")
            return

        agent_list = [agents.get(aid) for aid in topology.agents if agents.get(aid)]
        if len(agent_list) < 2:
            logger.error("P2P topology requires at least 2 agents")
            yield self.create_message("system", "user", "Error: Need at least 2 agents")
            return

        # Build bidirectional adjacency list from internal edges
        adjacency: Dict[str, Set[str]] = {agent_id: set() for agent_id in topology.agents}
        for edge in topology.internal_edges:
            if edge.from_agent in adjacency:
                adjacency[edge.from_agent].add(edge.to_agent)
            # For bidirectional edges, add reverse
            if edge.edge_type == "bidirectional" and edge.to_agent in adjacency:
                adjacency[edge.to_agent].add(edge.from_agent)

        # Log adjacency for debugging
        for agent_id, neighbors in adjacency.items():
            agent = agents.get(agent_id)
            neighbor_names = [agents.get(n).name for n in neighbors if agents.get(n)]
            if agent:
                logger.info(f"Agent {agent.name} is adjacent to: {neighbor_names}")

        # Use max_turns directly as max_rounds
        max_rounds = topology.max_turns
        current_round = 0

        # Track each agent's responses per round
        round_responses: Dict[str, str] = {}
        all_rounds_history: List[Dict[str, str]] = []

        # ============================================================
        # Round 1: All agents receive the same task (independent reasoning)
        # ============================================================
        current_round += 1
        logger.info(f"Starting round {current_round}: Independent reasoning")

        async def get_initial_response(agent: AgentConfig) -> Tuple[str, str]:
            """Get initial response from an agent."""
            # Get adjacent agent names for context
            neighbor_ids = adjacency.get(agent.id, set())
            neighbor_names = [agents.get(n).name for n in neighbor_ids if agents.get(n)]

            prompt = f"""You are {agent.name} in a peer-to-peer network with a ring/graph structure.
You can communicate with your adjacent agents: {', '.join(neighbor_names) if neighbor_names else 'None'}.

Task: {input_message}

This is Round 1 (Independent Reasoning). Analyze the task and provide your initial response.
In the next rounds, you will see your adjacent agents' responses and can refine your answer."""

            response = await self.call_agent(agent, [LLMMessage(role="user", content=prompt)])
            return agent.id, response

        # Execute all agents in parallel
        initial_tasks = [get_initial_response(agent) for agent in agent_list]
        initial_results = await asyncio.gather(*initial_tasks)

        # Store round 1 responses
        for agent_id, response in initial_results:
            round_responses[agent_id] = response
            agent = agents.get(agent_id)
            yield self.create_message(
                agent.name, "network", response,
                {"round": current_round, "type": "initial"}
            )

        all_rounds_history.append(round_responses.copy())

        # ============================================================
        # Round 2+: Each agent sees only adjacent agents' responses
        # ============================================================
        while current_round < max_rounds:
            current_round += 1
            logger.info(f"Starting round {current_round}: Adjacent reference and refinement")

            async def get_refined_response(agent: AgentConfig) -> Tuple[str, str]:
                """Get refined response from an agent based on adjacent agents' responses."""
                # Get this agent's previous response
                my_previous = round_responses.get(agent.id, "")

                # Get adjacent agents' responses
                neighbor_ids = adjacency.get(agent.id, set())
                neighbor_responses = []
                for neighbor_id in neighbor_ids:
                    neighbor = agents.get(neighbor_id)
                    neighbor_response = round_responses.get(neighbor_id, "")
                    if neighbor and neighbor_response:
                        neighbor_responses.append(f"[{neighbor.name}'s Response]: {neighbor_response}")

                neighbor_names = [agents.get(n).name for n in neighbor_ids if agents.get(n)]
                adjacent_context = "\n\n".join(neighbor_responses) if neighbor_responses else "No responses yet."

                prompt = f"""You are {agent.name} in a peer-to-peer network.
Your adjacent agents are: {', '.join(neighbor_names) if neighbor_names else 'None'}.

Task: {input_message}

This is Round {current_round}. Review your adjacent agents' responses and refine your answer.

Your Previous Response:
{my_previous}

Adjacent Agents' Responses:
{adjacent_context}

Based on your adjacent agents' information:
1. Integrate relevant new information from your neighbors
2. Refine and improve your response
3. Note any confirmations or contradictions

Provide your updated response."""

                response = await self.call_agent(agent, [LLMMessage(role="user", content=prompt)])
                return agent.id, response

            # Execute all agents in parallel
            refined_tasks = [get_refined_response(agent) for agent in agent_list]
            refined_results = await asyncio.gather(*refined_tasks)

            # Store this round's responses
            new_responses: Dict[str, str] = {}
            for agent_id, response in refined_results:
                new_responses[agent_id] = response
                agent = agents.get(agent_id)
                yield self.create_message(
                    agent.name, "network", response,
                    {"round": current_round, "type": "refined"}
                )

            # Update for next round
            all_rounds_history.append(new_responses.copy())
            round_responses = new_responses

            # Check for early termination (if all agents seem to converge)
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

            synthesis_prompt = f"""The peer-to-peer discussion has concluded after {current_round} rounds.

Original Task: {input_message}

All agents' final responses:

{final_outputs_text}

Your task:
1. Identify the majority answer or common consensus among all agents
2. If there's clear agreement, state the agreed answer
3. If there are differences, synthesize the best answer based on the information that propagated through the network

Provide the final answer that best represents the collective conclusion."""

            synthesis = await self.call_agent(
                start_agent,
                [LLMMessage(role="user", content=synthesis_prompt)],
            )

            yield self.create_message(
                start_agent.name, "output", synthesis,
                {"round": current_round, "type": "majority_voting"}
            )

        logger.info(f"P2P execution completed in {current_round} rounds")
