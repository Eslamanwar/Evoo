"""Detecting incident state workflow - generates and detects incidents."""

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

    if tool_name == "generate_incident":
        return (
            f"Incident generated: {result.get('incident_type', 'unknown')} "
            f"(severity: {result.get('severity', 'unknown')})"
        )
    if tool_name == "get_incident_state":
        if result.get("has_incident"):
            inc = result.get("incident", {})
            return (
                f"Active incident: {inc.get('incident_type', 'unknown')} | "
                f"Severity: {inc.get('severity', 'unknown')} | "
                f"Health: {result.get('health_score', 0):.3f}"
            )
        return "No active incident detected"
    if tool_name == "query_metrics":
        m = result.get("metrics", {})
        return (
            f"Latency: {m.get('latency_ms', 0):.0f}ms | "
            f"CPU: {m.get('cpu_percent', 0):.1f}% | "
            f"Memory: {m.get('memory_percent', 0):.1f}% | "
            f"Error rate: {m.get('error_rate', 0):.2%} | "
            f"Healthy: {result.get('is_healthy', False)}"
        )
    if tool_name == "analyze_logs":
        patterns = result.get("patterns", [])
        causes = result.get("root_cause_candidates", [])
        return (
            f"Patterns found: {len(patterns)} | "
            f"Root cause candidates: {len(causes)}"
        )
    if tool_name == "predict_incident_type":
        preds = result.get("predictions", [])
        if preds:
            top = preds[0]
            return f"Predicted: {top.get('type', 'unknown')} (confidence: {top.get('confidence', 0):.0%})"
        return "No prediction available"

    return f"Completed | Keys: {', '.join(list(result.keys())[:5])}"


class DetectingIncidentWorkflow(StateWorkflow):
    """Workflow for the DETECTING_INCIDENT state.

    Generates a simulated incident and captures initial metrics.
    Uses tools to analyze the incident and predict its type.
    """

    @override
    async def execute(
        self,
        state_machine: StateMachine,
        state_machine_data: Optional[EvooData] = None,
    ) -> str:
        """Detect and characterize an incident.

        Args:
            state_machine: The state machine instance.
            state_machine_data: Current state data.

        Returns:
            Next state to transition to.
        """
        if state_machine_data is None:
            return EvooState.FAILED

        try:
            state_machine_data.incident_count += 1
            logger.info(
                f"🚨 Detecting incident #{state_machine_data.incident_count}"
            )

            task_id = state_machine_data.task_id
            trace_id = state_machine_data.task_id

            # --- Tool: generate_incident ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="generate_incident",
                        arguments={},
                    ),
                    trace_id=trace_id,
                )

            incident_gen_json = await workflow.execute_activity(
                "generate_incident",
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            incident_gen = json.loads(incident_gen_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="generate_incident",
                        content=_format_tool_response("generate_incident", incident_gen),
                    ),
                    trace_id=trace_id,
                )

            # --- Tool: get_incident_state ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="get_incident_state",
                        arguments={},
                    ),
                    trace_id=trace_id,
                )

            incident_state_json = await workflow.execute_activity(
                "get_incident_state",
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            incident_state = json.loads(incident_state_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="get_incident_state",
                        content=_format_tool_response("get_incident_state", incident_state),
                    ),
                    trace_id=trace_id,
                )

            # --- Tool: query_metrics ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="query_metrics",
                        arguments={},
                    ),
                    trace_id=trace_id,
                )

            metrics_json = await workflow.execute_activity(
                "query_metrics",
                start_to_close_timeout=workflow.timedelta(seconds=30),
            )
            metrics = json.loads(metrics_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="query_metrics",
                        content=_format_tool_response("query_metrics", metrics),
                    ),
                    trace_id=trace_id,
                )

            # --- Tool: analyze_logs ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="analyze_logs",
                        arguments={},
                    ),
                    trace_id=trace_id,
                )

            log_analysis_json = await workflow.execute_activity(
                "analyze_logs",
                start_to_close_timeout=workflow.timedelta(minutes=5),
            )
            log_analysis = json.loads(log_analysis_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="analyze_logs",
                        content=_format_tool_response("analyze_logs", log_analysis),
                    ),
                    trace_id=trace_id,
                )

            # --- Tool: predict_incident_type ---
            tool_call_id = f"tool_{uuid.uuid4().hex[:12]}"
            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolRequestContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="predict_incident_type",
                        arguments={},
                    ),
                    trace_id=trace_id,
                )

            prediction_json = await workflow.execute_activity(
                "predict_incident_type",
                start_to_close_timeout=workflow.timedelta(minutes=5),
            )
            prediction = json.loads(prediction_json)

            if task_id:
                await adk.messages.create(
                    task_id=task_id,
                    content=ToolResponseContent(
                        author="agent",
                        tool_call_id=tool_call_id,
                        name="predict_incident_type",
                        content=_format_tool_response("predict_incident_type", prediction),
                    ),
                    trace_id=trace_id,
                )

            # Store incident data in state
            if incident_state.get("has_incident"):
                incident = incident_state["incident"]
                state_machine_data.current_incident_id = incident.get("id", "unknown")
                state_machine_data.current_incident_type = incident.get("incident_type", "unknown")
                state_machine_data.current_incident_severity = incident.get("severity", "medium")
                state_machine_data.incident_description = incident.get("description", "")
                state_machine_data.metrics_before = incident_state.get("metrics", {})
            else:
                # Use prediction data
                predictions = prediction.get("predictions", [])
                if predictions:
                    state_machine_data.current_incident_type = predictions[0]["type"]
                else:
                    state_machine_data.current_incident_type = "service_crash"
                state_machine_data.current_incident_severity = "medium"
                state_machine_data.metrics_before = metrics.get("metrics", {})

            # Send incident detection message
            if state_machine_data.task_id:
                incident_msg = (
                    f"🚨 **Incident #{state_machine_data.incident_count} Detected**\n\n"
                    f"**Type:** {state_machine_data.current_incident_type}\n"
                    f"**Severity:** {state_machine_data.current_incident_severity}\n"
                    f"**Description:** {state_machine_data.incident_description}\n\n"
                    f"**Current Metrics:**\n"
                    f"- Latency: {state_machine_data.metrics_before.get('latency_ms', 'N/A'):.0f}ms\n"
                    f"- CPU: {state_machine_data.metrics_before.get('cpu_percent', 'N/A'):.1f}%\n"
                    f"- Memory: {state_machine_data.metrics_before.get('memory_percent', 'N/A'):.1f}%\n"
                    f"- Error Rate: {state_machine_data.metrics_before.get('error_rate', 'N/A'):.2%}\n"
                    f"- Availability: {state_machine_data.metrics_before.get('availability', 'N/A'):.2%}\n\n"
                    f"**Log Analysis:** {len(log_analysis.get('patterns', []))} patterns detected\n"
                    f"**Root Causes:** {', '.join(rc['cause'] for rc in log_analysis.get('root_cause_candidates', [])[:2])}\n"
                )

                await adk.messages.create(
                    task_id=state_machine_data.task_id,
                    content=TextContent(
                        author="agent",
                        content=incident_msg,
                    ),
                    trace_id=state_machine_data.task_id,
                )

            logger.info(
                f"Incident detected: {state_machine_data.current_incident_type} "
                f"(severity: {state_machine_data.current_incident_severity})"
            )

            return EvooState.PLANNING_REMEDIATION

        except Exception as e:
            logger.error(f"Error detecting incident: {e}")
            state_machine_data.error_message = f"Incident detection failed: {str(e)}"
            return EvooState.FAILED