"""Strategy manager for EVOO - handles strategy selection with exploration vs exploitation."""

import math
import random
from typing import Any, Dict, List, Optional

from project.memory.experience_store import ExperienceStore
from project.models.enums import IncidentType
from project.models.strategies import RemediationStrategy, StrategyRecord
from project.strategy.strategy_catalog import get_strategies_for_incident, get_strategy_by_name

# UCB1 exploration constant — higher = more exploration
UCB1_C = 2.0

# Optimistic initial reward for untried strategies (encourages systematic exploration)
OPTIMISTIC_INIT_REWARD = 50.0


class StrategyManager:
    """Manages strategy selection using UCB1 (Upper Confidence Bound).

    UCB1 is provably better than epsilon-greedy for small sample sizes:
    - Untried strategies get an infinite exploration bonus (tried first)
    - Tried strategies get: avg_reward + C * sqrt(ln(N) / n_i)
    - Naturally balances exploitation vs exploration without tuning epsilon

    Falls back to epsilon-greedy behavior when only one strategy is available.
    """

    def __init__(
        self,
        experience_store: ExperienceStore,
        initial_epsilon: float = 0.3,
        min_epsilon: float = 0.05,
        epsilon_decay: float = 0.95,
        ucb_c: float = UCB1_C,
    ):
        self.experience_store = experience_store
        # Keep epsilon fields for API compatibility (used in reporting)
        self.epsilon = initial_epsilon
        self.min_epsilon = min_epsilon
        self.epsilon_decay = epsilon_decay
        self.ucb_c = ucb_c

        # Anti-repetition: track last strategy selected per incident type
        self._last_selected: Dict[str, str] = {}
        # Track consecutive failures per (incident_type, strategy) pair
        self._consecutive_failures: Dict[str, int] = {}

    def _ucb1_score(self, record: StrategyRecord, total_runs: int) -> float:
        """Compute UCB1 score for a strategy with historical data."""
        if record.total_uses == 0:
            return float("inf")
        exploration_bonus = self.ucb_c * math.sqrt(math.log(max(total_runs, 1)) / record.total_uses)
        return record.average_reward + exploration_bonus

    def select_strategy(
        self,
        incident_type: IncidentType,
        force_explore: bool = False,
    ) -> RemediationStrategy:
        """Select a remediation strategy using UCB1.

        UCB1 selection order:
        1. If any strategies are completely untried → pick the one with best catalog estimate
        2. Otherwise → pick strategy with highest UCB1 score
        3. Anti-repetition: avoid selecting the same strategy that just failed

        Args:
            incident_type: The type of incident to remediate.
            force_explore: If True, pick the least-tried strategy (pure exploration).

        Returns:
            The selected remediation strategy.
        """
        available_strategies = get_strategies_for_incident(incident_type)

        if not available_strategies:
            raise ValueError(f"No strategies available for incident type: {incident_type}")

        if len(available_strategies) == 1:
            return available_strategies[0]

        # Get historical performance records for this incident type
        all_records = self.experience_store.get_all_strategy_records()
        total_runs = sum(
            r.total_uses
            for key, r in all_records.items()
            if r.incident_type == incident_type
        )

        incident_key = incident_type.value
        last_selected = self._last_selected.get(incident_key)

        if force_explore:
            # Pure exploration: pick the least-used strategy (not the same as last)
            candidates = [s for s in available_strategies if s.name != last_selected]
            if not candidates:
                candidates = available_strategies
            record_map = {key.split(":")[0]: r for key, r in all_records.items()
                          if r.incident_type == incident_type}
            selected = min(candidates, key=lambda s: record_map.get(s.name, StrategyRecord(
                strategy_name=s.name, incident_type=incident_type
            )).total_uses)
            selection_reason = "exploration (least tried)"
        else:
            # UCB1 selection
            scored: List[tuple] = []
            for strategy in available_strategies:
                record_key = f"{strategy.name}:{incident_key}"
                record = all_records.get(record_key)

                if record is None or record.total_uses == 0:
                    # Untried: use optimistic score so it gets tried
                    score = float("inf")
                else:
                    # Check consecutive failures — penalize heavily repeated failures
                    fail_key = f"{incident_key}:{strategy.name}"
                    consec_fails = self._consecutive_failures.get(fail_key, 0)
                    penalty = consec_fails * 5.0  # -5 per consecutive failure
                    score = self._ucb1_score(record, total_runs) - penalty

                # Anti-repetition: penalize the strategy we just used
                if strategy.name == last_selected:
                    score -= 20.0

                scored.append((score, strategy))

            # Sort by score descending; break ties by estimated recovery time (prefer faster)
            scored.sort(key=lambda x: (x[0], -x[1].estimated_recovery_time_seconds), reverse=True)
            selected = scored[0][1]
            selection_reason = "UCB1"

        # Update tracking
        self._last_selected[incident_key] = selected.name

        # Decay epsilon for compatibility with any epsilon-based reporting
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

        return selected

    def get_strategy_recommendation(
        self,
        incident_type: IncidentType,
    ) -> Dict[str, Any]:
        """Get a detailed strategy recommendation with reasoning."""
        available = get_strategies_for_incident(incident_type)
        best_records = self.experience_store.get_best_strategy_for_incident(
            incident_type, top_k=len(available)
        )

        recommendation = {
            "incident_type": incident_type.value,
            "available_strategies": [s.name for s in available],
            "historical_data_available": len(best_records) > 0,
            "current_epsilon": round(self.epsilon, 3),
            "selection_algorithm": "UCB1",
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
        """Record a successful strategy execution."""
        fail_key = f"{incident_type.value}:{strategy_name}"
        self._consecutive_failures[fail_key] = 0  # Reset on success
        # Slightly reduce epsilon on good results (for reporting compatibility)
        if reward > 50:
            self.epsilon = max(self.min_epsilon, self.epsilon * 0.98)

    def mark_strategy_failure(
        self,
        strategy_name: str,
        incident_type: IncidentType,
        reward: float,
        recovery_time: float,
    ) -> None:
        """Record a failed strategy execution."""
        fail_key = f"{incident_type.value}:{strategy_name}"
        self._consecutive_failures[fail_key] = self._consecutive_failures.get(fail_key, 0) + 1
        # Increase epsilon slightly on failure (for reporting compatibility)
        self.epsilon = min(0.5, self.epsilon * 1.1)

    def get_exploration_rate(self) -> float:
        """Get the current exploration rate (epsilon, kept for reporting compatibility)."""
        return self.epsilon

    def get_strategy_rankings_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of all strategy rankings across all incident types."""
        return self.experience_store.get_strategy_rankings()
