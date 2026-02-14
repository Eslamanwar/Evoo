"""Strategy manager for EVOO - handles strategy selection with exploration vs exploitation."""

import random
from typing import Any, Dict, List, Optional

from project.memory.experience_store import ExperienceStore
from project.models.enums import IncidentType
from project.models.strategies import RemediationStrategy, StrategyRecord
from project.strategy.strategy_catalog import get_strategies_for_incident, get_strategy_by_name


class StrategyManager:
    """Manages strategy selection using reward-based learning with exploration.

    Implements an epsilon-greedy approach:
    - With probability (1 - epsilon): exploit the best known strategy
    - With probability epsilon: explore a random alternative strategy

    Epsilon decays over time as the agent gains more experience.
    """

    def __init__(
        self,
        experience_store: ExperienceStore,
        initial_epsilon: float = 0.3,
        min_epsilon: float = 0.05,
        epsilon_decay: float = 0.95,
    ):
        """Initialize the strategy manager.

        Args:
            experience_store: The experience store for accessing historical data.
            initial_epsilon: Initial exploration rate.
            min_epsilon: Minimum exploration rate.
            epsilon_decay: Decay factor applied to epsilon after each selection.
        """
        self.experience_store = experience_store
        self.epsilon = initial_epsilon
        self.min_epsilon = min_epsilon
        self.epsilon_decay = epsilon_decay

    def select_strategy(
        self,
        incident_type: IncidentType,
        force_explore: bool = False,
    ) -> RemediationStrategy:
        """Select a remediation strategy for the given incident type.

        Uses epsilon-greedy approach: exploit best known strategy most of the time,
        but occasionally explore alternatives.

        Args:
            incident_type: The type of incident to remediate.
            force_explore: If True, always explore (select random strategy).

        Returns:
            The selected remediation strategy.
        """
        available_strategies = get_strategies_for_incident(incident_type)

        if not available_strategies:
            raise ValueError(f"No strategies available for incident type: {incident_type}")

        # Get historical performance data
        best_records = self.experience_store.get_best_strategy_for_incident(
            incident_type, top_k=len(available_strategies)
        )

        # Decide: explore or exploit
        should_explore = force_explore or random.random() < self.epsilon

        if should_explore or not best_records:
            # Exploration: pick a random strategy
            selected = random.choice(available_strategies)
            selection_reason = "exploration"
        else:
            # Exploitation: pick the best known strategy
            best_strategy_name = best_records[0].strategy_name
            try:
                selected = get_strategy_by_name(best_strategy_name)
                selection_reason = "exploitation"
            except KeyError:
                # Fallback to random if best strategy no longer exists
                selected = random.choice(available_strategies)
                selection_reason = "fallback"

        # Decay epsilon
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

        return selected

    def get_strategy_recommendation(
        self,
        incident_type: IncidentType,
    ) -> Dict[str, Any]:
        """Get a detailed strategy recommendation with reasoning.

        Args:
            incident_type: The type of incident.

        Returns:
            Dictionary with recommendation details.
        """
        available = get_strategies_for_incident(incident_type)
        best_records = self.experience_store.get_best_strategy_for_incident(
            incident_type, top_k=len(available)
        )

        # Build recommendation
        recommendation = {
            "incident_type": incident_type.value,
            "available_strategies": [s.name for s in available],
            "historical_data_available": len(best_records) > 0,
            "current_epsilon": round(self.epsilon, 3),
            "best_known_strategies": [],
            "untried_strategies": [],
        }

        tried_names = {r.strategy_name for r in best_records}

        for record in best_records:
            recommendation["best_known_strategies"].append({
                "name": record.strategy_name,
                "average_reward": round(record.average_reward, 2),
                "success_rate": round(record.success_rate, 3),
                "total_uses": record.total_uses,
                "average_recovery_time": round(record.average_recovery_time, 1),
            })

        for strategy in available:
            if strategy.name not in tried_names:
                recommendation["untried_strategies"].append({
                    "name": strategy.name,
                    "description": strategy.description,
                    "estimated_recovery_time": strategy.estimated_recovery_time_seconds,
                    "estimated_cost": strategy.estimated_cost,
                })

        return recommendation

    def mark_strategy_success(
        self,
        strategy_name: str,
        incident_type: IncidentType,
        reward: float,
        recovery_time: float,
    ) -> None:
        """Record a successful strategy execution.

        Args:
            strategy_name: Name of the strategy.
            incident_type: Type of incident.
            reward: Reward score achieved.
            recovery_time: Recovery time in seconds.
        """
        # This is handled through the experience store
        # but we can use this to adjust epsilon more aggressively on success
        if reward > 50:
            # Good result - slightly reduce exploration
            self.epsilon = max(self.min_epsilon, self.epsilon * 0.98)

    def mark_strategy_failure(
        self,
        strategy_name: str,
        incident_type: IncidentType,
        reward: float,
        recovery_time: float,
    ) -> None:
        """Record a failed strategy execution.

        Args:
            strategy_name: Name of the strategy.
            incident_type: Type of incident.
            reward: Reward score achieved.
            recovery_time: Recovery time in seconds.
        """
        # On failure, slightly increase exploration to find better strategies
        self.epsilon = min(0.5, self.epsilon * 1.1)

    def get_exploration_rate(self) -> float:
        """Get the current exploration rate (epsilon)."""
        return self.epsilon

    def get_strategy_rankings_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of all strategy rankings across all incident types.

        Returns:
            List of ranking summaries.
        """
        return self.experience_store.get_strategy_rankings()