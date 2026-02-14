"""Main workflow for EVOO - Evolutionary Operations Optimizer agent."""

import asyncio
from typing import override

from temporalio import workflow

from agentex.lib import adk
from agentex.lib.core.temporal.types.workflow import SignalName
from agentex.lib.core.temporal.workflows.workflow import BaseWorkflow
from agentex.lib.environment_variables import EnvironmentVariables
from agentex.lib.sdk.state_machine.state import State
from agentex.lib.types.acp import CreateTaskParams, SendEventParams
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent

from project.models.enums import EvooState
from project.state_machines.evoo import EvooData, EvooStateMachine
from project.workflows.idle.idle_workflow import IdleWorkflow
from project.workflows.detection.detecting_incident_workflow import DetectingIncidentWorkflow
from project.workflows.planning.planning_workflow import PlanningRemediationWorkflow
from project.workflows.execution.execution_workflow import ExecutingRemediationWorkflow
from project.workflows.evaluation.evaluation_workflow import EvaluatingOutcomeWorkflow
from project.workflows.learning.learning_workflow import LearningWorkflow
from project.workflows.terminal_states import CompletedWorkflow, FailedWorkflow

environment_variables = EnvironmentVariables.refresh()

if environment_variables.WORKFLOW_NAME is None:
    raise ValueError("Environment variable WORKFLOW_NAME is not set")

if environment_variables.AGENT_NAME is None:
    raise ValueError("Environment variable AGENT_NAME is not set")

logger = make_logger(__name__)


@workflow.defn(name=environment_variables.WORKFLOW_NAME)
class EvooWorkflow(BaseWorkflow):
    """EVOO - Evolutionary Operations Optimizer Workflow.

    An autonomous AI agent that behaves like a Site Reliability Engineer (SRE)
    and continuously improves its incident remediation strategy over time
    using feedback, memory, and strategy optimization.

    Learning Loop:
        IDLE → DETECTING_INCIDENT → PLANNING_REMEDIATION → EXECUTING_REMEDIATION
        → EVALUATING_OUTCOME → LEARNING → IDLE (repeat)
    """

    def __init__(self):
        """Initialize the EVOO workflow with state machine."""
        super().__init__(display_name=environment_variables.AGENT_NAME)

        # Initialize state machine with all workflow states
        self.state_machine = EvooStateMachine(
            initial_state=EvooState.IDLE,
            states=[
                State(
                    name=EvooState.IDLE,
                    workflow=IdleWorkflow(),
                ),
                State(
                    name=EvooState.DETECTING_INCIDENT,
                    workflow=DetectingIncidentWorkflow(),
                ),
                State(
                    name=EvooState.PLANNING_REMEDIATION,
                    workflow=PlanningRemediationWorkflow(),
                ),
                State(
                    name=EvooState.EXECUTING_REMEDIATION,
                    workflow=ExecutingRemediationWorkflow(),
                ),
                State(
                    name=EvooState.EVALUATING_OUTCOME,
                    workflow=EvaluatingOutcomeWorkflow(),
                ),
                State(
                    name=EvooState.LEARNING,
                    workflow=LearningWorkflow(),
                ),
                State(
                    name=EvooState.COMPLETED,
                    workflow=CompletedWorkflow(),
                ),
                State(
                    name=EvooState.FAILED,
                    workflow=FailedWorkflow(),
                ),
            ],
            state_machine_data=EvooData(),
            trace_transitions=True,
        )

    @override
    @workflow.signal(name=SignalName.RECEIVE_EVENT)
    async def on_task_event_send(self, params: SendEventParams) -> None:
        """Handle incoming user messages.

        Users can:
        - Trigger manual incidents
        - Adjust settings (max_incidents, auto_mode)
        - Query agent status

        Args:
            params: Event parameters containing the user's message.
        """
        state_data = self.state_machine.get_state_machine_data()
        task = params.task
        message = params.event.content

        # Extract message content
        message_content = ""
        if hasattr(message, "content"):
            content_val = getattr(message, "content", "")
            if isinstance(content_val, str):
                message_content = content_val.strip()

        logger.info(f"Received message: {message_content[:100]}...")

        # Create span for tracing
        if not state_data.current_span:
            state_data.current_span = await adk.tracing.start_span(
                trace_id=task.id,
                name=f"Turn {state_data.current_turn}",
                input={
                    "task_id": task.id,
                    "message": message_content,
                },
            )

        state_data.messages_received += 1
        state_data.current_turn += 1

        # Echo user message
        await adk.messages.create(
            task_id=task.id,
            content=TextContent(
                author="user",
                content=message_content,
            ),
            trace_id=task.id,
            parent_span_id=state_data.current_span.id if state_data.current_span else None,
        )

        # Handle commands
        msg_lower = message_content.lower().strip()

        if msg_lower.startswith("start") or msg_lower == "run":
            # Start the learning loop
            state_data.auto_mode = True
            state_data.learning_loop_active = True
            state_data.waiting_for_user_input = False

            await adk.messages.create(
                task_id=task.id,
                content=TextContent(
                    author="agent",
                    content="🚀 Starting EVOO autonomous learning loop...",
                ),
                trace_id=task.id,
            )

        elif msg_lower.startswith("trigger"):
            # Trigger a manual incident
            state_data.waiting_for_user_input = False

            await adk.messages.create(
                task_id=task.id,
                content=TextContent(
                    author="agent",
                    content="🔔 Triggering manual incident...",
                ),
                trace_id=task.id,
            )

        elif msg_lower.startswith("status"):
            # Show current status
            metrics = state_data.agent_metrics
            current_state = self.state_machine.get_current_state()

            status_msg = (
                f"📊 **EVOO Status**\n\n"
                f"**State:** {current_state}\n"
                f"**Incidents Processed:** {state_data.incident_count}/{state_data.max_incidents}\n"
                f"**Auto Mode:** {'On' if state_data.auto_mode else 'Off'}\n"
                f"**Avg Reward:** {metrics.get('average_reward', 0):.2f}\n"
                f"**Avg Recovery Time:** {metrics.get('average_recovery_time', 0):.1f}s\n"
                f"**Reward Trend:** {metrics.get('reward_improvement_trend', 0):+.2f}\n"
            )

            await adk.messages.create(
                task_id=task.id,
                content=TextContent(
                    author="agent",
                    content=status_msg,
                ),
                trace_id=task.id,
            )

        elif msg_lower.startswith("set max"):
            # Set max incidents
            try:
                parts = message_content.split()
                max_val = int(parts[-1])
                state_data.max_incidents = max_val
                await adk.messages.create(
                    task_id=task.id,
                    content=TextContent(
                        author="agent",
                        content=f"✅ Max incidents set to {max_val}",
                    ),
                    trace_id=task.id,
                )
            except (ValueError, IndexError):
                await adk.messages.create(
                    task_id=task.id,
                    content=TextContent(
                        author="agent",
                        content="❌ Usage: set max <number>",
                    ),
                    trace_id=task.id,
                )

        else:
            # Default: add to conversation history
            state_data.conversation_history.append({
                "role": "user",
                "content": message_content,
            })
            state_data.waiting_for_user_input = False

    @override
    @workflow.run
    async def on_task_create(self, params: CreateTaskParams) -> None:
        """Initialize and run the EVOO workflow.

        Args:
            params: Task creation parameters.
        """
        task = params.task

        # Set task ID in state machine
        self.state_machine.set_task_id(task.id)

        # Initialize state data
        state_data = self.state_machine.get_state_machine_data()
        state_data.task_id = task.id

        logger.info(f"Starting EVOO workflow for task: {task.id}")

        # Send welcome message
        await adk.messages.create(
            task_id=task.id,
            content=TextContent(
                author="agent",
                content=(
                    "🧬 **EVOO - Evolutionary Operations Optimizer**\n\n"
                    "I'm an autonomous SRE agent that learns to remediate production incidents "
                    "through experience and continuous improvement.\n\n"
                    "**How I work:**\n"
                    "1. 🚨 Detect production incidents\n"
                    "2. 🧠 Plan remediation using learned strategies\n"
                    "3. ⚡ Execute remediation actions\n"
                    "4. 📊 Evaluate outcomes with reward scoring\n"
                    "5. 📚 Learn and improve for next time\n\n"
                    "**Commands:**\n"
                    "- `start` or `run` - Start the autonomous learning loop\n"
                    "- `trigger` - Trigger a manual incident\n"
                    "- `status` - Show current agent status\n"
                    "- `set max <N>` - Set max incidents per loop\n\n"
                    "Starting autonomous learning loop with 10 incidents...\n"
                ),
            ),
            trace_id=task.id,
        )

        # Start in auto mode
        state_data.auto_mode = True
        state_data.learning_loop_active = True

        try:
            # Run the state machine
            await self.state_machine.run()

        except asyncio.CancelledError as error:
            logger.warning(f"Task canceled by user: {task.id}")
            raise error

        except Exception as error:
            logger.error(f"Workflow error for task {task.id}: {str(error)}")

            try:
                await adk.messages.create(
                    task_id=task.id,
                    content=TextContent(
                        author="agent",
                        content=f"❌ EVOO encountered an error: {str(error)}",
                    ),
                    trace_id=task.id,
                )
            except Exception as msg_error:
                logger.error(f"Failed to send error message: {str(msg_error)}")

            state_data.error_message = str(error)
            await self.state_machine.transition(EvooState.FAILED)

            raise error
