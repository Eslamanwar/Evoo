"""Terminal state workflows for COMPLETED and FAILED states."""

from typing import Optional, override

from agentex.lib import adk
from agentex.lib.sdk.state_machine.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.models.enums import EvooState
from project.state_machines.evoo import EvooData

logger = make_logger(__name__)


class CompletedWorkflow(StateWorkflow):
    """Workflow for the COMPLETED terminal state."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Handle completed state - terminal.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Stays in COMPLETED state.
        """
        if state_machine_data:
            metrics = state_machine_data.agent_metrics
            logger.info(
                f"EVOO learning loop completed. "
                f"Total incidents: {state_machine_data.incident_count}, "
                f"Avg reward: {metrics.get('average_reward', 0):.2f}"
            )

            if state_machine_data.task_id:
                reward_history = metrics.get("reward_history", [])
                total = metrics.get("total_incidents", 0)
                success = metrics.get("total_successful_remediations", 0)

                # Determine evolution verdict
                verdict_emoji = "🧬"
                if len(reward_history) >= 4:
                    half = len(reward_history) // 2
                    early = sum(reward_history[:half]) / half
                    late = sum(reward_history[half:]) / (len(reward_history) - half)
                    if late > early + 10:
                        verdict_emoji = "🚀"
                        verdict = "EVOO has evolved — performance improved significantly!"
                    elif late > early:
                        verdict_emoji = "📈"
                        verdict = "EVOO is learning — gradual improvement detected."
                    else:
                        verdict_emoji = "🔬"
                        verdict = "EVOO needs more training cycles to demonstrate evolution."
                else:
                    verdict = "Completed with limited data for evolution assessment."

                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=(
                            f"### {verdict_emoji} EVOO Session Complete\n\n"
                            f"**{verdict}**\n\n"
                            f"- Incidents handled: **{total}**\n"
                            f"- Success rate: **{success}/{total}** ({success/total:.0%})\n"
                            f"- Final avg reward: **{metrics.get('average_reward', 0):.2f}**\n"
                            f"- Final avg recovery: **{metrics.get('average_recovery_time', 0):.1f}s**\n\n"
                            f"*EVOO's learned strategies are persisted in memory and will be used in future sessions.*"
                        ),
                    ),
                    trace_id=state_machine_data.task_id,
                )

        return EvooState.COMPLETED


class FailedWorkflow(StateWorkflow):
    """Workflow for the FAILED terminal state."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Handle failed state - terminal.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Stays in FAILED state.
        """
        if state_machine_data:
            logger.error(f"EVOO workflow failed: {state_machine_data.error_message}")

            if state_machine_data.task_id:
                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=(
                            f"### ❌ EVOO Workflow Failed\n\n"
                            f"**Error:** {state_machine_data.error_message}\n\n"
                            f"Incidents completed before failure: {state_machine_data.incident_count}\n"
                            f"*Any learned strategies have been saved and will persist for future sessions.*"
                        ),
                    ),
                    trace_id=state_machine_data.task_id,
                )

        return EvooState.FAILED
