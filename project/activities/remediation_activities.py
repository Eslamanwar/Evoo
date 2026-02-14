"""Remediation tool activities for EVOO.

All activities accept a single dict argument (ActivityHelpers constraint).
Each tool returns a structured JSON result.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from temporalio import activity

from agentex.lib.utils.logging import make_logger

from project.activities.llm_helpers import call_llm, parse_llm_json

logger = make_logger(__name__)


@activity.defn(name="restart_service_activity")
async def restart_service_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Restart the specified service."""
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Executing restart_service on {service_name}")
    await asyncio.sleep(0.1)
    return {
        "tool": "restart_service",
        "status": "success",
        "service": service_name,
        "action": "graceful_restart",
        "pid_old": 12345,
        "pid_new": 12399,
        "uptime_reset": True,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="scale_horizontal_activity")
async def scale_horizontal_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Scale the service horizontally to the target instance count."""
    target_instances = params.get("target_instances", 3)
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Executing scale_horizontal: {target_instances} instances")
    await asyncio.sleep(0.1)
    return {
        "tool": "scale_horizontal",
        "status": "success",
        "service": service_name,
        "target_instances": target_instances,
        "current_instances": target_instances,
        "scale_direction": "up" if target_instances > 1 else "down",
        "estimated_ready_seconds": 15,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="scale_vertical_activity")
async def scale_vertical_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Scale the service vertically by adjusting CPU and memory limits."""
    target_cpu = params.get("target_cpu", 2.0)
    target_memory_gb = params.get("target_memory_gb", 4.0)
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Executing scale_vertical: cpu={target_cpu}, mem={target_memory_gb}GB")
    await asyncio.sleep(0.1)
    return {
        "tool": "scale_vertical",
        "status": "success",
        "service": service_name,
        "target_cpu_cores": target_cpu,
        "target_memory_gb": target_memory_gb,
        "previous_cpu_cores": 1.0,
        "previous_memory_gb": 2.0,
        "restart_required": True,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="change_timeout_activity")
async def change_timeout_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Update the service timeout configuration."""
    new_timeout_ms = params.get("new_timeout_ms", 15000)
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Executing change_timeout: {new_timeout_ms}ms")
    await asyncio.sleep(0.05)
    return {
        "tool": "change_timeout",
        "status": "success",
        "service": service_name,
        "new_timeout_ms": new_timeout_ms,
        "previous_timeout_ms": 30000,
        "config_reload": True,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="rollback_deployment_activity")
async def rollback_deployment_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Rollback the service to the previous stable deployment."""
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    target_version = params.get("target_version")
    logger.info(f"[{task_id}] Executing rollback_deployment for {service_name}")
    await asyncio.sleep(0.15)
    return {
        "tool": "rollback_deployment",
        "status": "success",
        "service": service_name,
        "rolled_back_to": target_version or "v2.1.3",
        "rolled_back_from": "v2.2.0",
        "deployment_id": "deploy-abc123",
        "canary_disabled": True,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="clear_cache_activity")
async def clear_cache_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Clear service cache to free memory."""
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    cache_type = params.get("cache_type", "all")
    logger.info(f"[{task_id}] Executing clear_cache ({cache_type})")
    await asyncio.sleep(0.05)
    return {
        "tool": "clear_cache",
        "status": "success",
        "service": service_name,
        "cache_type": cache_type,
        "cleared_entries": 45231,
        "freed_memory_mb": 512,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="rebalance_load_activity")
async def rebalance_load_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Rebalance load across available instances."""
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Executing rebalance_load")
    await asyncio.sleep(0.08)
    return {
        "tool": "rebalance_load",
        "status": "success",
        "service": service_name,
        "algorithm": "least_connections",
        "rebalanced_connections": 1250,
        "overloaded_instances_before": 2,
        "overloaded_instances_after": 0,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="query_metrics_tool_activity")
async def query_metrics_tool_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query current metrics from the observability stack."""
    service_name = params.get("service_name", "api-service")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Querying metrics for {service_name}")
    await asyncio.sleep(0.02)
    return {
        "tool": "query_metrics",
        "status": "success",
        "service": service_name,
        "source": "prometheus",
        "time_range": "last_5m",
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="analyze_logs_activity")
async def analyze_logs_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze recent service logs to identify root cause patterns."""
    service_name = params.get("service_name", "api-service")
    incident_type = params.get("incident_type", "unknown")
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Analyzing logs for {service_name}")
    await asyncio.sleep(0.1)

    log_findings = {
        "service_crash": {"root_cause": "OOMKilled by kernel", "error_pattern": "FATAL: out of memory"},
        "high_latency": {"root_cause": "DB connection pool exhaustion", "error_pattern": "WARN: pool timeout"},
        "cpu_spike": {"root_cause": "Recursive loop in processor", "error_pattern": "CPU throttling activated"},
        "memory_leak": {"root_cause": "EventListener not removed", "error_pattern": "Memory grew 1.2GB to 4.8GB"},
        "network_degradation": {"root_cause": "BGP route flap", "error_pattern": "TCP retransmission 34%"},
        "timeout_misconfiguration": {"root_cause": "5s timeout too aggressive", "error_pattern": "context deadline exceeded"},
    }
    finding = log_findings.get(incident_type, {"root_cause": "Unknown", "error_pattern": "Multiple errors"})

    return {
        "tool": "analyze_logs",
        "status": "success",
        "service": service_name,
        "incident_type": incident_type,
        "log_lines_analyzed": 15432,
        "findings": finding,
        "executed_at": datetime.utcnow().isoformat(),
    }


def _heuristic_predict(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic fallback for incident prediction using threshold rules."""
    latency = metrics.get("latency_ms", 0)
    cpu = metrics.get("cpu_percent", 0)
    memory = metrics.get("memory_percent", 0)
    error_rate = metrics.get("error_rate", 0)
    availability = metrics.get("availability", 1.0)

    predictions = []
    if availability < 0.3 and error_rate > 0.7:
        predictions.append(("service_crash", 0.90))
    if memory > 85:
        predictions.append(("memory_leak", 0.85))
    if cpu > 80:
        predictions.append(("cpu_spike", 0.85))
    if latency > 4000:
        predictions.append(("timeout_misconfiguration", 0.70))
    if not predictions:
        predictions.append(("high_latency", 0.50))

    predictions.sort(key=lambda x: x[1], reverse=True)
    return {
        "predicted_type": predictions[0][0],
        "confidence": predictions[0][1],
        "reasoning": "heuristic_threshold_rules",
    }


VALID_INCIDENT_TYPES = {
    "service_crash", "high_latency", "cpu_spike",
    "memory_leak", "network_degradation", "timeout_misconfiguration",
}


@activity.defn(name="predict_incident_type_activity")
async def predict_incident_type_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Predict incident type from metrics using LLM reasoning with heuristic fallback."""
    metrics = params.get("metrics", {})
    task_id = params.get("task_id", "")
    logger.info(f"[{task_id}] Predicting incident type")

    # Try LLM-based prediction first
    try:
        system_prompt = """You are an expert SRE analyzing system metrics to diagnose an incident.

Valid incident types:
- service_crash: Service is completely down or returning errors
- high_latency: Response times are significantly elevated
- cpu_spike: CPU utilization is abnormally high
- memory_leak: Memory usage is growing uncontrollably
- network_degradation: Network performance is degraded
- timeout_misconfiguration: Timeouts are set incorrectly

Respond with valid JSON only:
{
  "predicted_type": "<incident_type>",
  "confidence": <0.0-1.0>,
  "reasoning": "<1-2 sentence explanation>"
}"""

        user_prompt = f"""Analyze these system metrics and predict the incident type:

- latency_ms: {metrics.get('latency_ms', 'N/A')}
- cpu_percent: {metrics.get('cpu_percent', 'N/A')}
- memory_percent: {metrics.get('memory_percent', 'N/A')}
- error_rate: {metrics.get('error_rate', 'N/A')}
- availability: {metrics.get('availability', 'N/A')}

What type of incident do these metrics indicate?"""

        response = await call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=200,
            json_mode=True,
        )

        result = parse_llm_json(response)
        if result and result.get("predicted_type") in VALID_INCIDENT_TYPES:
            return {
                "tool": "predict_incident_type",
                "status": "success",
                "predicted_type": result["predicted_type"],
                "confidence": min(1.0, max(0.0, float(result.get("confidence", 0.8)))),
                "reasoning": result.get("reasoning", ""),
                "llm_predicted": True,
                "executed_at": datetime.utcnow().isoformat(),
            }
        else:
            logger.warning(f"LLM returned invalid incident type: {result}")

    except Exception as e:
        logger.warning(f"LLM incident prediction failed: {e}")

    # Fall back to heuristic prediction
    heuristic = _heuristic_predict(metrics)
    return {
        "tool": "predict_incident_type",
        "status": "success",
        "predicted_type": heuristic["predicted_type"],
        "confidence": heuristic["confidence"],
        "reasoning": heuristic["reasoning"],
        "llm_predicted": False,
        "executed_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="mark_strategy_success_activity")
async def mark_strategy_success_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"tool": "mark_strategy_success", "status": "success"}


@activity.defn(name="mark_strategy_failure_activity")
async def mark_strategy_failure_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"tool": "mark_strategy_failure", "status": "success"}
