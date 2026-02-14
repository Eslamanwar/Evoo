"""Evaluating outcome state workflow - calculates reward and LLM evaluation."""

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

    if tool_name == "calculate_reward":
        reward = result.get("reward", 0)
        breakdown = result.get("breakdown", {})
        breakdown_str = ", ".join(f"{k}: {v:+.1f}" for k, v in list(breakdown.items())[:4])
        return f"Reward: {reward:.2f} | Breakdown: {breakdown_str}"

    if tool_name == "evaluate_remediation_with_llm":
        assessment = result.get("assessment", "unknown")
        adjusted = result.get("adjusted_reward", 0)
        positives = len(result.get("positives", []))
        improvements = len(result.get("improvements", []))
        return (
            f"Assessment: {assessment} | "
            f"Adjusted reward: {adjusted:.2f} | "
            f"Positives: {positives} | Improvements: {improvements}"
        )

    return f"Completed | Keys: {', '.join(list(result.keys())[:5])}"


class EvaluatingOutcomeWorkflow(StateWorkflow):
    """Workflow for the EVALUATING_OUTCOME state.

    Calculates numerical reward and uses LLM as a judge to evaluate
    the remediation effectiveness qualitatively.
    """

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Evaluate the remediation outcome.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Next state to transition to.
        """
        if state_machine_data is None:
            return EvooState.FAILED

        try:
            logger.info("📊 Evaluating remediation outcome")

            task_id = state_machine_data.task_id
            trace_id = state_machine_data.task_id

            # --- Tool: calculate_reward ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="calculate_reward",
                        arguments={
                            "service_restored": state_machine_data.service_restored,
                            "recovery_time": f"{state_machine_data.total_recovery_time:.1f}s",
                            "cost": f"{state_machine_data.total_cost:.2f}",
                        },
                    ),
                    trace_id=trace_id,
                )

            reward_json = await workflow.execute_activity(
                "calculate_reward",
                args=[
                    state_machine_data.metrics_before,
                    state_machine_data.metrics_after,
                    state_machine_data.total_recovery_time,
                    state_machine_data.total_cost,
                    state_machine_data.service_restored,
                ],
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            reward_data = json.loads(reward_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="calculate_reward",
                        content=_format_tool_response("calculate_reward", reward_data),
                    ),
                    trace_id=trace_id,
                )

            state_machine_data.reward = reward_data.get("reward", 0.0)
            state_machine_data.reward_breakdown = reward_data.get("breakdown", {})

            # --- Tool: evaluate_remediation_with_llm ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="evaluate_remediation_with_llm",
                        arguments={
                            "incident_type": state_machine_data.current_incident_type or "unknown",
                            "strategy": state_machine_data.selected_strategy or "unknown",
                            "numerical_reward": f"{state_machine_data.reward:.2f}",
                            "service_restored": state_machine_data.service_restored,
                        },
                    ),
                    trace_id=trace_id,
                )

            llm_eval_json = await workflow.execute_activity(
                "evaluate_remediation_with_llm",
                args=[
                    state_machine_data.current_incident_type or "unknown",
                    state_machine_data.current_incident_severity or "medium",
                    state_machine_data.selected_strategy or "unknown",
                    state_machine_data.tools_called,
                    state_machine_data.metrics_before,
                    state_machine_data.metrics_after,
                    state_machine_data.total_recovery_time,
                    state_machine_data.service_restored,
                    state_machine_data.reward,
                ],
                start_to_close_timeout=workflow.timedelta(minutes=5),
            )
            llm_eval = json.loads(llm_eval_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="evaluate_remediation_with_llm",
                        content=_format_tool_response("evaluate_remediation_with_llm", llm_eval),
                    ),
                    trace_id=trace_id,
                )

            state_machine_data.llm_evaluation = llm_eval.get("assessment", "unknown")
            state_machine_data.adjusted_reward = llm_eval.get(
                "adjusted_reward", state_machine_data.reward
            )

            # Send evaluation message
            if state_machine_data.task_id:
                breakdown = state_machine_data.reward_breakdown
                breakdown_str = "\n".join(
                    f"  - {key}: {value:+.2f}" for key, value in breakdown.items()
                )

                positives = llm_eval.get("positives", [])
                improvements = llm_eval.get("improvements", [])
                recommendations = llm_eval.get("recommendations", [])

                positives_str = "\n".join(f"  ✅ {p}" for p in positives) if positives else "  None"
                improvements_str = "\n".join(f"  ⚠️ {i}" for i in improvements) if improvements else "  None"
                recommendations_str = "\n".join(f"  💡 {r}" for r in recommendations) if recommendations else "  None"

                eval_msg = (
                    f"📊 **Remediation Evaluation**\n\n"
                    f"**Numerical Reward:** {state_machine_data.reward:.2f}\n"
                    f"**LLM Assessment:** {state_machine_data.llm_evaluation}\n"
                    f"**Adjusted Reward:** {state_machine_data.adjusted_reward:.2f}\n\n"
                    f"**Reward Breakdown:**\n{breakdown_str}\n\n"
                    f"**What Went Well:**\n{positives_str}\n\n"
                    f"**Areas for Improvement:**\n{improvements_str}\n\n"
                    f"**Recommendations:**\n{recommendations_str}\n"
                )

                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=eval_msg,
                    ),
                    trace_id=state_machine_data.task_id,
                )

            logger.info(
                f"Evaluation complete: reward={state_machine_data.reward:.2f}, "
                f"adjusted={state_machine_data.adjusted_reward:.2f}, "
                f"assessment={state_machine_data.llm_evaluation}"
            )

            return EvooState.LEARNING

        except Exception as e:
            logger.error(f"Error evaluating outcome: {e}")
            # Even if evaluation fails, try to learn from what we have
            state_machine_data.reward = 0.0
            state_machine_data.adjusted_reward = 0.0
            state_machine_data.llm_evaluation = "evaluation_failed"
            state_machine_data.error_message = f"Evaluation failed: {str(e)}"
            return EvooState.LEARNING