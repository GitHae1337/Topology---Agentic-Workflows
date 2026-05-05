from typing import Dict, List, AsyncGenerator, Tuple, Optional
import asyncio
import logging
import re

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class CentralizedExecutor(BaseTopologyExecutor):
    """
    Centralized (Leader-Member / Orchestrator-SubAgent) topology executor.

    Behavior:
    1. Round 1: Orchestrator receives task and decomposes it into subtasks for each sub-agent
    2. Sub-agents execute their assigned subtasks in parallel
    3. Round 2+: Orchestrator reviews results and assigns new tasks OR decides to synthesize
    4. Sub-agents execute new tasks (with their previous output as context)
    5. Final: Orchestrator synthesizes all findings into final answer (sub-agents not called)
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting centralized execution with {len(agents)} agents")
        logger.info(f"Conversation history: {len(conversation_history) if conversation_history else 0} messages")
        if conversation_history:
            for i, msg in enumerate(conversation_history):
                logger.info(f"  History[{i}]: {msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}...")

        # Build history context for prompts
        history_context = self.build_history_context(conversation_history) if conversation_history else ""
        logger.info(f"History context length: {len(history_context)} chars")

        # Find leader (orchestrator) and member agents
        leader_agent = None
        member_agents = []
        for agent_id in topology.agents:
            agent = agents.get(agent_id)
            if not agent:
                continue
            if agent.topology_role == "Leader":
                leader_agent = agent
            elif agent.topology_role == "Member":
                member_agents.append(agent)

        if not leader_agent:
            logger.error("No leader agent found in centralized topology")
            yield self.create_message("system", "user", "Error: No leader agent found")
            return

        if not member_agents:
            logger.error("No member agents found in centralized topology")
            yield self.create_message("system", "user", "Error: No member agents found")
            return

        logger.info(f"Leader: {leader_agent.name}, Members: {[s.name for s in member_agents]}")

        # Use max_turns directly as max_rounds
        max_rounds = topology.max_turns
        current_round = 0

        # Track each agent's output history
        agent_histories: Dict[str, List[str]] = {agent.id: [] for agent in member_agents}

        # Track all round results for orchestrator context
        all_round_results: List[Dict[str, str]] = []

        # Build sub-agent info for orchestrator
        agent_names = [agent.name for agent in member_agents]
        agent_info = "\n".join([
            f"- {agent.name}: {agent.instructions[:100]}..." if agent.instructions else f"- {agent.name}"
            for agent in member_agents
        ])

        # ============================================================
        # Round 1: Orchestrator decomposes task
        # ============================================================
        current_round += 1
        logger.info(f"Starting round {current_round}: Task decomposition")

        decomposition_prompt = f"""You are the orchestrator coordinating a team of sub-agents.

{history_context}Available Sub-Agents:
{agent_info}

Current Task: {input_message}

Your job is to decompose this task into subtasks and assign each subtask to a specific sub-agent.
{f"Note: Consider the previous conversation context when decomposing the task." if history_context else ""}

IMPORTANT: You must respond in this exact format for each agent assignment:
[ASSIGN:{agent_names[0]}] <subtask for this agent>
[ASSIGN:{agent_names[1]}] <subtask for this agent>
...and so on for each agent.

Decompose the task now and assign subtasks to your sub-agents."""

        orchestrator_response = await self.call_agent(
            leader_agent,
            [LLMMessage(role="user", content=decomposition_prompt)],
        )

        yield self.create_message(
            leader_agent.name, "all", orchestrator_response,
            {"round": current_round, "type": "decomposition"}
        )

        # Parse subtask assignments
        subtasks = self._parse_assignments(orchestrator_response, member_agents)

        # If parsing failed, assign the original task to all agents
        if not subtasks:
            logger.warning("Could not parse assignments, using original task for all agents")
            subtasks = {agent.id: input_message for agent in member_agents}

        # Execute sub-agents in parallel
        round_results = await self._execute_agents_parallel(
            member_agents, subtasks, agent_histories, current_round, input_message
        )

        # Yield messages for each agent response
        for agent_id, response in round_results.items():
            agent = agents.get(agent_id)
            if agent:
                yield self.create_message(
                    agent.name, leader_agent.name, response,
                    {"round": current_round, "type": "subtask_result"}
                )

        all_round_results.append(round_results.copy())

        # ============================================================
        # Round 2+: Orchestrator reviews and assigns new tasks or synthesizes
        # ============================================================
        while current_round < max_rounds:
            current_round += 1
            logger.info(f"Starting round {current_round}: Review and reassign")

            # Build context from all previous rounds
            results_context = self._build_results_context(all_round_results, agents)

            review_prompt = f"""You are the orchestrator coordinating a team of sub-agents.

Original Task: {input_message}

Results from previous rounds:
{results_context}

Review these results carefully. You must decide ONE of the following:

OPTION 1 - SYNTHESIZE NOW (preferred if possible):
If the sub-agents have provided enough information to answer the original task, or if their findings are consistent and complete, respond ONLY with:
[FINAL SYNTHESIS]
<your comprehensive synthesis of all findings>

OPTION 2 - REQUEST MORE WORK (only if truly necessary):
If there are significant gaps, contradictions, or missing critical information that cannot be resolved without additional work, assign new tasks:
[ASSIGN:AgentName] <specific new task>

IMPORTANT: Prefer [FINAL SYNTHESIS] unless there is a clear, specific reason to continue. Do not request more work just to be thorough - synthesize when you have enough to answer the task.

What is your decision?"""

            orchestrator_response = await self.call_agent(
                leader_agent,
                [LLMMessage(role="user", content=review_prompt)],
            )

            yield self.create_message(
                leader_agent.name, "all", orchestrator_response,
                {"round": current_round, "type": "review"}
            )

            # Check if orchestrator wants to synthesize
            if "[FINAL SYNTHESIS]" in orchestrator_response.upper():
                logger.info(f"Orchestrator initiated final synthesis at round {current_round}")
                break

            # Parse new assignments
            subtasks = self._parse_assignments(orchestrator_response, member_agents)

            if not subtasks:
                # No assignments parsed, assume synthesis is needed
                logger.info(f"No new assignments, proceeding to synthesis at round {current_round}")
                break

            # Execute sub-agents in parallel with their new tasks
            round_results = await self._execute_agents_parallel(
                member_agents, subtasks, agent_histories, current_round, input_message
            )

            # Yield messages for each agent response
            for agent_id, response in round_results.items():
                agent = agents.get(agent_id)
                if agent:
                    yield self.create_message(
                        agent.name, leader_agent.name, response,
                        {"round": current_round, "type": "subtask_result"}
                    )

            all_round_results.append(round_results.copy())

            # Check for early termination
            if topology.early_termination:
                if self.check_early_termination(orchestrator_response):
                    logger.info(f"Early termination at round {current_round}")
                    break

        # ============================================================
        # Final Synthesis: Orchestrator synthesizes all findings
        # ============================================================
        # Only do explicit synthesis if we didn't already get [FINAL SYNTHESIS]
        if "[FINAL SYNTHESIS]" not in orchestrator_response.upper():
            logger.info("Orchestrator performing final synthesis")

            results_context = self._build_results_context(all_round_results, agents)

            synthesis_prompt = f"""You are the orchestrator. The task execution is complete.

Original Task: {input_message}

All Results from Sub-Agents:
{results_context}

Synthesize all findings into a final, comprehensive answer to the original task."""

            final_synthesis = await self.call_agent(
                leader_agent,
                [LLMMessage(role="user", content=synthesis_prompt)],
            )

            yield self.create_message(
                leader_agent.name, "output", final_synthesis,
                {"round": current_round, "type": "final_synthesis"}
            )

        logger.info(f"Centralized execution completed in {current_round} rounds")

    def _parse_assignments(
        self,
        orchestrator_response: str,
        member_agents: List[AgentConfig]
    ) -> Dict[str, str]:
        """Parse [ASSIGN:AgentName] subtask assignments from orchestrator response."""
        subtasks: Dict[str, str] = {}

        # Pattern: [ASSIGN:AgentName] followed by the task
        pattern = r'\[ASSIGN:([^\]]+)\]\s*(.+?)(?=\[ASSIGN:|$)'
        matches = re.findall(pattern, orchestrator_response, re.DOTALL | re.IGNORECASE)

        for agent_name, task in matches:
            agent_name = agent_name.strip()
            task = task.strip()

            # Find matching agent
            for agent in member_agents:
                if agent.name.lower() == agent_name.lower():
                    subtasks[agent.id] = task
                    break

        logger.info(f"Parsed {len(subtasks)} assignments from orchestrator")
        return subtasks

    async def _execute_agents_parallel(
        self,
        member_agents: List[AgentConfig],
        subtasks: Dict[str, str],
        agent_histories: Dict[str, List[str]],
        current_round: int,
        input_message: str,
    ) -> Dict[str, str]:
        """Execute all sub-agents in parallel with their assigned tasks."""

        async def execute_single_agent(agent: AgentConfig) -> Tuple[str, str]:
            subtask = subtasks.get(agent.id)
            if not subtask:
                return agent.id, ""

            # Build prompt with agent's previous output for context
            previous_outputs = agent_histories.get(agent.id, [])

            if previous_outputs:
                previous_context = "\n".join([
                    f"[Your Round {i+1} Output]: {output}"
                    for i, output in enumerate(previous_outputs)
                ])
                prompt = f"""You are a sub-agent following the orchestrator's instructions.

Original task: {input_message}

Your previous outputs:
{previous_context}

Subtask from orchestrator: {subtask}

Execute this subtask while keeping the original task's overall goal in mind. Provide your response."""
            else:
                prompt = f"""You are a sub-agent following the orchestrator's instructions.

Original task: {input_message}

Subtask from orchestrator: {subtask}

Execute this subtask while keeping the original task's overall goal in mind. Provide your response."""

            response = await self.call_agent(
                agent,
                [LLMMessage(role="user", content=prompt)],
            )

            # Store this response in agent's history
            agent_histories[agent.id].append(response)

            return agent.id, response

        # Only execute agents that have assigned tasks
        agents_with_tasks = [agent for agent in member_agents if agent.id in subtasks]

        if not agents_with_tasks:
            return {}

        # Execute all in parallel
        tasks = [execute_single_agent(agent) for agent in agents_with_tasks]
        results = await asyncio.gather(*tasks)

        return {agent_id: response for agent_id, response in results if response}

    def _build_results_context(
        self,
        all_round_results: List[Dict[str, str]],
        agents: Dict[str, AgentConfig]
    ) -> str:
        """Build a formatted string of all round results for orchestrator context."""
        context_parts = []

        for round_num, round_results in enumerate(all_round_results, start=1):
            round_text = f"=== Round {round_num} Results ==="
            for agent_id, response in round_results.items():
                agent = agents.get(agent_id)
                if agent:
                    round_text += f"\n[{agent.name}]: {response}"
            context_parts.append(round_text)

        return "\n\n".join(context_parts)
