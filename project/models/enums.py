"""EVOO state and type enumerations."""

from enum import Enum


class EvooState(str, Enum):
    """States for the EVOO agent workflow."""

    IDLE = "IDLE"
    DETECTING_INCIDENT = "DETECTING_INCIDENT"
    PLANNING_REMEDIATION = "PLANNING_REMEDIATION"
    EXECUTING_REMEDIATION = "EXECUTING_REMEDIATION"
    EVALUATING_OUTCOME = "EVALUATING_OUTCOME"
    LEARNING = "LEARNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IncidentType(str, Enum):
    """Types of production incidents."""

    SERVICE_CRASH = "service_crash"
    HIGH_LATENCY = "high_latency"
    CPU_SPIKE = "cpu_spike"
    MEMORY_LEAK = "memory_leak"
    NETWORK_DEGRADATION = "network_degradation"
    TIMEOUT_MISCONFIGURATION = "timeout_misconfiguration"


class IncidentSeverity(str, Enum):
    """Severity levels for incidents."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RemediationActionType(str, Enum):
    """Types of remediation actions available."""

    RESTART_SERVICE = "restart_service"
    SCALE_HORIZONTAL = "scale_horizontal"
    SCALE_VERTICAL = "scale_vertical"
    CHANGE_TIMEOUT = "change_timeout"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    CLEAR_CACHE = "clear_cache"
    REBALANCE_LOAD = "rebalance_load"