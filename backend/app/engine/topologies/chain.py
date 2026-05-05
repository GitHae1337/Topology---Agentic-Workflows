from typing import Dict, List, AsyncGenerator
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class ChainExecutor(BaseTopologyExecutor):
    """
    Chain (Pipeline) topology executor.

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
        K = topology.max_turns
        logger.info(f"Starting chain execution with {len(agents)} agents, K={K} rounds")
        logger.info(f"Conversation history: {len(conversation_history) if conversation_history else 0} messages")

        history_context = self.build_history_context(conversation_history) if conversation_history else ""

        # Build adjacency list and topological order
        adj = self.get_adjacency_list(topology)
        has_incoming = set()
        for neighbors in adj.values():
            for n in neighbors:
                has_incoming.add(n)
        entry_nodes = [aid for aid in topology.agents if aid not in has_incoming]
        if not entry_nodes:
            logger.error("No entry node found in chain topology")
            yield self.create_message("system", "user", "Error: No entry node found")
            return

        execution_order: List[str] = []
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

        n_agents = len(execution_order)
        logger.info(f"Execution order: {[agents.get(aid).name for aid in execution_order if agents.get(aid)]}")

        # round_responses[t-1][agent_id] = response in round t (1-indexed externally, 0-indexed in list)
        round_responses: List[Dict[str, str]] = []

        for round_idx in range(1, K + 1):
            logger.info(f"Chain round {round_idx}/{K}")
            this_round: Dict[str, str] = {}

            for pos, agent_id in enumerate(execution_order):
                agent = agents.get(agent_id)
                if not agent:
                    logger.warning(f"Agent {agent_id} not found, skipping")
                    continue

                # Build prior context: this round's previous agent + own previous round output
                prior_parts: List[str] = []
                if pos > 0:
                    prev_agent_id = execution_order[pos - 1]
                    prev_agent = agents.get(prev_agent_id)
                    prev_response = this_round.get(prev_agent_id)
                    if prev_agent and prev_response:
                        prior_parts.append(
                            f"Previous agent ({prev_agent.name}) output (round {round_idx}):\n{prev_response}"
                        )
                if round_idx > 1:
                    last_round_self = round_responses[-1].get(agent_id)
                    if last_round_self:
                        prior_parts.append(
                            f"Your previous round (round {round_idx - 1}) output:\n{last_round_self}"
                        )
                prior_context = "\n\n".join(prior_parts)

                user_content = self.format_user_prompt_with_task(input_message, prior_context)

                position_info = f"Round {round_idx}/{K}. You are agent {pos + 1}/{n_agents} in a chain pipeline."
                if pos == 0:
                    position_info += " You are the first agent in this round."
                elif pos == n_agents - 1:
                    position_info += " You are the final agent. If this is the last round, provide the complete final answer."
                else:
                    position_info += " Process the input from the previous agent and refine."

                sys_content = (
                    f"{agent.instructions}\n\n{position_info}" if agent.instructions else position_info
                )
                if round_idx == 1 and pos == 0 and history_context:
                    sys_content += f"\n\n{history_context}"

                response = await self.call_agent(
                    AgentConfig(
                        id=agent.id,
                        name=agent.name,
                        instructions=sys_content,
                        model=agent.model,
                    ),
                    [LLMMessage(role="user", content=user_content)],
                )

                this_round[agent_id] = response

                if pos + 1 < n_agents:
                    next_agent_obj = agents.get(execution_order[pos + 1])
                    next_agent_name = next_agent_obj.name if next_agent_obj else "next"
                else:
                    next_agent_name = "output" if round_idx == K else "next-round"

                yield self.create_message(
                    agent.name,
                    next_agent_name,
                    response,
                    {"round": round_idx, "K": K, "position": pos + 1, "total": n_agents},
                )

            round_responses.append(this_round)

        logger.info(f"Chain execution completed: {K} rounds x {n_agents} agents = {K * n_agents} agent calls")
