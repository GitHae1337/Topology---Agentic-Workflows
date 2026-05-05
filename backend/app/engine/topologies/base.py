from abc import ABC, abstractmethod
from typing import Dict, List, AsyncGenerator
from pydantic import BaseModel
from datetime import datetime
import uuid
import logging

from ...models import TopologyConfig, AgentConfig, ExecutionMessage
from ...llm.base import LLMService, LLMMessage, LLMServiceFactory

logger = logging.getLogger(__name__)


class TopologyResult(BaseModel):
    """Result of topology execution."""
    output: str
    turns_used: int
    messages: List[ExecutionMessage]


class BaseTopologyExecutor(ABC):
    """Abstract base class for topology executors."""

    @abstractmethod
    async def execute(
        self,
        topology: TopologyConfig,
        agents: Dict[str, AgentConfig],
        input_message: str,
        conversation_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """
        Execute the topology with the given agents and input.

        Args:
            topology: Topology configuration
            agents: Dictionary of agent configs
            input_message: Current user input
            conversation_history: Previous conversation messages for context

        Yields ExecutionMessage objects as agents communicate.
        """
        pass

    def build_history_context(self, conversation_history: List[Dict[str, str]]) -> str:
        """Build a context string from conversation history."""
        if not conversation_history:
            return ""

        history_parts = []
        for msg in conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                history_parts.append(f"User: {content}")
            elif role == "assistant":
                history_parts.append(f"Assistant: {content}")

        if not history_parts:
            return ""

        return "Previous conversation:\n" + "\n\n".join(history_parts) + "\n\n---\n\n"

    def format_user_prompt_with_task(self, task: str, prior_context: str = "") -> str:
        """Standardized user-prompt format that always includes the original task Q.

        Per G-Designer (arXiv:2410.11782), every agent at every round should
        receive the original task in addition to its in-neighbor outputs. This
        helper unifies that format across topology executors so chain, mesh,
        centralized, hierarchical, and cycle all expose Q to every agent.
        """
        if prior_context:
            return f"Original task:\n{task}\n\n{prior_context}"
        return f"Original task:\n{task}"

    async def call_agent(
        self,
        agent: AgentConfig,
        conversation: List[LLMMessage],
    ) -> str:
        """Call an agent with the given conversation history."""
        llm_service = LLMServiceFactory.get_service(agent.model)

        # Add system message with agent instructions
        messages = []
        if agent.instructions:
            messages.append(LLMMessage(role="system", content=agent.instructions))
        messages.extend(conversation)

        logger.info(f"Calling agent {agent.name} ({agent.model}) with {len(messages)} messages")

        response = await llm_service.generate(
            messages=messages,
            model=agent.model,
        )

        return response.content

    def create_message(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        metadata: dict = None,
    ) -> ExecutionMessage:
        """Create an execution message."""
        return ExecutionMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

    def check_early_termination(self, content: str) -> bool:
        """Check if the content indicates task completion."""
        termination_signals = [
            "[TASK_COMPLETE]",
            "[DONE]",
            "[FINISHED]",
            "FINAL ANSWER:",
            "In conclusion,",
        ]
        return any(signal.lower() in content.lower() for signal in termination_signals)

    def get_adjacency_list(
        self,
        topology: TopologyConfig,
    ) -> Dict[str, List[str]]:
        """Build adjacency list from internal edges."""
        adj = {agent_id: [] for agent_id in topology.agents}
        for edge in topology.internal_edges:
            if edge.from_agent in adj:
                adj[edge.from_agent].append(edge.to_agent)
        return adj
