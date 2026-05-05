from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class TopologyType(str, Enum):
    CENTRALIZED = "centralized"
    CHAIN = "chain"
    HIERARCHICAL = "hierarchical"
    # P2P = "p2p"  # deprecated for the 5-topology study
    MESH = "mesh"
    # DAG = "dag"  # deprecated for the 5-topology study
    CYCLE = "cycle"


class EdgeType(str, Enum):
    BIDIRECTIONAL = "bidirectional"
    UNIDIRECTIONAL = "unidirectional"


class InternalEdge(BaseModel):
    """An edge between two agents within a topology."""

    id: str = Field(..., description="Unique identifier for the edge")
    from_agent: str = Field(..., alias="from", description="Source agent ID")
    to_agent: str = Field(..., alias="to", description="Target agent ID")
    edge_type: EdgeType = Field(..., alias="type", description="Type of edge")

    class Config:
        populate_by_name = True


class TopologyConfig(BaseModel):
    """Configuration for a topology template."""

    id: str = Field(..., description="Unique identifier for the topology")
    type: TopologyType = Field(..., description="Type of topology")
    name: str = Field(..., description="Display name")
    agents: List[str] = Field(default_factory=list, description="List of agent IDs in this topology")
    internal_edges: List[InternalEdge] = Field(default_factory=list, description="Edges between agents")
    max_turns: int = Field(default=3, ge=1, le=100, description="Maximum rounds")
    timeout: int = Field(default=180, ge=30, description="Execution timeout in seconds")
    early_termination: bool = Field(default=True, description="Stop when completion detected")
    start_agent_id: Optional[str] = Field(default=None, description="Start agent for Mesh/Cycle")

    @property
    def edge_type(self) -> EdgeType:
        """Get the edge type for this topology type."""
        if self.type in [TopologyType.CENTRALIZED, TopologyType.HIERARCHICAL, TopologyType.MESH]:
            return EdgeType.BIDIRECTIONAL
        return EdgeType.UNIDIRECTIONAL

    @property
    def needs_start_agent(self) -> bool:
        """Check if this topology requires a start agent to be specified."""
        return self.type in [TopologyType.MESH, TopologyType.CYCLE]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "topo-1",
                "type": "centralized",
                "name": "Centralized",
                "agents": ["agent-1", "agent-2", "agent-3"],
                "internal_edges": [
                    {"id": "edge-1", "from": "agent-1", "to": "agent-2", "type": "bidirectional"}
                ],
                "max_turns": 3,
                "timeout": 180,
                "early_termination": True,
            }
        }
