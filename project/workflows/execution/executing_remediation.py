"""EVOO: Executing Remediation state workflow.

This state implements the Executor agent — it:
1. Runs the agentic OBSERVE->THINK->ACT loop where an LLM decides
   which remediation tools to call and in what order
2. Records all tool outputs
3. Applies the remediation to the simulated system
4. Collects post-remediation metrics
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional, override

from temporalio.common import RetryPolicy

from agentex.lib import adk
from agentex.lib.core.temporal.activities.activity_helpers import ActivityHelpers
from agentex.lib.sdk.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.models.incident import SystemMetrics
from project.state_machines.evoo_agent import EVOOData, EVOOState

logger = make_logger(__name__)


class ExecutingRemediationWorkflow(StateWorkflow):
    """Executor agent: run agentic remediation loop."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EVOOData] = None,
    ) -> str:
        if state_machine_data is None or state_machine_data.current_plan is None:
            return EVOOState.FAILED

        plan = state_machine_data.current_plan
        incident = state_machine_data.current_incident
        task_id = state_machine_data.task_id or "no-task"
        run_index = state_machine_data.run_index

        logger.info(f"[Run {run_index + 1}] Starting agentic execution loop")

        # --- Step 1: Run the agentic OBSERVE->THINK->ACT loop ---
        loop_result = await ActivityHelpers.execute_activity(
            activity_name="run_sre_agent_loop_activity",
            request={
                "incident": {
                    "incident_type": incident.incident_type.value if incident else "unknown",
                    "affected_service": incident.affected_service if incident else "api-service",
                    "severity": incident.severity if incident else "unknown",
                    "description": incident.description if incident else "",
                },
                "plan": {
                    "strategy": plan.strategy,
                    "tools_to_call": plan.tools_to_call,
                    "tool_parameters": plan.tool_parameters,
                },
                "metrics_before": state_machine_data.metrics_before.model_dump(mode="json") if state_machine_data.metrics_before else {},
                "system_state": state_machine_data.simulated_system_state,
                "task_id": task_id,
                "trace_id": task_id,
            },
            response_type=dict,
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # Store agentic loop results
        tool_results = loop_result.get("tool_results", [])
        state_machine_data.tool_execution_results = tool_results
        state_machine_data.agent_loop_iterations = loop_result.get("iterations_used", 0)
        state_machine_data.agent_loop_actions = loop_result.get("actions_taken", [])

        logger.info(
            f"[Run {run_index + 1}] Agent loop: {loop_result.get('iterations_used', 0)} iterations, "
            f"{len(tool_results)} tools, finished={loop_result.get('finished_naturally', False)}"
        )

        # --- Step 2: Apply remediation to simulated system and get post-metrics ---
        sim_result = await ActivityHelpers.execute_activity(
            activity_name="apply_remediation_to_simulation_activity",
            request={
                "system_state": state_machine_data.simulated_system_state,
                "strategy_name": plan.strategy,
                "tool_parameters": plan.tool_parameters,
            },
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # Store post-remediation metrics
        metrics_after_data = sim_result.get("metrics_after", {})
        state_machine_data.metrics_after = SystemMetrics(**metrics_after_data)

        # Update system state
        state_machine_data.simulated_system_state["is_healthy"] = sim_result.get("service_restored", False)
        state_machine_data.simulated_system_state["sim_result"] = sim_result

        # Report execution results
        if state_machine_data.task_id:
            ma = state_machine_data.metrics_after
            restored_emoji = "Y" if sim_result.get("service_restored") else "N"
            tools_summary = "\n".join(
                [f"- `{r.get('tool', '?')}`: {r.get('status', '?')}" for r in tool_results[:8]]
            )
            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"#### Execution Complete [{restored_emoji} restored] "
                        f"({loop_result.get('iterations_used', 0)} iterations)\n"
                        f"**Tools executed**:\n{tools_summary}\n\n"
                        f"**Post-remediation metrics**:\n"
                        f"| Metric | After |\n"
                        f"|--------|-------|\n"
                        f"| Latency | {ma.latency_ms:.0f}ms |\n"
                        f"| CPU | {ma.cpu_percent:.1f}% |\n"
                        f"| Memory | {ma.memory_percent:.1f}% |\n"
                        f"| Error Rate | {ma.error_rate:.1%} |\n"
                        f"| Availability | {ma.availability:.1%} |\n"
                        f"| Recovery Time | {sim_result.get('recovery_time_seconds', '?')}s |\n"
                    ),
                ),
                trace_id=state_machine_data.task_id,
            )

        return EVOOState.EVALUATING_OUTCOME
