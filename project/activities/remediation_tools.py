"""Core remediation tool activities for EVOO agent."""

import json
from typing import Any, Dict

from temporalio import activity

from agentex.lib.utils.logging import make_logger
from project.models.enums import RemediationActionType
from project.simulation.production_system import ProductionSystem

logger = make_logger(__name__)

# Shared production system instance (initialized per worker)
_production_system: ProductionSystem = ProductionSystem()


def get_production_system() -> ProductionSystem:
    """Get the shared production system instance."""
    return _production_system


def set_production_system(system: ProductionSystem) -> None:
    """Set the shared production system instance."""
    global _production_system
    _production_system = system


@activity.defn(name="restart_service")
async def restart_service() -> str:
    """Restart the affected service.

    Returns:
        JSON string with action result.
    """
    logger.info("🔧 Executing: restart_service")
    system = get_production_system()
    result = system.apply_remediation_action(RemediationActionType.RESTART_SERVICE)
    logger.info(f"restart_service result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="scale_horizontal")
async def scale_horizontal(target_instances: int = 3) -> str:
    """Scale the service horizontally by adding instances.

    Args:
        target_instances: Target number of instances.

    Returns:
        JSON string with action result.
    """
    logger.info(f"🔧 Executing: scale_horizontal(target_instances={target_instances})")
    system = get_production_system()
    result = system.apply_remediation_action(
        RemediationActionType.SCALE_HORIZONTAL,
        {"target_instances": target_instances},
    )
    logger.info(f"scale_horizontal result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="scale_vertical")
async def scale_vertical(target_cpu: float = 2.0, target_memory: float = 4.0) -> str:
    """Scale the service vertically by increasing resources.

    Args:
        target_cpu: Target CPU cores.
        target_memory: Target memory in GB.

    Returns:
        JSON string with action result.
    """
    logger.info(f"🔧 Executing: scale_vertical(cpu={target_cpu}, memory={target_memory})")
    system = get_production_system()
    result = system.apply_remediation_action(
        RemediationActionType.SCALE_VERTICAL,
        {"target_cpu": target_cpu, "target_memory": target_memory},
    )
    logger.info(f"scale_vertical result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="change_timeout")
async def change_timeout(new_timeout: int = 5000) -> str:
    """Change the service timeout configuration.

    Args:
        new_timeout: New timeout value in milliseconds.

    Returns:
        JSON string with action result.
    """
    logger.info(f"🔧 Executing: change_timeout(new_timeout={new_timeout})")
    system = get_production_system()
    result = system.apply_remediation_action(
        RemediationActionType.CHANGE_TIMEOUT,
        {"new_timeout": new_timeout},
    )
    logger.info(f"change_timeout result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="rollback_deployment")
async def rollback_deployment() -> str:
    """Rollback to the previous deployment version.

    Returns:
        JSON string with action result.
    """
    logger.info("🔧 Executing: rollback_deployment")
    system = get_production_system()
    result = system.apply_remediation_action(RemediationActionType.ROLLBACK_DEPLOYMENT)
    logger.info(f"rollback_deployment result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="clear_cache")
async def clear_cache() -> str:
    """Clear the service cache.

    Returns:
        JSON string with action result.
    """
    logger.info("🔧 Executing: clear_cache")
    system = get_production_system()
    result = system.apply_remediation_action(RemediationActionType.CLEAR_CACHE)
    logger.info(f"clear_cache result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="rebalance_load")
async def rebalance_load() -> str:
    """Rebalance traffic across service instances.

    Returns:
        JSON string with action result.
    """
    logger.info("🔧 Executing: rebalance_load")
    system = get_production_system()
    result = system.apply_remediation_action(RemediationActionType.REBALANCE_LOAD)
    logger.info(f"rebalance_load result: success={result['success']}")
    return json.dumps(result)


@activity.defn(name="query_metrics")
async def query_metrics() -> str:
    """Query current system metrics.

    Returns:
        JSON string with current metrics.
    """
    logger.info("📊 Querying system metrics")
    system = get_production_system()
    metrics = system.get_current_metrics()
    result = {
        "metrics": metrics.to_dict(),
        "health_score": round(metrics.compute_health_score(), 3),
        "is_healthy": metrics.compute_health_score() >= 0.7,
    }
    logger.info(f"System health score: {result['health_score']}")
    return json.dumps(result)


@activity.defn(name="get_incident_state")
async def get_incident_state() -> str:
    """Get the current incident state of the production system.

    Returns:
        JSON string with incident state.
    """
    logger.info("🔍 Getting incident state")
    system = get_production_system()
    state = system.get_incident_state()
    return json.dumps(state, default=str)