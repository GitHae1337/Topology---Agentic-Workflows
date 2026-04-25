from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from .agent import AgentConfig
from .topology import TopologyConfig


class WorkflowNodeType(str, Enum):
    """Types of nodes in the workflow graph."""
    START = "start"
    END = "end"
    AGENT = "agent"
    TOPOLOGY = "topology"
    IFELSE = "ifelse"
    APPROVAL = "approval"
    NOTE = "note"


class IfElseConditionModel(BaseModel):
    """A condition branch in an If/Else node."""
    id: str = Field(..., description="Unique identifier for the condition")
    name: Optional[str] = Field(default=None, description="Display name for the condition")
    condition: str = Field(default="", description="Expression to evaluate")


class WorkflowNode(BaseModel):
    """A node in the workflow graph (for graph-based execution)."""
    id: str = Field(..., description="Unique identifier for the node")
    type: WorkflowNodeType = Field(..., description="Type of node")
    name: str = Field(..., description="Display name")
    config: Dict[str, Any] = Field(default_factory=dict, description="Node configuration")
    # For ifelse nodes
    conditions: List[IfElseConditionModel] = Field(default_factory=list, description="Conditions for if/else branching")
    # For approval nodes
    approval_message: Optional[str] = Field(default=None, description="Message to display for approval")


class ApprovalState(BaseModel):
    """State for a pending approval."""
    execution_id: str = Field(..., description="Unique execution ID")
    workflow_id: str = Field(..., description="Workflow ID")
    node_id: str = Field(..., description="Approval node ID")
    message: str = Field(..., description="Approval message")
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution context")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResumeRequest(BaseModel):
    """Request to resume execution after approval."""
    execution_id: str = Field(..., description="Execution ID to resume")
    decision: str = Field(..., description="Decision: 'approve' or 'reject'")


class WorkflowConnection(BaseModel):
    """A workflow-level connection between nodes or topologies."""

    id: str = Field(..., description="Unique identifier for the connection")
    from_id: str = Field(..., description="Source node or topology ID")
    to_id: str = Field(..., description="Target node or topology ID")
    from_type: str = Field(default="node", description="Type of source (node or template)")
    from_port: Optional[int] = Field(default=None, description="Port index for branching (ifelse: 0,1,2..., -1 for else; approval: 0=approve, 1=reject)")


class WorkflowDefinition(BaseModel):
    """Complete workflow definition."""

    id: str = Field(..., description="Unique identifier for the workflow")
    name: str = Field(default="Untitled Workflow", description="Name of the workflow")
    agents: List[AgentConfig] = Field(default_factory=list, description="All agents in the workflow")
    topologies: List[TopologyConfig] = Field(default_factory=list, description="All topology templates")
    connections: List[WorkflowConnection] = Field(default_factory=list, description="Workflow-level connections")
    nodes: List[WorkflowNode] = Field(default_factory=list, description="All workflow nodes (start, end, ifelse, approval)")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "workflow-1",
                "name": "Research Workflow",
                "agents": [],
                "topologies": [],
                "connections": [],
            }
        }


class WorkflowCreate(BaseModel):
    """Request model for creating a workflow."""

    name: str = Field(default="Untitled Workflow", description="Name of the workflow")
    agents: List[AgentConfig] = Field(default_factory=list)
    topologies: List[TopologyConfig] = Field(default_factory=list)
    connections: List[WorkflowConnection] = Field(default_factory=list)
    nodes: List[WorkflowNode] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    """Request model for updating a workflow."""

    name: Optional[str] = None
    agents: Optional[List[AgentConfig]] = None
    topologies: Optional[List[TopologyConfig]] = None
    connections: Optional[List[WorkflowConnection]] = None
    nodes: Optional[List[WorkflowNode]] = None


class ConversationMessage(BaseModel):
    """A message in conversation history."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ExecutionRequest(BaseModel):
    """Request model for executing a workflow."""

    input: str = Field(..., description="User input message")
    history: List[ConversationMessage] = Field(
        default_factory=list,
        description="Previous conversation history for context"
    )
    config_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional config overrides (max_turns, timeout, etc.)"
    )


class ExecutionMessage(BaseModel):
    """A message exchanged during execution."""

    id: str = Field(..., description="Unique message ID")
    from_agent: str = Field(..., description="Sending agent ID")
    to_agent: str = Field(..., description="Receiving agent ID")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "msg-1",
                "from_agent": "agent-1",
                "to_agent": "agent-2",
                "content": "Here is my analysis...",
                "timestamp": "2024-01-01T12:00:00Z",
                "metadata": {},
            }
        }


class ExecutionResult(BaseModel):
    """Result of workflow execution."""

    output: str = Field(..., description="Final output")
    turns_used: int = Field(..., description="Number of turns used")
    duration_seconds: float = Field(..., description="Execution duration")
    messages: List[ExecutionMessage] = Field(default_factory=list, description="All messages exchanged")
