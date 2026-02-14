"""EVOO: Evaluating Outcome state workflow.

This state implements the Evaluator (Judge) agent — it:
1. Calculates the deterministic reward score
2. Calls the LLM judge for qualitative evaluation
3. Composes a complete Experience tuple
4. Stores the experience in memory
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, override
import uuid

from temporalio.common import RetryPolicy

from agentex.lib import adk
from agentex.lib.core.temporal.activities.activity_helpers import ActivityHelpers
from agentex.lib.sdk.state_machine import StateMachine
from agentex.lib.sdk.state_machine.state_workflow import StateWorkflow
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.models.experience import Experience
from project.state_machines.evoo_agent import EVOOData, EVOOState

logger = make_logger(__name__)


class EvaluatingOutcomeWorkflow(StateWorkflow):
    """Evaluator agent: score the remediation and store the experience."""

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
        task_id = state_machine_data.task_id or "no-task"

        before = state_machine_data.metrics_before
        after = state_machine_data.metrics_after
        sim_result = state_machine_data.simulated_system_state.get("sim_result", {})

        if before is None or after is None or plan is None:
            logger.error(f"[Run {run_index + 1}] Missing metrics for evaluation")
            return EVOOState.FAILED

        recovery_time = sim_result.get("recovery_time_seconds", 120.0)
        service_restored = sim_result.get("service_restored", False)
        infra_cost = sim_result.get("infrastructure_cost", 1.0)

        # --- Step 1: Calculate deterministic reward ---
        reward_result = await ActivityHelpers.execute_activity(
            activity_name="calculate_reward_activity",
            request={
                "metrics_before": before.model_dump(mode="json"),
                "metrics_after": after.model_dump(mode="json"),
                "recovery_time_seconds": recovery_time,
                "service_restored": service_restored,
                "infrastructure_cost": infra_cost,
                "strategy_name": plan.strategy,
                "incident_type": incident.incident_type.value,
            },
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        reward = reward_result.get("reward", 0.0)
        state_machine_data.current_reward = reward

        # --- Step 2: LLM qualitative evaluation ---
        llm_eval_result = await ActivityHelpers.execute_activity(
            activity_name="llm_evaluate_remediation_activity",
            request={
                "incident_type": incident.incident_type.value,
                "strategy_used": plan.strategy,
                "metrics_before": before.model_dump(mode="json"),
                "metrics_after": after.model_dump(mode="json"),
                "tool_results": state_machine_data.tool_execution_results,
                "recovery_time_seconds": recovery_time,
                "numeric_reward": reward,
                "task_id": task_id,
            },
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        evaluation = llm_eval_result.get("evaluation", {})
        llm_verdict = evaluation.get("verdict", "unknown")
        llm_analysis = evaluation.get("analysis", "")
        llm_score = evaluation.get("overall_score", 0)
        state_machine_data.last_llm_evaluation = llm_analysis

        # --- Step 3: Build experience tuple ---
        experience = Experience(
            id=str(uuid.uuid4())[:8],
            incident_type=incident.incident_type,
            metrics_before=before,
            strategy_used=plan.strategy,
            tools_called=plan.tools_to_call,
            tool_results=state_machine_data.tool_execution_results,
            metrics_after=after,
            recovery_time_seconds=recovery_time,
            reward=reward,
            llm_evaluation=llm_analysis,
            success=service_restored,
            timestamp=datetime.utcnow(),
            run_index=run_index,
        )
        state_machine_data.current_experience = experience

        # --- Step 4: Persist experience to memory ---
        await ActivityHelpers.execute_activity(
            activity_name="store_experience_activity",
            request=experience.model_dump(mode="json"),
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Track history for observability
        state_machine_data.reward_history.append(reward)
        state_machine_data.recovery_time_history.append(recovery_time)
        state_machine_data.strategy_history.append(plan.strategy)
        state_machine_data.incident_type_history.append(incident.incident_type.value)
        state_machine_data.verdict_history.append(llm_verdict)
        state_machine_data.restored_history.append(service_restored)

        # Report to user
        if state_machine_data.task_id:
            reward_breakdown = reward_result.get("breakdown", {})
            breakdown_lines = "\n".join(
                [f"| {k.replace('_', ' ').title()} | {'+' if v >= 0 else ''}{v:.1f} |"
                 for k, v in reward_breakdown.items()]
            )

            # Trend indicator
            recent = state_machine_data.reward_history[-5:]
            trend = ""
            if len(recent) >= 2:
                avg_new = sum(recent[-2:]) / 2
                avg_old = sum(recent[:-2]) / max(1, len(recent) - 2)
                trend = " (↑ improving)" if avg_new > avg_old else " (↓ declining)"

            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"#### Evaluator Results\n"
                        f"**Numeric Reward**: `{reward:.2f}`{trend}\n"
                        f"**LLM Verdict**: `{llm_verdict}` (score: {llm_score}/10)\n"
                        f"**LLM Analysis**: {llm_analysis}\n\n"
                        f"**Reward Breakdown**:\n"
                        f"| Component | Points |\n"
                        f"|-----------|--------|\n"
                        f"{breakdown_lines}\n"
                    ),
                ),
                trace_id=state_machine_data.task_id,
            )

        logger.info(
            f"[Run {run_index + 1}] Evaluation complete: reward={reward:.2f} "
            f"verdict={llm_verdict} restored={service_restored}"
        )

        return EVOOState.UPDATING_STRATEGY
