"""Agentic SRE remediation loop for EVOO.

Implements the OBSERVE -> THINK -> ACT loop where an LLM decides which
remediation tools to call and in what order, based on real-time observations.
Modeled on the red-cell pentest agent loop pattern.

All activities accept a single dict argument (ActivityHelpers constraint).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from temporalio import activity

from agentex.lib import adk
from agentex.lib.utils.logging import make_logger
from agentex.types.text_content import TextContent
from agentex.types.tool_request_content import ToolRequestContent
from agentex.types.tool_response_content import ToolResponseContent

from project.activities.llm_helpers import (
    SRE_AVAILABLE_TOOLS,
    TOOL_TO_ACTIVITY,
    VALID_TOOL_NAMES,
    call_llm,
    parse_action,
)
from project.activities.remediation_activities import (
    analyze_logs_activity,
    change_timeout_activity,
    clear_cache_activity,
    query_metrics_tool_activity,
    rebalance_load_activity,
    restart_service_activity,
    rollback_deployment_activity,
    scale_horizontal_activity,
    scale_vertical_activity,
)
from project.activities.strategy_activities import (
    _heuristic_get_default_parameters,
    _heuristic_get_tools_for_strategy,
)

logger = make_logger(__name__)

MAX_ITERATIONS = int(os.getenv("MAX_AGENT_LOOP_ITERATIONS", "8"))

SRE_EXECUTOR_SYSTEM_PROMPT = """You are an expert SRE executing remediation for a production incident.

You operate in an OBSERVE -> THINK -> ACT loop:
- OBSERVE: Look at the current system metrics and previous action results
- THINK: Reason about what remediation tool to call next
- ACT: Call exactly one tool

{tools}

The incident plan suggests strategy "{strategy}" with tools: {suggested_tools}.
You may follow the plan or deviate if your observations suggest a better approach.

When you believe remediation is complete or you have executed enough tools, respond with:
ACTION: finish()

Respond in EXACTLY this format:
THOUGHT: [Your reasoning about current state and what to do next]
ACTION: [tool_name(key=value, key=value)]

Examples:
THOUGHT: The service has crashed with high error rate. I should analyze logs first to understand root cause.
ACTION: analyze_logs(service_name=api-service, incident_type=service_crash)

THOUGHT: Logs show OOM. I need to restart the service to recover immediately.
ACTION: restart_service(service_name=api-service)

THOUGHT: Service is back up and metrics look healthy. Remediation complete.
ACTION: finish()"""


class SREAgentState:
    """Tracks the state of the agentic SRE remediation loop."""

    def __init__(
        self,
        incident: Dict[str, Any],
        plan: Dict[str, Any],
        metrics_before: Dict[str, Any],
        system_state: Dict[str, Any],
    ):
        self.incident = incident
        self.plan = plan
        self.metrics_before = metrics_before
        self.system_state = system_state
        self.observations: List[Dict[str, Any]] = []
        self.actions_taken: List[Dict[str, Any]] = []
        self.tool_results: List[Dict[str, Any]] = []
        self.iteration = 0
        self.max_iterations = MAX_ITERATIONS
        self.finished = False
        self.service_name = incident.get("affected_service", "api-service")
        self.incident_type = incident.get("incident_type", "unknown")

    def add_observation(self, label: str, data: Any = None) -> None:
        self.observations.append({
            "label": label,
            "data": data,
            "iteration": self.iteration,
        })

    def add_action(self, action_str: str, result: Dict[str, Any]) -> None:
        self.actions_taken.append({
            "action": action_str,
            "result_status": result.get("status", "unknown"),
            "iteration": self.iteration,
        })
        self.tool_results.append(result)

    def get_context_for_llm(self) -> str:
        """Build context string for the LLM with current state."""
        lines = []

        # Incident info
        lines.append(f"INCIDENT: {self.incident_type} (severity: {self.incident.get('severity', '?')})")
        lines.append(f"Service: {self.service_name}")
        lines.append(f"Description: {self.incident.get('description', 'N/A')}")

        # Metrics at detection
        m = self.metrics_before
        lines.append(f"\nMETRICS AT DETECTION:")
        lines.append(f"  latency_ms: {m.get('latency_ms', '?')}")
        lines.append(f"  cpu_percent: {m.get('cpu_percent', '?')}")
        lines.append(f"  memory_percent: {m.get('memory_percent', '?')}")
        lines.append(f"  error_rate: {m.get('error_rate', '?')}")
        lines.append(f"  availability: {m.get('availability', '?')}")

        # Actions taken so far
        if self.actions_taken:
            lines.append(f"\nACTIONS TAKEN ({len(self.actions_taken)}):")
            for a in self.actions_taken:
                lines.append(f"  [{a['iteration']}] {a['action']} -> {a['result_status']}")

            # Show last tool result details
            last = self.tool_results[-1]
            lines.append(f"\nLAST TOOL RESULT:")
            for k, v in last.items():
                if k not in ("executed_at",):
                    lines.append(f"  {k}: {v}")
        else:
            lines.append("\nNo actions taken yet.")

        lines.append(f"\nIteration: {self.iteration}/{self.max_iterations}")

        return "\n".join(lines)


async def _execute_sre_tool(
    tool_name: str,
    params: Dict[str, Any],
    state: SREAgentState,
    task_id: str,
    trace_id: str,
) -> Dict[str, Any]:
    """Dispatch to the appropriate remediation tool function."""
    tool_call_id = f"sre_tool_{uuid.uuid4().hex[:12]}"

    # Stream ToolRequestContent to UI
    if task_id:
        try:
            await adk.messages.create(
                task_id=task_id,
                content=ToolRequestContent(
                    author="agent",
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    arguments=params,
                ),
                trace_id=trace_id,
            )
        except Exception:
            pass

    # Build the activity params dict
    activity_params: Dict[str, Any] = {
        "service_name": params.get("service_name", state.service_name),
        "task_id": task_id,
        "trace_id": trace_id,
    }

    # Merge tool-specific params
    for k, v in params.items():
        if k not in ("service_name", "task_id", "trace_id"):
            activity_params[k] = v

    # Add incident_type for analyze_logs
    if tool_name == "analyze_logs" and "incident_type" not in activity_params:
        activity_params["incident_type"] = state.incident_type

    # Call the tool function directly (we're inside an activity)
    tool_functions = {
        "analyze_logs": analyze_logs_activity,
        "restart_service": restart_service_activity,
        "scale_horizontal": scale_horizontal_activity,
        "scale_vertical": scale_vertical_activity,
        "change_timeout": change_timeout_activity,
        "rollback_deployment": rollback_deployment_activity,
        "clear_cache": clear_cache_activity,
        "rebalance_load": rebalance_load_activity,
        "query_metrics": query_metrics_tool_activity,
    }

    func = tool_functions.get(tool_name)
    if func is None:
        result = {"tool": tool_name, "status": "error", "error": f"Unknown tool: {tool_name}"}
    else:
        try:
            result = await func(activity_params)
        except Exception as e:
            result = {"tool": tool_name, "status": "error", "error": str(e)}

    # Stream ToolResponseContent to UI
    if task_id:
        try:
            result_preview = json.dumps(result, default=str)[:500]
            await adk.messages.create(
                task_id=task_id,
                content=ToolResponseContent(
                    author="agent",
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    content=result_preview,
                ),
                trace_id=trace_id,
            )
        except Exception:
            pass

    return result


def _fallback_next_tool(
    state: SREAgentState,
    plan: Dict[str, Any],
) -> Tuple[str, str, Dict[str, Any]]:
    """When LLM fails, return the next unexecuted tool from the plan."""
    plan_tools = plan.get("tools_to_call", [])
    executed = {a["action"].split("(")[0] for a in state.actions_taken}

    for tool_activity_name in plan_tools:
        # Convert activity name to short tool name
        short_name = tool_activity_name.replace("_activity", "").replace("_tool", "")
        # Map back from activity names
        for short, act in TOOL_TO_ACTIVITY.items():
            if act == tool_activity_name:
                short_name = short
                break
        if short_name not in executed:
            params = {
                "service_name": state.service_name,
            }
            # Add plan-level parameters
            tool_params = plan.get("tool_parameters", {})
            params.update(tool_params)
            return (
                "LLM failed, following planned tool sequence",
                short_name,
                params,
            )

    return ("All planned tools executed", "finish", {})


@activity.defn(name="run_sre_agent_loop_activity")
async def run_sre_agent_loop_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run the agentic SRE OBSERVE->THINK->ACT remediation loop."""
    incident_data = params.get("incident", {})
    plan_data = params.get("plan", {})
    metrics_before = params.get("metrics_before", {})
    system_state = params.get("system_state", {})
    task_id = params.get("task_id", "")
    trace_id = params.get("trace_id", task_id)

    state = SREAgentState(incident_data, plan_data, metrics_before, system_state)

    system_prompt = SRE_EXECUTOR_SYSTEM_PROMPT.format(
        strategy=plan_data.get("strategy", "unknown"),
        suggested_tools=", ".join(plan_data.get("tools_to_call", [])),
        tools=SRE_AVAILABLE_TOOLS,
    )

    # Announce the agentic loop start
    if task_id:
        try:
            await adk.messages.create(
                task_id=task_id,
                content=TextContent(
                    author="agent",
                    content=(
                        f"#### Executor Agent -- OBSERVE/THINK/ACT Loop (max {state.max_iterations} iterations)\n"
                        f"**Strategy**: `{plan_data.get('strategy', '?')}`\n"
                        f"**Suggested tools**: {', '.join(plan_data.get('tools_to_call', []))}\n"
                    ),
                ),
                trace_id=trace_id,
            )
        except Exception:
            pass

    while not state.finished and state.iteration < state.max_iterations:
        state.iteration += 1
        activity.heartbeat(f"SRE Agent iteration {state.iteration}/{state.max_iterations}")

        # --- OBSERVE ---
        context = state.get_context_for_llm()
        prompt = f"Current remediation state:\n\n{context}\n\nWhat tool should be called next? Remember: THOUGHT first, then ACTION."

        # --- THINK ---
        thought = ""
        tool_name = "none"
        tool_params: Dict[str, Any] = {}

        try:
            llm_response = await call_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=float(os.getenv("LLM_TEMPERATURE_EXECUTION", "0.2")),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS_EXECUTION", "500")),
            )

            # Extract thought
            import re
            thought_match = re.search(r"THOUGHT:\s*(.+?)(?=ACTION:|$)", llm_response, re.DOTALL)
            thought = thought_match.group(1).strip() if thought_match else llm_response[:200]

            tool_name, tool_params = parse_action(llm_response)

        except Exception as e:
            logger.warning(f"[Iter {state.iteration}] LLM failed: {e}, using fallback")
            thought, tool_name, tool_params = _fallback_next_tool(state, plan_data)

        # If LLM didn't produce a valid action, use fallback
        if tool_name == "none" or tool_name not in VALID_TOOL_NAMES:
            logger.warning(f"[Iter {state.iteration}] Invalid tool '{tool_name}', using fallback")
            thought, tool_name, tool_params = _fallback_next_tool(state, plan_data)

        # --- Stream reasoning to UI ---
        if task_id:
            try:
                params_display = ", ".join(
                    f"{k}={str(v)[:30]}" for k, v in tool_params.items()
                ) if tool_params else ""
                await adk.messages.create(
                    task_id=task_id,
                    content=TextContent(
                        author="agent",
                        content=(
                            f"**Iteration {state.iteration}**\n"
                            f"**Thinking:** {thought[:500]}\n"
                            f"**Action:** `{tool_name}({params_display})`"
                        ),
                    ),
                    trace_id=trace_id,
                )
            except Exception:
                pass

        # --- ACT ---
        if tool_name == "finish":
            state.finished = True
            break

        result = await _execute_sre_tool(tool_name, tool_params, state, task_id, trace_id)
        state.add_action(f"{tool_name}({json.dumps(tool_params, default=str)})", result)

        logger.info(
            f"[Iter {state.iteration}] Tool: {tool_name} -> {result.get('status', '?')}"
        )

    # Summary
    logger.info(
        f"SRE Agent loop complete: {state.iteration} iterations, "
        f"{len(state.tool_results)} tools executed, finished={state.finished}"
    )

    return {
        "tool_results": state.tool_results,
        "iterations_used": state.iteration,
        "actions_taken": [a["action"] for a in state.actions_taken],
        "finished_naturally": state.finished,
    }
