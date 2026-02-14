"""Simulated production system that generates incidents and responds to remediation."""

import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from project.models.enums import IncidentSeverity, IncidentType, RemediationActionType
from project.models.incidents import Incident, SystemMetrics


# Incident profiles define how each incident type affects system metrics
INCIDENT_PROFILES: Dict[IncidentType, Dict[str, Any]] = {
    IncidentType.SERVICE_CRASH: {
        "latency_ms": (5000, 30000),
        "cpu_percent": (10, 30),
        "memory_percent": (10, 30),
        "error_rate": (0.8, 1.0),
        "availability": (0.0, 0.2),
        "requests_per_second": (0, 10),
        "description": "Service has crashed and is not responding to requests",
        "severity_weights": {
            IncidentSeverity.CRITICAL: 0.6,
            IncidentSeverity.HIGH: 0.3,
            IncidentSeverity.MEDIUM: 0.1,
        },
    },
    IncidentType.HIGH_LATENCY: {
        "latency_ms": (2000, 10000),
        "cpu_percent": (60, 85),
        "memory_percent": (50, 70),
        "error_rate": (0.05, 0.3),
        "availability": (0.7, 0.95),
        "requests_per_second": (30, 60),
        "description": "Service experiencing abnormally high latency",
        "severity_weights": {
            IncidentSeverity.HIGH: 0.4,
            IncidentSeverity.MEDIUM: 0.5,
            IncidentSeverity.LOW: 0.1,
        },
    },
    IncidentType.CPU_SPIKE: {
        "latency_ms": (500, 3000),
        "cpu_percent": (90, 100),
        "memory_percent": (50, 70),
        "error_rate": (0.02, 0.15),
        "availability": (0.8, 0.95),
        "requests_per_second": (40, 70),
        "description": "CPU utilization has spiked to dangerous levels",
        "severity_weights": {
            IncidentSeverity.HIGH: 0.5,
            IncidentSeverity.MEDIUM: 0.4,
            IncidentSeverity.LOW: 0.1,
        },
    },
    IncidentType.MEMORY_LEAK: {
        "latency_ms": (300, 2000),
        "cpu_percent": (40, 60),
        "memory_percent": (85, 99),
        "error_rate": (0.03, 0.2),
        "availability": (0.75, 0.95),
        "requests_per_second": (50, 80),
        "description": "Memory usage is continuously increasing indicating a memory leak",
        "severity_weights": {
            IncidentSeverity.HIGH: 0.4,
            IncidentSeverity.MEDIUM: 0.5,
            IncidentSeverity.LOW: 0.1,
        },
    },
    IncidentType.NETWORK_DEGRADATION: {
        "latency_ms": (1000, 8000),
        "cpu_percent": (30, 50),
        "memory_percent": (40, 60),
        "error_rate": (0.1, 0.4),
        "availability": (0.6, 0.85),
        "requests_per_second": (20, 50),
        "description": "Network connectivity is degraded causing packet loss and timeouts",
        "severity_weights": {
            IncidentSeverity.HIGH: 0.3,
            IncidentSeverity.MEDIUM: 0.5,
            IncidentSeverity.LOW: 0.2,
        },
    },
    IncidentType.TIMEOUT_MISCONFIGURATION: {
        "latency_ms": (3000, 15000),
        "cpu_percent": (30, 50),
        "memory_percent": (40, 55),
        "error_rate": (0.2, 0.6),
        "availability": (0.5, 0.8),
        "requests_per_second": (20, 40),
        "description": "Timeout settings are misconfigured causing cascading failures",
        "severity_weights": {
            IncidentSeverity.MEDIUM: 0.6,
            IncidentSeverity.HIGH: 0.3,
            IncidentSeverity.LOW: 0.1,
        },
    },
}

# Remediation effectiveness profiles: how well each action works for each incident type
# Values are (effectiveness_probability, recovery_factor) where recovery_factor
# determines how much metrics improve (1.0 = full recovery)
REMEDIATION_EFFECTIVENESS: Dict[IncidentType, Dict[RemediationActionType, Tuple[float, float]]] = {
    IncidentType.SERVICE_CRASH: {
        RemediationActionType.RESTART_SERVICE: (0.85, 0.9),
        RemediationActionType.ROLLBACK_DEPLOYMENT: (0.75, 0.85),
        RemediationActionType.SCALE_HORIZONTAL: (0.4, 0.5),
        RemediationActionType.SCALE_VERTICAL: (0.3, 0.4),
        RemediationActionType.CLEAR_CACHE: (0.2, 0.3),
        RemediationActionType.REBALANCE_LOAD: (0.3, 0.4),
        RemediationActionType.CHANGE_TIMEOUT: (0.1, 0.1),
    },
    IncidentType.HIGH_LATENCY: {
        RemediationActionType.SCALE_HORIZONTAL: (0.8, 0.85),
        RemediationActionType.CLEAR_CACHE: (0.7, 0.75),
        RemediationActionType.REBALANCE_LOAD: (0.75, 0.8),
        RemediationActionType.SCALE_VERTICAL: (0.65, 0.7),
        RemediationActionType.RESTART_SERVICE: (0.5, 0.6),
        RemediationActionType.CHANGE_TIMEOUT: (0.4, 0.5),
        RemediationActionType.ROLLBACK_DEPLOYMENT: (0.3, 0.4),
    },
    IncidentType.CPU_SPIKE: {
        RemediationActionType.SCALE_VERTICAL: (0.85, 0.9),
        RemediationActionType.SCALE_HORIZONTAL: (0.8, 0.85),
        RemediationActionType.RESTART_SERVICE: (0.6, 0.65),
        RemediationActionType.REBALANCE_LOAD: (0.55, 0.6),
        RemediationActionType.ROLLBACK_DEPLOYMENT: (0.4, 0.5),
        RemediationActionType.CLEAR_CACHE: (0.3, 0.35),
        RemediationActionType.CHANGE_TIMEOUT: (0.1, 0.15),
    },
    IncidentType.MEMORY_LEAK: {
        RemediationActionType.RESTART_SERVICE: (0.9, 0.95),
        RemediationActionType.SCALE_VERTICAL: (0.6, 0.65),
        RemediationActionType.ROLLBACK_DEPLOYMENT: (0.7, 0.8),
        RemediationActionType.CLEAR_CACHE: (0.5, 0.55),
        RemediationActionType.SCALE_HORIZONTAL: (0.4, 0.45),
        RemediationActionType.REBALANCE_LOAD: (0.2, 0.25),
        RemediationActionType.CHANGE_TIMEOUT: (0.05, 0.1),
    },
    IncidentType.NETWORK_DEGRADATION: {
        RemediationActionType.REBALANCE_LOAD: (0.8, 0.85),
        RemediationActionType.SCALE_HORIZONTAL: (0.6, 0.65),
        RemediationActionType.CHANGE_TIMEOUT: (0.55, 0.6),
        RemediationActionType.RESTART_SERVICE: (0.4, 0.45),
        RemediationActionType.CLEAR_CACHE: (0.3, 0.35),
        RemediationActionType.SCALE_VERTICAL: (0.2, 0.25),
        RemediationActionType.ROLLBACK_DEPLOYMENT: (0.25, 0.3),
    },
    IncidentType.TIMEOUT_MISCONFIGURATION: {
        RemediationActionType.CHANGE_TIMEOUT: (0.9, 0.95),
        RemediationActionType.RESTART_SERVICE: (0.5, 0.55),
        RemediationActionType.ROLLBACK_DEPLOYMENT: (0.7, 0.75),
        RemediationActionType.REBALANCE_LOAD: (0.4, 0.45),
        RemediationActionType.CLEAR_CACHE: (0.2, 0.25),
        RemediationActionType.SCALE_HORIZONTAL: (0.3, 0.35),
        RemediationActionType.SCALE_VERTICAL: (0.15, 0.2),
    },
}

# Cost multipliers for each action type
ACTION_COSTS: Dict[RemediationActionType, float] = {
    RemediationActionType.RESTART_SERVICE: 0.1,
    RemediationActionType.SCALE_HORIZONTAL: 2.0,
    RemediationActionType.SCALE_VERTICAL: 1.5,
    RemediationActionType.CHANGE_TIMEOUT: 0.05,
    RemediationActionType.ROLLBACK_DEPLOYMENT: 0.5,
    RemediationActionType.CLEAR_CACHE: 0.1,
    RemediationActionType.REBALANCE_LOAD: 0.3,
}

# Baseline healthy metrics
HEALTHY_METRICS = SystemMetrics(
    latency_ms=50.0,
    cpu_percent=30.0,
    memory_percent=40.0,
    error_rate=0.01,
    availability=0.999,
    recovery_time_seconds=0.0,
    active_instances=2,
    requests_per_second=100.0,
    timeout_ms=5000,
    cache_hit_rate=0.8,
)


class ProductionSystem:
    """Simulated production system that generates incidents and responds to remediation actions."""

    def __init__(self):
        """Initialize the production system in a healthy state."""
        self.current_metrics = HEALTHY_METRICS.model_copy()
        self.current_incident: Optional[Incident] = None
        self.incident_history: List[Incident] = []
        self.action_log: List[Dict[str, Any]] = []
        self.total_cost: float = 0.0

    def get_current_metrics(self) -> SystemMetrics:
        """Get current system metrics."""
        return self.current_metrics.model_copy()

    def get_incident_state(self) -> Dict[str, Any]:
        """Get the current incident state."""
        if self.current_incident is None:
            return {
                "has_incident": False,
                "system_healthy": True,
                "metrics": self.current_metrics.to_dict(),
            }
        return {
            "has_incident": True,
            "system_healthy": False,
            "incident": self.current_incident.to_dict(),
            "metrics": self.current_metrics.to_dict(),
        }

    def generate_incident(self, incident_type: Optional[IncidentType] = None) -> Incident:
        """Generate a random or specified incident.

        Args:
            incident_type: Specific incident type to generate, or None for random.

        Returns:
            The generated Incident.
        """
        if incident_type is None:
            incident_type = random.choice(list(IncidentType))

        profile = INCIDENT_PROFILES[incident_type]

        # Determine severity based on weights
        severity_weights = profile["severity_weights"]
        severities = list(severity_weights.keys())
        weights = list(severity_weights.values())
        severity = random.choices(severities, weights=weights, k=1)[0]

        # Generate degraded metrics based on incident profile
        self.current_metrics = SystemMetrics(
            latency_ms=random.uniform(*profile["latency_ms"]),
            cpu_percent=random.uniform(*profile["cpu_percent"]),
            memory_percent=random.uniform(*profile["memory_percent"]),
            error_rate=random.uniform(*profile["error_rate"]),
            availability=random.uniform(*profile["availability"]),
            recovery_time_seconds=0.0,
            active_instances=max(1, HEALTHY_METRICS.active_instances - random.randint(0, 1)),
            requests_per_second=random.uniform(*profile["requests_per_second"]),
            timeout_ms=HEALTHY_METRICS.timeout_ms,
            cache_hit_rate=max(0.1, HEALTHY_METRICS.cache_hit_rate - random.uniform(0.1, 0.5)),
        )

        incident = Incident(
            id=f"INC-{uuid.uuid4().hex[:8].upper()}",
            incident_type=incident_type,
            severity=severity,
            description=profile["description"],
            service_name="production-service",
            metrics_at_detection=self.current_metrics.model_copy(),
            detected_at=datetime.utcnow().isoformat(),
        )

        self.current_incident = incident
        self.incident_history.append(incident)

        return incident

    def apply_remediation_action(
        self,
        action_type: RemediationActionType,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply a remediation action to the system and return the result.

        Args:
            action_type: The type of remediation action to apply.
            parameters: Optional parameters for the action.

        Returns:
            Dictionary with action result details.
        """
        if parameters is None:
            parameters = {}

        if self.current_incident is None:
            return {
                "success": False,
                "action": action_type.value,
                "message": "No active incident to remediate",
                "metrics": self.current_metrics.to_dict(),
                "cost": 0.0,
            }

        incident_type = self.current_incident.incident_type
        effectiveness_map = REMEDIATION_EFFECTIVENESS.get(incident_type, {})
        effectiveness = effectiveness_map.get(action_type, (0.1, 0.1))

        success_prob, recovery_factor = effectiveness

        # Add some randomness to make it realistic
        success_prob = min(1.0, success_prob + random.uniform(-0.1, 0.1))
        recovery_factor = min(1.0, recovery_factor + random.uniform(-0.1, 0.1))

        # Determine if action succeeds
        action_succeeded = random.random() < success_prob

        # Calculate cost
        base_cost = ACTION_COSTS.get(action_type, 0.5)
        action_cost = base_cost

        # Adjust cost based on parameters
        if action_type == RemediationActionType.SCALE_HORIZONTAL:
            target_instances = parameters.get("target_instances", 3)
            action_cost *= target_instances / 2.0
        elif action_type == RemediationActionType.SCALE_VERTICAL:
            target_cpu = parameters.get("target_cpu", 2.0)
            target_memory = parameters.get("target_memory", 4.0)
            action_cost *= (target_cpu + target_memory) / 4.0

        self.total_cost += action_cost

        # Apply the remediation effect
        if action_succeeded:
            self._apply_recovery(recovery_factor, action_type, parameters)
            message = f"Action {action_type.value} executed successfully"
        else:
            # Partial or no recovery
            partial_factor = recovery_factor * random.uniform(0.0, 0.3)
            self._apply_recovery(partial_factor, action_type, parameters)
            message = f"Action {action_type.value} had limited effect"

        # Simulate recovery time
        base_recovery_time = random.uniform(5, 30)
        if action_type == RemediationActionType.RESTART_SERVICE:
            base_recovery_time = random.uniform(10, 45)
        elif action_type == RemediationActionType.ROLLBACK_DEPLOYMENT:
            base_recovery_time = random.uniform(30, 90)
        elif action_type == RemediationActionType.SCALE_HORIZONTAL:
            base_recovery_time = random.uniform(20, 60)

        self.current_metrics.recovery_time_seconds += base_recovery_time

        result = {
            "success": action_succeeded,
            "action": action_type.value,
            "message": message,
            "metrics": self.current_metrics.to_dict(),
            "cost": action_cost,
            "recovery_time_added": base_recovery_time,
        }

        self.action_log.append(result)
        return result

    def _apply_recovery(
        self,
        recovery_factor: float,
        action_type: RemediationActionType,
        parameters: Dict[str, Any],
    ) -> None:
        """Apply recovery effects to system metrics.

        Args:
            recovery_factor: How much to recover (0.0 to 1.0).
            action_type: The action being applied.
            parameters: Action parameters.
        """
        healthy = HEALTHY_METRICS

        # Interpolate between current degraded metrics and healthy metrics
        self.current_metrics.latency_ms = self.current_metrics.latency_ms + (
            healthy.latency_ms - self.current_metrics.latency_ms
        ) * recovery_factor

        self.current_metrics.cpu_percent = self.current_metrics.cpu_percent + (
            healthy.cpu_percent - self.current_metrics.cpu_percent
        ) * recovery_factor

        self.current_metrics.memory_percent = self.current_metrics.memory_percent + (
            healthy.memory_percent - self.current_metrics.memory_percent
        ) * recovery_factor

        self.current_metrics.error_rate = self.current_metrics.error_rate + (
            healthy.error_rate - self.current_metrics.error_rate
        ) * recovery_factor

        self.current_metrics.availability = self.current_metrics.availability + (
            healthy.availability - self.current_metrics.availability
        ) * recovery_factor

        self.current_metrics.requests_per_second = self.current_metrics.requests_per_second + (
            healthy.requests_per_second - self.current_metrics.requests_per_second
        ) * recovery_factor

        self.current_metrics.cache_hit_rate = self.current_metrics.cache_hit_rate + (
            healthy.cache_hit_rate - self.current_metrics.cache_hit_rate
        ) * recovery_factor

        # Handle specific action effects
        if action_type == RemediationActionType.SCALE_HORIZONTAL:
            target = parameters.get("target_instances", 3)
            self.current_metrics.active_instances = max(
                self.current_metrics.active_instances, target
            )

        if action_type == RemediationActionType.CHANGE_TIMEOUT:
            new_timeout = parameters.get("new_timeout", 5000)
            self.current_metrics.timeout_ms = new_timeout

        if action_type == RemediationActionType.CLEAR_CACHE:
            # Cache clear temporarily reduces hit rate then improves
            self.current_metrics.cache_hit_rate = max(0.5, self.current_metrics.cache_hit_rate)

    def check_if_resolved(self) -> bool:
        """Check if the current incident is resolved based on metrics.

        Returns:
            True if the system has recovered to acceptable levels.
        """
        if self.current_incident is None:
            return True

        health_score = self.current_metrics.compute_health_score()
        is_resolved = health_score >= 0.7

        if is_resolved:
            self.current_incident.resolved = True
            self.current_incident.resolved_at = datetime.utcnow().isoformat()

        return is_resolved

    def reset_to_healthy(self) -> None:
        """Reset the system to a healthy state."""
        self.current_metrics = HEALTHY_METRICS.model_copy()
        self.current_incident = None
        self.action_log = []
        self.total_cost = 0.0

    def get_logs(self) -> List[Dict[str, Any]]:
        """Get the action log for the current incident."""
        return self.action_log.copy()

    def get_total_cost(self) -> float:
        """Get the total infrastructure cost incurred."""
        return self.total_cost