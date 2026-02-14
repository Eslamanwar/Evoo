"""Advanced analysis tool activities for EVOO agent.

All analysis is driven by LLM reasoning using the OpenAI SDK via OpenRouter.
No hardcoded rules — the LLM acts as an expert SRE analyzing metrics, logs,
and system state to make predictions and recommendations.
"""

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI
from temporalio import activity

from agentex.lib.utils.logging import make_logger
from project.activities.remediation_tools import get_production_system
from project.constants import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from project.memory.experience_store import ExperienceStore
from project.models.enums import IncidentType
from project.strategy.strategy_catalog import get_strategies_for_incident

logger = make_logger(__name__)

# Shared experience store (initialized per worker)
_experience_store: Optional[ExperienceStore] = None


def get_experience_store() -> ExperienceStore:
    """Get the shared experience store instance."""
    global _experience_store
    if _experience_store is None:
        _experience_store = ExperienceStore()
    return _experience_store


def set_experience_store(store: ExperienceStore) -> None:
    """Set the shared experience store instance."""
    global _experience_store
    _experience_store = store


async def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 1000) -> str:
    """Call LLM via OpenAI SDK with OpenRouter.

    Follows the same pattern as red-cell agent for consistency.

    Args:
        system_prompt: System message for the LLM.
        user_prompt: User message for the LLM.
        max_tokens: Maximum tokens in response.

    Returns:
        LLM response content string.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or OPENAI_API_KEY
    base_url = os.environ.get("OPENAI_BASE_URL", OPENAI_BASE_URL)
    model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)

    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(120.0),
    )

    try:
        activity.heartbeat("Calling LLM...")
    except Exception:
        pass

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )

    try:
        activity.heartbeat("LLM call completed")
    except Exception:
        pass

    return response.choices[0].message.content


@activity.defn(name="analyze_logs")
async def analyze_logs() -> str:
    """Analyze system logs using LLM to identify patterns and root causes.

    The LLM acts as an expert SRE, analyzing the current system metrics
    and incident state to identify log patterns and root cause candidates.
    No hardcoded rules — all analysis is LLM-driven.

    Returns:
        JSON string with log analysis results.
    """
    logger.info("📋 Analyzing system logs with LLM")
    system = get_production_system()
    incident_state = system.get_incident_state()

    if not incident_state.get("has_incident"):
        return json.dumps({
            "analysis": "No active incident detected in logs",
            "patterns": [],
            "root_cause_candidates": [],
        })

    incident = incident_state.get("incident", {})
    incident_type = incident.get("incident_type", "unknown")
    metrics = incident_state.get("metrics", {})

    system_prompt = """You are an expert Site Reliability Engineer analyzing production system logs.
You have deep expertise in distributed systems, microservices, databases, networking, and cloud infrastructure.

Your task is to analyze the current system metrics and incident information to:
1. Identify log patterns that would be observed during this type of incident
2. Determine the most likely root causes with confidence scores

You MUST respond in valid JSON format with this exact structure:
{
    "patterns": ["pattern1", "pattern2", "pattern3"],
    "root_cause_candidates": [
        {"cause": "description of root cause", "confidence": 0.0 to 1.0},
        {"cause": "description of root cause", "confidence": 0.0 to 1.0}
    ]
}

Be specific and realistic. Base your analysis on the actual metrics provided.
Provide 3-5 patterns and 2-4 root cause candidates ordered by confidence."""

    user_prompt = f"""Analyze the following production incident and system metrics:

INCIDENT TYPE: {incident_type}
INCIDENT DESCRIPTION: {incident.get('description', 'N/A')}
SEVERITY: {incident.get('severity', 'N/A')}

CURRENT SYSTEM METRICS:
- Latency: {metrics.get('latency_ms', 'N/A')}ms
- CPU Utilization: {metrics.get('cpu_percent', 'N/A')}%
- Memory Utilization: {metrics.get('memory_percent', 'N/A')}%
- Error Rate: {metrics.get('error_rate', 'N/A')} (0.0 to 1.0)
- Availability: {metrics.get('availability', 'N/A')} (0.0 to 1.0)
- Active Instances: {metrics.get('active_instances', 'N/A')}
- Requests/sec: {metrics.get('requests_per_second', 'N/A')}
- Timeout Config: {metrics.get('timeout_ms', 'N/A')}ms
- Cache Hit Rate: {metrics.get('cache_hit_rate', 'N/A')}

Based on these metrics and the incident type, what log patterns would you expect to see,
and what are the most likely root causes? Consider the relationships between metrics
(e.g., high CPU + high latency might indicate different root causes than high memory + errors)."""

    try:
        llm_response = await _call_llm(system_prompt, user_prompt, max_tokens=800)

        try:
            analysis = json.loads(llm_response)
            patterns = analysis.get("patterns", [])
            root_causes = analysis.get("root_cause_candidates", [])
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                analysis = json.loads(json_match.group())
                patterns = analysis.get("patterns", [])
                root_causes = analysis.get("root_cause_candidates", [])
            else:
                patterns = [f"LLM analysis: {llm_response[:200]}"]
                root_causes = [{"cause": "Unable to parse structured analysis", "confidence": 0.5}]

        result = {
            "analysis": f"LLM-driven log analysis for {incident_type} incident",
            "incident_type": incident_type,
            "patterns": patterns,
            "root_cause_candidates": root_causes,
            "analysis_method": "llm_reasoning",
            "time_range_analyzed": "last 60 minutes",
        }

        logger.info(f"LLM log analysis complete: {len(patterns)} patterns, {len(root_causes)} root causes")
        return json.dumps(result)

    except Exception as e:
        logger.error(f"LLM log analysis failed: {e}")
        # Graceful fallback — return minimal analysis
        return json.dumps({
            "analysis": f"Log analysis for {incident_type} incident (LLM unavailable)",
            "incident_type": incident_type,
            "patterns": [f"Anomalous metrics detected for {incident_type}"],
            "root_cause_candidates": [
                {"cause": f"Potential {incident_type} based on metric anomalies", "confidence": 0.5}
            ],
            "analysis_method": "fallback",
            "error": str(e),
        })


@activity.defn(name="predict_incident_type")
async def predict_incident_type() -> str:
    """Predict the incident type using LLM reasoning based on current metrics.

    The LLM acts as an expert SRE, analyzing raw system metrics to predict
    what type of incident is occurring. No hardcoded rules — the LLM uses
    its understanding of system behavior to make predictions.

    Returns:
        JSON string with prediction results.
    """
    logger.info("🔮 Predicting incident type with LLM")
    system = get_production_system()
    metrics = system.get_current_metrics()

    system_prompt = """You are an expert Site Reliability Engineer specializing in incident detection and classification.

Given a set of system metrics, you must predict what type of production incident is occurring.

The possible incident types are:
- service_crash: Service has crashed or is unresponsive (very low availability, high error rate)
- high_latency: Service is responding slowly (elevated latency, possibly high CPU or memory)
- cpu_spike: CPU utilization is abnormally high (high CPU, may affect latency)
- memory_leak: Memory is being consumed without release (high and growing memory usage)
- network_degradation: Network issues causing packet loss or connectivity problems (high latency + errors)
- timeout_misconfiguration: Timeout settings are causing cascading failures (very high latency + errors)

You MUST respond in valid JSON format with this exact structure:
{
    "predictions": [
        {"type": "incident_type", "confidence": 0.0 to 1.0, "reasoning": "brief explanation"},
        {"type": "incident_type", "confidence": 0.0 to 1.0, "reasoning": "brief explanation"}
    ]
}

Provide 1-3 predictions ordered by confidence (highest first).
Consider the RELATIONSHIPS between metrics — a single metric rarely tells the full story.
For example:
- Low availability + high error rate → likely service_crash
- High latency alone → likely high_latency
- High CPU + moderate latency → likely cpu_spike
- High memory + gradual degradation → likely memory_leak
- High latency + high errors + moderate CPU → likely network_degradation
- Very high latency + high errors + normal CPU/memory → likely timeout_misconfiguration"""

    metrics_dict = metrics.to_dict()
    health_score = metrics.compute_health_score()

    user_prompt = f"""Analyze these production system metrics and predict the incident type:

SYSTEM METRICS:
- Latency: {metrics_dict['latency_ms']:.1f}ms (normal: ~50ms)
- CPU Utilization: {metrics_dict['cpu_percent']:.1f}% (normal: ~30%)
- Memory Utilization: {metrics_dict['memory_percent']:.1f}% (normal: ~40%)
- Error Rate: {metrics_dict['error_rate']:.4f} (normal: ~0.01, range 0.0-1.0)
- Availability: {metrics_dict['availability']:.4f} (normal: ~0.999, range 0.0-1.0)
- Active Instances: {metrics_dict['active_instances']} (normal: 2)
- Requests/sec: {metrics_dict['requests_per_second']:.1f} (normal: ~100)
- Timeout Config: {metrics_dict['timeout_ms']}ms (normal: 5000ms)
- Cache Hit Rate: {metrics_dict['cache_hit_rate']:.2f} (normal: ~0.8)

COMPUTED HEALTH SCORE: {health_score:.3f} (1.0 = perfectly healthy, 0.0 = completely degraded)

Based on these metrics, what type of incident is most likely occurring?
Consider which metrics are most anomalous and how they relate to each other."""

    try:
        llm_response = await _call_llm(system_prompt, user_prompt, max_tokens=600)

        try:
            prediction_data = json.loads(llm_response)
            predictions = prediction_data.get("predictions", [])
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                prediction_data = json.loads(json_match.group())
                predictions = prediction_data.get("predictions", [])
            else:
                predictions = [{"type": "service_crash", "confidence": 0.5, "reasoning": "Unable to parse LLM response"}]

        # Validate prediction types
        valid_types = {t.value for t in IncidentType}
        validated_predictions = []
        for pred in predictions:
            if pred.get("type") in valid_types:
                validated_predictions.append(pred)
            else:
                logger.warning(f"LLM predicted invalid incident type: {pred.get('type')}")

        # Sort by confidence
        validated_predictions.sort(key=lambda p: p.get("confidence", 0), reverse=True)

        result = {
            "predictions": validated_predictions[:3],
            "metrics_snapshot": metrics_dict,
            "health_score": round(health_score, 3),
            "prediction_method": "llm_reasoning",
        }

        if validated_predictions:
            top = validated_predictions[0]
            logger.info(
                f"LLM prediction: {top['type']} (confidence: {top['confidence']}) "
                f"— {top.get('reasoning', 'N/A')}"
            )
        else:
            logger.info("LLM could not make a valid prediction")

        return json.dumps(result)

    except Exception as e:
        logger.error(f"LLM prediction failed: {e}")
        # Graceful fallback — use health score as a basic signal
        health_score = metrics.compute_health_score()
        fallback_type = "service_crash" if health_score < 0.3 else "high_latency"
        return json.dumps({
            "predictions": [
                {
                    "type": fallback_type,
                    "confidence": 0.4,
                    "reasoning": f"Fallback prediction based on health score {health_score:.3f} (LLM unavailable)",
                }
            ],
            "metrics_snapshot": metrics.to_dict(),
            "health_score": round(health_score, 3),
            "prediction_method": "fallback",
            "error": str(e),
        })


@activity.defn(name="apply_previous_successful_strategy")
async def apply_previous_successful_strategy(incident_type: str) -> str:
    """Look up and return the best previously successful strategy for an incident type.

    Uses memory store to find historically successful strategies, then uses LLM
    to evaluate whether the best historical strategy is appropriate for the current context.

    Args:
        incident_type: The incident type to find strategies for.

    Returns:
        JSON string with the best strategy recommendation.
    """
    logger.info(f"📚 Looking up best strategy for {incident_type}")
    store = get_experience_store()

    try:
        inc_type = IncidentType(incident_type)
    except ValueError:
        return json.dumps({
            "found": False,
            "message": f"Unknown incident type: {incident_type}",
        })

    best_records = store.get_best_strategy_for_incident(inc_type, top_k=3)

    if not best_records:
        # No historical data — use LLM to suggest initial strategies
        available = get_strategies_for_incident(inc_type)

        try:
            system_prompt = """You are an expert SRE. Given an incident type and available remediation strategies,
recommend which strategy to try first. Respond in valid JSON with:
{
    "recommended_strategy": "strategy_name",
    "reasoning": "why this strategy is best for a first attempt"
}"""

            strategies_info = "\n".join([
                f"- {s.name}: {s.description} (est. recovery: {s.estimated_recovery_time_seconds}s, est. cost: {s.estimated_cost})"
                for s in available
            ])

            user_prompt = f"""Incident type: {incident_type}
No historical data available — this is the first time we're seeing this incident type.

Available strategies:
{strategies_info}

Which strategy should we try first and why?"""

            llm_response = await _call_llm(system_prompt, user_prompt, max_tokens=300)

            try:
                recommendation = json.loads(llm_response)
            except json.JSONDecodeError:
                recommendation = {"recommended_strategy": available[0].name if available else "restart_and_verify",
                                  "reasoning": "Default first strategy"}

            return json.dumps({
                "found": False,
                "message": "No historical data — LLM recommending initial strategy",
                "llm_recommendation": recommendation,
                "available_strategies": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "estimated_recovery_time": s.estimated_recovery_time_seconds,
                    }
                    for s in available
                ],
            })

        except Exception as e:
            logger.warning(f"LLM recommendation failed: {e}")
            return json.dumps({
                "found": False,
                "message": "No historical data available for this incident type",
                "available_strategies": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "estimated_recovery_time": s.estimated_recovery_time_seconds,
                    }
                    for s in available
                ],
            })

    result = {
        "found": True,
        "best_strategy": {
            "name": best_records[0].strategy_name,
            "average_reward": round(best_records[0].average_reward, 2),
            "success_rate": round(best_records[0].success_rate, 3),
            "total_uses": best_records[0].total_uses,
            "average_recovery_time": round(best_records[0].average_recovery_time, 1),
        },
        "alternatives": [
            {
                "name": r.strategy_name,
                "average_reward": round(r.average_reward, 2),
                "success_rate": round(r.success_rate, 3),
                "total_uses": r.total_uses,
            }
            for r in best_records[1:]
        ],
    }

    logger.info(f"Best strategy: {best_records[0].strategy_name} (reward: {best_records[0].average_reward:.2f})")
    return json.dumps(result)