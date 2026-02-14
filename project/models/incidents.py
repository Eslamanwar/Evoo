"""Incident and system metrics data models."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from project.models.enums import IncidentSeverity, IncidentType


class SystemMetrics(BaseModel):
    """Measurable system metrics for a production service."""

    latency_ms: float = Field(default=50.0, description="Request latency in milliseconds")
    cpu_percent: float = Field(default=30.0, description="CPU utilization percentage")
    memory_percent: float = Field(default=40.0, description="Memory utilization percentage")
    error_rate: float = Field(default=0.01, description="Error rate (0.0 to 1.0)")
    availability: float = Field(default=0.999, description="Service availability (0.0 to 1.0)")
    recovery_time_seconds: float = Field(default=0.0, description="Time to recover in seconds")
    active_instances: int = Field(default=2, description="Number of active service instances")
    requests_per_second: float = Field(default=100.0, description="Current request throughput")
    timeout_ms: int = Field(default=5000, description="Current timeout configuration in ms")
    cache_hit_rate: float = Field(default=0.8, description="Cache hit rate (0.0 to 1.0)")

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return self.model_dump()

    def compute_health_score(self) -> float:
        """Compute an overall health score from 0.0 (worst) to 1.0 (best)."""
        latency_score = max(0.0, 1.0 - (self.latency_ms / 5000.0))
        cpu_score = max(0.0, 1.0 - (self.cpu_percent / 100.0))
        memory_score = max(0.0, 1.0 - (self.memory_percent / 100.0))
        error_score = max(0.0, 1.0 - self.error_rate)
        availability_score = self.availability

        return (
            latency_score * 0.25
            + cpu_score * 0.15
            + memory_score * 0.15
            + error_score * 0.25
            + availability_score * 0.20
        )


class Incident(BaseModel):
    """Represents a production incident."""

    id: str = Field(description="Unique incident identifier")
    incident_type: IncidentType = Field(description="Type of incident")
    severity: IncidentSeverity = Field(default=IncidentSeverity.MEDIUM, description="Incident severity")
    description: str = Field(default="", description="Human-readable incident description")
    service_name: str = Field(default="production-service", description="Affected service name")
    metrics_at_detection: Optional[SystemMetrics] = Field(default=None, description="System metrics when incident was detected")
    detected_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="ISO timestamp of detection")
    resolved: bool = Field(default=False, description="Whether the incident has been resolved")
    resolved_at: Optional[str] = Field(default=None, description="ISO timestamp of resolution")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional incident metadata")

    def to_dict(self) -> Dict[str, Any]:
        """Convert incident to dictionary."""
        data = self.model_dump()
        if self.metrics_at_detection:
            data["metrics_at_detection"] = self.metrics_at_detection.to_dict()
        return data