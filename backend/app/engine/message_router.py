from typing import Dict, List, Optional
from ..models import ExecutionMessage, AgentConfig, TopologyConfig
import logging

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes messages between agents based on topology structure."""

    def __init__(self, topology: TopologyConfig, agents: Dict[str, AgentConfig]):
        self.topology = topology
        self.agents = agents
        self.message_history: List[ExecutionMessage] = []
        self._build_routing_table()

    def _build_routing_table(self):
        """Build routing table from topology edges."""
        self.routes: Dict[str, List[str]] = {}

        for agent_id in self.topology.agents:
            self.routes[agent_id] = []

        for edge in self.topology.internal_edges:
            if edge.from_agent in self.routes:
                self.routes[edge.from_agent].append(edge.to_agent)

        logger.info(f"Built routing table: {self.routes}")

    def get_neighbors(self, agent_id: str) -> List[str]:
        """Get neighboring agents that this agent can send messages to."""
        return self.routes.get(agent_id, [])

    def record_message(self, message: ExecutionMessage):
        """Record a message in history."""
        self.message_history.append(message)
        logger.info(f"Message: {message.from_agent} -> {message.to_agent}: {message.content[:100]}...")

    def get_messages_for_agent(self, agent_id: str) -> List[ExecutionMessage]:
        """Get all messages sent to a specific agent."""
        return [m for m in self.message_history if m.to_agent == agent_id]

    def get_messages_from_agent(self, agent_id: str) -> List[ExecutionMessage]:
        """Get all messages sent by a specific agent."""
        return [m for m in self.message_history if m.from_agent == agent_id]

    def get_conversation_context(self, agent_id: str) -> str:
        """Build conversation context for an agent from message history."""
        relevant_messages = []

        # Messages TO this agent
        for msg in self.message_history:
            if msg.to_agent == agent_id or msg.to_agent == "all" or msg.to_agent == "broadcast":
                sender = self.agents.get(msg.from_agent)
                sender_name = sender.name if sender else msg.from_agent
                relevant_messages.append(f"[{sender_name}]: {msg.content}")

        return "\n\n".join(relevant_messages)
