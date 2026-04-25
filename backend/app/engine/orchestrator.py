from typing import Dict, List, AsyncGenerator
import time
import logging

from ..models import (
    WorkflowDefinition,
    TopologyConfig,
    AgentConfig,
    ExecutionMessage,
    ExecutionResult,
)
from .topologies import get_executor
from .message_router import MessageRouter

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestration engine for executing workflows."""

    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.agents: Dict[str, AgentConfig] = {a.id: a for a in workflow.agents}
        self.topologies: Dict[str, TopologyConfig] = {t.id: t for t in workflow.topologies}

    async def execute(
        self,
        input_message: str,
        config_overrides: Dict = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """
        Execute the workflow with the given input.

        Yields ExecutionMessage objects as agents communicate.
        """
        logger.info(f"Starting workflow execution: {self.workflow.id}")
        start_time = time.time()
        config_overrides = config_overrides or {}

        # For now, execute each topology in order
        # TODO: Respect workflow-level connections for complex workflows

        all_messages: List[ExecutionMessage] = []

        for topology in self.workflow.topologies:
            # Apply config overrides
            effective_topology = TopologyConfig(
                id=topology.id,
                type=topology.type,
                name=topology.name,
                agents=topology.agents,
                internal_edges=topology.internal_edges,
                max_turns=config_overrides.get("max_turns", topology.max_turns),
                timeout=config_overrides.get("timeout", topology.timeout),
                early_termination=config_overrides.get("early_termination", topology.early_termination),
                start_agent_id=topology.start_agent_id,
            )

            # Get agents for this topology
            topology_agents = {
                agent_id: self.agents[agent_id]
                for agent_id in topology.agents
                if agent_id in self.agents
            }

            if not topology_agents:
                logger.warning(f"No agents found for topology {topology.id}")
                continue

            logger.info(f"Executing topology: {topology.name} ({topology.type}) with {len(topology_agents)} agents")

            # Get appropriate executor
            executor = get_executor(topology.type)

            # Execute and yield messages
            async for message in executor.execute(
                effective_topology,
                topology_agents,
                input_message,
            ):
                all_messages.append(message)
                yield message

            # Use last message output as input for next topology
            if all_messages:
                input_message = all_messages[-1].content

        duration = time.time() - start_time
        logger.info(f"Workflow execution completed in {duration:.2f}s with {len(all_messages)} messages")

    async def execute_full(
        self,
        input_message: str,
        config_overrides: Dict = None,
    ) -> ExecutionResult:
        """
        Execute the workflow and return the complete result.
        """
        start_time = time.time()
        messages: List[ExecutionMessage] = []

        async for message in self.execute(input_message, config_overrides):
            messages.append(message)

        duration = time.time() - start_time
        output = messages[-1].content if messages else "No output generated"

        return ExecutionResult(
            output=output,
            turns_used=len(messages),
            duration_seconds=duration,
            messages=messages,
        )
