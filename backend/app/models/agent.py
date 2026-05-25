from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum


class ModelProvider(str, Enum):
    OPENAI = "openai"


class AgentConfig(BaseModel):
    """Configuration for an AI agent in the workflow."""

    id: str = Field(..., description="Unique identifier for the agent")
    name: str = Field(..., description="Display name of the agent")
    instructions: str = Field(default="", description="System prompt / instructions for the agent")
    model: str = Field(default="gpt-4.1", description="LLM model to use (gpt-4.1, gpt-5, gpt-5.2, gpt-5-nano, gpt-5-mini, gpt-5.4-mini)")
    temperature: float = Field(default=0.7, description="Sampling temperature (0 for max determinism on temperature-controllable models like gpt-4.1, gpt-5.4-mini; ignored by gpt-5 reasoning family unless reasoning_effort=='none')")
    reasoning_effort: str = Field(default="minimal", description="Reasoning effort for gpt-5 family: 'minimal'/'low'/'medium'/'high' enables reasoning (temperature ignored); 'none' disables reasoning and allows temperature/top_p control")
    topology_id: Optional[str] = Field(default=None, description="ID of the topology this agent belongs to")
    topology_role: Optional[str] = Field(default=None, description="Role within topology (Hub, Spoke, Manager, Worker)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration")

    @property
    def provider(self) -> ModelProvider:
        """All models use OpenAI provider."""
        return ModelProvider.OPENAI

    class Config:
        json_schema_extra = {
            "example": {
                "id": "agent-1",
                "name": "Research Agent",
                "instructions": "You are a research agent that gathers information on topics.",
                "model": "gpt-4.1",
                "topology_id": "topo-1",
                "topology_role": "Spoke",
            }
        }
