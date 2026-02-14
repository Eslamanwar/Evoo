"""Simulation activities for generating incidents in the production system."""

import json
from typing import Optional

from temporalio import activity

from agentex.lib.utils.logging import make_logger
from project.activities.remediation_tools import get_production_system
from project.models.enums import IncidentType

logger = make_logger(__name__)


@activity.defn(name="generate_incident")
async def generate_incident(incident_type: Optional[str] = None) -> str:
    """Generate a simulated production incident.

    Args:
        incident_type: Optional specific incident type to generate.

    Returns:
        JSON string with the generated incident details.
    """
    logger.info(f"🔥 Generating incident (type={incident_type or 'random'})")
    system = get_production_system()

    # Reset system to healthy before generating new incident
    system.reset_to_healthy()

    inc_type = None
    if incident_type:
        try:
            inc_type = IncidentType(incident_type)
        except ValueError:
            logger.warning(f"Unknown incident type: {incident_type}, generating random")

    incident = system.generate_incident(inc_type)

    result = {
        "incident": incident.to_dict(),
        "metrics": system.get_current_metrics().to_dict(),
        "health_score": round(system.get_current_metrics().compute_health_score(), 3),
    }

    logger.info(
        f"Generated incident: {incident.incident_type.value} "
        f"(severity: {incident.severity.value}, id: {incident.id})"
    )

    return json.dumps(result, default=str)


@activity.defn(name="reset_production_system")
async def reset_production_system() -> str:
    """Reset the production system to a healthy state.

    Returns:
        JSON string confirming reset.
    """
    logger.info("🔄 Resetting production system to healthy state")
    system = get_production_system()
    system.reset_to_healthy()

    return json.dumps({
        "status": "healthy",
        "metrics": system.get_current_metrics().to_dict(),
        "health_score": round(system.get_current_metrics().compute_health_score(), 3),
    })