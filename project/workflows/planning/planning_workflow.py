"""Planning remediation state workflow - selects strategy using LLM planner."""

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

from project.models.enums import EvooState
from project.state_machines.evoo import EvooData

logger = make_logger(__name__)


def _format_tool_response(tool_name: str, result: dict) -> str:
    """Format tool result for ToolResponseContent display."""
    if "error" in result:
        return f"Error: {result['error'][:200]}"

    if tool_name == "apply_previous_successful_strategy":
        if result.get("found"):
            best = result.get("best_strategy", {})
            return (
                f"Found best strategy: {best.get('name', 'unknown')} | "
                f"Avg reward: {best.get('average_reward', 0):.1f} | "
                f"Success rate: {best.get('success_rate', 0):.0%}"
            )
        return f"No previous strategy found for this incident type | Recommendation: {result.get('recommendation', 'explore')}"

    if tool_name == "plan_remediation":
        strategy = result.get("selected_strategy", "unknown")
        confidence = result.get("confidence", 0)
        is_exploration = result.get("is_exploration", False)
        mode = "exploration" if is_exploration else "exploitation"
        actions = result.get("strategy_details", {}).get("actions", [])
        return (
            f"Strategy: {strategy} ({mode}) | "
            f"Confidence: {confidence:.0%} | "
            f"Actions: {len(actions)}"
        )

    return f"Completed | Keys: {', '.join(list(result.keys())[:5])}"


class PlanningRemediationWorkflow(StateWorkflow):
    """Workflow for the PLANNING_REMEDIATION state.

    Uses the LLM planner agent to evaluate the incident and select
    the best remediation strategy based on historical data and current context.
    """

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Plan the remediation strategy.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Next state to transition to.
        """
        if state_machine_data is None:
            return EvooState.FAILED

        try:
            logger.info(
                f"🧠 Planning remediation for {state_machine_data.current_incident_type}"
            )

            task_id = state_machine_data.task_id
            trace_id = state_machine_data.task_id
            incident_type = state_machine_data.current_incident_type or "service_crash"

            # --- Tool: apply_previous_successful_strategy ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="apply_previous_successful_strategy",
                        arguments={"incident_type": incident_type},
                    ),
                    trace_id=trace_id,
                )

            prev_strategy_json = await workflow.execute_activity(
                "apply_previous_successful_strategy",
                args=[incident_type],
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            prev_strategy = json.loads(prev_strategy_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="apply_previous_successful_strategy",
                        content=_format_tool_response("apply_previous_successful_strategy", prev_strategy),
                    ),
                    trace_id=trace_id,
                )

            # --- Tool: plan_remediation ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            plan_args = {
                "incident_type": incident_type,
                "severity": state_machine_data.current_incident_severity or "medium",
                "metrics": "current system metrics",
                "history": f"{len(state_machine_data.conversation_history)} prior entries",
            }
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="plan_remediation",
                        arguments=plan_args,
                    ),
                    trace_id=trace_id,
                )

            plan_json = await workflow.execute_activity(
                "plan_remediation",
                args=[
                    incident_type,
                    state_machine_data.current_incident_severity or "medium",
                    state_machine_data.metrics_before,
                    state_machine_data.conversation_history,
                ],
                start_to_close_timeout=workflow.timedelta(minutes=5),
            )
            plan = json.loads(plan_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="plan_remediation",
                        content=_format_tool_response("plan_remediation", plan),
                    ),
                    trace_id=trace_id,
                )

            # Store planning results
            state_machine_data.selected_strategy = plan.get("selected_strategy", "restart_and_verify")
            state_machine_data.strategy_details = plan.get("strategy_details", {})
            state_machine_data.planning_reasoning = plan.get("reasoning", "")
            state_machine_data.planning_confidence = plan.get("confidence", 0.5)
            state_machine_data.is_exploration = plan.get("is_exploration", False)

            # Send planning message
            if state_machine_data.task_id:
                exploration_tag = " 🔍 (exploration)" if state_machine_data.is_exploration else " ✅ (exploitation)"
                prev_info = ""
                if prev_strategy.get("found"):
                    best = prev_strategy["best_strategy"]
                    prev_info = (
                        f"\n**Best Historical Strategy:** {best['name']} "
                        f"(reward: {best['average_reward']}, "
                        f"success: {best['success_rate']:.0%})\n"
                    )

                actions_list = ""
                for action in state_machine_data.strategy_details.get("actions", []):
                    actions_list += f"  - {action.get('description', action.get('action_type', 'unknown'))}\n"

                plan_msg = (
                    f"🧠 **Remediation Plan**{exploration_tag}\n\n"
                    f"**Strategy:** {state_machine_data.selected_strategy}\n"
                    f"**Confidence:** {state_machine_data.planning_confidence:.0%}\n"
                    f"**Reasoning:** {state_machine_data.planning_reasoning}\n"
                    f"{prev_info}"
                    f"\n**Actions to Execute:**\n{actions_list}"
                )

                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=plan_msg,
                    ),
                    trace_id=state_machine_data.task_id,
                )

            logger.info(
                f"Strategy selected: {state_machine_data.selected_strategy} "
                f"(confidence: {state_machine_data.planning_confidence:.2f})"
            )

            return EvooState.EXECUTING_REMEDIATION

        except Exception as e:
            logger.error(f"Error planning remediation: {e}")
            state_machine_data.error_message = f"Planning failed: {str(e)}"

            # Retry with fallback
            if state_machine_data.retry_count < state_machine_data.max_retries:
                state_machine_data.retry_count += 1
                state_machine_data.selected_strategy = "restart_and_verify"
                state_machine_data.planning_reasoning = "Fallback strategy due to planning error"
                state_machine_data.planning_confidence = 0.3
                logger.info("Using fallback strategy: restart_and_verify")
                return EvooState.EXECUTING_REMEDIATION

            return EvooState.FAILED