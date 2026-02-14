"""Predefined remediation strategy catalog for EVOO."""

from typing import Dict, List

from project.models.enums import IncidentType, RemediationActionType
from project.models.strategies import RemediationAction, RemediationStrategy


def _build_strategy(
    name: str,
    description: str,
    target_types: List[IncidentType],
    actions: List[tuple],
    est_recovery: float = 60.0,
    est_cost: float = 1.0,
) -> RemediationStrategy:
    """Helper to build a RemediationStrategy."""
    return RemediationStrategy(
        name=name,
        description=description,
        target_incident_types=target_types,
        actions=[
            RemediationAction(
                action_type=action_type,
                parameters=params,
                description=desc,
                order=i,
            )
            for i, (action_type, params, desc) in enumerate(actions)
        ],
        estimated_recovery_time_seconds=est_recovery,
        estimated_cost=est_cost,
    )


# ─── Strategy Catalog ───────────────────────────────────────────────────────

STRATEGY_CATALOG: Dict[str, RemediationStrategy] = {
    # ── Service Crash Strategies ──
    "restart_and_verify": _build_strategy(
        name="restart_and_verify",
        description="Restart the crashed service and verify recovery",
        target_types=[IncidentType.SERVICE_CRASH],
        actions=[
            (RemediationActionType.RESTART_SERVICE, {}, "Restart the crashed service"),
        ],
        est_recovery=30.0,
        est_cost=0.1,
    ),
    "rollback_and_restart": _build_strategy(
        name="rollback_and_restart",
        description="Rollback to previous deployment then restart",
        target_types=[IncidentType.SERVICE_CRASH],
        actions=[
            (RemediationActionType.ROLLBACK_DEPLOYMENT, {}, "Rollback to last known good deployment"),
            (RemediationActionType.RESTART_SERVICE, {}, "Restart service after rollback"),
        ],
        est_recovery=90.0,
        est_cost=0.6,
    ),
    "scale_and_restart": _build_strategy(
        name="scale_and_restart",
        description="Scale up instances then restart the failed one",
        target_types=[IncidentType.SERVICE_CRASH],
        actions=[
            (RemediationActionType.SCALE_HORIZONTAL, {"target_instances": 3}, "Add more instances for redundancy"),
            (RemediationActionType.RESTART_SERVICE, {}, "Restart the crashed instance"),
        ],
        est_recovery=60.0,
        est_cost=2.1,
    ),

    # ── High Latency Strategies ──
    "scale_out_for_latency": _build_strategy(
        name="scale_out_for_latency",
        description="Scale horizontally to distribute load and reduce latency",
        target_types=[IncidentType.HIGH_LATENCY],
        actions=[
            (RemediationActionType.SCALE_HORIZONTAL, {"target_instances": 4}, "Scale out to 4 instances"),
            (RemediationActionType.REBALANCE_LOAD, {}, "Rebalance traffic across instances"),
        ],
        est_recovery=45.0,
        est_cost=2.3,
    ),
    "cache_and_rebalance": _build_strategy(
        name="cache_and_rebalance",
        description="Clear cache and rebalance load to reduce latency",
        target_types=[IncidentType.HIGH_LATENCY],
        actions=[
            (RemediationActionType.CLEAR_CACHE, {}, "Clear stale cache entries"),
            (RemediationActionType.REBALANCE_LOAD, {}, "Rebalance traffic distribution"),
        ],
        est_recovery=30.0,
        est_cost=0.4,
    ),
    "vertical_scale_for_latency": _build_strategy(
        name="vertical_scale_for_latency",
        description="Scale up instance resources to handle load",
        target_types=[IncidentType.HIGH_LATENCY],
        actions=[
            (RemediationActionType.SCALE_VERTICAL, {"target_cpu": 4.0, "target_memory": 8.0}, "Increase CPU and memory"),
        ],
        est_recovery=40.0,
        est_cost=1.5,
    ),

    # ── CPU Spike Strategies ──
    "vertical_scale_cpu": _build_strategy(
        name="vertical_scale_cpu",
        description="Scale up CPU resources to handle spike",
        target_types=[IncidentType.CPU_SPIKE],
        actions=[
            (RemediationActionType.SCALE_VERTICAL, {"target_cpu": 4.0, "target_memory": 4.0}, "Increase CPU allocation"),
        ],
        est_recovery=35.0,
        est_cost=1.5,
    ),
    "horizontal_scale_cpu": _build_strategy(
        name="horizontal_scale_cpu",
        description="Scale out to distribute CPU load",
        target_types=[IncidentType.CPU_SPIKE],
        actions=[
            (RemediationActionType.SCALE_HORIZONTAL, {"target_instances": 4}, "Add instances to distribute load"),
            (RemediationActionType.REBALANCE_LOAD, {}, "Rebalance traffic"),
        ],
        est_recovery=50.0,
        est_cost=2.3,
    ),
    "restart_for_cpu": _build_strategy(
        name="restart_for_cpu",
        description="Restart service to clear runaway processes",
        target_types=[IncidentType.CPU_SPIKE],
        actions=[
            (RemediationActionType.RESTART_SERVICE, {}, "Restart to clear runaway processes"),
        ],
        est_recovery=30.0,
        est_cost=0.1,
    ),

    # ── Memory Leak Strategies ──
    "restart_for_memory": _build_strategy(
        name="restart_for_memory",
        description="Restart service to reclaim leaked memory",
        target_types=[IncidentType.MEMORY_LEAK],
        actions=[
            (RemediationActionType.RESTART_SERVICE, {}, "Restart to reclaim leaked memory"),
        ],
        est_recovery=30.0,
        est_cost=0.1,
    ),
    "rollback_memory_leak": _build_strategy(
        name="rollback_memory_leak",
        description="Rollback deployment that introduced the memory leak",
        target_types=[IncidentType.MEMORY_LEAK],
        actions=[
            (RemediationActionType.ROLLBACK_DEPLOYMENT, {}, "Rollback to version without memory leak"),
            (RemediationActionType.RESTART_SERVICE, {}, "Restart with rolled-back version"),
        ],
        est_recovery=90.0,
        est_cost=0.6,
    ),
    "scale_and_cache_memory": _build_strategy(
        name="scale_and_cache_memory",
        description="Scale up memory and clear cache to mitigate leak",
        target_types=[IncidentType.MEMORY_LEAK],
        actions=[
            (RemediationActionType.SCALE_VERTICAL, {"target_cpu": 2.0, "target_memory": 8.0}, "Increase memory allocation"),
            (RemediationActionType.CLEAR_CACHE, {}, "Clear cache to free memory"),
        ],
        est_recovery=40.0,
        est_cost=1.6,
    ),

    # ── Network Degradation Strategies ──
    "rebalance_network": _build_strategy(
        name="rebalance_network",
        description="Rebalance load to route around degraded network paths",
        target_types=[IncidentType.NETWORK_DEGRADATION],
        actions=[
            (RemediationActionType.REBALANCE_LOAD, {}, "Rebalance to healthy network paths"),
        ],
        est_recovery=25.0,
        est_cost=0.3,
    ),
    "scale_and_timeout_network": _build_strategy(
        name="scale_and_timeout_network",
        description="Scale out and adjust timeouts for network issues",
        target_types=[IncidentType.NETWORK_DEGRADATION],
        actions=[
            (RemediationActionType.SCALE_HORIZONTAL, {"target_instances": 3}, "Add instances in different zones"),
            (RemediationActionType.CHANGE_TIMEOUT, {"new_timeout": 10000}, "Increase timeout for slow network"),
        ],
        est_recovery=50.0,
        est_cost=2.05,
    ),
    "restart_and_rebalance_network": _build_strategy(
        name="restart_and_rebalance_network",
        description="Restart service and rebalance to recover from network issues",
        target_types=[IncidentType.NETWORK_DEGRADATION],
        actions=[
            (RemediationActionType.RESTART_SERVICE, {}, "Restart to reset network connections"),
            (RemediationActionType.REBALANCE_LOAD, {}, "Rebalance traffic"),
        ],
        est_recovery=40.0,
        est_cost=0.4,
    ),

    # ── Timeout Misconfiguration Strategies ──
    "fix_timeout": _build_strategy(
        name="fix_timeout",
        description="Correct the timeout configuration",
        target_types=[IncidentType.TIMEOUT_MISCONFIGURATION],
        actions=[
            (RemediationActionType.CHANGE_TIMEOUT, {"new_timeout": 5000}, "Set timeout to optimal value"),
        ],
        est_recovery=10.0,
        est_cost=0.05,
    ),
    "rollback_timeout": _build_strategy(
        name="rollback_timeout",
        description="Rollback the deployment that changed timeout settings",
        target_types=[IncidentType.TIMEOUT_MISCONFIGURATION],
        actions=[
            (RemediationActionType.ROLLBACK_DEPLOYMENT, {}, "Rollback to previous timeout config"),
        ],
        est_recovery=60.0,
        est_cost=0.5,
    ),
    "timeout_and_restart": _build_strategy(
        name="timeout_and_restart",
        description="Fix timeout and restart to apply changes",
        target_types=[IncidentType.TIMEOUT_MISCONFIGURATION],
        actions=[
            (RemediationActionType.CHANGE_TIMEOUT, {"new_timeout": 5000}, "Correct timeout value"),
            (RemediationActionType.RESTART_SERVICE, {}, "Restart to apply new timeout"),
            (RemediationActionType.REBALANCE_LOAD, {}, "Rebalance after restart"),
        ],
        est_recovery=40.0,
        est_cost=0.45,
    ),
}


def get_strategies_for_incident(incident_type: IncidentType) -> List[RemediationStrategy]:
    """Get all strategies applicable to a given incident type.

    Args:
        incident_type: The type of incident.

    Returns:
        List of applicable strategies.
    """
    return [
        strategy
        for strategy in STRATEGY_CATALOG.values()
        if incident_type in strategy.target_incident_types
    ]


def get_strategy_by_name(name: str) -> RemediationStrategy:
    """Get a strategy by its name.

    Args:
        name: Strategy name.

    Returns:
        The strategy.

    Raises:
        KeyError: If strategy not found.
    """
    if name not in STRATEGY_CATALOG:
        raise KeyError(f"Strategy '{name}' not found in catalog")
    return STRATEGY_CATALOG[name]