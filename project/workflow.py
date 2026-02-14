"""Main workflow for EVOO — Evolutionary Operations Optimizer.

Orchestrates the autonomous SRE learning loop:
    Detect Incident → Plan Remediation → Execute → Evaluate → Learn → Repeat
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from typing import Optional, override

from temporalio import workflow
from temporalio.common import RetryPolicy

from agentex.lib import adk
from agentex.lib.core.temporal.workflows.workflow import BaseWorkflow
from agentex.lib.core.temporal.types.workflow import SignalName
from agentex.lib.environment_variables import EnvironmentVariables
from agentex.lib.types.acp import CreateTaskParams, SendEventParams
from agentex.lib.utils.logging import make_logger
from agentex.lib.sdk.state_machine.state import State
from agentex.types.text_content import TextContent

from project.state_machines.evoo_agent import EVOOData, EVOOState, EVOOStateMachine
from project.workflows.idle.waiting_for_incident import WaitingForIncidentWorkflow
from project.workflows.planning.planning_remediation import PlanningRemediationWorkflow
from project.workflows.execution.executing_remediation import ExecutingRemediationWorkflow
from project.workflows.evaluation.evaluating_outcome import EvaluatingOutcomeWorkflow
from project.workflows.learning.updating_strategy import UpdatingStrategyWorkflow
from project.workflows.terminal_states import CompletedWorkflow, FailedWorkflow

environment_variables = EnvironmentVariables.refresh()

if environment_variables.WORKFLOW_NAME is None:
    raise ValueError("Environment variable WORKFLOW_NAME is not set")

if environment_variables.AGENT_NAME is None:
    raise ValueError("Environment variable AGENT_NAME is not set")

logger = make_logger(__name__)

MAX_RUNS = int(os.getenv("MAX_LEARNING_RUNS", "50"))


@workflow.defn(name=environment_variables.WORKFLOW_NAME)
class EVOOWorkflow(BaseWorkflow):
    """
    EVOO: Evolutionary Operations Optimizer

    An autonomous AI SRE agent that continuously improves its incident
    remediation strategy through a reward-based learning loop.

    Learning cycle:
        WAITING_FOR_INCIDENT
            ↓ (incident detected)
        PLANNING_REMEDIATION   ← LLM Planner + memory retrieval
            ↓
        EXECUTING_REMEDIATION  ← Tool execution engine
            ↓
        EVALUATING_OUTCOME     ← Numeric reward + LLM judge
            ↓
        UPDATING_STRATEGY      ← Strategy Manager update
            ↓
        WAITING_FOR_INCIDENT   ← (loop, max_runs times)
            ↓
        COMPLETED
    """

    def __init__(self):
        super().__init__(display_name=environment_variables.AGENT_NAME)

        self.state_machine = EVOOStateMachine(
            initial_state=EVOOState.WAITING_FOR_INCIDENT,
            states=[
                # Learning loop states
                State(
                    name=EVOOState.WAITING_FOR_INCIDENT,
                    workflow=WaitingForIncidentWorkflow(),
                ),
                State(
                    name=EVOOState.PLANNING_REMEDIATION,
                    workflow=PlanningRemediationWorkflow(),
                ),
                State(
                    name=EVOOState.EXECUTING_REMEDIATION,
                    workflow=ExecutingRemediationWorkflow(),
                ),
                State(
                    name=EVOOState.EVALUATING_OUTCOME,
                    workflow=EvaluatingOutcomeWorkflow(),
                ),
                State(
                    name=EVOOState.UPDATING_STRATEGY,
                    workflow=UpdatingStrategyWorkflow(),
                ),
                # Terminal states
                State(
                    name=EVOOState.COMPLETED,
                    workflow=CompletedWorkflow(),
                ),
                State(
                    name=EVOOState.FAILED,
                    workflow=FailedWorkflow(),
                ),
            ],
            state_machine_data=EVOOData(
                max_runs=MAX_RUNS,
                waiting_for_user_input=False,  # EVOO starts autonomously
            ),
        )

    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> None:
        """
        Entry point: start the EVOO learning loop.
        The agent begins autonomous operation immediately.
        """
        task_id = params.task.id
        self.state_machine.set_task_id(task_id)
        self.state_machine.state_machine_data.task_id = task_id

        logger.info(f"EVOO starting: task_id={task_id} max_runs={MAX_RUNS}")

        # Welcome message
        await adk.messages.create(
            task_id=task_id,
            content=TextContent(
                author="agent",
                content=(
                    f"# EVOO — Evolutionary Operations Optimizer\n\n"
                    f"**Mode**: Autonomous SRE Learning Loop\n"
                    f"**Planned runs**: {MAX_RUNS}\n"
                    f"**Exploration rate**: {os.getenv('EXPLORATION_RATE', '0.2')}\n\n"
                    f"EVOO will autonomously:\n"
                    f"1. Detect simulated production incidents\n"
                    f"2. Select remediation strategies (epsilon-greedy)\n"
                    f"3. Execute tool sequences\n"
                    f"4. Score outcomes with reward function + LLM judge\n"
                    f"5. Store experiences in memory\n"
                    f"6. Improve strategy selection over time\n\n"
                    f"*Starting learning loop now...*"
                ),
            ),
            trace_id=task_id,
        )

        # Run the state machine (full learning loop)
        await self.state_machine.run()

        logger.info(f"EVOO completed: task_id={task_id}")

    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        """
        Handle user signals during the learning run.
        Supports: stop command, config updates.
        """
        try:
            message = params.event.content
            event_content = message.content if hasattr(message, "content") else str(message)
            data = self.state_machine.state_machine_data

            if isinstance(event_content, str):
                event_lower = event_content.lower().strip()
                if event_lower in ("stop", "quit", "exit", "done"):
                    logger.info("User requested EVOO stop")
                    data.is_learning_complete = True
                elif event_lower.startswith("{"):
                    # JSON config update
                    try:
                        config = json.loads(event_content)
                        if "max_runs" in config:
                            data.max_runs = int(config["max_runs"])
                        if "exploration_rate" in config:
                            import os
                            os.environ["EXPLORATION_RATE"] = str(config["exploration_rate"])
                        logger.info(f"Config updated: {config}")
                    except json.JSONDecodeError:
                        pass

        except Exception as e:
            logger.warning(f"Signal handling error: {e}")
