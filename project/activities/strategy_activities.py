"""Strategy manager activities for EVOO.

All activities accept a single dict argument (ActivityHelpers constraint).
The exploit path uses LLM reasoning with memory context; the explore path
remains random for epsilon-greedy exploration guarantee. Every LLM path
falls back to heuristics on failure.
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from temporalio import activity

from agentex.lib.utils.logging import make_logger

from project.activities.llm_helpers import (
    STRATEGY_DESCRIPTIONS,
    SRE_AVAILABLE_TOOLS,
    call_llm,
    parse_llm_json,
)
from project.models.incident import IncidentType, RemediationStrategy

logger = make_logger(__name__)

STRATEGY_FILE = os.getenv("STRATEGY_FILE_PATH", "/tmp/evoo_strategies.json")
EXPLORATION_RATE = float(os.getenv("EXPLORATION_RATE", "0.2"))

ALL_STRATEGIES = [s.value for s in RemediationStrategy]

STRATEGY_PRIORS: Dict[str, List[str]] = {
    IncidentType.SERVICE_CRASH.value: [RemediationStrategy.RESTART_SERVICE.value, RemediationStrategy.ROLLBACK_DEPLOYMENT.value],
    IncidentType.HIGH_LATENCY.value: [RemediationStrategy.SCALE_HORIZONTAL.value, RemediationStrategy.REBALANCE_LOAD.value],
    IncidentType.CPU_SPIKE.value: [RemediationStrategy.SCALE_VERTICAL.value, RemediationStrategy.SCALE_HORIZONTAL.value],
    IncidentType.MEMORY_LEAK.value: [RemediationStrategy.RESTART_SERVICE.value, RemediationStrategy.CLEAR_CACHE.value],
    IncidentType.NETWORK_DEGRADATION.value: [RemediationStrategy.REBALANCE_LOAD.value, RemediationStrategy.SCALE_HORIZONTAL.value],
    IncidentType.TIMEOUT_MISCONFIGURATION.value: [RemediationStrategy.CHANGE_TIMEOUT.value, RemediationStrategy.ROLLBACK_DEPLOYMENT.value],
}


def _load_strategies() -> Dict[str, Any]:
    if os.path.exists(STRATEGY_FILE):
        with open(STRATEGY_FILE) as f:
            return json.load(f)
    return {}


def _save_strategies(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STRATEGY_FILE) if os.path.dirname(STRATEGY_FILE) else ".", exist_ok=True)
    with open(STRATEGY_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Heuristic fallbacks (original hardcoded logic)
# ---------------------------------------------------------------------------

def _heuristic_get_tools_for_strategy(strategy: str) -> List[str]:
    tool_map = {
        RemediationStrategy.RESTART_SERVICE.value: ["analyze_logs_activity", "restart_service_activity", "query_metrics_tool_activity"],
        RemediationStrategy.SCALE_HORIZONTAL.value: ["query_metrics_tool_activity", "scale_horizontal_activity", "rebalance_load_activity"],
        RemediationStrategy.SCALE_VERTICAL.value: ["query_metrics_tool_activity", "scale_vertical_activity", "restart_service_activity"],
        RemediationStrategy.CHANGE_TIMEOUT.value: ["analyze_logs_activity", "change_timeout_activity", "query_metrics_tool_activity"],
        RemediationStrategy.ROLLBACK_DEPLOYMENT.value: ["analyze_logs_activity", "rollback_deployment_activity", "query_metrics_tool_activity"],
        RemediationStrategy.CLEAR_CACHE.value: ["clear_cache_activity", "query_metrics_tool_activity"],
        RemediationStrategy.REBALANCE_LOAD.value: ["rebalance_load_activity", "query_metrics_tool_activity"],
        RemediationStrategy.COMBINED_RESTART_SCALE.value: ["analyze_logs_activity", "restart_service_activity", "scale_horizontal_activity", "rebalance_load_activity"],
        RemediationStrategy.COMBINED_CACHE_REBALANCE.value: ["clear_cache_activity", "rebalance_load_activity", "query_metrics_tool_activity"],
        RemediationStrategy.COMBINED_ROLLBACK_SCALE.value: ["analyze_logs_activity", "rollback_deployment_activity", "scale_horizontal_activity"],
    }
    return tool_map.get(strategy, ["query_metrics_tool_activity", "restart_service_activity"])


def _heuristic_get_default_parameters(strategy: str) -> Dict[str, Any]:
    params_map = {
        RemediationStrategy.SCALE_HORIZONTAL.value: {"target_instances": 4},
        RemediationStrategy.SCALE_VERTICAL.value: {"target_cpu": 4.0, "target_memory_gb": 8.0},
        RemediationStrategy.CHANGE_TIMEOUT.value: {"new_timeout": 15000},
        RemediationStrategy.COMBINED_RESTART_SCALE.value: {"target_instances": 3},
        RemediationStrategy.COMBINED_ROLLBACK_SCALE.value: {"target_instances": 3},
    }
    return params_map.get(strategy, {})


def _validate_strategy(strategy: str) -> bool:
    return strategy in ALL_STRATEGIES


def _clamp_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp LLM-generated parameters to safe ranges."""
    if "target_instances" in params:
        params["target_instances"] = max(1, min(10, int(params["target_instances"])))
    if "target_cpu" in params:
        params["target_cpu"] = max(0.5, min(16.0, float(params["target_cpu"])))
    if "target_memory_gb" in params:
        params["target_memory_gb"] = max(0.5, min(64.0, float(params["target_memory_gb"])))
    if "new_timeout" in params:
        params["new_timeout"] = max(1000, min(300000, int(params["new_timeout"])))
    if "new_timeout_ms" in params:
        params["new_timeout_ms"] = max(1000, min(300000, int(params["new_timeout_ms"])))
    return params


# ---------------------------------------------------------------------------
# LLM-driven strategy selection
# ---------------------------------------------------------------------------

async def _llm_select_strategy(
    incident_type: str,
    severity: str,
    description: str,
    metrics: Dict[str, Any],
    memory_context: Dict[str, Any],
    known_strategies: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """Use LLM to select strategy, tools, and parameters.

    Returns None on failure (caller falls back to heuristic).
    """
    # Format memory context for the prompt
    memory_lines = []
    best_data = memory_context.get("best_strategy_data", {})
    if best_data.get("best_strategy"):
        ranking = best_data.get("strategy_ranking", [])
        for r in ranking[:5]:
            memory_lines.append(f"  - {r['strategy']}: avg_reward={r['avg_reward']}")

    recent_exps = memory_context.get("recent_experiences", [])
    recent_lines = []
    for exp in recent_exps[-3:]:
        recent_lines.append(
            f"  - {exp.get('strategy_used', '?')}: reward={exp.get('reward', 0):.1f}, "
            f"restored={exp.get('success', False)}"
        )

    known_lines = []
    for s, r in sorted(known_strategies.items(), key=lambda x: x[1], reverse=True):
        known_lines.append(f"  - {s}: avg_reward={r:.2f}")

    system_prompt = f"""You are an expert SRE planner selecting the optimal remediation strategy.

{STRATEGY_DESCRIPTIONS}

{SRE_AVAILABLE_TOOLS}

You must respond with valid JSON only:
{{
  "strategy": "<one of the strategy names above>",
  "tools_to_call": ["tool1_activity", "tool2_activity"],
  "tool_parameters": {{"target_instances": 3}},
  "reasoning": "<1-2 sentence explanation>"
}}

Rules:
- Pick the strategy most likely to resolve the incident quickly with minimal cost.
- Use historical performance data to inform your choice.
- Tool names in tools_to_call must end with _activity (e.g., restart_service_activity).
- Only include tool_parameters relevant to the tools you choose."""

    user_prompt = f"""Incident: {incident_type} (severity: {severity})
Description: {description}

Current Metrics:
  latency_ms: {metrics.get('latency_ms', 'N/A')}
  cpu_percent: {metrics.get('cpu_percent', 'N/A')}
  memory_percent: {metrics.get('memory_percent', 'N/A')}
  error_rate: {metrics.get('error_rate', 'N/A')}
  availability: {metrics.get('availability', 'N/A')}

Historical Strategy Performance (this incident type):
{chr(10).join(known_lines) if known_lines else '  No prior data.'}

Memory Rankings:
{chr(10).join(memory_lines) if memory_lines else '  No prior data.'}

Recent Experiences (last 3):
{chr(10).join(recent_lines) if recent_lines else '  No prior experiences.'}

Select the best remediation strategy."""

    try:
        response = await call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=float(os.getenv("LLM_TEMPERATURE_PLANNING", "0.3")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS_PLANNING", "800")),
            json_mode=True,
        )
        result = parse_llm_json(response)
        if not result:
            return None

        strategy = result.get("strategy", "")
        if not _validate_strategy(strategy):
            logger.warning(f"LLM selected invalid strategy: {strategy}")
            return None

        # Validate tool names
        tools = result.get("tools_to_call", [])
        valid_tools = [t for t in tools if t.endswith("_activity")]
        if not valid_tools:
            valid_tools = _heuristic_get_tools_for_strategy(strategy)

        params = _clamp_parameters(result.get("tool_parameters", {}))

        return {
            "strategy": strategy,
            "tools_to_call": valid_tools,
            "tool_parameters": params,
            "reasoning": result.get("reasoning", ""),
            "llm_selected": True,
        }

    except Exception as e:
        logger.warning(f"LLM strategy selection failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Temporal activities
# ---------------------------------------------------------------------------

@activity.defn(name="select_strategy_activity")
async def select_strategy_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Select a remediation strategy. Uses LLM for exploit, random for explore."""
    incident_type = params.get("incident_type", "")
    run_index = params.get("run_index", 0)
    force_explore = params.get("force_explore", False)

    strategies = _load_strategies()
    explore_rate = float(os.getenv("EXPLORATION_RATE", "0.2"))

    known_strategies = {}
    for strategy in ALL_STRATEGIES:
        key = f"{incident_type}::{strategy}"
        if key in strategies and strategies[key]["total_uses"] > 0:
            known_strategies[strategy] = strategies[key]["average_reward"]

    is_exploratory = False
    llm_selected = False

    if force_explore or random.random() < explore_rate or not known_strategies:
        # EXPLORE: keep random selection (unchanged)
        priors = STRATEGY_PRIORS.get(incident_type, ALL_STRATEGIES)
        if not known_strategies:
            selected_strategy = random.choice(priors)
            reason = "no_history_using_prior"
        else:
            underused = [s for s in ALL_STRATEGIES if known_strategies.get(s, 0) < 1.0]
            pool = underused if underused else ALL_STRATEGIES
            selected_strategy = random.choice(pool)
            reason = "epsilon_greedy_explore"
        is_exploratory = True
        tools_to_call = _heuristic_get_tools_for_strategy(selected_strategy)
        tool_parameters = _heuristic_get_default_parameters(selected_strategy)
    else:
        # EXPLOIT: use LLM with memory context, fall back to heuristic
        llm_result = await _llm_select_strategy(
            incident_type=incident_type,
            severity=params.get("severity", "unknown"),
            description=params.get("description", ""),
            metrics=params.get("metrics", {}),
            memory_context=params.get("memory_context", {}),
            known_strategies=known_strategies,
        )

        if llm_result:
            selected_strategy = llm_result["strategy"]
            tools_to_call = llm_result["tools_to_call"]
            tool_parameters = llm_result["tool_parameters"]
            reason = f"llm_exploit ({llm_result.get('reasoning', '')[:100]})"
            llm_selected = True
        else:
            # Fallback to heuristic exploit
            best = max(known_strategies, key=known_strategies.get)
            selected_strategy = best
            tools_to_call = _heuristic_get_tools_for_strategy(best)
            tool_parameters = _heuristic_get_default_parameters(best)
            reason = f"exploit_best_known_fallback (avg_reward={known_strategies[best]:.2f})"

    logger.info(f"[Run {run_index}] Strategy: {selected_strategy} ({reason})")

    return {
        "strategy": selected_strategy,
        "tools_to_call": tools_to_call,
        "tool_parameters": tool_parameters,
        "is_exploratory": is_exploratory,
        "selection_reason": reason,
        "known_strategies_count": len(known_strategies),
        "llm_selected": llm_selected,
        "reasoning": reason,
    }


@activity.defn(name="update_strategy_record_activity")
async def update_strategy_record_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Update the strategy performance record."""
    incident_type = params.get("incident_type", "")
    strategy = params.get("strategy", "")
    reward = params.get("reward", 0.0)
    success = params.get("success", False)

    strategies = _load_strategies()
    key = f"{incident_type}::{strategy}"

    record = strategies.get(key, {
        "incident_type": incident_type,
        "strategy": strategy,
        "total_uses": 0,
        "total_reward": 0.0,
        "success_count": 0,
        "failure_count": 0,
        "average_reward": 0.0,
        "success_rate": 0.0,
    })

    record["total_uses"] += 1
    record["total_reward"] += reward
    record["success_count"] += (1 if success else 0)
    record["failure_count"] += (0 if success else 1)
    record["average_reward"] = round(record["total_reward"] / record["total_uses"], 3)
    record["success_rate"] = round(record["success_count"] / record["total_uses"], 3)
    record["last_used"] = datetime.utcnow().isoformat()

    strategies[key] = record
    _save_strategies(strategies)

    logger.info(f"Strategy updated: {key} avg_reward={record['average_reward']:.2f}")
    return {"status": "updated", "key": key, "record": record}


@activity.defn(name="get_strategy_rankings_activity")
async def get_strategy_rankings_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return strategy rankings."""
    incident_type = params.get("incident_type")

    strategies = _load_strategies()
    rankings: Dict[str, List[Dict]] = {}
    incident_types = [incident_type] if incident_type else [i.value for i in IncidentType]

    for itype in incident_types:
        type_records = []
        for strategy in ALL_STRATEGIES:
            key = f"{itype}::{strategy}"
            if key in strategies and strategies[key]["total_uses"] > 0:
                r = strategies[key]
                type_records.append({
                    "strategy": strategy,
                    "avg_reward": r["average_reward"],
                    "success_rate": r["success_rate"],
                    "total_uses": r["total_uses"],
                    "rank": 0,
                })
        type_records.sort(key=lambda x: x["avg_reward"], reverse=True)
        for i, rec in enumerate(type_records):
            rec["rank"] = i + 1
        if type_records:
            rankings[itype] = type_records

    return {"status": "success", "rankings": rankings}
