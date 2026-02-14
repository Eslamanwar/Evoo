"""Simulated production system activities for EVOO.

This module implements a realistic production system simulator that:
- Generates random incidents with realistic metrics
- Responds to remediation actions with measurable state changes
- Simulates recovery dynamics over time

IMPORTANT: All activities accept a single dict argument because
ActivityHelpers.execute_activity passes request as arg=request (single arg).
"""
from __future__ import annotations

import random
import time
import uuid
from datetime import datetime
from typing import Any, Dict

from temporalio import activity

from agentex.lib.utils.logging import make_logger

from project.models.incident import (
    Incident,
    IncidentType,
    SystemMetrics,
)

logger = make_logger(__name__)

# ---------------------------------------------------------------------------
# Incident profiles: defines the metric signature of each incident type
# ---------------------------------------------------------------------------
INCIDENT_PROFILES: Dict[str, Dict[str, Any]] = {
    IncidentType.SERVICE_CRASH: {
        "latency_ms": (5000, 15000),
        "cpu_percent": (5, 30),
        "memory_percent": (10, 40),
        "error_rate": (0.8, 1.0),
        "availability": (0.0, 0.2),
        "severity_weights": {"critical": 0.7, "high": 0.3},
    },
    IncidentType.HIGH_LATENCY: {
        "latency_ms": (2000, 8000),
        "cpu_percent": (40, 70),
        "memory_percent": (50, 80),
        "error_rate": (0.1, 0.4),
        "availability": (0.6, 0.9),
        "severity_weights": {"high": 0.5, "medium": 0.5},
    },
    IncidentType.CPU_SPIKE: {
        "latency_ms": (500, 3000),
        "cpu_percent": (85, 99),
        "memory_percent": (40, 65),
        "error_rate": (0.05, 0.25),
        "availability": (0.7, 0.95),
        "severity_weights": {"high": 0.4, "medium": 0.6},
    },
    IncidentType.MEMORY_LEAK: {
        "latency_ms": (800, 4000),
        "cpu_percent": (30, 60),
        "memory_percent": (88, 99),
        "error_rate": (0.1, 0.5),
        "availability": (0.5, 0.85),
        "severity_weights": {"critical": 0.3, "high": 0.5, "medium": 0.2},
    },
    IncidentType.NETWORK_DEGRADATION: {
        "latency_ms": (1500, 6000),
        "cpu_percent": (20, 50),
        "memory_percent": (30, 60),
        "error_rate": (0.2, 0.6),
        "availability": (0.4, 0.75),
        "severity_weights": {"high": 0.6, "medium": 0.4},
    },
    IncidentType.TIMEOUT_MISCONFIGURATION: {
        "latency_ms": (4000, 12000),
        "cpu_percent": (20, 45),
        "memory_percent": (25, 55),
        "error_rate": (0.3, 0.7),
        "availability": (0.3, 0.7),
        "severity_weights": {"high": 0.5, "medium": 0.5},
    },
}

# How each remediation strategy affects the system state
REMEDIATION_EFFECTS: Dict[str, Dict[str, Any]] = {
    "restart_service": {
        IncidentType.SERVICE_CRASH: {"effectiveness": 0.95, "recovery_time": (10, 30)},
        IncidentType.MEMORY_LEAK: {"effectiveness": 0.80, "recovery_time": (15, 45)},
        IncidentType.CPU_SPIKE: {"effectiveness": 0.50, "recovery_time": (20, 60)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.40, "recovery_time": (25, 70)},
        IncidentType.NETWORK_DEGRADATION: {"effectiveness": 0.20, "recovery_time": (40, 120)},
        IncidentType.TIMEOUT_MISCONFIGURATION: {"effectiveness": 0.10, "recovery_time": (60, 180)},
        "default": {"effectiveness": 0.30, "recovery_time": (30, 90)},
    },
    "scale_horizontal": {
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.85, "recovery_time": (20, 60)},
        IncidentType.CPU_SPIKE: {"effectiveness": 0.80, "recovery_time": (20, 50)},
        IncidentType.NETWORK_DEGRADATION: {"effectiveness": 0.65, "recovery_time": (25, 70)},
        IncidentType.SERVICE_CRASH: {"effectiveness": 0.50, "recovery_time": (15, 40)},
        IncidentType.MEMORY_LEAK: {"effectiveness": 0.30, "recovery_time": (30, 90)},
        IncidentType.TIMEOUT_MISCONFIGURATION: {"effectiveness": 0.20, "recovery_time": (40, 120)},
        "default": {"effectiveness": 0.40, "recovery_time": (30, 80)},
    },
    "scale_vertical": {
        IncidentType.CPU_SPIKE: {"effectiveness": 0.88, "recovery_time": (15, 45)},
        IncidentType.MEMORY_LEAK: {"effectiveness": 0.75, "recovery_time": (20, 60)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.60, "recovery_time": (20, 55)},
        "default": {"effectiveness": 0.35, "recovery_time": (30, 90)},
    },
    "change_timeout": {
        IncidentType.TIMEOUT_MISCONFIGURATION: {"effectiveness": 0.92, "recovery_time": (5, 20)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.45, "recovery_time": (10, 30)},
        "default": {"effectiveness": 0.15, "recovery_time": (20, 60)},
    },
    "rollback_deployment": {
        IncidentType.SERVICE_CRASH: {"effectiveness": 0.88, "recovery_time": (20, 60)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.70, "recovery_time": (20, 55)},
        IncidentType.CPU_SPIKE: {"effectiveness": 0.60, "recovery_time": (25, 65)},
        "default": {"effectiveness": 0.45, "recovery_time": (30, 80)},
    },
    "clear_cache": {
        IncidentType.MEMORY_LEAK: {"effectiveness": 0.70, "recovery_time": (5, 20)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.55, "recovery_time": (8, 25)},
        IncidentType.CPU_SPIKE: {"effectiveness": 0.40, "recovery_time": (10, 35)},
        "default": {"effectiveness": 0.25, "recovery_time": (10, 40)},
    },
    "rebalance_load": {
        IncidentType.NETWORK_DEGRADATION: {"effectiveness": 0.80, "recovery_time": (10, 35)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.65, "recovery_time": (12, 40)},
        IncidentType.CPU_SPIKE: {"effectiveness": 0.55, "recovery_time": (15, 45)},
        "default": {"effectiveness": 0.30, "recovery_time": (20, 60)},
    },
    "combined_restart_scale": {
        IncidentType.SERVICE_CRASH: {"effectiveness": 0.97, "recovery_time": (12, 35)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.88, "recovery_time": (18, 50)},
        IncidentType.CPU_SPIKE: {"effectiveness": 0.85, "recovery_time": (15, 45)},
        "default": {"effectiveness": 0.70, "recovery_time": (20, 55)},
    },
    "combined_cache_rebalance": {
        IncidentType.MEMORY_LEAK: {"effectiveness": 0.85, "recovery_time": (8, 25)},
        IncidentType.NETWORK_DEGRADATION: {"effectiveness": 0.82, "recovery_time": (10, 30)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.75, "recovery_time": (12, 38)},
        "default": {"effectiveness": 0.55, "recovery_time": (15, 50)},
    },
    "combined_rollback_scale": {
        IncidentType.SERVICE_CRASH: {"effectiveness": 0.93, "recovery_time": (18, 50)},
        IncidentType.HIGH_LATENCY: {"effectiveness": 0.87, "recovery_time": (18, 52)},
        "default": {"effectiveness": 0.65, "recovery_time": (25, 65)},
    },
}


def _sample_metric(range_tuple: tuple) -> float:
    lo, hi = range_tuple
    return round(random.uniform(lo, hi), 2)


def _pick_severity(weights: Dict[str, float]) -> str:
    labels = list(weights.keys())
    probs = list(weights.values())
    return random.choices(labels, weights=probs, k=1)[0]


@activity.defn(name="generate_incident_activity")
async def generate_incident_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a realistic simulated production incident."""
    run_index = params.get("run_index", 0)

    incident_types = list(IncidentType)
    incident_type = random.choice(incident_types)
    profile = INCIDENT_PROFILES[incident_type]

    metrics = SystemMetrics(
        latency_ms=_sample_metric(profile["latency_ms"]),
        cpu_percent=_sample_metric(profile["cpu_percent"]),
        memory_percent=_sample_metric(profile["memory_percent"]),
        error_rate=round(random.uniform(*profile["error_rate"]), 3),
        availability=round(random.uniform(*profile["availability"]), 3),
        active_instances=random.randint(1, 3),
        timeout_ms=random.choice([5000, 10000, 30000, 60000]),
        timestamp=datetime.utcnow(),
    )

    severity = _pick_severity(profile["severity_weights"])

    descriptions = {
        IncidentType.SERVICE_CRASH: f"Service api-service has crashed. Error rate at {metrics.error_rate:.0%}, availability {metrics.availability:.0%}.",
        IncidentType.HIGH_LATENCY: f"P99 latency spiked to {metrics.latency_ms:.0f}ms. CPU at {metrics.cpu_percent:.1f}%.",
        IncidentType.CPU_SPIKE: f"CPU usage hit {metrics.cpu_percent:.1f}%. Service is throttling requests.",
        IncidentType.MEMORY_LEAK: f"Memory usage at {metrics.memory_percent:.1f}%. OOMKiller risk imminent.",
        IncidentType.NETWORK_DEGRADATION: f"Network packet loss detected. Latency {metrics.latency_ms:.0f}ms, error rate {metrics.error_rate:.0%}.",
        IncidentType.TIMEOUT_MISCONFIGURATION: f"Client timeouts at {metrics.timeout_ms}ms causing cascading failures. Error rate {metrics.error_rate:.0%}.",
    }

    incident = Incident(
        id=str(uuid.uuid4())[:8],
        incident_type=incident_type,
        severity=severity,
        affected_service="api-service",
        metrics_at_detection=metrics,
        detected_at=datetime.utcnow(),
        description=descriptions[incident_type],
    )

    logger.info(f"[Run {run_index}] Generated incident: {incident_type.value} ({severity})")
    return incident.model_dump(mode="json")


@activity.defn(name="get_incident_state_activity")
async def get_incident_state_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query current system state and return metrics."""
    system_state = params.get("system_state", {})
    return {
        "status": "active_incident",
        "system_state": system_state,
        "queried_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="query_metrics_activity")
async def query_metrics_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return current system metrics from the simulated system."""
    system_state = params.get("system_state", {})
    incident_data = system_state.get("current_incident", {})
    metrics_data = incident_data.get("metrics_at_detection", {})

    return {
        "metrics": metrics_data,
        "service": system_state.get("service_name", "api-service"),
        "healthy": system_state.get("is_healthy", False),
        "timestamp": datetime.utcnow().isoformat(),
    }


@activity.defn(name="apply_remediation_to_simulation_activity")
async def apply_remediation_to_simulation_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a remediation strategy to the simulated system and compute resulting metrics.
    This is the core simulation function that produces measurable outcomes.
    """
    system_state = params.get("system_state", {})
    strategy_name = params.get("strategy_name", "restart_service")
    tool_parameters = params.get("tool_parameters", {})

    incident_data = system_state.get("current_incident", {})
    incident_type_str = incident_data.get("incident_type", "service_crash")
    metrics_before_data = incident_data.get("metrics_at_detection", {})

    before = SystemMetrics(**metrics_before_data) if metrics_before_data else SystemMetrics()

    # Look up effectiveness for this strategy + incident combination
    strategy_effects = REMEDIATION_EFFECTS.get(strategy_name, {})
    effect = strategy_effects.get(
        incident_type_str,
        strategy_effects.get("default", {"effectiveness": 0.20, "recovery_time": (30, 120)}),
    )

    effectiveness = effect["effectiveness"]
    noise = random.gauss(0, 0.08)
    effectiveness = max(0.0, min(1.0, effectiveness + noise))

    recovery_low, recovery_high = effect["recovery_time"]
    recovery_time = round(random.uniform(recovery_low, recovery_high), 1)

    baseline_latency = 120.0
    baseline_cpu = 25.0
    baseline_memory = 45.0
    baseline_error_rate = 0.005
    baseline_availability = 0.999

    def lerp(bad_val: float, good_val: float, eff: float) -> float:
        return bad_val + (good_val - bad_val) * eff

    after = SystemMetrics(
        latency_ms=round(lerp(before.latency_ms, baseline_latency, effectiveness), 1),
        cpu_percent=round(lerp(before.cpu_percent, baseline_cpu, effectiveness), 1),
        memory_percent=round(lerp(before.memory_percent, baseline_memory, effectiveness), 1),
        error_rate=round(lerp(before.error_rate, baseline_error_rate, effectiveness), 4),
        availability=round(lerp(before.availability, baseline_availability, effectiveness), 4),
        active_instances=tool_parameters.get("target_instances", before.active_instances),
        timeout_ms=tool_parameters.get("new_timeout", before.timeout_ms),
        recovery_time_seconds=recovery_time,
        timestamp=datetime.utcnow(),
    )

    service_restored = after.availability >= 0.95 and after.error_rate <= 0.05
    logger.info(
        f"Remediation simulation: strategy={strategy_name} "
        f"effectiveness={effectiveness:.2f} recovery={recovery_time}s "
        f"restored={service_restored}"
    )

    return {
        "metrics_after": after.model_dump(mode="json"),
        "recovery_time_seconds": recovery_time,
        "service_restored": service_restored,
        "effectiveness": effectiveness,
        "infrastructure_cost": _compute_infra_cost(after, tool_parameters),
    }


def _compute_infra_cost(metrics: SystemMetrics, params: Dict[str, Any]) -> float:
    """Estimate relative infrastructure cost change from remediation."""
    base_cost = 1.0
    instances = params.get("target_instances", metrics.active_instances)
    if instances > 3:
        base_cost += (instances - 3) * 0.5
    cpu_cores = params.get("target_cpu", 1)
    if cpu_cores > 2:
        base_cost += (cpu_cores - 2) * 0.3
    return round(base_cost, 2)
