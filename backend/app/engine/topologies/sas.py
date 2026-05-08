from typing import Dict, List, AsyncGenerator
import logging

from .base import BaseTopologyExecutor
from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMMessage

logger = logging.getLogger(__name__)


class SASExecutor(BaseTopologyExecutor):
    """
    SAS (Single-Agent System) executor.

    PDF arXiv:2512.08296: |A|=1, C=∅. A single agent runs a monolithic
    reasoning loop on the user input and emits one final answer. No
    inter-agent edges, no rounds.
    """

    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        logger.info(f"Starting SAS execution with {len(agents)} agent(s)")

        agent_id = topology.start_agent_id or (topology.agents[0] if topology.agents else None)
        if not agent_id or agent_id not in agents:
            logger.error("SAS topology requires exactly one agent in topology.agents/start_agent_id")
            yield self.create_message("system", "user", "Error: SAS requires one agent")
            return

        agent = agents[agent_id]
        if len(topology.agents) != 1:
            logger.warning(
                f"SAS expected |A|=1 but got {len(topology.agents)}; using start agent {agent.name}"
            )

        user_msg = self.format_user_prompt_with_task(input_message)
        response = await self.call_agent(
            agent,
            [LLMMessage(role="user", content=user_msg)],
        )
        logger.info(f"SAS agent {agent.name} produced {len(response)} chars")

        yield self.create_message(
            from_agent=agent.id,
            to_agent="user",
            content=response,
            metadata={"role": "final"},
        )
