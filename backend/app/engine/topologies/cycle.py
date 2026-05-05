from typing import Dict, List, AsyncGenerator
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class CycleExecutor(BaseTopologyExecutor):
    """
    Cycle (Loop) topology executor.

    Behavior:
    1. Start agent receives input
    2. Agents iterate following edges (cycles allowed)
    3. Each iteration refines the previous output
    4. Track iteration count
    5. Terminate when max turns reached or early termination triggered
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting cycle execution with {len(agents)} agents")
        logger.info(f"Conversation history: {len(conversation_history) if conversation_history else 0} messages")

        # Build history context for prompts
        history_context = self.build_history_context(conversation_history) if conversation_history else ""

        if not topology.start_agent_id:
            logger.error("No start agent specified for cycle topology")
            yield self.create_message("system", "user", "Error: Start agent not specified")
            return

        start_agent = agents.get(topology.start_agent_id)
        if not start_agent:
            logger.error(f"Start agent {topology.start_agent_id} not found")
            yield self.create_message("system", "user", "Error: Start agent not found")
            return

        # Build adjacency list
        adj = self.get_adjacency_list(topology)

        logger.info(f"=== CYCLE DEBUG ===")
        logger.info(f"Topology agents: {topology.agents}")
        logger.info(f"Internal edges count: {len(topology.internal_edges)}")
        for edge in topology.internal_edges:
            logger.info(f"  Edge: {edge.from_agent} -> {edge.to_agent} (type: {edge.edge_type})")
        logger.info(f"Adjacency list: {adj}")
        logger.info(f"Start agent ID: {topology.start_agent_id}")
        logger.info(f"=== END DEBUG ===")

        # Track conversation history per agent
        agent_history: Dict[str, List[str]] = {agent_id: [] for agent_id in topology.agents}
        current_content = input_message
        current_agent_id = topology.start_agent_id
        turns = 0
        iterations = 0

        # max_turns = number of complete cycles (iterations)
        while iterations < topology.max_turns:
            current_agent = agents.get(current_agent_id)
            if not current_agent:
                logger.warning(f"Agent {current_agent_id} not found")
                break

            turns += 1

            # Build context
            history = agent_history.get(current_agent_id, [])
            iteration_info = f"This is iteration {iterations + 1}. "
            if history:
                iteration_info += f"Your previous response was:\n{history[-1]}\n\n"
                iteration_info += "Refine and improve upon your previous work based on the new input."
            else:
                iteration_info += "This is your first time processing this task."

            response = await self.call_agent(
                current_agent,
                [LLMMessage(role="user", content=f"""You are part of an iterative refinement process.

{history_context}Original task: {input_message}

{iteration_info}

Current input from previous agent:
{current_content}

Provide your refined output. If you believe the task is complete, include "TASK COMPLETE:" followed by your final answer.""")],
            )

            agent_history[current_agent_id].append(response)

            # Find next agent
            neighbors = adj.get(current_agent_id, [])
            next_agent_id = neighbors[0] if neighbors else None

            # Check if we've completed a cycle
            if next_agent_id == topology.start_agent_id:
                iterations += 1

            next_agent = agents.get(next_agent_id) if next_agent_id else None
            yield self.create_message(
                current_agent.name,
                next_agent.name if next_agent else "output",
                response,
                {"turn": turns, "iteration": iterations}
            )

            # Check for early termination (only if early_termination is enabled)
            if topology.early_termination:
                if self.check_early_termination(response) or "TASK COMPLETE:" in response.upper():
                    logger.info(f"Early termination at turn {turns}, iteration {iterations}")
                    break

            # Move to next agent
            current_content = response
            if next_agent_id:
                current_agent_id = next_agent_id
            else:
                # No next agent, end the loop
                break

        logger.info(f"Cycle execution completed in {turns} turns, {iterations} iterations")
