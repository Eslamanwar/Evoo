"""Reward function and LLM-based evaluator activities for EVOO.

All activities accept a single dict argument (ActivityHelpers constraint).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

import httpx
from temporalio import activity

from agentex.lib.utils.logging import make_logger

logger = make_logger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


@activity.defn(name="calculate_reward_activity")
async def calculate_reward_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a scalar reward for a remediation action."""
    metrics_before = params.get("metrics_before", {})
    metrics_after = params.get("metrics_after", {})
    recovery_time_seconds = params.get("recovery_time_seconds", 120.0)
    service_restored = params.get("service_restored", False)
    infrastructure_cost = params.get("infrastructure_cost", 1.0)
    strategy_name = params.get("strategy_name", "")
    incident_type = params.get("incident_type", "")

    reward = 0.0
    breakdown = {}

    if service_restored:
        reward += 100.0
        breakdown["service_restored"] = 100.0
    else:
        reward -= 50.0
        breakdown["service_not_restored"] = -50.0

    rt_penalty = recovery_time_seconds * 0.5
    reward -= rt_penalty
    breakdown["recovery_time_penalty"] = -round(rt_penalty, 2)

    cost_penalty = infrastructure_cost * 0.2
    reward -= cost_penalty
    breakdown["infrastructure_cost_penalty"] = -round(cost_penalty, 2)

    error_rate_after = metrics_after.get("error_rate", 0.0)
    error_penalty = error_rate_after * 50.0
    reward -= error_penalty
    breakdown["error_rate_penalty"] = -round(error_penalty, 2)

    latency_before = metrics_before.get("latency_ms", 0.0)
    latency_after = metrics_after.get("latency_ms", 0.0)
    # Cap improvement at 500ms to prevent latency bonus from dwarfing the service_restored signal
    latency_improvement = min(max(0.0, latency_before - latency_after), 500.0)
    latency_bonus = latency_improvement * 0.02  # max +10 (was uncapped, up to +500)
    reward += latency_bonus
    breakdown["latency_improvement_bonus"] = round(latency_bonus, 2)

    avail_before = metrics_before.get("availability", 0.5)
    avail_after = metrics_after.get("availability", 0.5)
    avail_improvement = max(0.0, avail_after - avail_before)
    avail_bonus = avail_improvement * 50.0  # max +50 when availability fully restored
    reward += avail_bonus
    breakdown["availability_improvement_bonus"] = round(avail_bonus, 2)

    if strategy_name in ("scale_horizontal", "combined_restart_scale", "combined_rollback_scale"):
        if incident_type in ("timeout_misconfiguration", "memory_leak"):
            reward -= 10.0
            breakdown["unnecessary_scaling_penalty"] = -10.0

    cpu_before = metrics_before.get("cpu_percent", 0.0)
    cpu_after = metrics_after.get("cpu_percent", 0.0)
    cpu_improvement = max(0.0, cpu_before - cpu_after)
    reward += cpu_improvement * 0.05
    breakdown["cpu_improvement_bonus"] = round(cpu_improvement * 0.05, 2)

    reward = round(reward, 2)

    logger.info(f"Reward computed: {reward:.2f} | strategy={strategy_name} restored={service_restored}")

    return {
        "reward": reward,
        "breakdown": breakdown,
        "service_restored": service_restored,
        "recovery_time_seconds": recovery_time_seconds,
        "evaluated_at": datetime.utcnow().isoformat(),
    }


@activity.defn(name="llm_evaluate_remediation_activity")
async def llm_evaluate_remediation_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Use OpenAI GPT as a judge to qualitatively evaluate remediation."""
    incident_type = params.get("incident_type", "")
    strategy_used = params.get("strategy_used", "")
    metrics_before = params.get("metrics_before", {})
    metrics_after = params.get("metrics_after", {})
    tool_results = params.get("tool_results", [])
    recovery_time_seconds = params.get("recovery_time_seconds", 0.0)
    numeric_reward = params.get("numeric_reward", 0.0)
    task_id = params.get("task_id", "")

    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", None)

    try:
        from openai import AsyncOpenAI
        client_kwargs = {"api_key": api_key, "timeout": httpx.Timeout(120.0)}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = AsyncOpenAI(**client_kwargs)

        prompt = (
            f"You are an expert SRE evaluating an automated remediation.\n"
            f"Incident: {incident_type}, Strategy: {strategy_used}, Recovery: {recovery_time_seconds:.1f}s\n"
            f"Reward: {numeric_reward:.2f}\n"
            f"Before: latency={metrics_before.get('latency_ms')}ms, "
            f"cpu={metrics_before.get('cpu_percent')}%, "
            f"avail={metrics_before.get('availability', 0)*100:.0f}%\n"
            f"After: latency={metrics_after.get('latency_ms')}ms, "
            f"cpu={metrics_after.get('cpu_percent')}%, "
            f"avail={metrics_after.get('availability', 0)*100:.0f}%\n"
            f"Respond in JSON: {{\"overall_score\": 0-10, \"verdict\": \"excellent|good|adequate|poor|failed\", "
            f"\"analysis\": \"<2 sentences>\", \"better_strategy\": \"<or null>\"}}"
        )

        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert SRE. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"},
        )

        import json
        evaluation = json.loads(response.choices[0].message.content)
        return {"status": "success", "evaluation": evaluation, "model_used": OPENAI_MODEL}

    except Exception as e:
        logger.warning(f"[{task_id}] LLM evaluation failed: {e}")
        return _fallback_evaluation(metrics_after, recovery_time_seconds)


def _fallback_evaluation(metrics_after: Dict, recovery_time: float) -> Dict[str, Any]:
    avail_after = metrics_after.get("availability", 0)
    error_after = metrics_after.get("error_rate", 1.0)

    if avail_after >= 0.99 and error_after <= 0.01:
        verdict, score = "excellent", 9
    elif avail_after >= 0.95:
        verdict, score = "good", 7
    elif avail_after >= 0.80:
        verdict, score = "adequate", 5
    elif avail_after >= 0.50:
        verdict, score = "poor", 3
    else:
        verdict, score = "failed", 1

    return {
        "status": "fallback",
        "evaluation": {
            "overall_score": score,
            "verdict": verdict,
            "analysis": f"Heuristic: availability={avail_after:.2%}, recovery={recovery_time:.0f}s",
            "better_strategy": None,
        },
        "model_used": "fallback_heuristic",
    }
