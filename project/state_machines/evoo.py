"""State machine for EVOO agent workflow."""

from typing import Any, Dict, List, Optional, override

from pydantic import BaseModel, Field

from agentex.lib.sdk.state_machine import StateMachine
from agentex.types.span import Span

from project.models.enums import EvooState


class EvooData(BaseModel):
    """Data model for EVOO agent workflow state."""

    # Task tracking
    task_id: Optional[str] = None
    current_span: Optional[Span] = None
    current_turn: int = 0
    messages_received: int = 0

    # Incident state
    current_incident_id: Optional[str] = None
    current_incident_type: Optional[str] = None
    current_incident_severity: Optional[str] = None
    incident_description: str = ""
    metrics_before: Dict[str, Any] = Field(default_factory=dict)
    metrics_after: Dict[str, Any] = Field(default_factory=dict)

    # Planning state
    selected_strategy: Optional[str] = None
    strategy_details: Dict[str, Any] = Field(default_factory=dict)
    planning_reasoning: str = ""
    planning_confidence: float = 0.0
    is_exploration: bool = False

    # Execution state
    actions_executed: List[Dict[str, Any]] = Field(default_factory=list)
    tools_called: List[str] = Field(default_factory=list)
    execution_results: List[Dict[str, Any]] = Field(default_factory=list)
    total_recovery_time: float = 0.0
    total_cost: float = 0.0

    # Evaluation state
    service_restored: bool = False
    reward: float = 0.0
    reward_breakdown: Dict[str, float] = Field(default_factory=dict)
    llm_evaluation: str = ""
    adjusted_reward: float = 0.0

    # Learning state
    experience_stored: bool = False
    strategy_rankings_updated: bool = False

    # Conversation
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)

    # Loop control
    incident_count: int = 0
    max_incidents: int = 10
    waiting_for_user_input: bool = False
    auto_mode: bool = True  # If True, automatically generates incidents
    learning_loop_active: bool = True

    # Error handling
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3

    # Observability
    agent_metrics: Dict[str, Any] = Field(default_factory=dict)
    strategy_rankings: List[Dict[str, Any]] = Field(default_factory=list)

    def reset_for_new_incident(self) -> None:
        """Reset state for a new incident cycle."""
        self.current_incident_id = None
        self.current_incident_type = None
        self.current_incident_severity = None
        self.incident_description = ""
        self.metrics_before = {}
        self.metrics_after = {}
        self.selected_strategy = None
        self.strategy_details = {}
        self.planning_reasoning = ""
        self.planning_confidence = 0.0
        self.is_exploration = False
        self.actions_executed = []
        self.tools_called = []
        self.execution_results = []
        self.total_recovery_time = 0.0
        self.total_cost = 0.0
        self.service_restored = False
        self.reward = 0.0
        self.reward_breakdown = {}
        self.llm_evaluation = ""
        self.adjusted_reward = 0.0
        self.experience_stored = False
        self.strategy_rankings_updated = False
        self.error_message = ""
        self.retry_count = 0


class EvooStateMachine(StateMachine[EvooData]):
    """State machine for orchestrating the EVOO learning loop."""

    @override
    async def terminal_condition(self) -> bool:
        """Check if the state machine has reached a terminal state."""
        current_state = self.get_current_state()
        state_data = self.get_state_machine_data()

        # Terminal if in COMPLETED or FAILED state
        if current_state in [EvooState.COMPLETED, EvooState.FAILED]:
            return True

        # Terminal if max incidents reached and learning loop is not active
        if state_data and state_data.incident_count >= state_data.max_incidents:
            if not state_data.learning_loop_active:
                return True

        return False