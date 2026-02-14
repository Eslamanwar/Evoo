"""Idle state workflow - waits for incidents or user input."""

from typing import Optional, override

from temporalio import workflow

from agentex.lib import adk
from agentex.lib.sdk.state_machine.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.memory.experience_store import ExperienceStore
from project.models.enums import EvooState
from project.state_machines.evoo import EvooData
from project.strategy.strategy_manager import StrategyManager

logger = make_logger(__name__)

# Shared instances (set by worker initialization)
_experience_store: Optional[ExperienceStore] = None
_strategy_manager: Optional[StrategyManager] = None


def set_idle_instances(store: ExperienceStore, manager: StrategyManager) -> None:
    """Set shared instances for the idle workflow."""
    global _experience_store, _strategy_manager
    _experience_store = store
    _strategy_manager = manager


class IdleWorkflow(StateWorkflow):
    """Workflow for the IDLE state.

    In auto mode: generates a new incident and transitions to DETECTING_INCIDENT.
    In manual mode: waits for user input to trigger an incident.
    Shows evolution progress to the user at the start of each new cycle.
    """

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Execute the idle state logic.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Next state to transition to.
        """
        if state_machine_data is None:
            return EvooState.FAILED

        # Check if we've reached max incidents
        if state_machine_data.incident_count >= state_machine_data.max_incidents:
            logger.info(
                f"Max incidents reached ({state_machine_data.max_incidents}). "
                "Completing learning loop."
            )

            # Send comprehensive final evolution report
            if state_machine_data.task_id:
                await self._send_final_evolution_report(state_machine_data)

            return EvooState.COMPLETED

        if state_machine_data.auto_mode:
            # Auto mode: immediately transition to incident detection
            next_cycle = state_machine_data.incident_count + 1
            logger.info(
                f"Auto mode: Starting incident cycle {next_cycle}"
                f"/{state_machine_data.max_incidents}"
            )

            # Send evolution progress banner (skip for first cycle)
            if state_machine_data.task_id and state_machine_data.incident_count > 0:
                await self._send_cycle_banner(state_machine_data)

            # Send welcome message on first cycle
            if state_machine_data.task_id and state_machine_data.incident_count == 0:
                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=(
                            f"### 🧬 EVOO — Evolutionary Operations Optimizer\n\n"
                            f"Starting autonomous SRE learning loop with **{state_machine_data.max_incidents}** incident cycles.\n\n"
                            f"**How EVOO evolves:**\n"
                            f"1. 🚨 **Detect** — Identify production incidents using LLM analysis\n"
                            f"2. 🧠 **Plan** — Select remediation strategy (LLM + historical data)\n"
                            f"3. ⚡ **Execute** — Run remediation actions\n"
                            f"4. 📊 **Evaluate** — Score results with reward function + LLM judge\n"
                            f"5. 📚 **Learn** — Store experience, update strategy rankings\n"
                            f"6. 🔄 **Repeat** — Each cycle improves decision-making\n\n"
                            f"Watch the reward trend and strategy rankings evolve over time!\n\n"
                            f"---\n"
                        ),
                    ),
                    trace_id=state_machine_data.task_id,
                )

            # Reset state for new incident
            state_machine_data.reset_for_new_incident()

            return EvooState.DETECTING_INCIDENT
        else:
            # Manual mode: wait for user input
            logger.info("Manual mode: Waiting for user input to trigger incident...")
            state_machine_data.waiting_for_user_input = True

            await workflow.wait_condition(
                lambda: not state_machine_data.waiting_for_user_input
            )

            # Reset state for new incident
            state_machine_data.reset_for_new_incident()

            return EvooState.DETECTING_INCIDENT

    async def _send_cycle_banner(self, data: EvooData) -> None:
        """Send a cycle transition banner showing evolution progress."""
        metrics = data.agent_metrics
        next_cycle = data.incident_count + 1
        reward_history = metrics.get("reward_history", [])
        exploration_rate = _strategy_manager.get_exploration_rate() if _strategy_manager else 0.3

        # Determine agent's current phase
        if next_cycle <= 3:
            phase = "🔍 Exploration Phase"
            phase_desc = "Trying different strategies to build experience"
        elif exploration_rate > 0.15:
            phase = "🔄 Learning Phase"
            phase_desc = "Balancing exploration with proven strategies"
        else:
            phase = "🎯 Optimization Phase"
            phase_desc = "Exploiting best-known strategies"

        # Last reward indicator
        last_reward = reward_history[-1] if reward_history else 0
        if last_reward > 80:
            reward_emoji = "🟢"
        elif last_reward > 40:
            reward_emoji = "🟡"
        else:
            reward_emoji = "🔴"

        banner = (
            f"\n{'═' * 50}\n"
            f"### 🔄 Cycle {next_cycle}/{data.max_incidents} — {phase}\n"
            f"*{phase_desc}*\n\n"
            f"Last reward: {reward_emoji} **{last_reward:.1f}** | "
            f"Avg reward: **{metrics.get('average_reward', 0):.1f}** | "
            f"Exploration: **{exploration_rate:.0%}**\n"
            f"{'═' * 50}\n"
        )

        await adk.messages.create(
            task_id=data.task_id,
            content=TextContent(author="agent", content=banner),
            trace_id=data.task_id,
        )

    async def _send_final_evolution_report(self, data: EvooData) -> None:
        """Send a comprehensive final evolution report."""
        metrics = data.agent_metrics
        rankings = data.strategy_rankings
        reward_history = metrics.get("reward_history", [])
        recovery_history = metrics.get("recovery_time_history", [])
        total = metrics.get("total_incidents", 0)
        success_count = metrics.get("total_successful_remediations", 0)
        fail_count = metrics.get("total_failed_remediations", 0)

        # Build sparkline for full reward history
        sparkline = ""
        if reward_history:
            max_r = max(reward_history) if max(reward_history) > 0 else 1
            min_r = min(reward_history)
            bars = "▁▂▃▄▅▆▇█"
            for r in reward_history:
                normalized = (r - min_r) / (max_r - min_r) if max_r != min_r else 0.5
                idx = min(int(normalized * (len(bars) - 1)), len(bars) - 1)
                sparkline += bars[idx]

        # Early vs late comparison
        evolution_table = ""
        if len(reward_history) >= 4:
            half = len(reward_history) // 2
            early_rewards = reward_history[:half]
            late_rewards = reward_history[half:]
            early_recovery = recovery_history[:half] if recovery_history else []
            late_recovery = recovery_history[half:] if recovery_history else []

            early_avg_reward = sum(early_rewards) / len(early_rewards)
            late_avg_reward = sum(late_rewards) / len(late_rewards)
            reward_change = late_avg_reward - early_avg_reward
            reward_pct = (reward_change / abs(early_avg_reward) * 100) if early_avg_reward != 0 else 0

            early_avg_recovery = sum(early_recovery) / len(early_recovery) if early_recovery else 0
            late_avg_recovery = sum(late_recovery) / len(late_recovery) if late_recovery else 0
            recovery_change = early_avg_recovery - late_avg_recovery

            early_success = sum(1 for r in early_rewards if r > 50) / len(early_rewards)
            late_success = sum(1 for r in late_rewards if r > 50) / len(late_rewards)

            trend_icon = "📈" if reward_change > 5 else "📉" if reward_change < -5 else "➡️"

            evolution_table = (
                f"\n### {trend_icon} Evolution Comparison\n"
                f"```\n"
                f"{'Metric':<25} {'First Half':>12} {'Second Half':>12} {'Change':>12}\n"
                f"{'─' * 61}\n"
                f"{'Avg Reward':<25} {early_avg_reward:>12.1f} {late_avg_reward:>12.1f} {reward_change:>+12.1f}\n"
                f"{'Avg Recovery Time':<25} {early_avg_recovery:>11.1f}s {late_avg_recovery:>11.1f}s {recovery_change:>+11.1f}s\n"
                f"{'Success Rate':<25} {early_success:>11.0%} {late_success:>11.0%} {(late_success - early_success):>+11.0%}\n"
                f"{'Best Reward':<25} {max(early_rewards):>12.1f} {max(late_rewards):>12.1f}\n"
                f"{'Worst Reward':<25} {min(early_rewards):>12.1f} {min(late_rewards):>12.1f}\n"
                f"```\n"
            )

        # Top strategies table
        strategies_table = ""
        if rankings:
            strategies_table = "\n### 🏆 Final Strategy Rankings\n```\n"
            strategies_table += f"{'#':<3} {'Strategy':<30} {'Type':<20} {'Reward':>8} {'Success':>8} {'Uses':>5}\n"
            strategies_table += f"{'─' * 74}\n"
            for i, r in enumerate(rankings[:10]):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f" {i+1}"
                strategies_table += (
                    f"{medal:<3} {r['strategy']:<30} {r['incident_type']:<20} "
                    f"{r['average_reward']:>8.1f} {r['success_rate']:>7.0%} {r['uses']:>5}\n"
                )
            strategies_table += "```\n"

        # Determine overall verdict
        if len(reward_history) >= 4:
            half = len(reward_history) // 2
            early_avg = sum(reward_history[:half]) / half
            late_avg = sum(reward_history[half:]) / (len(reward_history) - half)
            if late_avg > early_avg + 10:
                verdict = "🟢 **EVOO demonstrated clear learning and improvement!**"
            elif late_avg > early_avg:
                verdict = "🟡 **EVOO showed modest improvement over time.**"
            else:
                verdict = "🔴 **EVOO needs more iterations or strategy tuning to show improvement.**"
        else:
            verdict = "⚪ **Not enough data to assess evolution trend.**"

        report = (
            f"\n{'═' * 60}\n"
            f"## 🏁 EVOO Learning Loop Complete\n"
            f"### Final Evolution Report\n"
            f"{'═' * 60}\n\n"
            f"**Total Cycles:** {total} | "
            f"**Success Rate:** {success_count}/{total} ({success_count/total:.0%})\n"
            f"**Avg Reward:** {metrics.get('average_reward', 0):.2f} | "
            f"**Avg Recovery:** {metrics.get('average_recovery_time', 0):.1f}s\n\n"
            f"**Reward History:** `{sparkline}`\n"
            f"  *(left = early runs, right = recent runs)*\n"
            f"{evolution_table}"
            f"{strategies_table}"
            f"\n### Verdict\n{verdict}\n"
            f"\n{'═' * 60}\n"
        )

        await adk.messages.create(
            task_id=data.task_id,
            content=TextContent(author="agent", content=report),
            trace_id=data.task_id,
        )