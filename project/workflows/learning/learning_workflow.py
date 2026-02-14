"""Learning state workflow - stores experience and updates strategy rankings."""

import uuid
from typing import Optional, override

from temporalio import workflow

from agentex.lib import adk
from agentex.lib.sdk.state_machine.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.memory.experience_store import ExperienceStore
from project.models.enums import EvooState, IncidentType
from project.models.experience import Experience
from project.state_machines.evoo import EvooData
from project.strategy.strategy_manager import StrategyManager

logger = make_logger(__name__)

# Shared instances (set by worker initialization)
_experience_store: Optional[ExperienceStore] = None
_strategy_manager: Optional[StrategyManager] = None


def set_learning_instances(store: ExperienceStore, manager: StrategyManager) -> None:
    """Set shared instances for the learning workflow."""
    global _experience_store, _strategy_manager
    _experience_store = store
    _strategy_manager = manager


class LearningWorkflow(StateWorkflow):
    """Workflow for the LEARNING state.

    Stores the experience tuple in memory, updates strategy rankings,
    and prepares for the next incident cycle.
    """

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Execute the learning step.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Next state to transition to (IDLE for next cycle).
        """
        if state_machine_data is None:
            return EvooState.FAILED

        try:
            logger.info("📚 Learning from remediation experience")

            # Create experience tuple
            try:
                incident_type = IncidentType(state_machine_data.current_incident_type)
            except (ValueError, TypeError):
                incident_type = IncidentType.SERVICE_CRASH

            experience = Experience(
                id=f"EXP-{uuid.uuid4().hex[:8].upper()}",
                incident_type=incident_type,
                incident_id=state_machine_data.current_incident_id or "unknown",
                incident_severity=state_machine_data.current_incident_severity or "medium",
                metrics_before=state_machine_data.metrics_before,
                strategy_used=state_machine_data.selected_strategy or "unknown",
                tools_called=state_machine_data.tools_called,
                actions_taken=state_machine_data.actions_executed,
                metrics_after=state_machine_data.metrics_after,
                recovery_time_seconds=state_machine_data.total_recovery_time,
                reward=state_machine_data.adjusted_reward or state_machine_data.reward,
                reward_breakdown=state_machine_data.reward_breakdown,
                success=state_machine_data.service_restored,
                llm_evaluation=state_machine_data.llm_evaluation,
            )

            # Store experience in memory
            # Note: In a Temporal workflow, we should use activities for side effects.
            # However, since ExperienceStore writes to local disk, we handle it here
            # for simplicity. In production, this would be an activity writing to a DB.
            if _experience_store:
                _experience_store.store_experience(experience)
                state_machine_data.experience_stored = True

                # Update strategy manager
                if _strategy_manager:
                    if state_machine_data.service_restored:
                        _strategy_manager.mark_strategy_success(
                            strategy_name=state_machine_data.selected_strategy or "unknown",
                            incident_type=incident_type,
                            reward=experience.reward,
                            recovery_time=experience.recovery_time_seconds,
                        )
                    else:
                        _strategy_manager.mark_strategy_failure(
                            strategy_name=state_machine_data.selected_strategy or "unknown",
                            incident_type=incident_type,
                            reward=experience.reward,
                            recovery_time=experience.recovery_time_seconds,
                        )

                # Get updated metrics and rankings
                agent_metrics = _experience_store.get_agent_metrics()
                strategy_rankings = _experience_store.get_strategy_rankings()

                state_machine_data.agent_metrics = agent_metrics
                state_machine_data.strategy_rankings = strategy_rankings
                state_machine_data.strategy_rankings_updated = True

                logger.info(
                    f"Experience stored: {experience.id}, "
                    f"Total experiences: {_experience_store.get_experience_count()}"
                )
            else:
                logger.warning("No experience store available - learning skipped")

            # Send learning summary message with evolution tracking
            if state_machine_data.task_id:
                metrics = state_machine_data.agent_metrics
                rankings = state_machine_data.strategy_rankings

                # Format top strategies
                top_strategies = ""
                if rankings:
                    for i, ranking in enumerate(rankings[:5]):
                        top_strategies += (
                            f"  {i + 1}. **{ranking['strategy']}** "
                            f"({ranking['incident_type']}): "
                            f"reward={ranking['average_reward']:.1f}, "
                            f"success={ranking['success_rate']:.0%}, "
                            f"uses={ranking['uses']}\n"
                        )
                else:
                    top_strategies = "  No strategy data yet\n"

                exploration_rate = _strategy_manager.get_exploration_rate() if _strategy_manager else 0.3

                # Build evolution visualization
                reward_history = metrics.get("reward_history", [])
                recovery_history = metrics.get("recovery_time_history", [])
                total = metrics.get("total_incidents", 0)
                success_count = metrics.get("total_successful_remediations", 0)
                fail_count = metrics.get("total_failed_remediations", 0)
                success_rate = success_count / total if total > 0 else 0

                # Reward trend sparkline (last 10 rewards)
                recent_rewards = reward_history[-10:] if reward_history else []
                sparkline = ""
                if recent_rewards:
                    max_r = max(recent_rewards) if max(recent_rewards) > 0 else 1
                    min_r = min(recent_rewards)
                    bars = "▁▂▃▄▅▆▇█"
                    for r in recent_rewards:
                        normalized = (r - min_r) / (max_r - min_r) if max_r != min_r else 0.5
                        idx = min(int(normalized * (len(bars) - 1)), len(bars) - 1)
                        sparkline += bars[idx]

                # Early vs recent comparison
                evolution_comparison = ""
                if len(reward_history) >= 4:
                    half = len(reward_history) // 2
                    early_avg = sum(reward_history[:half]) / half
                    recent_avg = sum(reward_history[half:]) / (len(reward_history) - half)
                    improvement = recent_avg - early_avg
                    improvement_pct = (improvement / abs(early_avg) * 100) if early_avg != 0 else 0

                    early_recovery = sum(recovery_history[:half]) / half if recovery_history else 0
                    recent_recovery = sum(recovery_history[half:]) / (len(recovery_history) - half) if recovery_history else 0
                    recovery_improvement = early_recovery - recent_recovery

                    trend_icon = "📈" if improvement > 0 else "📉" if improvement < 0 else "➡️"

                    evolution_comparison = (
                        f"\n**{trend_icon} Evolution Progress:**\n"
                        f"```\n"
                        f"              Early Runs    →    Recent Runs\n"
                        f"  Avg Reward:  {early_avg:>8.1f}     →    {recent_avg:>8.1f}  ({improvement:+.1f}, {improvement_pct:+.0f}%)\n"
                        f"  Recovery:    {early_recovery:>8.1f}s    →    {recent_recovery:>8.1f}s ({recovery_improvement:+.1f}s)\n"
                        f"```\n"
                    )

                # Progress bar for learning loop
                progress = state_machine_data.incident_count / state_machine_data.max_incidents
                filled = int(progress * 20)
                progress_bar = "█" * filled + "░" * (20 - filled)

                learning_msg = (
                    f"### 📚 Learning Update — Cycle {state_machine_data.incident_count}/{state_machine_data.max_incidents}\n\n"
                    f"**Progress:** `[{progress_bar}]` {progress:.0%}\n\n"
                    f"**This Cycle:**\n"
                    f"- Experience: `{experience.id}`\n"
                    f"- Strategy: **{experience.strategy_used}**\n"
                    f"- Reward: **{experience.reward:.2f}** {'✅ Success' if experience.success else '❌ Failed'}\n"
                    f"- Recovery Time: {experience.recovery_time_seconds:.1f}s\n\n"
                    f"**Reward Trend:** `{sparkline}` (last {len(recent_rewards)} cycles)\n\n"
                    f"**Overall Performance:**\n"
                    f"- Total: {total} incidents ({success_count}✅ / {fail_count}❌) — {success_rate:.0%} success rate\n"
                    f"- Avg Reward: {metrics.get('average_reward', 0):.2f}\n"
                    f"- Recent Avg Reward (last 5): {metrics.get('recent_average_reward', 0):.2f}\n"
                    f"- Avg Recovery Time: {metrics.get('average_recovery_time', 0):.1f}s\n"
                    f"- Exploration Rate: {exploration_rate:.0%}\n"
                    f"{evolution_comparison}"
                    f"\n**Top Strategies:**\n{top_strategies}"
                    f"\n---\n"
                )

                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=learning_msg,
                    ),
                    trace_id=state_machine_data.task_id,
                )

            logger.info(
                f"Learning complete. Avg reward: {state_machine_data.agent_metrics.get('average_reward', 0):.2f}, "
                f"Trend: {state_machine_data.agent_metrics.get('reward_improvement_trend', 0):+.2f}"
            )

            # Transition back to IDLE for next cycle
            return EvooState.IDLE

        except Exception as e:
            logger.error(f"Error in learning step: {e}")
            state_machine_data.error_message = f"Learning failed: {str(e)}"
            # Even if learning fails, continue to next cycle
            return EvooState.IDLE