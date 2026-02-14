"""Executing remediation state workflow - executes the planned strategy actions."""

import json
import uuid
from typing import Optional, override

from temporalio import workflow

from agentex.lib import adk
from agentex.lib.sdk.state_machine.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent
from agentex.types.tool_request_content import ToolRequestContent
from agentex.types.tool_response_content import ToolResponseContent

from project.guardrails.safety_rules import GuardrailEngine, GuardrailVerdict
from project.models.enums import EvooState
from project.state_machines.evoo import EvooData

logger = make_logger(__name__)

# Shared guardrail engine instance (set by worker initialization)
_guardrail_engine: Optional[GuardrailEngine] = None


def set_guardrail_engine(engine: GuardrailEngine) -> None:
    """Set the shared guardrail engine instance."""
    global _guardrail_engine
    _guardrail_engine = engine


def get_guardrail_engine() -> GuardrailEngine:
    """Get the shared guardrail engine, creating default if needed."""
    global _guardrail_engine
    if _guardrail_engine is None:
        _guardrail_engine = GuardrailEngine()
    return _guardrail_engine


# Mapping of action types to activity names
ACTION_TO_ACTIVITY = {
    "restart_service": "restart_service",
    "scale_horizontal": "scale_horizontal",
    "scale_vertical": "scale_vertical",
    "change_timeout": "change_timeout",
    "rollback_deployment": "rollback_deployment",
    "clear_cache": "clear_cache",
    "rebalance_load": "rebalance_load",
}


def _format_remediation_response(action_type: str, result: dict) -> str:
    """Format remediation tool result for ToolResponseContent display."""
    if "error" in result:
        return f"Error: {result['error'][:200]}"

    success = result.get("success", False)
    status = "SUCCESS" if success else "FAILED"
    msg = result.get("message", "completed")
    cost = result.get("cost", 0.0)
    recovery = result.get("recovery_time_added", 0.0)

    return f"{status}: {msg} | Cost: {cost:.2f} | Recovery time: {recovery:.1f}s"


def _format_metrics_response(result: dict) -> str:
    """Format query_metrics result for ToolResponseContent display."""
    m = result.get("metrics", {})
    healthy = result.get("is_healthy", False)
    health_score = result.get("health_score", 0)
    return (
        f"Latency: {m.get('latency_ms', 0):.0f}ms | "
        f"CPU: {m.get('cpu_percent', 0):.1f}% | "
        f"Memory: {m.get('memory_percent', 0):.1f}% | "
        f"Error rate: {m.get('error_rate', 0):.2%} | "
        f"Healthy: {healthy} | Score: {health_score:.3f}"
    )


class ExecutingRemediationWorkflow(StateWorkflow):
    """Workflow for the EXECUTING_REMEDIATION state.

    Executes each action in the selected strategy sequentially,
    collecting results and metrics after each action.
    """

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Execute the remediation strategy.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Next state to transition to.
        """
        if state_machine_data is None:
            return EvooState.FAILED

        try:
            strategy_name = state_machine_data.selected_strategy or "restart_and_verify"
            actions = state_machine_data.strategy_details.get("actions", [])

            if not actions:
                # Fallback: just restart
                actions = [{"action_type": "restart_service", "parameters": {}, "description": "Restart service"}]

            logger.info(
                f"⚡ Executing strategy '{strategy_name}' with {len(actions)} actions"
            )

            # Send execution start message
            if state_machine_data.task_id:
                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=f"⚡ **Executing Remediation Strategy:** {strategy_name}\n",
                    ),
                    trace_id=state_machine_data.task_id,
                )

            task_id = state_machine_data.task_id
            trace_id = state_machine_data.task_id

            total_cost = 0.0
            total_recovery_time = 0.0
            all_results = []
            blocked_actions = []

            # Get guardrail engine
            guardrails = get_guardrail_engine()

            # Get initial system state for guardrail checks
            pre_metrics_json = await workflow.execute_activity(
                "query_metrics",
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            pre_metrics = json.loads(pre_metrics_json)

            # Execute each action in order
            for i, action in enumerate(actions):
                action_type = action.get("action_type", "restart_service")
                parameters = action.get("parameters", {})
                description = action.get("description", action_type)

                activity_name = ACTION_TO_ACTIVITY.get(action_type)
                if not activity_name:
                    logger.warning(f"Unknown action type: {action_type}, skipping")
                    continue

                logger.info(f"  Action {i + 1}/{len(actions)}: {description}")

                # Build activity arguments based on action type
                args = []
                tool_arguments = {"action": action_type}
                if action_type == "scale_horizontal":
                    args = [parameters.get("target_instances", 3)]
                    tool_arguments["target_instances"] = parameters.get("target_instances", 3)
                elif action_type == "scale_vertical":
                    args = [
                        parameters.get("target_cpu", 2.0),
                        parameters.get("target_memory", 4.0),
                    ]
                    tool_arguments["target_cpu"] = parameters.get("target_cpu", 2.0)
                    tool_arguments["target_memory"] = parameters.get("target_memory", 4.0)
                elif action_type == "change_timeout":
                    args = [parameters.get("new_timeout", 5000)]
                    tool_arguments["new_timeout"] = parameters.get("new_timeout", 5000)

                # ─── Guardrail Check ───────────────────────────────────
                system_state = {
                    "active_instances": pre_metrics.get("metrics", {}).get("active_instances", 2),
                    "health_score": pre_metrics.get("health_score", 0.0),
                    "metrics": pre_metrics.get("metrics", {}),
                }
                incident_context = {
                    "actions_taken": state_machine_data.actions_executed,
                    "total_cost": total_cost,
                }

                guardrail_result = guardrails.check_action(
                    action_type=action_type,
                    parameters=parameters,
                    system_state=system_state,
                    incident_context=incident_context,
                )

                # --- Tool Request: remediation action ---
                tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
                if task_id:
                    await adk.messages.create(
                        task_id=task_id,
                        content=ToolRequestContent(
                            author="agent",
                            tool_call_id=tool_call_id,
                            name=activity_name,
                            arguments=tool_arguments,
                        ),
                        trace_id=trace_id,
                    )

                # Handle guardrail verdict
                if guardrail_result.verdict == GuardrailVerdict.BLOCK:
                    # Action blocked by guardrail — do NOT execute
                    logger.warning(
                        f"🛑 Action '{action_type}' BLOCKED by guardrail: "
                        f"{guardrail_result.rule_name}"
                    )

                    blocked_actions.append({
                        "action": action_type,
                        "rule": guardrail_result.rule_name,
                        "reason": guardrail_result.reason,
                    })

                    # Send blocked response via ToolResponseContent
                    if task_id:
                        block_msg = (
                            f"🛑 BLOCKED by guardrail [{guardrail_result.rule_name}]: "
                            f"{guardrail_result.reason}"
                        )
                        if guardrail_result.suggestion:
                            block_msg += f" | Suggestion: {guardrail_result.suggestion}"

                        await adk.messages.create(
                            task_id=task_id,
                            content=ToolResponseContent(
                                author="agent",
                                tool_call_id=tool_call_id,
                                name=activity_name,
                                content=block_msg,
                            ),
                            trace_id=trace_id,
                        )

                    # Track as blocked (not executed)
                    state_machine_data.actions_executed.append({
                        "action": action_type,
                        "parameters": parameters,
                        "success": False,
                        "cost": 0.0,
                        "blocked_by_guardrail": True,
                        "guardrail_rule": guardrail_result.rule_name,
                        "guardrail_reason": guardrail_result.reason,
                    })
                    continue  # Skip to next action

                # Handle guardrail warning (execute but notify)
                if guardrail_result.verdict == GuardrailVerdict.WARN:
                    logger.info(
                        f"⚠️ Guardrail warning for '{action_type}': "
                        f"{guardrail_result.rule_name}"
                    )
                    if task_id:
                        await adk.messages.create(
                            task_id=task_id,
                            content=TextContent(
                                author="agent",
                                content=(
                                    f"⚠️ **Guardrail Warning** [{guardrail_result.rule_name}]: "
                                    f"{guardrail_result.reason}\n"
                                    f"*Proceeding with action...*"
                                ),
                            ),
                            trace_id=trace_id,
                        )

                # ─── Execute the activity (guardrail passed) ──────────
                result_json = await workflow.execute_activity(
                    activity_name,
                    args=args if args else None,
                    start_to_close_timeout=workflow.timedelta(seconds=60),
                )
                result = json.loads(result_json)

                # --- Tool Response: remediation action ---
                if task_id:
                    await adk.messages.create(
                        task_id=task_id,
                        content=ToolResponseContent(
                            author="agent",
                            tool_call_id=tool_call_id,
                            name=activity_name,
                            content=_format_remediation_response(action_type, result),
                        ),
                        trace_id=trace_id,
                    )

                all_results.append(result)
                total_cost += result.get("cost", 0.0)
                total_recovery_time += result.get("recovery_time_added", 0.0)

                # Update pre_metrics with latest state for next guardrail check
                latest_metrics = result.get("metrics", {})
                if latest_metrics:
                    pre_metrics = {
                        "metrics": latest_metrics,
                        "health_score": latest_metrics.get("availability", 0.5),
                        "is_healthy": latest_metrics.get("availability", 0) >= 0.7,
                    }

                # Track tools called
                state_machine_data.tools_called.append(activity_name)
                state_machine_data.actions_executed.append({
                    "action": action_type,
                    "parameters": parameters,
                    "success": result.get("success", False),
                    "cost": result.get("cost", 0.0),
                })

            # Store execution results
            state_machine_data.execution_results = all_results
            state_machine_data.total_cost = total_cost
            state_machine_data.total_recovery_time = total_recovery_time

            # --- Tool: query_metrics (post-remediation) ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="query_metrics",
                        arguments={"phase": "post_remediation"},
                    ),
                    trace_id=trace_id,
                )

            final_metrics_json = await workflow.execute_activity(
                "query_metrics",
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            final_metrics = json.loads(final_metrics_json)
            state_machine_data.metrics_after = final_metrics.get("metrics", {})
            state_machine_data.service_restored = final_metrics.get("is_healthy", False)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="query_metrics",
                        content=_format_metrics_response(final_metrics),
                    ),
                    trace_id=trace_id,
                )

            # Send execution summary
            if state_machine_data.task_id:
                health_icon = "🟢" if state_machine_data.service_restored else "🔴"

                # Count executed vs blocked
                executed_count = len([a for a in state_machine_data.actions_executed if not a.get("blocked_by_guardrail")])
                blocked_count = len(blocked_actions)

                blocked_summary = ""
                if blocked_actions:
                    blocked_lines = "\n".join(
                        f"  🛑 {b['action']} — {b['rule']}: {b['reason'][:80]}"
                        for b in blocked_actions
                    )
                    blocked_summary = f"\n**Blocked by Guardrails ({blocked_count}):**\n{blocked_lines}\n"

                summary_msg = (
                    f"\n**Execution Summary:**\n"
                    f"- Actions executed: {executed_count}\n"
                    f"- Actions blocked: {blocked_count}\n"
                    f"- Total cost: {total_cost:.2f}\n"
                    f"- Recovery time: {total_recovery_time:.1f}s\n"
                    f"- Service status: {health_icon} {'Restored' if state_machine_data.service_restored else 'Still degraded'}\n"
                    f"- Health score: {final_metrics.get('health_score', 0):.3f}\n"
                    f"{blocked_summary}"
                )

                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=summary_msg,
                    ),
                    trace_id=state_machine_data.task_id,
                )

            logger.info(
                f"Execution complete: restored={state_machine_data.service_restored}, "
                f"cost={total_cost:.2f}, recovery_time={total_recovery_time:.1f}s"
            )

            return EvooState.EVALUATING_OUTCOME

        except Exception as e:
            logger.error(f"Error executing remediation: {e}")
            state_machine_data.error_message = f"Execution failed: {str(e)}"

            # Still try to evaluate what happened
            try:
                final_metrics_json = await workflow.execute_activity(
                    "query_metrics",
                    start_to_close_timeout=workflow.timedelta(seconds=30),
                )
                final_metrics = json.loads(final_metrics_json)
                state_machine_data.metrics_after = final_metrics.get("metrics", {})
                state_machine_data.service_restored = False
                return EvooState.EVALUATING_OUTCOME
            except Exception:
                return EvooState.FAILED