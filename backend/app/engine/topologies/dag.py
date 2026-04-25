from typing import Dict, List, Set, AsyncGenerator
from collections import defaultdict
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class DAGExecutor(BaseTopologyExecutor):
    """
    DAG (Directed Acyclic Graph) topology executor.

    Behavior:
    1. Identify entry nodes (no incoming edges)
    2. Execute entry nodes in parallel with input
    3. When node completes, trigger downstream nodes
    4. Nodes with multiple inputs wait for all predecessors
    5. Terminal nodes (no outgoing edges) produce output
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting DAG execution with {len(agents)} agents")

        # Build adjacency list and in-degree map
        adj: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {agent_id: 0 for agent_id in topology.agents}
        predecessors: Dict[str, List[str]] = defaultdict(list)

        for edge in topology.internal_edges:
            adj[edge.from_agent].append(edge.to_agent)
            in_degree[edge.to_agent] = in_degree.get(edge.to_agent, 0) + 1
            predecessors[edge.to_agent].append(edge.from_agent)

        # Find entry nodes (in-degree 0)
        entry_nodes = [agent_id for agent_id in topology.agents if in_degree.get(agent_id, 0) == 0]

        # Find terminal nodes (no outgoing edges)
        terminal_nodes = [agent_id for agent_id in topology.agents if not adj.get(agent_id)]

        if not entry_nodes:
            logger.error("No entry nodes found in DAG")
            yield self.create_message("system", "user", "Error: No entry nodes found")
            return

        logger.info(f"Entry nodes: {entry_nodes}, Terminal nodes: {terminal_nodes}")

        # Track completed nodes and their outputs
        completed: Dict[str, str] = {}
        remaining_in_degree = dict(in_degree)
        ready_queue = list(entry_nodes)
        turns = 0

        while ready_queue and turns < topology.max_turns:
            # Process all ready nodes (could be parallelized)
            current_batch = list(ready_queue)
            ready_queue.clear()

            for agent_id in current_batch:
                agent = agents.get(agent_id)
                if not agent:
                    logger.warning(f"Agent {agent_id} not found")
                    completed[agent_id] = ""
                    continue

                turns += 1
                if turns > topology.max_turns:
                    break

                # Build input from predecessors
                pred_ids = predecessors.get(agent_id, [])
                if pred_ids:
                    pred_outputs = "\n\n".join([
                        f"[From {agents.get(pid).name if agents.get(pid) else pid}]:\n{completed.get(pid, '')}"
                        for pid in pred_ids
                    ])
                    context = f"You are processing inputs from previous agents:\n\n{pred_outputs}\n\nOriginal task: {input_message}"
                else:
                    context = f"You are the first agent in a workflow. Task: {input_message}"

                # Determine position info
                is_terminal = agent_id in terminal_nodes
                position_info = ""
                if is_terminal:
                    position_info = "\n\nYou are at the end of the workflow. Provide the final, complete output."
                else:
                    position_info = "\n\nYour output will be passed to downstream agents. Be thorough and clear."

                response = await self.call_agent(
                    agent,
                    [LLMMessage(role="user", content=context + position_info)],
                )

                completed[agent_id] = response
                downstream = adj.get(agent_id, [])
                downstream_agent = agents.get(downstream[0]) if downstream else None
                yield self.create_message(
                    agent.name,
                    downstream_agent.name if downstream_agent else "output",
                    response,
                    {"turn": turns, "is_terminal": is_terminal}
                )

                # Update downstream nodes
                for downstream_id in adj.get(agent_id, []):
                    remaining_in_degree[downstream_id] -= 1
                    if remaining_in_degree[downstream_id] == 0:
                        ready_queue.append(downstream_id)

                # Check for early termination
                if topology.early_termination and is_terminal and self.check_early_termination(response):
                    logger.info(f"Early termination at turn {turns}")
                    ready_queue.clear()
                    break

        logger.info(f"DAG execution completed in {turns} turns")
