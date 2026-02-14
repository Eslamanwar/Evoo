"""Experience and memory data models for EVOO learning loop.

This module defines:
- Experience tuples for storing remediation outcomes
- Strategy performance records
- Memory summaries for observability
- Learning statistics
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field

from project.models.incident import IncidentType, RemediationStrategy, SystemMetrics


class Experience(BaseModel):
    """A single remediation experience stored in memory.

    This is the core unit of learning in EVOO. Each experience captures:
    - The incident context (type, metrics before)
    - The action taken (strategy, tools called)
    - The outcome (metrics after, recovery time)
    - The evaluation (reward, LLM assessment)
    """
    id: str = Field(default="", description="Unique experience identifier")

    # Incident context
    incident_type: IncidentType = Field(
        default=IncidentType.SERVICE_CRASH,
        description="Type of incident that was remediated"
    )
    incident_severity: str = Field(default="medium", description="Severity of the incident")
    metrics_before: SystemMetrics = Field(
        default_factory=SystemMetrics,
        description="System metrics before remediation"
    )

    # Action taken
    strategy_used: RemediationStrategy = Field(
        default=RemediationStrategy.RESTART_SERVICE,
        description="Remediation strategy that was applied"
    )
    tools_called: List[str] = Field(
        default_factory=list,
        description="List of tools executed as part of the strategy"
    )
    tool_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Results returned by each tool"
    )
    tool_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters passed to the tools"
    )

    # Outcome
    metrics_after: SystemMetrics = Field(
        default_factory=SystemMetrics,
        description="System metrics after remediation"
    )
    recovery_time_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Total time to recover in seconds"
    )
    service_restored: bool = Field(
        default=False,
        description="Whether the service was successfully restored"
    )
    infrastructure_cost: float = Field(
        default=1.0,
        ge=0.0,
        description="Relative infrastructure cost incurred"
    )

    # Evaluation
    reward: float = Field(
        default=0.0,
        description="Numeric reward score from reward function"
    )
    reward_breakdown: Dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown of reward components"
    )
    llm_evaluation: str = Field(
        default="",
        description="Qualitative evaluation from LLM judge"
    )
    llm_verdict: str = Field(
        default="unknown",
        description="LLM verdict: excellent, good, adequate, poor, failed"
    )
    llm_score: int = Field(
        default=0,
        ge=0,
        le=10,
        description="LLM score (0-10)"
    )

    # Metadata
    success: bool = Field(
        default=False,
        description="Whether remediation was considered successful"
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="When the experience was recorded"
    )
    run_index: int = Field(
        default=0,
        ge=0,
        description="Index of this run in the learning loop"
    )
    is_exploratory: bool = Field(
        default=False,
        description="Whether this was an exploratory action"
    )

    @computed_field
    @property
    def effectiveness(self) -> float:
        """Calculate effectiveness as a 0-1 score based on metrics improvement."""
        if self.metrics_before.availability <= 0:
            return 0.0

        avail_improvement = (
            self.metrics_after.availability - self.metrics_before.availability
        )
        error_improvement = (
            self.metrics_before.error_rate - self.metrics_after.error_rate
        )
        latency_improvement = (
            self.metrics_before.latency_ms - self.metrics_after.latency_ms
        ) / max(self.metrics_before.latency_ms, 1.0)

        # Weighted average
        score = (
            avail_improvement * 0.4
            + error_improvement * 0.3
            + latency_improvement * 0.3
        )
        return round(max(0.0, min(1.0, score + 0.5)), 3)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a summary suitable for logging/display."""
        return {
            "id": self.id,
            "incident_type": self.incident_type.value,
            "strategy": self.strategy_used.value if isinstance(self.strategy_used, RemediationStrategy) else str(self.strategy_used),
            "reward": round(self.reward, 2),
            "success": self.success,
            "recovery_time": round(self.recovery_time_seconds, 1),
            "llm_verdict": self.llm_verdict,
            "run_index": self.run_index,
        }

    class Config:
        json_schema_extra = {
            "example": {
                "id": "exp-abc123",
                "incident_type": "high_latency",
                "strategy_used": "scale_horizontal",
                "reward": 78.5,
                "success": True,
                "recovery_time_seconds": 24.3,
                "llm_verdict": "good",
            }
        }


class StrategyRecord(BaseModel):
    """Tracks performance of a strategy for a given incident type.

    This record is updated after each remediation attempt and is used
    by the strategy manager for epsilon-greedy selection.
    """
    incident_type: IncidentType = Field(
        default=IncidentType.SERVICE_CRASH,
        description="Incident type this record applies to"
    )
    strategy: RemediationStrategy = Field(
        default=RemediationStrategy.RESTART_SERVICE,
        description="The strategy being tracked"
    )

    # Usage statistics
    total_uses: int = Field(default=0, ge=0, description="Total times this strategy was used")
    total_reward: float = Field(default=0.0, description="Sum of all rewards received")
    success_count: int = Field(default=0, ge=0, description="Number of successful remediations")
    failure_count: int = Field(default=0, ge=0, description="Number of failed remediations")

    # Computed statistics
    average_reward: float = Field(default=0.0, description="Average reward per use")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Success rate (0-1)")
    average_recovery_time: float = Field(default=0.0, ge=0.0, description="Average recovery time")

    # Time tracking
    total_recovery_time: float = Field(default=0.0, ge=0.0, description="Sum of all recovery times")
    last_used: Optional[datetime] = Field(default=None, description="When last used")
    first_used: Optional[datetime] = Field(default=None, description="When first used")

    # Reward tracking for variance calculation
    rewards_history: List[float] = Field(
        default_factory=list,
        description="History of rewards (limited to last 20)"
    )

    def update(
        self,
        reward: float,
        success: bool,
        recovery_time: float = 0.0,
    ) -> None:
        """Update the record with a new experience."""
        now = datetime.utcnow()

        self.total_uses += 1
        self.total_reward += reward
        self.total_recovery_time += recovery_time

        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Update computed stats
        self.average_reward = round(self.total_reward / self.total_uses, 3)
        self.success_rate = round(self.success_count / self.total_uses, 3)
        self.average_recovery_time = round(
            self.total_recovery_time / self.total_uses, 1
        )

        # Track reward history (keep last 20)
        self.rewards_history.append(reward)
        if len(self.rewards_history) > 20:
            self.rewards_history = self.rewards_history[-20:]

        # Update timestamps
        self.last_used = now
        if self.first_used is None:
            self.first_used = now

    @computed_field
    @property
    def reward_variance(self) -> float:
        """Calculate variance in recent rewards."""
        if len(self.rewards_history) < 2:
            return 0.0
        mean = sum(self.rewards_history) / len(self.rewards_history)
        variance = sum((r - mean) ** 2 for r in self.rewards_history) / len(self.rewards_history)
        return round(variance, 2)

    @computed_field
    @property
    def confidence_score(self) -> float:
        """Calculate confidence in this strategy (higher = more data, more consistent)."""
        if self.total_uses == 0:
            return 0.0

        # More uses = higher confidence (up to 20 uses)
        usage_confidence = min(1.0, self.total_uses / 20.0)

        # Lower variance = higher confidence
        variance_penalty = min(1.0, self.reward_variance / 500.0)  # 500 is high variance

        # Success rate contributes to confidence
        success_confidence = self.success_rate

        score = (
            usage_confidence * 0.4
            + (1.0 - variance_penalty) * 0.3
            + success_confidence * 0.3
        )
        return round(score, 3)

    def to_ranking_dict(self) -> Dict[str, Any]:
        """Return a dict suitable for ranking display."""
        return {
            "strategy": self.strategy.value if isinstance(self.strategy, RemediationStrategy) else str(self.strategy),
            "avg_reward": self.average_reward,
            "success_rate": self.success_rate,
            "total_uses": self.total_uses,
            "avg_recovery_time": self.average_recovery_time,
            "confidence": self.confidence_score,
        }


class MemorySummary(BaseModel):
    """Summary of agent's memory and learning progress.

    Used for observability and reporting.
    """
    # Overall statistics
    total_experiences: int = Field(default=0, ge=0, description="Total experiences stored")
    total_runs: int = Field(default=0, ge=0, description="Total learning runs completed")

    # Reward statistics
    average_reward: float = Field(default=0.0, description="Average reward across all runs")
    best_reward: float = Field(default=0.0, description="Best reward achieved")
    worst_reward: float = Field(default=0.0, description="Worst reward received")
    reward_std_dev: float = Field(default=0.0, description="Standard deviation of rewards")

    # Recovery statistics
    average_recovery_time: float = Field(default=0.0, description="Average recovery time in seconds")
    best_recovery_time: float = Field(default=float("inf"), description="Best (lowest) recovery time")
    worst_recovery_time: float = Field(default=0.0, description="Worst (highest) recovery time")

    # Success statistics
    overall_success_rate: float = Field(default=0.0, description="Overall success rate")
    success_count: int = Field(default=0, description="Total successful remediations")
    failure_count: int = Field(default=0, description="Total failed remediations")

    # Strategy rankings per incident type
    strategy_rankings: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Top strategies ranked by average reward per incident type"
    )

    # Learning trend
    improvement_trend: List[float] = Field(
        default_factory=list,
        description="Recent rewards for trend analysis"
    )
    early_average: float = Field(default=0.0, description="Average of first N rewards")
    recent_average: float = Field(default=0.0, description="Average of last N rewards")
    improvement_delta: float = Field(default=0.0, description="Difference: recent - early")

    # Incident type breakdown
    incidents_by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of incidents handled per type"
    )
    success_by_type: Dict[str, float] = Field(
        default_factory=dict,
        description="Success rate per incident type"
    )

    @computed_field
    @property
    def is_improving(self) -> bool:
        """Check if the agent is showing improvement."""
        return self.improvement_delta > 0

    @computed_field
    @property
    def learning_status(self) -> str:
        """Human-readable learning status."""
        if self.total_runs < 5:
            return "warming_up"
        if self.improvement_delta > 10:
            return "rapidly_improving"
        if self.improvement_delta > 0:
            return "improving"
        if self.improvement_delta > -5:
            return "stable"
        return "needs_adjustment"

    def to_report(self) -> str:
        """Generate a human-readable report."""
        lines = [
            f"📊 EVOO Memory Summary",
            f"├─ Total Runs: {self.total_runs}",
            f"├─ Success Rate: {self.overall_success_rate:.1%}",
            f"├─ Avg Reward: {self.average_reward:.2f} (best: {self.best_reward:.2f})",
            f"├─ Avg Recovery: {self.average_recovery_time:.1f}s (best: {self.best_recovery_time:.1f}s)",
            f"├─ Learning Status: {self.learning_status}",
            f"└─ Improvement: {self.improvement_delta:+.2f}",
        ]
        return "\n".join(lines)


class LearningMetrics(BaseModel):
    """Metrics for tracking learning progress over time.

    Used for detailed observability and debugging.
    """
    # Run tracking
    current_run: int = Field(default=0, description="Current run index")
    max_runs: int = Field(default=50, description="Maximum planned runs")

    # Rolling averages
