"""EVOO: Planning Remediation state workflow.

This state implements the Planner agent — it:
1. Queries memory for best historical strategies and recent experiences
2. Uses epsilon-greedy to select exploit vs explore
3. LLM reasons about strategy selection (exploit path) with full memory context
4. Produces a RemediationPlan with tools to call
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

from project.state_machines.evoo_agent import EVOOData, EVOOState, RemediationPlan

logger = make_logger(__name__)


class PlanningRemediationWorkflow(StateWorkflow):
    """Planner agent: select the optimal remediation strategy."""

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EVOOData] = None,
    ) -> str:
        if state_machine_data is None or state_machine_data.current_incident is None:
            return EVOOState.FAILED

        incident = state_machine_data.current_incident
        run_index = state_machine_data.run_index

        logger.info(f"[Run {run_index + 1}] Planning remediation for {incident.incident_type.value}")

        # --- Step 1: Retrieve historical best strategy from memory ---
        best_strategy_data = await ActivityHelpers.execute_activity(
            activity_name="retrieve_best_strategy_activity",
            request={"incident_type": incident.incident_type.value, "top_k": 5},
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # --- Step 2: Retrieve recent experiences for memory context ---
        recent_experiences = await ActivityHelpers.execute_activity(
            activity_name="retrieve_recent_experiences_activity",
            request={"limit": 5},
            response_type=dict,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        # Build memory context for LLM-driven strategy selection
        memory_context = {
            "best_strategy_data": best_strategy_data,
            "recent_experiences": recent_experiences.get("experiences", []),
        }

        # --- Step 3: Epsilon-greedy strategy selection (LLM on exploit path) ---
        strategy_selection = await ActivityHelpers.execute_activity(
            activity_name="select_strategy_activity",
            request={
                "incident_type": incident.incident_type.value,
                "run_index": run_index,
                "force_explore": False,
                "severity": incident.severity.value,
                "description": incident.description,
                "metrics": state_machine_data.metrics_before.model_dump(mode="json") if state_machine_data.metrics_before else {},
                "memory_context": memory_context,
            },
            response_type=dict,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        strategy_name = strategy_selection["strategy"]
        tools_to_call = strategy_selection["tools_to_call"]
        tool_parameters = strategy_selection["tool_parameters"]
        is_exploratory = strategy_selection["is_exploratory"]
        selection_reason = strategy_selection.get("selection_reason", "unknown")
        llm_selected = strategy_selection.get("llm_selected", False)
        reasoning = strategy_selection.get("reasoning", selection_reason)

        # --- Step 4: Build the plan ---
        plan = RemediationPlan(
            strategy=strategy_name,
            tools_to_call=tools_to_call,
            tool_parameters=tool_parameters,
            reasoning=reasoning,
            confidence=0.8 if not is_exploratory else 0.5,
            is_exploratory=is_exploratory,
            llm_selected=llm_selected,
        )
        state_machine_data.current_plan = plan

        # Report to user
        if state_machine_data.task_id:
            exploit_label = "EXPLORE (random)" if is_exploratory else "EXPLOIT (LLM)" if llm_selected else "EXPLOIT (heuristic)"
            history_note = ""
            if best_strategy_data.get("best_strategy"):
                history_note = (
                    f"\n**Best Historical Strategy**: `{best_strategy_data['best_strategy']}` "
                    f"({best_strategy_data.get('experiences_found', 0)} past runs)"
                )

            await adk.messages.create(
                task_id=state_machine_data.task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"#### Planner Decision [{exploit_label}]\n"
                        f"**Strategy**: `{strategy_name}`{history_note}\n"
                        f"**Tools**: {', '.join(tools_to_call)}\n"
                        f"**Reasoning**: {reasoning}\n"
                    ),
                ),
                trace_id=state_machine_data.task_id,
            )

        logger.info(
            f"[Run {run_index + 1}] Plan: strategy={strategy_name} "
            f"explore={is_exploratory} llm={llm_selected} tools={len(tools_to_call)}"
        )

        return EVOOState.EXECUTING_REMEDIATION
