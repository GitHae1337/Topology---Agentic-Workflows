from typing import Dict, List, AsyncGenerator
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class SequentialExecutor(BaseTopologyExecutor):
    """
    Sequential (Pipeline) topology executor.

    Behavior:
    1. First agent receives input
    2. Agent processes and produces output
    3. Output becomes input for next agent (following edges)
    4. Continue until final agent produces output
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting sequential execution with {len(agents)} agents")
        logger.info(f"Conversation history: {len(conversation_history) if conversation_history else 0} messages")

        # Build history context for the first agent
        history_context = self.build_history_context(conversation_history) if conversation_history else ""

        # Build adjacency list to determine order
        adj = self.get_adjacency_list(topology)

        # Find entry node (no incoming edges)
        has_incoming = set()
        for neighbors in adj.values():
            for n in neighbors:
                has_incoming.add(n)

        entry_nodes = [agent_id for agent_id in topology.agents if agent_id not in has_incoming]

        if not entry_nodes:
            logger.error("No entry node found in sequential topology")
            yield self.create_message("system", "user", "Error: No entry node found")
            return

        # Build execution order using topological sort
        execution_order = []
        visited = set()

        def dfs(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)
            execution_order.append(node_id)
            for neighbor in adj.get(node_id, []):
                dfs(neighbor)

        for entry in entry_nodes:
            dfs(entry)

        logger.info(f"Execution order: {[agents.get(aid, {}).name if agents.get(aid) else aid for aid in execution_order]}")

        current_input = input_message

        # Sequential is a DAG/FSM - execute all agents in order until the last one completes
        for i, agent_id in enumerate(execution_order):
            agent = agents.get(agent_id)
            if not agent:
                logger.warning(f"Agent {agent_id} not found, skipping")
                continue

            # Build context for this agent
            position_info = f"You are agent {i + 1} of {len(execution_order)} in a pipeline."
            if i == 0:
                position_info += " You are the first agent receiving the original input."
                # Include conversation history for the first agent
                if history_context:
                    position_info += f"\n\n{history_context}"
            elif i == len(execution_order) - 1:
                position_info += " You are the final agent. Provide the complete final output."
            else:
                position_info += " Process the input from the previous agent and pass to the next."

            messages = [
                LLMMessage(role="system", content=f"{agent.instructions}\n\n{position_info}") if agent.instructions else LLMMessage(role="system", content=position_info),
                LLMMessage(role="user", content=current_input),
            ]

            response = await self.call_agent(
                AgentConfig(
                    id=agent.id,
                    name=agent.name,
                    instructions=messages[0].content,
                    model=agent.model,
                ),
                [messages[1]],
            )

            next_agent = agents.get(execution_order[i + 1]) if i + 1 < len(execution_order) else None
            next_agent_name = next_agent.name if next_agent else "output"
            yield self.create_message(agent.name, next_agent_name, response, {"position": i + 1, "total": len(execution_order)})

            current_input = response

        logger.info(f"Sequential execution completed with {len(execution_order)} agents")
