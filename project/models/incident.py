"""Incident and metrics data models for EVOO.

This module defines the core data structures for:
- Incident types and their characteristics
- System metrics (before/after remediation)
- Remediation strategies
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IncidentType(str, Enum):
    """Supported production incident types."""
    SERVICE_CRASH = "service_crash"
    HIGH_LATENCY = "high_latency"
    CPU_SPIKE = "cpu_spike"
    MEMORY_LEAK = "memory_leak"
    NETWORK_DEGRADATION = "network_degradation"
    TIMEOUT_MISCONFIGURATION = "timeout_misconfiguration"

    @classmethod
    def all_types(cls) -> List["IncidentType"]:
        """Return all incident types."""
        return list(cls)

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self.value.replace("_", " ").title()


class IncidentSeverity(str, Enum):
    """Incident severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def priority_weight(self) -> float:
        """Higher weight = more urgent."""
        weights = {
            "low": 0.25,
            "medium": 0.5,
            "high": 0.75,
            "critical": 1.0,
        }
        return weights.get(self.value, 0.5)


class RemediationStrategy(str, Enum):
    """Available remediation strategies."""
    # Single-action strategies
    RESTART_SERVICE = "restart_service"
    SCALE_HORIZONTAL = "scale_horizontal"
    SCALE_VERTICAL = "scale_vertical"
    CHANGE_TIMEOUT = "change_timeout"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    CLEAR_CACHE = "clear_cache"
    REBALANCE_LOAD = "rebalance_load"

    # Combined strategies (multiple actions)
    COMBINED_RESTART_SCALE = "combined_restart_scale"
    COMBINED_CACHE_REBALANCE = "combined_cache_rebalance"
    COMBINED_ROLLBACK_SCALE = "combined_rollback_scale"

    @classmethod
    def all_strategies(cls) -> List["RemediationStrategy"]:
        """Return all available strategies."""
        return list(cls)

    @classmethod
    def single_action_strategies(cls) -> List["RemediationStrategy"]:
        """Return strategies that involve a single action."""
        return [
            cls.RESTART_SERVICE,
            cls.SCALE_HORIZONTAL,
            cls.SCALE_VERTICAL,
            cls.CHANGE_TIMEOUT,
            cls.ROLLBACK_DEPLOYMENT,
            cls.CLEAR_CACHE,
            cls.REBALANCE_LOAD,
        ]

    @classmethod
    def combined_strategies(cls) -> List["RemediationStrategy"]:
        """Return strategies that combine multiple actions."""
        return [
            cls.COMBINED_RESTART_SCALE,
            cls.COMBINED_CACHE_REBALANCE,
            cls.COMBINED_ROLLBACK_SCALE,
        ]

    @property
    def estimated_cost(self) -> float:
        """Relative infrastructure cost of the strategy."""
        cost_map = {
            "restart_service": 1.0,
            "scale_horizontal": 2.5,
            "scale_vertical": 2.0,
            "change_timeout": 0.5,
            "rollback_deployment": 1.5,
            "clear_cache": 0.3,
            "rebalance_load": 0.8,
            "combined_restart_scale": 3.0,
            "combined_cache_rebalance": 1.2,
            "combined_rollback_scale": 3.5,
        }
        return cost_map.get(self.value, 1.0)

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self.value.replace("_", " ").title()


class SystemMetrics(BaseModel):
    """Measurable system metrics at a point in time.

    These metrics are used to:
    1. Characterize the incident state
    2. Measure remediation effectiveness
    3. Calculate reward scores
    """
    # Performance metrics
    latency_ms: float = Field(default=0.0, description="P99 latency in milliseconds")
    cpu_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="CPU utilization percentage")
    memory_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Memory utilization percentage")

    # Reliability metrics
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Error rate (0.0-1.0)")
    availability: float = Field(default=1.0, ge=0.0, le=1.0, description="Service availability (0.0-1.0)")

    # Recovery metrics
    recovery_time_seconds: float = Field(default=0.0, ge=0.0, description="Time to recover in seconds")

    # Infrastructure metrics
    active_instances: int = Field(default=1, ge=1, description="Number of active service instances")
    timeout_ms: int = Field(default=30000, ge=1000, description="Current timeout configuration in ms")

    # Metadata
    timestamp: Optional[datetime] = Field(default=None, description="When metrics were collected")

    def is_healthy(self) -> bool:
        """Check if metrics indicate a healthy system."""
        return (
            self.availability >= 0.95
            and self.error_rate <= 0.05
            and self.latency_ms < 500
            and self.cpu_percent < 80
            and self.memory_percent < 85
        )

    def severity_score(self) -> float:
        """Calculate a severity score (0.0-1.0) based on metrics."""
        scores = []

        # Availability (inverted: lower availability = higher severity)
        scores.append(1.0 - self.availability)

        # Error rate
        scores.append(self.error_rate)

        # Latency (normalized to 0-1, assuming 10000ms is critical)
        scores.append(min(1.0, self.latency_ms / 10000.0))

        # CPU (above 80% is concerning)
        if self.cpu_percent > 80:
            scores.append((self.cpu_percent - 80) / 20)
        else:
            scores.append(0.0)

        # Memory (above 85% is concerning)
        if self.memory_percent > 85:
            scores.append((self.memory_percent - 85) / 15)
        else:
            scores.append(0.0)

        return round(sum(scores) / len(scores), 3)

    def improvement_from(self, before: "SystemMetrics") -> Dict[str, float]:
        """Calculate improvement metrics compared to a previous state."""
        return {
            "latency_improvement": before.latency_ms - self.latency_ms,
            "cpu_improvement": before.cpu_percent - self.cpu_percent,
            "memory_improvement": before.memory_percent - self.memory_percent,
            "error_rate_improvement": before.error_rate - self.error_rate,
            "availability_improvement": self.availability - before.availability,
        }

    class Config:
        json_schema_extra = {
            "example": {
                "latency_ms": 2500.0,
                "cpu_percent": 75.5,
                "memory_percent": 68.2,
                "error_rate": 0.15,
                "availability": 0.85,
                "recovery_time_seconds": 45.0,
                "active_instances": 2,
                "timeout_ms": 30000,
            }
        }


class Incident(BaseModel):
    """Represents a detected production incident.

    An incident captures:
    - What type of problem occurred
    - The severity level
    - Which service is affected
    - The metrics at time of detection
    - A human-readable description
    """
    id: str = Field(default="", description="Unique incident identifier")
    incident_type: IncidentType = Field(
        default=IncidentType.SERVICE_CRASH,
        description="Classification of the incident"
    )
    severity: str = Field(default="medium", description="Severity: low, medium, high, critical")
    affected_service: str = Field(default="api-service", description="Name of the affected service")
    metrics_at_detection: SystemMetrics = Field(
        default_factory=SystemMetrics,
        description="System metrics when incident was detected"
    )
    detected_at: Optional[datetime] = Field(default=None, description="When the incident was detected")
    description: str = Field(default="", description="Human-readable incident description")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Additional raw incident data")

    def to_summary(self) -> str:
        """Generate a brief summary of the incident."""
        metrics = self.metrics_at_detection
        return (
            f"[{self.severity.upper()}] {self.incident_type.value}: "
            f"latency={metrics.latency_ms:.0f}ms, "
            f"error_rate={metrics.error_rate:.1%}, "
            f"availability={metrics.availability:.1%}"
        )

    def suggested_strategies(self) -> List[RemediationStrategy]:
        """Return suggested strategies based on incident type."""
        suggestions = {
            IncidentType.SERVICE_CRASH: [
                RemediationStrategy.RESTART_SERVICE,
                RemediationStrategy.ROLLBACK_DEPLOYMENT,
                RemediationStrategy.COMBINED_RESTART_SCALE,
            ],
            IncidentType.HIGH_LATENCY: [
                RemediationStrategy.SCALE_HORIZONTAL,
                RemediationStrategy.REBALANCE_LOAD,
                RemediationStrategy.CLEAR_CACHE,
            ],
            IncidentType.CPU_SPIKE: [
                RemediationStrategy.SCALE_VERTICAL,
                RemediationStrategy.SCALE_HORIZONTAL,
                RemediationStrategy.RESTART_SERVICE,
            ],
            IncidentType.MEMORY_LEAK: [
                RemediationStrategy.RESTART_SERVICE,
                RemediationStrategy.CLEAR_CACHE,
                RemediationStrategy.COMBINED_CACHE_REBALANCE,
            ],
            IncidentType.NETWORK_DEGRADATION: [
                RemediationStrategy.REBALANCE_LOAD,
                RemediationStrategy.SCALE_HORIZONTAL,
                RemediationStrategy.COMBINED_CACHE_REBALANCE,
            ],
            IncidentType.TIMEOUT_MISCONFIGURATION: [
                RemediationStrategy.CHANGE_TIMEOUT,
                RemediationStrategy.ROLLBACK_DEPLOYMENT,
                RemediationStrategy.COMBINED_ROLLBACK_SCALE,
            ],
        }
        return suggestions.get(self.incident_type, [RemediationStrategy.RESTART_SERVICE])

    class Config:
        json_schema_extra = {
            "example": {
                "id": "inc-abc123",
                "incident_type": "high_latency",
                "severity": "high",
                "affected_service": "api-service",
                "description": "P99 latency spiked to 5420ms. CPU at 72.3%.",
            }
        }


class IncidentProfile(BaseModel):
    """Profile defining characteristics of an incident type.

    Used by the simulator to generate realistic incidents.
    """
    incident_type: IncidentType
    latency_range: tuple = Field(default=(100, 500))
    cpu_range: tuple = Field(default=(20, 50))
    memory_range: tuple = Field(default=(30, 60))
    error_rate_range: tuple = Field(default=(0.0, 0.05))
    availability_range: tuple = Field(default=(0.95, 1.0))
    severity_weights: Dict[str, float] = Field(default_factory=dict)
    description_template: str = ""


class RemediationEffect(BaseModel):
    """Defines how a remediation strategy affects a specific incident type.

    Used by the simulator to model realistic remediation outcomes.
    """
    strategy: RemediationStrategy
    incident_type: IncidentType
    effectiveness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How effective this strategy is for this incident (0.0-1.0)"
    )
    recovery_time_range: tuple = Field(
        default=(30, 90),
        description="Expected recovery time range in seconds (min, max)"
    )
    side_effects: Dict[str, float] = Field(
        default_factory=dict,
        description="Potential side effects (e.g., temporary latency spike)"
    )
