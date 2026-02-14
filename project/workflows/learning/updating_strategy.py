"""EVOO: Updating Strategy state workflow.

This state implements the Strategy Manager — it:
1. Updates the strategy performance record with the latest reward
2. Retrieves updated strategy rankings
3. Logs learning progress with observability metrics
4. Increments the run counter and transitions back to idle
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

from project.state_machines.evoo_agent import EVOOData, EVOOState

logger = make_logger(__name__)


class UpdatingStrategyWorkflow(StateWorkflow):
    """Strategy Manager: update rankings and prepare for the next incident."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EVOOData] = None,
    ) -> str:
        if state_machine_data is None or state_machine_data.current_incident is None:
            return EVOOState.FAILED

        incident = state_machine_data.current_incident
        plan = state_machine_data.current_plan
        run_index = state_machine_data.run_index
        reward = state_machine_data.current_reward
        experience = state_machine_data.current_experience

        if plan is None or experience is None:
            return EVOOState.FAILED

        # --- Step 1: Update strategy performance record ---
        await ActivityHelpers.execute_activity(
            activity_name="update_strategy_record_activity",
            request={
                "incident_type": incident.incident_type.value,
                "strategy": plan.strategy,
                "reward": reward,
                "success": experience.success,
            },
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # --- Step 2: Get updated rankings for this incident type ---
        rankings_result = await ActivityHelpers.execute_activity(
            activity_name="get_strategy_rankings_activity",
            request={"incident_type": incident.incident_type.value},
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # --- Step 3: Get memory summary every 5 runs ---
        if (run_index + 1) % 5 == 0:
            memory_summary = await ActivityHelpers.execute_activity(
                activity_name="get_memory_summary_activity",
                request={},
                response_type=dict,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            from project.models.experience import MemorySummary
            state_machine_data.memory_summary = MemorySummary(**memory_summary)

        # --- Step 4: Report progress with per-run trend table ---
        if state_machine_data.task_id:
            rankings = rankings_result.get("rankings", {})
            type_rankings = rankings.get(incident.incident_type.value, [])

            rankings_table = ""
            if type_rankings:
                rankings_table = (
                    f"\n**Strategy Rankings for `{incident.incident_type.value}`**:\n"
                    f"| Rank | Strategy | Avg Reward | Success Rate | Uses |\n"
                    f"|------|----------|------------|--------------|------|\n"
                )
                for r in type_rankings[:5]:
                    rankings_table += (
                        f"| #{r['rank']} | `{r['strategy']}` | "
                        f"{r['avg_reward']:.2f} | "
                        f"{r['success_rate']:.0%} | "
                        f"{r['total_uses']} |\n"
                    )

            # Build per-run trend table
            rewards = state_machine_data.reward_history
            num_runs = len(rewards)
            trend_table = (
                f"\n**Run-by-Run Trend** ({num_runs} runs):\n"
                f"| Run | Incident | Strategy | Reward | Verdict | Restored | Recovery |\n"
                f"|-----|----------|----------|--------|---------|----------|----------|\n"
            )
            for i in range(num_runs):
                r_reward = rewards[i]
                r_incident = state_machine_data.incident_type_history[i] if i < len(state_machine_data.incident_type_history) else "?"
                r_strategy = state_machine_data.strategy_history[i] if i < len(state_machine_data.strategy_history) else "?"
                r_verdict = state_machine_data.verdict_history[i] if i < len(state_machine_data.verdict_history) else "?"
                r_restored = state_machine_data.restored_history[i] if i < len(state_machine_data.restored_history) else False
                r_recovery = state_machine_data.recovery_time_history[i] if i < len(state_machine_data.recovery_time_history) else 0.0
                restored_icon = "Y" if r_restored else "N"
                trend_table += (
                    f"| {i + 1} | {r_incident} | {r_strategy} | "
                    f"{r_reward:.1f} | {r_verdict} | {restored_icon} | {r_recovery:.1f}s |\n"
                )

            # Rolling average summary
            rolling_avg = ""
            if num_runs >= 5:
                recent_avg = sum(rewards[-5:]) / 5
                overall_avg = sum(rewards) / num_runs
                delta = recent_avg - overall_avg
                direction = "+" if delta > 0 else "" if delta < 0 else ""
                success_count = sum(1 for r in state_machine_data.restored_history if r)
                rolling_avg = (
                    f"\n**Summary**: Run {run_index + 1}/{state_machine_data.max_runs} | "
                    f"Overall avg: {overall_avg:.1f} | Last-5 avg: {recent_avg:.1f} ({direction}{delta:.1f}) | "
                    f"Restored: {success_count}/{num_runs} ({success_count/num_runs:.0%})"
                )

            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"#### Strategy Manager — Updated{rolling_avg}"
                        f"{trend_table}"
                        f"{rankings_table}"
                    ),
                ),
                trace_id=state_machine_data.task_id,
            )

        # --- Step 5: Log observability data ---
        if len(state_machine_data.reward_history) >= 3:
            recent = state_machine_data.reward_history[-3:]
            logger.info(
                f"[Run {run_index + 1}] Learning stats: "
                f"recent_rewards={[round(r, 1) for r in recent]} "
                f"strategy_history={state_machine_data.strategy_history[-3:]}"
            )

        # --- Step 6: Periodic full summary milestone ---
        if (run_index + 1) % 10 == 0 and state_machine_data.task_id:
            await _emit_milestone_summary(state_machine_data, run_index + 1)

        # Advance run counter
        state_machine_data.run_index += 1

        # Loop back to incident detection
        return EVOOState.WAITING_FOR_INCIDENT


async def _emit_milestone_summary(data: EVOOData, run_count: int) -> None:
    """Emit a detailed milestone summary every 10 runs."""
    rewards = data.reward_history
    recovery_times = data.recovery_time_history

    if not rewards:
        return

    # Compute stats
    avg_reward_all = sum(rewards) / len(rewards)
    avg_reward_recent = sum(rewards[-10:]) / min(10, len(rewards))
    best_reward = max(rewards)
    avg_recovery = sum(recovery_times) / len(recovery_times) if recovery_times else 0
    best_recovery = min(recovery_times) if recovery_times else 0

    # Strategy usage
    from collections import Counter
    strategy_counts = Counter(data.strategy_history)
    top_strategies = strategy_counts.most_common(3)

    await adk.messages.create(
        task_id=data.task_id,
        content=TextContent(
            author="agent",
            content=(
                f"\n## EVOO Milestone Report — {run_count} Runs Completed\n\n"
                f"### Reward Metrics\n"
                f"| Metric | Value |\n"
                f"|--------|-------|\n"
                f"| Average Reward (all runs) | {avg_reward_all:.2f} |\n"
                f"| Average Reward (last 10) | {avg_reward_recent:.2f} |\n"
                f"| Best Reward Achieved | {best_reward:.2f} |\n"
                f"| Average Recovery Time | {avg_recovery:.1f}s |\n"
                f"| Best Recovery Time | {best_recovery:.1f}s |\n\n"
                f"### Most Used Strategies\n"
                + "\n".join([f"- `{s}`: {c} times" for s, c in top_strategies])
                + "\n\n"
                f"### Learning Trend\n"
                f"Early avg (first 5): {sum(rewards[:5]) / min(5, len(rewards)):.2f}\n"
                f"Recent avg (last 5): {sum(rewards[-5:]) / min(5, len(rewards)):.2f}\n"
            ),
        ),
        trace_id=data.task_id,
    )
