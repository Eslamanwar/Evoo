"""Experience data model for memory storage."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from project.models.enums import IncidentType


class Experience(BaseModel):
    """An experience tuple stored in memory after each remediation cycle."""

    id: str = Field(description="Unique experience identifier")
    incident_type: IncidentType = Field(description="Type of incident that occurred")
    incident_id: str = Field(description="ID of the incident")
    incident_severity: str = Field(default="medium", description="Severity of the incident")
    metrics_before: Dict[str, Any] = Field(
        default_factory=dict, description="System metrics before remediation"
    )
    strategy_used: str = Field(description="Name of the strategy that was applied")
    tools_called: List[str] = Field(
        default_factory=list, description="List of tool names that were called"
    )
    actions_taken: List[Dict[str, Any]] = Field(
        default_factory=list, description="Detailed actions taken during remediation"
    )
    metrics_after: Dict[str, Any] = Field(
        default_factory=dict, description="System metrics after remediation"
    )
    recovery_time_seconds: float = Field(
        default=0.0, description="Time taken to recover in seconds"
    )
    reward: float = Field(default=0.0, description="Reward score for this experience")
    reward_breakdown: Dict[str, float] = Field(
        default_factory=dict, description="Breakdown of reward components"
    )
    success: bool = Field(default=False, description="Whether remediation was successful")
    llm_evaluation: str = Field(
        default="", description="LLM-generated qualitative evaluation"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="ISO timestamp of the experience",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert experience to dictionary."""
        return self.model_dump()
