"""Persistent experience store for EVOO agent memory."""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from project.models.enums import IncidentType
from project.models.experience import Experience
from project.models.strategies import StrategyRecord


class ExperienceStore:
    """Persistent storage for agent experiences and strategy records.

    Stores experience tuples and strategy performance records to enable
    the agent to learn from past remediation attempts.
    """

    def __init__(self, storage_path: str = "/tmp/evoo_memory"):
        """Initialize the experience store.

        Args:
            storage_path: Directory path for persistent storage.
        """
        self.storage_path = storage_path
        self.experiences_file = os.path.join(storage_path, "experiences.json")
        self.strategies_file = os.path.join(storage_path, "strategy_records.json")
        self.metrics_file = os.path.join(storage_path, "agent_metrics.json")

        # In-memory caches
        self._experiences: List[Experience] = []
        self._strategy_records: Dict[str, StrategyRecord] = {}
        self._agent_metrics: Dict[str, Any] = {
            "total_incidents": 0,
            "total_successful_remediations": 0,
            "total_failed_remediations": 0,
            "average_reward": 0.0,
            "average_recovery_time": 0.0,
            "reward_history": [],
            "recovery_time_history": [],
        }

        # Load from disk if available
        self._ensure_storage_dir()
        self._load()

    def _ensure_storage_dir(self) -> None:
        """Ensure the storage directory exists."""
        os.makedirs(self.storage_path, exist_ok=True)

    def _load(self) -> None:
        """Load data from persistent storage."""
        # Load experiences
        if os.path.exists(self.experiences_file):
            try:
                with open(self.experiences_file, "r") as f:
                    data = json.load(f)
                    self._experiences = [Experience(**exp) for exp in data]
            except (json.JSONDecodeError, Exception):
                self._experiences = []

        # Load strategy records
        if os.path.exists(self.strategies_file):
            try:
                with open(self.strategies_file, "r") as f:
                    data = json.load(f)
                    self._strategy_records = {
                        key: StrategyRecord(**val) for key, val in data.items()
                    }
            except (json.JSONDecodeError, Exception):
                self._strategy_records = {}

        # Load agent metrics
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, "r") as f:
                    self._agent_metrics = json.load(f)
            except (json.JSONDecodeError, Exception):
                pass

    def _save(self) -> None:
        """Save data to persistent storage."""
        self._ensure_storage_dir()

        # Save experiences
        with open(self.experiences_file, "w") as f:
            json.dump([exp.to_dict() for exp in self._experiences], f, indent=2, default=str)

        # Save strategy records
        with open(self.strategies_file, "w") as f:
            json.dump(
                {key: val.to_dict() for key, val in self._strategy_records.items()},
                f,
                indent=2,
                default=str,
            )

        # Save agent metrics
        with open(self.metrics_file, "w") as f:
            json.dump(self._agent_metrics, f, indent=2, default=str)

    def store_experience(self, experience: Experience) -> None:
        """Store a new experience and update strategy records.

        Args:
            experience: The experience to store.
        """
        self._experiences.append(experience)

        # Update strategy record
        record_key = f"{experience.strategy_used}:{experience.incident_type.value}"
        if record_key not in self._strategy_records:
            self._strategy_records[record_key] = StrategyRecord(
                strategy_name=experience.strategy_used,
                incident_type=experience.incident_type,
            )

        record = self._strategy_records[record_key]
        record.update_with_result(
            reward=experience.reward,
            recovery_time=experience.recovery_time_seconds,
            success=experience.success,
        )
        record.last_used = experience.timestamp

        # Update agent metrics
        self._agent_metrics["total_incidents"] += 1
        if experience.success:
            self._agent_metrics["total_successful_remediations"] += 1
        else:
            self._agent_metrics["total_failed_remediations"] += 1

        self._agent_metrics["reward_history"].append(experience.reward)
        self._agent_metrics["recovery_time_history"].append(experience.recovery_time_seconds)

        total = self._agent_metrics["total_incidents"]
        self._agent_metrics["average_reward"] = (
            sum(self._agent_metrics["reward_history"]) / total
        )
        self._agent_metrics["average_recovery_time"] = (
            sum(self._agent_metrics["recovery_time_history"]) / total
        )

        # Persist to disk
        self._save()

    def get_best_strategy_for_incident(
        self, incident_type: IncidentType, top_k: int = 3
    ) -> List[StrategyRecord]:
        """Get the best performing strategies for a given incident type.

        Args:
            incident_type: The type of incident to find strategies for.
            top_k: Number of top strategies to return.

        Returns:
            List of top strategy records sorted by average reward.
        """
        relevant_records = [
            record
            for record in self._strategy_records.values()
            if record.incident_type == incident_type and record.total_uses > 0
        ]

        # Sort by average reward (descending), then by success rate
        relevant_records.sort(
            key=lambda r: (r.average_reward, r.success_rate), reverse=True
        )

        return relevant_records[:top_k]

    def get_experiences_for_incident_type(
        self, incident_type: IncidentType, limit: int = 10
    ) -> List[Experience]:
        """Get recent experiences for a given incident type.

        Args:
            incident_type: The type of incident.
            limit: Maximum number of experiences to return.

        Returns:
            List of recent experiences for the incident type.
        """
        relevant = [
            exp for exp in self._experiences if exp.incident_type == incident_type
        ]
        # Return most recent first
        return sorted(relevant, key=lambda e: e.timestamp, reverse=True)[:limit]

    def get_all_strategy_records(self) -> Dict[str, StrategyRecord]:
        """Get all strategy records.

        Returns:
            Dictionary of all strategy records.
        """
        return self._strategy_records.copy()

    def get_strategy_rankings(self, incident_type: Optional[IncidentType] = None) -> List[Dict[str, Any]]:
        """Get strategy rankings, optionally filtered by incident type.

        Args:
            incident_type: Optional filter by incident type.

        Returns:
            List of strategy ranking dictionaries.
        """
        records = self._strategy_records.values()
        if incident_type:
            records = [r for r in records if r.incident_type == incident_type]

        rankings = []
        for record in sorted(records, key=lambda r: r.average_reward, reverse=True):
            rankings.append({
                "strategy": record.strategy_name,
                "incident_type": record.incident_type.value,
                "uses": record.total_uses,
                "success_rate": round(record.success_rate, 3),
                "average_reward": round(record.average_reward, 2),
                "average_recovery_time": round(record.average_recovery_time, 1),
            })

        return rankings

    def get_agent_metrics(self) -> Dict[str, Any]:
        """Get overall agent performance metrics.

        Returns:
            Dictionary of agent performance metrics.
        """
        metrics = self._agent_metrics.copy()

        # Compute rolling averages for recent performance
        reward_history = metrics.get("reward_history", [])
        recovery_history = metrics.get("recovery_time_history", [])

        if len(reward_history) >= 5:
            metrics["recent_average_reward"] = round(
                sum(reward_history[-5:]) / 5, 2
            )
        else:
            metrics["recent_average_reward"] = metrics.get("average_reward", 0.0)

        if len(recovery_history) >= 5:
            metrics["recent_average_recovery_time"] = round(
                sum(recovery_history[-5:]) / 5, 1
            )
        else:
            metrics["recent_average_recovery_time"] = metrics.get("average_recovery_time", 0.0)

        # Compute improvement trend
        if len(reward_history) >= 10:
            first_half = sum(reward_history[: len(reward_history) // 2]) / (len(reward_history) // 2)
            second_half = sum(reward_history[len(reward_history) // 2 :]) / (
                len(reward_history) - len(reward_history) // 2
            )
            metrics["reward_improvement_trend"] = round(second_half - first_half, 2)
        else:
            metrics["reward_improvement_trend"] = 0.0

        return metrics

    def get_experience_count(self) -> int:
        """Get total number of stored experiences."""
        return len(self._experiences)

    def clear(self) -> None:
        """Clear all stored data."""
        self._experiences = []
        self._strategy_records = {}
        self._agent_metrics = {
            "total_incidents": 0,
            "total_successful_remediations": 0,
            "total_failed_remediations": 0,
            "average_reward": 0.0,
            "average_recovery_time": 0.0,
            "reward_history": [],
            "recovery_time_history": [],
        }
        self._save()