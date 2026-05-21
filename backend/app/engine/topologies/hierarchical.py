from typing import Dict, List, AsyncGenerator, Tuple, Optional
import asyncio
import logging
import re

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class HierarchicalExecutor(BaseTopologyExecutor):
    """
    Hierarchical (Tree) topology executor with peer communication support.

    Behavior:
    1. Round 1: Manager receives task and decomposes it into subtasks for each worker
    2. Workers execute their assigned subtasks in parallel
    3. Round 2+: Manager reviews results and can:
       - Assign new tasks to workers using [ASSIGN:WorkerName]
       - Instruct peer discussions using [PEER:WorkerA,WorkerB] instruction
       - Decide to synthesize with [FINAL SYNTHESIS]
    4. Peer rounds: Specified worker pairs discuss with full context (parallel)
    5. Final: Manager synthesizes all findings including peer discussion results
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting hierarchical execution with {len(agents)} agents")

        # Find manager and worker agents
        manager_agent = None
        worker_agents = []
        for agent_id in topology.agents:
            agent = agents.get(agent_id)
            if not agent:
                continue
            if agent.topology_role == "Manager":
                manager_agent = agent
            elif agent.topology_role == "Worker":
                worker_agents.append(agent)

        if not manager_agent:
            logger.error("No manager agent found in hierarchical topology")
            yield self.create_message("system", "user", "Error: No manager agent found")
            return

        if not worker_agents:
            logger.error("No worker agents found in hierarchical topology")
            yield self.create_message("system", "user", "Error: No worker agents found")
            return

        logger.info(f"Manager: {manager_agent.name}, Workers: {[w.name for w in worker_agents]}")

        # Use max_turns directly as max_rounds
        max_rounds = topology.max_turns
        current_round = 0

        # Track each agent's task and output history
        agent_tasks: Dict[str, str] = {}  # agent_id -> latest assigned task
        agent_outputs: Dict[str, List[str]] = {agent.id: [] for agent in worker_agents}

        # Track all results for manager context
        all_round_results: List[Dict[str, str]] = []
        all_peer_results: List[Dict[str, str]] = []

        # Build worker info for manager
        worker_names = [agent.name for agent in worker_agents]
        worker_info = "\n".join([
            f"- {agent.name}: {agent.instructions[:100]}..." if agent.instructions else f"- {agent.name}"
            for agent in worker_agents
        ])

        # ============================================================
        # Round 1: Manager decomposes task
        # ============================================================
        current_round += 1
        logger.info(f"Starting round {current_round}: Task decomposition")

        decomposition_prompt = f"""You are the manager coordinating a team of worker agents.

Available Workers:
{worker_info}

Task: {input_message}

Your job is to decompose this task into subtasks and assign each subtask to a specific worker.

IMPORTANT: You must respond in this exact format, with one [ASSIGN:...] line per worker listed above (do not skip any):
{chr(10).join(f"[ASSIGN:{name}] <subtask for this worker>" for name in worker_names)}

Decompose the task now and assign subtasks to your workers."""

        manager_response = await self.call_agent(
            manager_agent,
            [LLMMessage(role="user", content=decomposition_prompt)],
        )

        yield self.create_message(
            manager_agent.name, "all", manager_response,
            {"round": current_round, "type": "decomposition"}
        )

        # Parse subtask assignments
        subtasks = self._parse_assignments(manager_response, worker_agents)

        # If parsing failed, assign the original task to all agents
        if not subtasks:
            logger.warning("Could not parse assignments, using original task for all workers")
            subtasks = {agent.id: input_message for agent in worker_agents}

        # Store assigned tasks
        for agent_id, task in subtasks.items():
            agent_tasks[agent_id] = task

        # Execute workers in parallel
        round_results = await self._execute_workers_parallel(
            worker_agents, subtasks, agent_outputs, current_round, input_message
        )

        # Yield messages for each worker response
        for agent_id, response in round_results.items():
            agent = agents.get(agent_id)
            if agent:
                yield self.create_message(
                    agent.name, manager_agent.name, response,
                    {"round": current_round, "type": "subtask_result"}
                )

        all_round_results.append(round_results.copy())

        # ============================================================
        # Round 2+: Manager reviews and coordinates (with peer communication)
        # ============================================================
        while current_round < max_rounds:
            current_round += 1
            logger.info(f"Starting round {current_round}: Review and coordinate")

            # Build context from all previous rounds
            results_context = self._build_results_context(all_round_results, agents)
            peer_context = self._build_peer_context(all_peer_results) if all_peer_results else ""

            # Build a human-readable list of available worker names so the
            # prompt examples use the exact strings the parser matches on.
            worker_list_str = ", ".join(worker_names)
            example_pair = (
                f"{worker_names[0]},{worker_names[1]}"
                if len(worker_names) >= 2 else worker_names[0]
            )

            review_prompt = f"""당신은 worker agent들을 조율하는 매니저입니다.

원래 task: {input_message}

이전 라운드 결과:
{results_context}
{f'''
이전 peer 토론 결과:
{peer_context}
''' if peer_context else ''}

위 결과를 검토하고 다음 행동을 결정하세요. 명령은 반드시 아래 형식 그대로
출력하세요. 자연어로 풀어서 말하면 시스템이 인식하지 못합니다.

1. 특정 worker에게 새 task를 할당:
   [ASSIGN:WorkerName] <새 task>
   예: [ASSIGN:{worker_names[0]}] 숙소 가격을 다시 검토해주세요

2. 두 worker가 직접 토론하도록 지시 (서로의 결과를 교차 검증):
   [PEER:WorkerA,WorkerB] <토론 지시>
   예: [PEER:{example_pair}] 두 분 결과에서 일정 충돌이 있는지 교차 검증해주세요

3. 충분한 정보가 모였으면 최종 답변을 합치기:
   [FINAL SYNTHESIS]
   <최종 답변>

사용 가능한 worker 이름 (이 이름을 그대로 사용하세요):
{worker_list_str}

소통/조율이 필요한 worker pair가 있으면 [PEER:...] 명령을 적극 활용하세요.
한 응답에 여러 명령을 동시에 사용해도 됩니다.

당신의 결정은?"""

            manager_response = await self.call_agent(
                manager_agent,
                [LLMMessage(role="user", content=review_prompt)],
            )

            yield self.create_message(
                manager_agent.name, "all", manager_response,
                {"round": current_round, "type": "review"}
            )

            # Check if manager wants to synthesize
            if "[FINAL SYNTHESIS]" in manager_response.upper():
                logger.info(f"Manager initiated final synthesis at round {current_round}")
                break

            # Parse peer discussion instructions
            peer_instructions = self._parse_peer_instructions(manager_response, worker_agents)

            if peer_instructions:
                # Execute peer discussions
                for (agent_a, agent_b), instruction in peer_instructions:
                    logger.info(f"Executing peer discussion: {agent_a.name} ↔ {agent_b.name}")

                    peer_results = await self._execute_peer_discussion(
                        agent_a, agent_b, instruction,
                        agent_tasks, agent_outputs, current_round, input_message
                    )

                    # Yield peer discussion messages
                    for agent_id, response in peer_results.items():
                        agent = agents.get(agent_id)
                        peer_agent = agent_b if agent_id == agent_a.id else agent_a
                        if agent:
                            yield self.create_message(
                                agent.name, peer_agent.name, response,
                                {"round": current_round, "type": "peer_discussion"}
                            )

                    all_peer_results.append({
                        "pair": f"{agent_a.name} ↔ {agent_b.name}",
                        "instruction": instruction,
                        "results": {agents.get(aid).name: resp for aid, resp in peer_results.items() if agents.get(aid)}
                    })

            # Parse new task assignments
            subtasks = self._parse_assignments(manager_response, worker_agents)

            if subtasks:
                # Update assigned tasks
                for agent_id, task in subtasks.items():
                    agent_tasks[agent_id] = task

                # Execute workers in parallel
                round_results = await self._execute_workers_parallel(
                    worker_agents, subtasks, agent_outputs, current_round, input_message
                )

                # Yield messages for each worker response
                for agent_id, response in round_results.items():
                    agent = agents.get(agent_id)
                    if agent:
                        yield self.create_message(
                            agent.name, manager_agent.name, response,
                            {"round": current_round, "type": "subtask_result"}
                        )

                all_round_results.append(round_results.copy())

            # If no peer instructions and no assignments, assume synthesis is needed
            if not peer_instructions and not subtasks:
                logger.info(f"No new instructions, proceeding to synthesis at round {current_round}")
                break

            # Check for early termination
            if topology.early_termination:
                if self.check_early_termination(manager_response):
                    logger.info(f"Early termination at round {current_round}")
                    break

        # ============================================================
        # Final Synthesis: Manager synthesizes all findings
        # ============================================================
        if "[FINAL SYNTHESIS]" not in manager_response.upper():
            logger.info("Manager performing final synthesis")

            results_context = self._build_results_context(all_round_results, agents)
            peer_context = self._build_peer_context(all_peer_results) if all_peer_results else ""

            synthesis_prompt = f"""You are the manager. The task execution is complete.

Original Task: {input_message}

All Results from Workers:
{results_context}
{f'''
Peer Discussion Results:
{peer_context}
''' if peer_context else ''}

Synthesize all findings into a final, comprehensive answer to the original task."""

            final_synthesis = await self.call_agent(
                manager_agent,
                [LLMMessage(role="user", content=synthesis_prompt)],
            )

            yield self.create_message(
                manager_agent.name, "output", final_synthesis,
                {"round": current_round, "type": "final_synthesis"}
            )

        logger.info(f"Hierarchical execution completed in {current_round} rounds")

    def _parse_assignments(
        self,
        manager_response: str,
        worker_agents: List[AgentConfig]
    ) -> Dict[str, str]:
        """Parse [ASSIGN:WorkerName] subtask assignments from manager response."""
        subtasks: Dict[str, str] = {}

        pattern = r'\[ASSIGN:([^\]]+)\]\s*(.+?)(?=\[ASSIGN:|\[PEER:|\[FINAL|\Z)'
        matches = re.findall(pattern, manager_response, re.DOTALL | re.IGNORECASE)

        for worker_name, task in matches:
            worker_name = worker_name.strip()
            task = task.strip()

            for agent in worker_agents:
                if agent.name.lower() == worker_name.lower():
                    subtasks[agent.id] = task
                    break

        logger.info(f"Parsed {len(subtasks)} assignments from manager")
        return subtasks

    def _parse_peer_instructions(
        self,
        manager_response: str,
        worker_agents: List[AgentConfig]
    ) -> List[Tuple[Tuple[AgentConfig, AgentConfig], str]]:
        """Parse [PEER:WorkerA,WorkerB] instructions from manager response."""
        peer_instructions = []

        pattern = r'\[PEER:([^\]]+)\]\s*(.+?)(?=\[ASSIGN:|\[PEER:|\[FINAL|\Z)'
        matches = re.findall(pattern, manager_response, re.DOTALL | re.IGNORECASE)

        for agents_str, instruction in matches:
            agent_names = [name.strip() for name in agents_str.split(',')]
            if len(agent_names) != 2:
                continue

            instruction = instruction.strip()

            # Find matching agents
            agent_a = None
            agent_b = None
            for agent in worker_agents:
                if agent.name.lower() == agent_names[0].lower():
                    agent_a = agent
                elif agent.name.lower() == agent_names[1].lower():
                    agent_b = agent

            if agent_a and agent_b:
                peer_instructions.append(((agent_a, agent_b), instruction))

        logger.info(f"Parsed {len(peer_instructions)} peer instructions from manager")
        return peer_instructions

    async def _execute_workers_parallel(
        self,
        worker_agents: List[AgentConfig],
        subtasks: Dict[str, str],
        agent_outputs: Dict[str, List[str]],
        current_round: int,
        input_message: str,
    ) -> Dict[str, str]:
        """Execute all workers in parallel with their assigned tasks."""

        async def execute_single_worker(agent: AgentConfig) -> Tuple[str, str]:
            subtask = subtasks.get(agent.id)
            if not subtask:
                return agent.id, ""

            previous_outputs = agent_outputs.get(agent.id, [])
            reference_only = self.extract_reference(input_message)

            if previous_outputs:
                previous_context = "\n".join([
                    f"[Your Round {i+1} Output]: {output}"
                    for i, output in enumerate(previous_outputs)
                ])
                prompt = f"""You are a worker following the manager's instructions.

{reference_only}

Your previous outputs:
{previous_context}

Subtask from manager: {subtask}

Execute this subtask. Provide your response."""
            else:
                prompt = f"""You are a worker following the manager's instructions.

{reference_only}

Subtask from manager: {subtask}

Execute this subtask. Provide your response."""

            response = await self.call_agent(
                agent,
                [LLMMessage(role="user", content=prompt)],
            )

            agent_outputs[agent.id].append(response)
            return agent.id, response

        agents_with_tasks = [agent for agent in worker_agents if agent.id in subtasks]

        if not agents_with_tasks:
            return {}

        tasks = [execute_single_worker(agent) for agent in agents_with_tasks]
        results = await asyncio.gather(*tasks)

        return {agent_id: response for agent_id, response in results if response}

    async def _execute_peer_discussion(
        self,
        agent_a: AgentConfig,
        agent_b: AgentConfig,
        instruction: str,
        agent_tasks: Dict[str, str],
        agent_outputs: Dict[str, List[str]],
        current_round: int,
        input_message: str,
    ) -> Dict[str, str]:
        """Execute peer discussion between two agents in parallel."""

        async def get_peer_response(
            agent: AgentConfig,
            peer: AgentConfig
        ) -> Tuple[str, str]:
            agent_task = agent_tasks.get(agent.id, "No specific task")
            agent_output = agent_outputs.get(agent.id, ["No output yet"])[-1] if agent_outputs.get(agent.id) else "No output yet"
            peer_task = agent_tasks.get(peer.id, "No specific task")
            peer_output = agent_outputs.get(peer.id, ["No output yet"])[-1] if agent_outputs.get(peer.id) else "No output yet"

            reference_only = self.extract_reference(input_message)
            prompt = f"""You are a worker participating in a peer discussion with {peer.name}.

{reference_only}

Your Subtask: {agent_task}
Your Output: {agent_output}

{peer.name}'s Subtask: {peer_task}
{peer.name}'s Output: {peer_output}

Manager's Instruction for this discussion: {instruction}

Discuss with your peer and provide your insights based on the manager's instruction."""

            response = await self.call_agent(
                agent,
                [LLMMessage(role="user", content=prompt)],
            )

            # Store peer discussion output
            agent_outputs[agent.id].append(f"[Peer discussion with {peer.name}]: {response}")

            return agent.id, response

        # Execute both agents in parallel
        tasks = [
            get_peer_response(agent_a, agent_b),
            get_peer_response(agent_b, agent_a)
        ]
        results = await asyncio.gather(*tasks)

        return {agent_id: response for agent_id, response in results}

    def _build_results_context(
        self,
        all_round_results: List[Dict[str, str]],
        agents: Dict[str, AgentConfig]
    ) -> str:
        """Build a formatted string of all round results for manager context."""
        context_parts = []

        for round_num, round_results in enumerate(all_round_results, start=1):
            round_text = f"=== Round {round_num} Results ==="
            for agent_id, response in round_results.items():
                agent = agents.get(agent_id)
                if agent:
                    round_text += f"\n[{agent.name}]: {response}"
            context_parts.append(round_text)

        return "\n\n".join(context_parts)

    def _build_peer_context(
        self,
        all_peer_results: List[Dict]
    ) -> str:
        """Build a formatted string of all peer discussion results."""
        context_parts = []

        for i, peer_result in enumerate(all_peer_results, start=1):
            pair = peer_result.get("pair", "Unknown")
            instruction = peer_result.get("instruction", "")
            results = peer_result.get("results", {})

            peer_text = f"=== Peer Discussion {i}: {pair} ==="
            peer_text += f"\nInstruction: {instruction}"
            for agent_name, response in results.items():
                peer_text += f"\n[{agent_name}]: {response}"
            context_parts.append(peer_text)

        return "\n\n".join(context_parts)
