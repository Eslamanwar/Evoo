"""State machine definition for the EVOO autonomous SRE agent."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, override

from pydantic import BaseModel, Field

from agentex.lib.sdk.state_machine import StateMachine

from project.models.incident import Incident, RemediationStrategy, SystemMetrics
from project.models.experience import Experience, MemorySummary


class EVOOState(str, Enum):
    """Operational states of the EVOO learning loop."""
    # Idle — waiting for an incident
    WAITING_FOR_INCIDENT = "waiting_for_incident"

    # Active learning cycle
    PLANNING_REMEDIATION = "planning_remediation"
    EXECUTING_REMEDIATION = "executing_remediation"
    EVALUATING_OUTCOME = "evaluating_outcome"
    UPDATING_STRATEGY = "updating_strategy"

    # Terminal
    COMPLETED = "completed"
    FAILED = "failed"


class RemediationPlan(BaseModel):
    """The remediation plan selected by the Planner agent."""
    strategy: RemediationStrategy = RemediationStrategy.RESTART_SERVICE
    tools_to_call: List[str] = Field(default_factory=list)
    tool_parameters: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 0.5
    is_exploratory: bool = False
    llm_selected: bool = False


class EVOOData(BaseModel):
    """Persistent state data for the EVOO workflow."""
    # Runtime context
    task_id: str = ""
    waiting_for_user_input: bool = True

    # Current incident context
    current_incident: Optional[Incident] = None
    current_plan: Optional[RemediationPlan] = None
    metrics_before: Optional[SystemMetrics] = None
    metrics_after: Optional[SystemMetrics] = None
    tool_execution_results: List[Dict[str, Any]] = Field(default_factory=list)

    # Simulation state
    simulated_system_state: Dict[str, Any] = Field(default_factory=dict)

    # Learning loop tracking
    run_index: int = 0
    max_runs: int = 50
    current_reward: float = 0.0
    last_llm_evaluation: str = ""
    current_experience: Optional[Experience] = None

    # Memory summary for display
    memory_summary: Optional[MemorySummary] = None

    # Learning progress history for observability
    reward_history: List[float] = Field(default_factory=list)
    recovery_time_history: List[float] = Field(default_factory=list)
    strategy_history: List[str] = Field(default_factory=list)
    incident_type_history: List[str] = Field(default_factory=list)
    verdict_history: List[str] = Field(default_factory=list)
    restored_history: List[bool] = Field(default_factory=list)

    # Agentic loop tracking
    agent_loop_iterations: int = 0
    agent_loop_actions: List[str] = Field(default_factory=list)

    # Status
    error_message: str = ""
    is_learning_complete: bool = False


class EVOOStateMachine(StateMachine[EVOOData]):
    """State machine for the EVOO autonomous SRE agent."""

    @override
    async def terminal_condition(self) -> bool:
        """Run until max_runs is reached or completion signal."""
        return self.state_machine_data.is_learning_complete
