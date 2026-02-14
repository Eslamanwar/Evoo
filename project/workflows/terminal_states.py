"""EVOO: Terminal state workflows (completed, failed)."""
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

from project.state_machines.evoo_agent import EVOOData, EVOOState

logger = make_logger(__name__)


class CompletedWorkflow(StateWorkflow):
    """EVOO learning run completed successfully."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EVOOData] = None,
    ) -> str:
        if state_machine_data is None:
            return EVOOState.COMPLETED

        logger.info("EVOO learning loop completed successfully!")

        # Fetch final memory summary
        try:
            summary = await ActivityHelpers.execute_activity(
                activity_name="get_memory_summary_activity",
                request={},
                response_type=dict,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except Exception:
            summary = {}

        rankings_result = {}
        try:
            rankings_result = await ActivityHelpers.execute_activity(
                activity_name="get_strategy_rankings_activity",
                request={},
                response_type=dict,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except Exception:
            pass

        if state_machine_data.task_id:
            rewards = state_machine_data.reward_history
            recovery_times = state_machine_data.recovery_time_history

            avg_all = sum(rewards) / len(rewards) if rewards else 0
            avg_early = sum(rewards[:5]) / min(5, len(rewards)) if rewards else 0
            avg_late = sum(rewards[-5:]) / min(5, len(rewards)) if rewards else 0
            improvement = avg_late - avg_early

            rankings = rankings_result.get("rankings", {})
            rankings_section = ""
            for itype, records in list(rankings.items())[:6]:
                top = records[:3]
                rankings_section += f"\n**{itype}**: " + " > ".join(
                    [f"`{r['strategy']}`({r['avg_reward']:.1f})" for r in top]
                )

            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"\n# EVOO Learning Complete — Final Report\n\n"
                        f"## Performance Summary\n"
                        f"| Metric | Value |\n"
                        f"|--------|-------|\n"
                        f"| Total Runs | {state_machine_data.run_index} |\n"
                        f"| Total Experiences | {summary.get('total_experiences', 0)} |\n"
                        f"| Average Reward | {summary.get('average_reward', avg_all):.2f} |\n"
                        f"| Best Reward | {summary.get('best_reward', max(rewards) if rewards else 0):.2f} |\n"
                        f"| Avg Recovery Time | {summary.get('average_recovery_time', 0):.1f}s |\n"
                        f"| Best Recovery Time | {summary.get('best_recovery_time', 0):.1f}s |\n\n"
                        f"## Learning Improvement\n"
                        f"- Early avg reward (first 5 runs): **{avg_early:.2f}**\n"
                        f"- Recent avg reward (last 5 runs): **{avg_late:.2f}**\n"
                        f"- Net improvement: **{improvement:+.2f}** "
                        f"({'✅ IMPROVED' if improvement > 0 else '⚠️ NEEDS MORE TRAINING'})\n\n"
                        f"## Optimal Strategies Learned{rankings_section}\n\n"
                        f"*EVOO has completed its evolutionary learning cycle.*"
                    ),
                ),
                trace_id=state_machine_data.task_id,
            )

        return EVOOState.COMPLETED


class FailedWorkflow(StateWorkflow):
    """EVOO encountered a fatal error."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EVOOData] = None,
    ) -> str:
        error_msg = "Unknown error"
        if state_machine_data:
            error_msg = state_machine_data.error_message or "Unspecified failure"

        logger.error(f"EVOO failed: {error_msg}")

        if state_machine_data and state_machine_data.task_id:
            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=f"## EVOO Error\n\nThe learning loop encountered a fatal error:\n```\n{error_msg}\n```",
                ),
                trace_id=state_machine_data.task_id,
            )

        return EVOOState.FAILED
