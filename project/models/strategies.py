"""Remediation strategy data models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from project.models.enums import IncidentType, RemediationActionType


class RemediationAction(BaseModel):
    """A single remediation action to execute."""

    action_type: RemediationActionType = Field(description="Type of remediation action")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    description: str = Field(default="", description="Human-readable description of the action")
    order: int = Field(default=0, description="Execution order within a strategy")

    def to_dict(self) -> Dict[str, Any]:
        """Convert action to dictionary."""
        return self.model_dump()


class RemediationStrategy(BaseModel):
    """A complete remediation strategy consisting of ordered actions."""

    name: str = Field(description="Strategy name")
    description: str = Field(default="", description="Strategy description")
    target_incident_types: List[IncidentType] = Field(
        default_factory=list, description="Incident types this strategy addresses"
    )
    actions: List[RemediationAction] = Field(
        default_factory=list, description="Ordered list of remediation actions"
    )
    estimated_recovery_time_seconds: float = Field(
        default=60.0, description="Estimated time to recover in seconds"
    )
    estimated_cost: float = Field(
        default=1.0, description="Estimated infrastructure cost impact (1.0 = baseline)"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy to dictionary."""
        data = self.model_dump()
        data["actions"] = [a.to_dict() for a in self.actions]
        return data


class StrategyRecord(BaseModel):
    """Historical record of a strategy's performance."""

    strategy_name: str = Field(description="Name of the strategy")
    incident_type: IncidentType = Field(description="Incident type this record applies to")
    total_uses: int = Field(default=0, description="Total number of times this strategy was used")
    total_successes: int = Field(default=0, description="Total successful remediations")
    total_failures: int = Field(default=0, description="Total failed remediations")
    total_reward: float = Field(default=0.0, description="Cumulative reward score")
    average_reward: float = Field(default=0.0, description="Average reward per use")
    average_recovery_time: float = Field(default=0.0, description="Average recovery time in seconds")
    success_rate: float = Field(default=0.0, description="Success rate (0.0 to 1.0)")
    last_used: Optional[str] = Field(default=None, description="ISO timestamp of last use")

    def update_with_result(self, reward: float, recovery_time: float, success: bool) -> None:
        """Update the record with a new result."""
        self.total_uses += 1
        self.total_reward += reward

        if success:
            self.total_successes += 1
        else:
            self.total_failures += 1

        self.average_reward = self.total_reward / self.total_uses
        self.success_rate = self.total_successes / self.total_uses
        self.average_recovery_time = (
            (self.average_recovery_time * (self.total_uses - 1) + recovery_time) / self.total_uses
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return self.model_dump()