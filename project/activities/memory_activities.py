"""Memory persistence activities for EVOO.

All activities accept a single dict argument (ActivityHelpers constraint).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from temporalio import activity

from agentex.lib.utils.logging import make_logger

from project.models.experience import MemorySummary
from project.models.incident import IncidentType

logger = make_logger(__name__)

MEMORY_FILE = os.getenv("MEMORY_FILE_PATH", "/tmp/evoo_memory.json")


def _load_json(path: str) -> Any:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


@activity.defn(name="store_experience_activity")
async def store_experience_activity(experience_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist an experience tuple to memory."""
    experience_data["id"] = str(uuid.uuid4())[:8]
    experience_data["timestamp"] = datetime.utcnow().isoformat()

    memories = _load_json(MEMORY_FILE) or []
    memories.append(experience_data)
    _save_json(MEMORY_FILE, memories)

    logger.info(
        f"Stored experience: id={experience_data['id']} "
        f"strategy={experience_data.get('strategy_used')} "
        f"reward={experience_data.get('reward', 0):.2f}"
    )
    return {"status": "stored", "experience_id": experience_data["id"], "total_memories": len(memories)}


@activity.defn(name="retrieve_best_strategy_activity")
async def retrieve_best_strategy_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve the best-performing strategies for a given incident type."""
    incident_type = params.get("incident_type", "")
    top_k = params.get("top_k", 5)

    memories = _load_json(MEMORY_FILE) or []
    relevant = [m for m in memories if m.get("incident_type") == incident_type]

    if not relevant:
        return {
            "status": "no_history",
            "incident_type": incident_type,
            "best_strategy": None,
            "experiences_found": 0,
        }

    strategy_rewards: Dict[str, List[float]] = {}
    for mem in relevant:
        s = mem.get("strategy_used", "unknown")
        r = mem.get("reward", 0.0)
        strategy_rewards.setdefault(s, []).append(r)

    strategy_avg = {s: sum(rewards) / len(rewards) for s, rewards in strategy_rewards.items()}
    ranked = sorted(strategy_avg.items(), key=lambda x: x[1], reverse=True)

    best_strategy = ranked[0][0] if ranked else None
    return {
        "status": "found",
        "incident_type": incident_type,
        "best_strategy": best_strategy,
        "strategy_ranking": [{"strategy": s, "avg_reward": round(r, 2)} for s, r in ranked[:top_k]],
        "experiences_found": len(relevant),
        "total_experiences": len(memories),
    }


@activity.defn(name="retrieve_recent_experiences_activity")
async def retrieve_recent_experiences_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve the most recent experiences."""
    incident_type = params.get("incident_type")
    limit = params.get("limit", 10)

    memories = _load_json(MEMORY_FILE) or []
    if incident_type:
        relevant = [m for m in memories if m.get("incident_type") == incident_type]
    else:
        relevant = memories

    recent = relevant[-limit:]
    return {"status": "success", "experiences": recent, "total_returned": len(recent)}


@activity.defn(name="get_memory_summary_activity")
async def get_memory_summary_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a high-level summary of what the agent has learned so far."""
    memories = _load_json(MEMORY_FILE) or []

    if not memories:
        return MemorySummary().model_dump()

    rewards = [m.get("reward", 0.0) for m in memories]
    recovery_times = [m.get("recovery_time", 0.0) for m in memories if m.get("recovery_time")]

    rankings: Dict[str, List[Dict]] = {}
    for incident_type in IncidentType:
        relevant = [m for m in memories if m.get("incident_type") == incident_type.value]
        if not relevant:
            continue
        agg: Dict[str, List[float]] = {}
        for m in relevant:
            s = m.get("strategy_used", "unknown")
            agg.setdefault(s, []).append(m.get("reward", 0.0))
        ranked = sorted(
            [(s, sum(r) / len(r)) for s, r in agg.items()],
            key=lambda x: x[1], reverse=True,
        )
        rankings[incident_type.value] = [
            {"strategy": s, "avg_reward": round(r, 2), "uses": len(agg[s])} for s, r in ranked[:3]
        ]

    summary = MemorySummary(
        total_experiences=len(memories),
        total_runs=len(memories),
        average_reward=round(sum(rewards) / len(rewards), 2),
        best_reward=round(max(rewards), 2),
        average_recovery_time=round(sum(recovery_times) / len(recovery_times), 1) if recovery_times else 0.0,
        best_recovery_time=round(min(recovery_times), 1) if recovery_times else 0.0,
        strategy_rankings=rankings,
        improvement_trend=rewards[-20:],
    )
    return summary.model_dump()


@activity.defn(name="apply_previous_successful_strategy_activity")
async def apply_previous_successful_strategy_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve the most successful strategy for this incident type."""
    incident_type = params.get("incident_type", "")
    task_id = params.get("task_id", "")

    memories = _load_json(MEMORY_FILE) or []
    relevant = [m for m in memories if m.get("incident_type") == incident_type and m.get("success", False)]

    if not relevant:
        return {"tool": "apply_previous_successful_strategy", "status": "no_successful_history"}

    relevant.sort(key=lambda x: x.get("reward", 0), reverse=True)
    best = relevant[0]
    return {
        "tool": "apply_previous_successful_strategy",
        "status": "found",
        "recommendation": {
            "strategy": best.get("strategy_used"),
            "tools_called": best.get("tools_called", []),
            "avg_reward": best.get("reward"),
        },
    }
