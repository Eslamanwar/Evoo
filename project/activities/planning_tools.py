"""Planning and strategy selection activities for EVOO agent."""

import json
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from temporalio import activity

from agentex.lib.utils.logging import make_logger
from project.constants import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from project.memory.experience_store import ExperienceStore
from project.models.enums import IncidentType
from project.strategy.strategy_catalog import get_strategies_for_incident
from project.strategy.strategy_manager import StrategyManager

logger = make_logger(__name__)

# Shared instances
_experience_store: Optional[ExperienceStore] = None
_strategy_manager: Optional[StrategyManager] = None


def get_experience_store() -> ExperienceStore:
    """Get the shared experience store."""
    global _experience_store
    if _experience_store is None:
        _experience_store = ExperienceStore()
    return _experience_store


def get_strategy_manager() -> StrategyManager:
    """Get the shared strategy manager."""
    global _strategy_manager
    if _strategy_manager is None:
        _strategy_manager = StrategyManager(get_experience_store())
    return _strategy_manager


def set_shared_instances(store: ExperienceStore, manager: StrategyManager) -> None:
    """Set shared instances for activities."""
    global _experience_store, _strategy_manager
    _experience_store = store
    _strategy_manager = manager


@activity.defn(name="plan_remediation")
async def plan_remediation(
    incident_type: str,
    incident_severity: str,
    metrics: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
) -> str:
    """Use LLM to plan remediation strategy based on incident context and history.

    The planner agent evaluates the system state, considers historical performance,
    and selects the best remediation strategy.

    Args:
        incident_type: Type of incident.
        incident_severity: Severity level.
        metrics: Current system metrics.
        conversation_history: Previous conversation context.

    Returns:
        JSON string with the remediation plan.
    """
    logger.info(f"🧠 Planning remediation for {incident_type} ({incident_severity})")

    store = get_experience_store()
    manager = get_strategy_manager()

    try:
        inc_type = IncidentType(incident_type)
    except ValueError:
        return json.dumps({
            "error": f"Unknown incident type: {incident_type}",
            "strategy": None,
        })

    # Get available strategies
    available = get_strategies_for_incident(inc_type)
    best_records = store.get_best_strategy_for_incident(inc_type, top_k=5)

    # Build context for LLM planner
    strategy_context = ""
    for strategy in available:
        strategy_context += f"\n- {strategy.name}: {strategy.description}"
        strategy_context += f"\n  Actions: {', '.join(a.description for a in strategy.actions)}"
        strategy_context += f"\n  Est. recovery: {strategy.estimated_recovery_time_seconds}s, Est. cost: {strategy.estimated_cost}"

    history_context = ""
    if best_records:
        history_context = "\n\nHISTORICAL PERFORMANCE DATA:"
        for record in best_records:
            history_context += f"\n- {record.strategy_name}: avg_reward={record.average_reward:.1f}, "
            history_context += f"success_rate={record.success_rate:.1%}, "
            history_context += f"avg_recovery={record.average_recovery_time:.0f}s, "
            history_context += f"uses={record.total_uses}"
    else:
        history_context = "\n\nNo historical data available - this is an exploration phase."

    planning_prompt = f"""You are an expert SRE planner for the EVOO autonomous remediation system.

CURRENT INCIDENT:
- Type: {incident_type}
- Severity: {incident_severity}
- Current Metrics:
  - Latency: {metrics.get('latency_ms', 'N/A')}ms
  - CPU: {metrics.get('cpu_percent', 'N/A')}%
  - Memory: {metrics.get('memory_percent', 'N/A')}%
  - Error Rate: {metrics.get('error_rate', 'N/A')}
  - Availability: {metrics.get('availability', 'N/A')}
  - Active Instances: {metrics.get('active_instances', 'N/A')}

AVAILABLE STRATEGIES:{strategy_context}
{history_context}

EXPLORATION RATE: {manager.get_exploration_rate():.1%}

Based on the incident details, available strategies, and historical performance data,
select the best remediation strategy. Consider:
1. Historical success rates and rewards
2. Incident severity (higher severity = prefer proven strategies)
3. Cost efficiency
4. Recovery time
5. Whether exploration of untried strategies is warranted

Respond in JSON format with:
- selected_strategy: name of the chosen strategy
- reasoning: brief explanation of why this strategy was chosen
- confidence: 0.0 to 1.0
- is_exploration: true if this is an exploratory choice"""

    try:
        api_key = os.environ.get("OPENAI_API_KEY") or OPENAI_API_KEY
        base_url = os.environ.get("OPENAI_BASE_URL", OPENAI_BASE_URL)
        model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)

        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert SRE planner. Respond only in valid JSON."},
                {"role": "user", "content": planning_prompt},
            ],
            max_tokens=500,
        )

        llm_response = response.choices[0].message.content

        try:
            plan = json.loads(llm_response)
        except json.JSONDecodeError:
            # Fallback to strategy manager selection
            selected = manager.select_strategy(inc_type)
            plan = {
                "selected_strategy": selected.name,
                "reasoning": "LLM response parsing failed, using strategy manager selection",
                "confidence": 0.5,
                "is_exploration": True,
            }

        # Validate the selected strategy exists
        selected_name = plan.get("selected_strategy", "")
        valid_names = [s.name for s in available]
        if selected_name not in valid_names:
            # Fallback to strategy manager
            selected = manager.select_strategy(inc_type)
            plan["selected_strategy"] = selected.name
            plan["reasoning"] += f" (original selection '{selected_name}' not found, using fallback)"

        # Get the full strategy details
        selected_strategy = next(s for s in available if s.name == plan["selected_strategy"])
        plan["strategy_details"] = selected_strategy.to_dict()

        logger.info(f"Plan selected: {plan['selected_strategy']} (confidence: {plan.get('confidence', 'N/A')})")
        return json.dumps(plan, default=str)

    except Exception as e:
        logger.error(f"LLM planning failed: {e}")
        # Fallback to strategy manager
        selected = manager.select_strategy(inc_type)
        fallback_plan = {
            "selected_strategy": selected.name,
            "reasoning": f"LLM planning failed ({str(e)}), using strategy manager selection",
            "confidence": 0.4,
            "is_exploration": True,
            "strategy_details": selected.to_dict(),
        }
        return json.dumps(fallback_plan, default=str)


@activity.defn(name="get_strategy_recommendation")
async def get_strategy_recommendation(incident_type: str) -> str:
    """Get a strategy recommendation from the strategy manager.

    Args:
        incident_type: The incident type.

    Returns:
        JSON string with recommendation details.
    """
    logger.info(f"📋 Getting strategy recommendation for {incident_type}")
    manager = get_strategy_manager()

    try:
        inc_type = IncidentType(incident_type)
    except ValueError:
        return json.dumps({"error": f"Unknown incident type: {incident_type}"})

    recommendation = manager.get_strategy_recommendation(inc_type)
    return json.dumps(recommendation, default=str)