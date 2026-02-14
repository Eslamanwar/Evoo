"""Evaluation and reward calculation activities for EVOO agent."""

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI
from temporalio import activity

from agentex.lib.utils.logging import make_logger
from project.constants import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

logger = make_logger(__name__)


@activity.defn(name="calculate_reward")
async def calculate_reward(
    metrics_before: Dict[str, Any],
    metrics_after: Dict[str, Any],
    recovery_time_seconds: float,
    infrastructure_cost: float,
    service_restored: bool,
) -> str:
    """Calculate the reward score for a remediation attempt.

    Reward formula:
        reward = 100 if service_restored
               - recovery_time_seconds * 0.5
               - infrastructure_cost * 0.2
               - error_rate_after * 50
               + latency_improvement * 0.1

    Args:
        metrics_before: System metrics before remediation.
        metrics_after: System metrics after remediation.
        recovery_time_seconds: Total recovery time.
        infrastructure_cost: Total infrastructure cost incurred.
        service_restored: Whether the service was restored.

    Returns:
        JSON string with reward calculation details.
    """
    logger.info("📊 Calculating reward score")

    # Base reward for service restoration
    reward = 100.0 if service_restored else 0.0

    # Penalty for recovery time
    recovery_penalty = recovery_time_seconds * 0.5
    reward -= recovery_penalty

    # Penalty for infrastructure cost
    cost_penalty = infrastructure_cost * 0.2
    reward -= cost_penalty

    # Penalty for remaining error rate
    error_rate_after = metrics_after.get("error_rate", 0.0)
    error_penalty = error_rate_after * 50.0
    reward -= error_penalty

    # Bonus for latency improvement
    latency_before = metrics_before.get("latency_ms", 0.0)
    latency_after = metrics_after.get("latency_ms", 0.0)
    latency_improvement = max(0, latency_before - latency_after)
    latency_bonus = latency_improvement * 0.1
    reward += latency_bonus

    # Bonus for availability improvement
    avail_before = metrics_before.get("availability", 0.0)
    avail_after = metrics_after.get("availability", 0.0)
    avail_improvement = max(0, avail_after - avail_before)
    avail_bonus = avail_improvement * 100.0
    reward += avail_bonus

    # Bonus for CPU improvement
    cpu_before = metrics_before.get("cpu_percent", 0.0)
    cpu_after = metrics_after.get("cpu_percent", 0.0)
    cpu_improvement = max(0, cpu_before - cpu_after)
    cpu_bonus = cpu_improvement * 0.3
    reward += cpu_bonus

    # Bonus for memory improvement
    mem_before = metrics_before.get("memory_percent", 0.0)
    mem_after = metrics_after.get("memory_percent", 0.0)
    mem_improvement = max(0, mem_before - mem_after)
    mem_bonus = mem_improvement * 0.3
    reward += mem_bonus

    # Clamp reward
    reward = max(-100.0, min(200.0, reward))

    result = {
        "reward": round(reward, 2),
        "breakdown": {
            "base_restoration": 100.0 if service_restored else 0.0,
            "recovery_time_penalty": round(-recovery_penalty, 2),
            "cost_penalty": round(-cost_penalty, 2),
            "error_rate_penalty": round(-error_penalty, 2),
            "latency_bonus": round(latency_bonus, 2),
            "availability_bonus": round(avail_bonus, 2),
            "cpu_bonus": round(cpu_bonus, 2),
            "memory_bonus": round(mem_bonus, 2),
        },
        "service_restored": service_restored,
        "recovery_time_seconds": recovery_time_seconds,
        "infrastructure_cost": infrastructure_cost,
    }

    logger.info(f"Reward calculated: {reward:.2f} (restored={service_restored})")
    return json.dumps(result)


@activity.defn(name="evaluate_remediation_with_llm")
async def evaluate_remediation_with_llm(
    incident_type: str,
    incident_severity: str,
    strategy_used: str,
    actions_taken: List[str],
    metrics_before: Dict[str, Any],
    metrics_after: Dict[str, Any],
    recovery_time_seconds: float,
    service_restored: bool,
    numerical_reward: float,
) -> str:
    """Use LLM as a judge to qualitatively evaluate remediation effectiveness.

    Args:
        incident_type: Type of incident.
        incident_severity: Severity of the incident.
        strategy_used: Name of the strategy used.
        actions_taken: List of actions taken.
        metrics_before: Metrics before remediation.
        metrics_after: Metrics after remediation.
        recovery_time_seconds: Recovery time.
        service_restored: Whether service was restored.
        numerical_reward: The numerical reward score.

    Returns:
        JSON string with LLM evaluation.
    """
    logger.info("🤖 Evaluating remediation with LLM judge")

    evaluation_prompt = f"""You are an expert Site Reliability Engineer evaluating a remediation attempt.

INCIDENT DETAILS:
- Type: {incident_type}
- Severity: {incident_severity}
- Strategy Used: {strategy_used}
- Actions Taken: {', '.join(actions_taken)}

METRICS BEFORE REMEDIATION:
- Latency: {metrics_before.get('latency_ms', 'N/A')}ms
- CPU: {metrics_before.get('cpu_percent', 'N/A')}%
- Memory: {metrics_before.get('memory_percent', 'N/A')}%
- Error Rate: {metrics_before.get('error_rate', 'N/A')}
- Availability: {metrics_before.get('availability', 'N/A')}

METRICS AFTER REMEDIATION:
- Latency: {metrics_after.get('latency_ms', 'N/A')}ms
- CPU: {metrics_after.get('cpu_percent', 'N/A')}%
- Memory: {metrics_after.get('memory_percent', 'N/A')}%
- Error Rate: {metrics_after.get('error_rate', 'N/A')}
- Availability: {metrics_after.get('availability', 'N/A')}

OUTCOME:
- Service Restored: {service_restored}
- Recovery Time: {recovery_time_seconds:.1f} seconds
- Numerical Reward: {numerical_reward:.2f}

Please evaluate this remediation attempt. Provide:
1. Overall assessment (excellent/good/adequate/poor/failed)
2. What went well
3. What could be improved
4. Recommended strategy adjustments for future similar incidents
5. A qualitative reward adjustment (-20 to +20) based on your expert judgment

Respond in JSON format with keys: assessment, positives, improvements, recommendations, reward_adjustment"""

    try:
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
            activity.heartbeat("Calling LLM for evaluation...")
        except Exception:
            pass

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert SRE evaluating incident remediation. Respond only in valid JSON."},
                {"role": "user", "content": evaluation_prompt},
            ],
            max_tokens=1000,
        )

        llm_response = response.choices[0].message.content

        # Try to parse as JSON
        try:
            evaluation = json.loads(llm_response)
        except json.JSONDecodeError:
            evaluation = {
                "assessment": "unknown",
                "positives": [],
                "improvements": [],
                "recommendations": [],
                "reward_adjustment": 0,
                "raw_response": llm_response,
            }

        # Add the adjusted reward
        reward_adjustment = evaluation.get("reward_adjustment", 0)
        evaluation["original_reward"] = numerical_reward
        evaluation["adjusted_reward"] = numerical_reward + reward_adjustment

        logger.info(f"LLM evaluation: {evaluation.get('assessment', 'unknown')}, adjustment: {reward_adjustment}")
        return json.dumps(evaluation)

    except Exception as e:
        logger.error(f"LLM evaluation failed: {e}")
        # Return a default evaluation on failure
        fallback = {
            "assessment": "unable_to_evaluate",
            "error": str(e),
            "positives": ["Service restored" if service_restored else "Attempted remediation"],
            "improvements": ["LLM evaluation unavailable"],
            "recommendations": ["Retry LLM evaluation"],
            "reward_adjustment": 0,
            "original_reward": numerical_reward,
            "adjusted_reward": numerical_reward,
        }
        return json.dumps(fallback)