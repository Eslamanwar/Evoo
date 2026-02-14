"""EVOO: Waiting for Incident state workflow.

This state generates a new simulated incident and transitions the agent
into the planning phase.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, override

from temporalio import workflow
from temporalio.common import RetryPolicy

from agentex.lib import adk
from agentex.lib.core.temporal.activities.activity_helpers import ActivityHelpers
from agentex.lib.sdk.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.models.incident import Incident, SystemMetrics
from project.state_machines.evoo_agent import EVOOData, EVOOState

logger = make_logger(__name__)


class WaitingForIncidentWorkflow(StateWorkflow):
    """Generate a new incident and prepare for remediation planning."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EVOOData] = None,
    ) -> str:
        if state_machine_data is None:
            return EVOOState.FAILED

        run_index = state_machine_data.run_index

        # Check if we've reached the max runs
        if run_index >= state_machine_data.max_runs:
            state_machine_data.is_learning_complete = True
            return EVOOState.COMPLETED

        logger.info(f"[Run {run_index + 1}/{state_machine_data.max_runs}] Waiting for incident...")

        # Announce new run
        if state_machine_data.task_id and run_index > 0:
            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=f"\n---\n## Run {run_index + 1}/{state_machine_data.max_runs} — Incident Detection\n",
                ),
                trace_id=state_machine_data.task_id,
            )

        # Generate a new simulated incident
        incident_data = await ActivityHelpers.execute_activity(
            activity_name="generate_incident_activity",
            request={"run_index": run_index},
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Deserialize and store in state
        incident = Incident(**incident_data)
        state_machine_data.current_incident = incident
        state_machine_data.metrics_before = incident.metrics_at_detection
        state_machine_data.tool_execution_results = []
        state_machine_data.current_plan = None
        state_machine_data.metrics_after = None
        state_machine_data.current_reward = 0.0
        state_machine_data.last_llm_evaluation = ""

        # Update simulated system state
        state_machine_data.simulated_system_state = {
            "service_name": incident.affected_service,
            "is_healthy": False,
            "current_incident": incident.model_dump(mode="json"),
        }

        # Report incident to user
        if state_machine_data.task_id:
            metrics = incident.metrics_at_detection
            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"### Incident Detected: `{incident.incident_type.value}` [{incident.severity.upper()}]\n"
                        f"> {incident.description}\n\n"
                        f"| Metric | Value |\n"
                        f"|--------|-------|\n"
                        f"| Latency | {metrics.latency_ms:.0f}ms |\n"
                        f"| CPU | {metrics.cpu_percent:.1f}% |\n"
                        f"| Memory | {metrics.memory_percent:.1f}% |\n"
                        f"| Error Rate | {metrics.error_rate:.1%} |\n"
                        f"| Availability | {metrics.availability:.1%} |\n"
                    ),
                ),
                trace_id=state_machine_data.task_id,
            )

        logger.info(
            f"[Run {run_index + 1}] Incident: {incident.incident_type.value} "
            f"severity={incident.severity}"
        )

        return EVOOState.PLANNING_REMEDIATION
