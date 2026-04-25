"""
Graph-based workflow orchestrator.

Executes workflows by following the connection graph from Start to End nodes.
Handles branching (IfElse), human-in-the-loop (Approval), and topology execution.
"""

from typing import Dict, List, AsyncGenerator, Optional, Any, Tuple
import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from ..models import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowNodeType,
    TopologyConfig,
    AgentConfig,
    ExecutionMessage,
    WorkflowConnection,
)
from .topologies import get_executor
from ..llm.base import LLMMessage, LLMServiceFactory

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Holds execution state as we traverse the graph."""
    workflow_id: str
    execution_id: str
    user_input: str
    current_output: str
    variables: Dict[str, Any] = field(default_factory=dict)
    message_history: List[ExecutionMessage] = field(default_factory=list)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # Previous user/assistant messages


class ConditionEvaluator:
    """Safe expression evaluator for If/Else conditions."""

    OPERATORS = {
        '==': lambda a, b: str(a) == str(b),
        '!=': lambda a, b: str(a) != str(b),
        '>': lambda a, b: float(a) > float(b) if _is_numeric(a) and _is_numeric(b) else False,
        '<': lambda a, b: float(a) < float(b) if _is_numeric(a) and _is_numeric(b) else False,
        '>=': lambda a, b: float(a) >= float(b) if _is_numeric(a) and _is_numeric(b) else False,
        '<=': lambda a, b: float(a) <= float(b) if _is_numeric(a) and _is_numeric(b) else False,
        'contains': lambda a, b: str(b).lower() in str(a).lower(),
        'startswith': lambda a, b: str(a).lower().startswith(str(b).lower()),
        'endswith': lambda a, b: str(a).lower().endswith(str(b).lower()),
    }

    @classmethod
    def evaluate(cls, condition: str, context: ExecutionContext) -> bool:
        """Evaluate a condition expression against the execution context."""
        logger.info(f"Evaluating condition: {condition}")

        if not condition or not condition.strip():
            return False

        # Build variable context
        vars_dict = {
            'input': context.user_input,
            'output': context.current_output,
            'true': True,
            'false': False,
            **context.variables,
        }

        # Pattern: variable operator value
        # Examples: "output contains error", "status == success", "confidence > 0.8"
        pattern = r'(\w+(?:\.\w+)?)\s*(==|!=|>=|<=|>|<|contains|startswith|endswith)\s*["\']?([^"\']*)["\']?'
        match = re.match(pattern, condition.strip(), re.IGNORECASE)

        if match:
            var_name, operator, value = match.groups()
            var_name = var_name.lower()
            operator = operator.lower()
            value = value.strip()

            var_value = cls._get_var(var_name, vars_dict)

            # Type coercion for value
            if value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif _is_numeric(value):
                value = float(value) if '.' in value else int(value)

            result = cls.OPERATORS.get(operator, lambda a, b: False)(var_value, value)
            logger.info(f"Condition result: {var_value} {operator} {value} = {result}")
            return result

        # Invalid condition format
        logger.error(f"Invalid condition format: '{condition}'")
        raise ValueError(f"If/else node requires a valid condition expression. Invalid format: '{condition}'. Use format: 'variable operator value' (e.g., 'output contains error')")

    @classmethod
    def _get_var(cls, name: str, vars_dict: Dict) -> Any:
        """Get variable value, supporting dot notation."""
        parts = name.split('.')
        value = vars_dict.get(parts[0], '')
        for part in parts[1:]:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict):
                value = value.get(part, '')
            else:
                return ''
        return value


def _is_numeric(value) -> bool:
    """Check if a value can be converted to a number."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


class GraphOrchestrator:
    """Executes workflows by traversing the connection graph."""

    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.agents: Dict[str, AgentConfig] = {a.id: a for a in workflow.agents}
        self.topologies: Dict[str, TopologyConfig] = {t.id: t for t in workflow.topologies}
        self.nodes: Dict[str, WorkflowNode] = {n.id: n for n in workflow.nodes}
        self.adjacency: Dict[str, List[WorkflowConnection]] = self._build_adjacency()

        logger.info(f"GraphOrchestrator initialized for workflow: {workflow.id}")
        logger.info(f"  - Agents: {list(self.agents.keys())}")
        logger.info(f"  - Topologies: {list(self.topologies.keys())}")
        logger.info(f"  - Nodes: {list(self.nodes.keys())}")
        logger.info(f"  - Connections: {len(workflow.connections)}")

    def _build_adjacency(self) -> Dict[str, List[WorkflowConnection]]:
        """Build adjacency list from connections."""
        adj: Dict[str, List[WorkflowConnection]] = {}
        for conn in self.workflow.connections:
            if conn.from_id not in adj:
                adj[conn.from_id] = []
            adj[conn.from_id].append(conn)
        return adj

    def _find_start_node(self) -> Optional[str]:
        """Find the start node in the workflow."""
        for node in self.workflow.nodes:
            if node.type == WorkflowNodeType.START:
                return node.id
        return None

    def _get_next_nodes(self, node_id: str, port: Optional[int] = None) -> List[str]:
        """Get nodes connected from this node, optionally filtering by port."""
        connections = self.adjacency.get(node_id, [])
        if port is not None:
            connections = [c for c in connections if c.from_port == port]
        return [c.to_id for c in connections]

    async def execute(
        self,
        input_message: str,
        config_overrides: Dict = None,
        history: List = None,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute the workflow graph."""
        logger.info(f"Starting graph execution for workflow: {self.workflow.id}")
        logger.info(f"Input message: {input_message[:100]}...")
        logger.info(f"Conversation history: {len(history) if history else 0} messages")

        # Convert history to list of dicts if provided
        conversation_history = []
        if history:
            for msg in history:
                if hasattr(msg, 'role') and hasattr(msg, 'content'):
                    conversation_history.append({"role": msg.role, "content": msg.content})
                elif isinstance(msg, dict):
                    conversation_history.append(msg)

        context = ExecutionContext(
            workflow_id=self.workflow.id,
            execution_id=f"exec-{uuid.uuid4().hex[:8]}",
            user_input=input_message,
            current_output=input_message,
            conversation_history=conversation_history,
        )

        start_node_id = self._find_start_node()

        if not start_node_id:
            logger.error("No start node found in workflow. Workflow must have a Start node.")
            yield self._create_message("system", "user", "Error: No start node found. Please add a Start node to your workflow.", {"error": True})
            return

        logger.info(f"Found start node: {start_node_id}")

        # Execute starting from start node's connections
        next_nodes = self._get_next_nodes(start_node_id)
        logger.info(f"[START] Next nodes from start: {next_nodes}")
        logger.info(f"[START] Number of nodes to execute: {len(next_nodes)}")
        if len(next_nodes) > 1:
            logger.info(f"[START] Will execute in PARALLEL: {next_nodes}")

        async for message in self._execute_nodes(next_nodes, context, config_overrides or {}):
            yield message

    async def _execute_nodes(
        self,
        node_ids: List[str],
        context: ExecutionContext,
        config_overrides: Dict,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute a list of nodes in parallel if multiple, sequential if single."""
        if not node_ids:
            return

        # Single node - execute directly (no parallelism needed)
        if len(node_ids) == 1:
            async for message in self._execute_node(node_ids[0], context, config_overrides):
                yield message
                # Check for approval pause
                if message.metadata.get('approval_required'):
                    return
            return

        # Multiple nodes - execute in PARALLEL
        logger.info(f"[PARALLEL] Executing {len(node_ids)} nodes in parallel: {node_ids}")

        # Create separate context copies for each parallel branch
        # Each branch gets its own context to avoid race conditions
        branch_contexts = []
        for node_id in node_ids:
            branch_context = ExecutionContext(
                workflow_id=context.workflow_id,
                execution_id=context.execution_id,
                user_input=context.user_input,
                current_output=context.current_output,  # All branches start with same input
                variables=dict(context.variables),  # Copy variables
                message_history=list(context.message_history),  # Copy history
                conversation_history=list(context.conversation_history),  # Copy conversation history
            )
            branch_contexts.append(branch_context)

        # Execute all nodes in parallel using asyncio.gather
        # return_exceptions=False means if one fails, all fail
        async def collect_node_execution(node_id: str, branch_ctx: ExecutionContext) -> Tuple[List[ExecutionMessage], str, bool]:
            """Collect all messages from a node execution and return (messages, final_output, has_approval)."""
            messages = []
            has_approval = False
            async for message in self._execute_node(node_id, branch_ctx, config_overrides):
                messages.append(message)
                if message.metadata.get('approval_required'):
                    has_approval = True
                    break
            return (messages, branch_ctx.current_output, has_approval)

        # Run all branches in parallel
        tasks = [
            collect_node_execution(node_id, branch_ctx)
            for node_id, branch_ctx in zip(node_ids, branch_contexts)
        ]

        # If any branch fails, this will raise the exception (fail entirely)
        results = await asyncio.gather(*tasks)

        # Collect all outputs and messages
        all_outputs = []
        has_any_approval = False

        for messages, final_output, has_approval in results:
            # Yield all messages from this branch
            for message in messages:
                yield message
            all_outputs.append(final_output)
            if has_approval:
                has_any_approval = True

        # Concatenate all outputs for the combined result
        combined_output = "\n\n".join(all_outputs)
        context.current_output = combined_output
        logger.info(f"[PARALLEL] Parallel execution complete. Combined {len(all_outputs)} outputs.")
        logger.info(f"[PARALLEL] Individual outputs: {[o[:100] + '...' if len(o) > 100 else o for o in all_outputs]}")
        logger.info(f"[PARALLEL] Combined output length: {len(combined_output)}")

        # If any branch required approval, pause
        if has_any_approval:
            return

        # Yield a combined result message so it becomes the final output
        # This ensures messages[-1].content contains the full parallel result
        logger.info(f"[PARALLEL] Yielding combined result message")
        yield self._create_message(
            "End",
            "user",
            combined_output,
            {
                "parallel_execution": True,
                "branch_count": len(all_outputs),
                "individual_outputs": all_outputs,
            }
        )
        logger.info(f"[PARALLEL] Combined result message yielded")

    async def _execute_node(
        self,
        node_id: str,
        context: ExecutionContext,
        config_overrides: Dict,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute a single node based on its type."""
        logger.info(f"Executing node: {node_id}")

        # Check if it's a topology
        if node_id in self.topologies:
            logger.info(f"Node {node_id} is a topology")
            async for msg in self._execute_topology(node_id, context, config_overrides):
                yield msg
            return

        # Check if it's a standalone agent
        if node_id in self.agents:
            logger.info(f"Node {node_id} is a standalone agent")
            async for msg in self._execute_standalone_agent(node_id, context):
                yield msg
            return

        # Check if it's a workflow node
        node = self.nodes.get(node_id)
        if not node:
            logger.warning(f"Node {node_id} not found")
            return

        logger.info(f"Node {node_id} is type: {node.type}")

        if node.type == WorkflowNodeType.END:
            # End node just terminates - no message needed (content already sent by previous node)
            logger.info(f"Reached End node: {node_id}")
            return

        if node.type == WorkflowNodeType.IFELSE:
            async for msg in self._execute_ifelse(node, context, config_overrides):
                yield msg
            return

        if node.type == WorkflowNodeType.APPROVAL:
            async for msg in self._execute_approval(node, context):
                yield msg
            return

        if node.type == WorkflowNodeType.NOTE:
            # Notes are just for documentation, pass through
            next_nodes = self._get_next_nodes(node_id)
            async for msg in self._execute_nodes(next_nodes, context, config_overrides):
                yield msg
            return

        # For other node types, just follow connections
        next_nodes = self._get_next_nodes(node_id)
        async for msg in self._execute_nodes(next_nodes, context, config_overrides):
            yield msg

    async def _execute_topology(
        self,
        topology_id: str,
        context: ExecutionContext,
        config_overrides: Dict,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute a topology."""
        topology = self.topologies[topology_id]
        logger.info(f"Executing topology: {topology.name} ({topology.type})")

        # Get agents for this topology
        topology_agents = {
            agent_id: self.agents[agent_id]
            for agent_id in topology.agents
            if agent_id in self.agents
        }

        if not topology_agents:
            logger.error(f"No agents found for topology {topology_id}")
            yield self._create_message(
                "system", "user",
                f"Error: Topology '{topology.name}' has no agents. Add agents to the topology before running.",
                {"error": True, "topology_id": topology_id}
            )
            return

        logger.info(f"Topology has {len(topology_agents)} agents")

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

        executor = get_executor(topology.type)

        async for message in executor.execute(
            effective_topology,
            topology_agents,
            context.current_output,
            conversation_history=context.conversation_history,
        ):
            context.message_history.append(message)
            context.current_output = message.content
            yield message

        # Continue to next nodes
        next_nodes = self._get_next_nodes(topology_id)
        async for msg in self._execute_nodes(next_nodes, context, config_overrides):
            yield msg

    async def _execute_standalone_agent(
        self,
        agent_id: str,
        context: ExecutionContext,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute a standalone agent (not in a topology)."""
        agent = self.agents[agent_id]
        logger.info(f"Executing standalone agent: {agent.name} (model: {agent.model})")

        llm_service = LLMServiceFactory.get_service(agent.model)
        messages = []
        if agent.instructions:
            messages.append(LLMMessage(role="system", content=agent.instructions))
        messages.append(LLMMessage(role="user", content=context.current_output))

        response = await llm_service.generate(messages=messages, model=agent.model)

        message = self._create_message(agent.name, "next", response.content, {"agent_id": agent_id})
        context.current_output = response.content
        context.message_history.append(message)
        yield message

        # Continue to next nodes
        next_nodes = self._get_next_nodes(agent_id)
        async for msg in self._execute_nodes(next_nodes, context, {}):
            yield msg

    async def _execute_ifelse(
        self,
        node: WorkflowNode,
        context: ExecutionContext,
        config_overrides: Dict,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute an if/else node, evaluating conditions."""
        logger.info(f"Executing if/else node: {node.id} with {len(node.conditions)} conditions")

        # Evaluate each condition in order
        for i, condition in enumerate(node.conditions):
            logger.info(f"Evaluating condition {i}: {condition.condition}")

            # Check for empty condition
            if not condition.condition or not condition.condition.strip():
                logger.error(f"Empty condition in if/else node: {node.id}")
                yield self._create_message(
                    "system", "user",
                    f"Error: If/else node '{node.name}' has an empty condition. Enter a condition before running.",
                    {"error": True, "node_id": node.id}
                )
                return

            evaluated = False
            try:
                evaluated = ConditionEvaluator.evaluate(condition.condition, context)
            except ValueError as e:
                yield self._create_message(
                    "system", "user",
                    f"Error: {str(e)}",
                    {"error": True, "node_id": node.id}
                )
                return

            if evaluated:
                logger.info(f"Condition {i} matched: {condition.condition}")
                yield self._create_message(
                    node.id, "branch",
                    f"Condition matched: {condition.name or condition.condition}",
                    {"branch": i, "condition": condition.condition}
                )

                # Get nodes connected to this condition's port
                next_nodes = self._get_next_nodes(node.id, port=i)
                logger.info(f"Following branch {i} to nodes: {next_nodes}")
                async for msg in self._execute_nodes(next_nodes, context, config_overrides):
                    yield msg
                return

        # No condition matched - use else branch (port -1)
        logger.info("No conditions matched, using else branch")
        yield self._create_message(
            node.id, "branch",
            "No conditions matched, using else branch",
            {"branch": -1, "condition": "else"}
        )

        next_nodes = self._get_next_nodes(node.id, port=-1)
        logger.info(f"Following else branch to nodes: {next_nodes}")
        async for msg in self._execute_nodes(next_nodes, context, config_overrides):
            yield msg

    async def _execute_approval(
        self,
        node: WorkflowNode,
        context: ExecutionContext,
    ) -> AsyncGenerator[ExecutionMessage, None]:
        """Execute an approval node - pauses for human input."""
        logger.info(f"Executing approval node: {node.id}")

        approval_message = node.approval_message or node.config.get('message', 'Approval required')

        yield self._create_message(
            node.id, "user",
            approval_message,
            {
                "approval_required": True,
                "execution_id": context.execution_id,
                "node_id": node.id,
                "message": approval_message,
                "context": {
                    "user_input": context.user_input,
                    "current_output": context.current_output,
                    "variables": context.variables,
                }
            }
        )
        # Execution pauses here - will be resumed via resume endpoint

    def _create_message(
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
