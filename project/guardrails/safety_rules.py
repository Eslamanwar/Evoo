"""Safety guardrails for EVOO remediation actions.

Guardrails prevent the agent from taking dangerous actions that could
worsen an incident or cause additional outages. Each rule is configurable
and can be enabled/disabled independently.

Example guardrails:
- Don't restart if only 1 service pod (would cause full outage)
- Don't scale beyond max instance limits
- Don't rollback more than once per incident
- Don't change timeout below minimum threshold
- Cost budget limits per incident
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agentex.lib.utils.logging import make_logger

logger = make_logger(__name__)


class GuardrailVerdict(str, Enum):
    """Result of a guardrail check."""
    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"


@dataclass
class GuardrailResult:
    """Result of evaluating a guardrail rule."""
    verdict: GuardrailVerdict
    rule_name: str
    reason: str
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "rule_name": self.rule_name,
            "reason": self.reason,
            "suggestion": self.suggestion,
        }


@dataclass
class GuardrailConfig:
    """Configuration for all guardrail rules.

    All thresholds are configurable via environment variables or direct assignment.
    """

    # --- Instance / Pod Safety ---
    min_instances_for_restart: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MIN_INSTANCES_FOR_RESTART", "2"))
    )
    min_instances_for_rollback: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MIN_INSTANCES_FOR_ROLLBACK", "2"))
    )

    # --- Scaling Limits ---
    max_horizontal_instances: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MAX_HORIZONTAL_INSTANCES", "10"))
    )
    min_horizontal_instances: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MIN_HORIZONTAL_INSTANCES", "1"))
    )
    max_vertical_cpu: float = field(
        default_factory=lambda: float(os.getenv("EVOO_MAX_VERTICAL_CPU", "8.0"))
    )
    max_vertical_memory: float = field(
        default_factory=lambda: float(os.getenv("EVOO_MAX_VERTICAL_MEMORY", "16.0"))
    )

    # --- Timeout Safety ---
    min_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MIN_TIMEOUT_MS", "500"))
    )
    max_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MAX_TIMEOUT_MS", "60000"))
    )

    # --- Cost Budget ---
    max_cost_per_incident: float = field(
        default_factory=lambda: float(os.getenv("EVOO_MAX_COST_PER_INCIDENT", "50.0"))
    )

    # --- Action Frequency Limits ---
    max_restarts_per_incident: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MAX_RESTARTS_PER_INCIDENT", "3"))
    )
    max_rollbacks_per_incident: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MAX_ROLLBACKS_PER_INCIDENT", "1"))
    )
    max_total_actions_per_incident: int = field(
        default_factory=lambda: int(os.getenv("EVOO_MAX_ACTIONS_PER_INCIDENT", "10"))
    )

    # --- Health-Based Guards ---
    block_actions_if_healthy: bool = field(
        default_factory=lambda: os.getenv("EVOO_BLOCK_IF_HEALTHY", "true").lower() == "true"
    )
    healthy_threshold: float = field(
        default_factory=lambda: float(os.getenv("EVOO_HEALTHY_THRESHOLD", "0.85"))
    )

    # --- Feature Flags ---
    enabled: bool = field(
        default_factory=lambda: os.getenv("EVOO_GUARDRAILS_ENABLED", "true").lower() == "true"
    )


class GuardrailEngine:
    """Engine that evaluates safety guardrails before remediation actions.

    Usage:
        engine = GuardrailEngine()
        result = engine.check_action(
            action_type="restart_service",
            parameters={},
            system_state={"active_instances": 1, "health_score": 0.3},
            incident_context={"actions_taken": [], "total_cost": 0.0},
        )
        if result.verdict == GuardrailVerdict.BLOCK:
            # Skip this action
            ...
    """

    def __init__(self, config: Optional[GuardrailConfig] = None):
        self.config = config or GuardrailConfig()
        self._rules = self._build_rules()

    def _build_rules(self) -> List:
        """Build the list of guardrail rules."""
        return [
            self._check_restart_min_instances,
            self._check_rollback_min_instances,
            self._check_horizontal_scale_limits,
            self._check_vertical_scale_limits,
            self._check_timeout_bounds,
            self._check_cost_budget,
            self._check_action_frequency,
            self._check_already_healthy,
        ]

    def check_action(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> GuardrailResult:
        """Evaluate all guardrail rules for a proposed action.

        Args:
            action_type: The remediation action type (e.g., "restart_service").
            parameters: Action parameters (e.g., {"target_instances": 5}).
            system_state: Current system state including metrics.
                Expected keys: active_instances, health_score, metrics (dict)
            incident_context: Context about the current incident remediation.
                Expected keys: actions_taken (list of dicts), total_cost (float)

        Returns:
            GuardrailResult with the most restrictive verdict found.
        """
        if not self.config.enabled:
            return GuardrailResult(
                verdict=GuardrailVerdict.ALLOW,
                rule_name="guardrails_disabled",
                reason="Guardrails are disabled",
            )

        # Evaluate all rules, return the first BLOCK or most severe result
        warnings = []
        for rule_fn in self._rules:
            result = rule_fn(action_type, parameters, system_state, incident_context)
            if result is not None:
                if result.verdict == GuardrailVerdict.BLOCK:
                    logger.warning(
                        f"🛑 Guardrail BLOCKED: {result.rule_name} — {result.reason}"
                    )
                    return result
                if result.verdict == GuardrailVerdict.WARN:
                    warnings.append(result)

        if warnings:
            # Return the first warning
            logger.info(
                f"⚠️ Guardrail WARNING: {warnings[0].rule_name} — {warnings[0].reason}"
            )
            return warnings[0]

        return GuardrailResult(
            verdict=GuardrailVerdict.ALLOW,
            rule_name="all_checks_passed",
            reason="All guardrail checks passed",
        )

    # ─── Individual Rule Implementations ───────────────────────────────

    def _check_restart_min_instances(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Block restart_service if active instances below minimum threshold."""
        if action_type != "restart_service":
            return None

        active = system_state.get("active_instances", 2)
        min_required = self.config.min_instances_for_restart

        if active < min_required:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="min_instances_for_restart",
                reason=(
                    f"Cannot restart service: only {active} instance(s) running "
                    f"(minimum {min_required} required). Restarting would cause "
                    f"complete service outage."
                ),
                suggestion=(
                    f"Scale horizontally to at least {min_required} instances first, "
                    f"then retry the restart."
                ),
            )
        return None

    def _check_rollback_min_instances(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Block rollback if active instances below minimum threshold."""
        if action_type != "rollback_deployment":
            return None

        active = system_state.get("active_instances", 2)
        min_required = self.config.min_instances_for_rollback

        if active < min_required:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="min_instances_for_rollback",
                reason=(
                    f"Cannot rollback deployment: only {active} instance(s) running "
                    f"(minimum {min_required} required). Rollback during low capacity "
                    f"risks extended downtime."
                ),
                suggestion="Scale up first, then attempt rollback.",
            )
        return None

    def _check_horizontal_scale_limits(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Enforce horizontal scaling limits."""
        if action_type != "scale_horizontal":
            return None

        target = parameters.get("target_instances", 3)

        if target > self.config.max_horizontal_instances:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="max_horizontal_instances",
                reason=(
                    f"Cannot scale to {target} instances: exceeds maximum limit "
                    f"of {self.config.max_horizontal_instances}."
                ),
                suggestion=f"Scale to at most {self.config.max_horizontal_instances} instances.",
            )

        if target < self.config.min_horizontal_instances:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="min_horizontal_instances",
                reason=(
                    f"Cannot scale down to {target} instances: below minimum "
                    f"of {self.config.min_horizontal_instances}."
                ),
                suggestion=f"Maintain at least {self.config.min_horizontal_instances} instance(s).",
            )

        # Warn if scaling more than 3x current
        current = system_state.get("active_instances", 2)
        if current > 0 and target > current * 3:
            return GuardrailResult(
                verdict=GuardrailVerdict.WARN,
                rule_name="aggressive_horizontal_scaling",
                reason=(
                    f"Scaling from {current} to {target} instances is aggressive "
                    f"(>{3}x increase). This may cause cost spikes."
                ),
                suggestion="Consider incremental scaling.",
            )

        return None

    def _check_vertical_scale_limits(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Enforce vertical scaling limits."""
        if action_type != "scale_vertical":
            return None

        target_cpu = parameters.get("target_cpu", 2.0)
        target_memory = parameters.get("target_memory", 4.0)

        if target_cpu > self.config.max_vertical_cpu:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="max_vertical_cpu",
                reason=(
                    f"Cannot allocate {target_cpu} CPU cores: exceeds maximum "
                    f"of {self.config.max_vertical_cpu} cores."
                ),
                suggestion=f"Use at most {self.config.max_vertical_cpu} CPU cores.",
            )

        if target_memory > self.config.max_vertical_memory:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="max_vertical_memory",
                reason=(
                    f"Cannot allocate {target_memory}GB memory: exceeds maximum "
                    f"of {self.config.max_vertical_memory}GB."
                ),
                suggestion=f"Use at most {self.config.max_vertical_memory}GB memory.",
            )

        return None

    def _check_timeout_bounds(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Enforce timeout configuration bounds."""
        if action_type != "change_timeout":
            return None

        new_timeout = parameters.get("new_timeout", 5000)

        if new_timeout < self.config.min_timeout_ms:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="min_timeout",
                reason=(
                    f"Cannot set timeout to {new_timeout}ms: below minimum "
                    f"of {self.config.min_timeout_ms}ms. Too-low timeouts cause "
                    f"cascading failures."
                ),
                suggestion=f"Set timeout to at least {self.config.min_timeout_ms}ms.",
            )

        if new_timeout > self.config.max_timeout_ms:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="max_timeout",
                reason=(
                    f"Cannot set timeout to {new_timeout}ms: exceeds maximum "
                    f"of {self.config.max_timeout_ms}ms. Excessively high timeouts "
                    f"tie up resources."
                ),
                suggestion=f"Set timeout to at most {self.config.max_timeout_ms}ms.",
            )

        return None

    def _check_cost_budget(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Block actions if cost budget for this incident is exceeded."""
        total_cost = incident_context.get("total_cost", 0.0)

        if total_cost >= self.config.max_cost_per_incident:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="cost_budget_exceeded",
                reason=(
                    f"Cost budget exceeded: ${total_cost:.2f} spent "
                    f"(limit: ${self.config.max_cost_per_incident:.2f}). "
                    f"No further remediation actions allowed."
                ),
                suggestion="Escalate to human operator for manual intervention.",
            )

        # Warn if approaching budget (>80%)
        if total_cost >= self.config.max_cost_per_incident * 0.8:
            return GuardrailResult(
                verdict=GuardrailVerdict.WARN,
                rule_name="cost_budget_warning",
                reason=(
                    f"Approaching cost budget: ${total_cost:.2f} of "
                    f"${self.config.max_cost_per_incident:.2f} "
                    f"({total_cost / self.config.max_cost_per_incident:.0%} used)."
                ),
                suggestion="Prefer low-cost actions (restart, clear_cache, change_timeout).",
            )

        return None

    def _check_action_frequency(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Enforce limits on how many times each action can be repeated."""
        actions_taken = incident_context.get("actions_taken", [])

        # Total action limit
        if len(actions_taken) >= self.config.max_total_actions_per_incident:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                rule_name="max_total_actions",
                reason=(
                    f"Maximum actions per incident reached: {len(actions_taken)} "
                    f"(limit: {self.config.max_total_actions_per_incident}). "
                    f"Further automated remediation blocked."
                ),
                suggestion="Escalate to human operator.",
            )

        # Per-action-type limits
        action_counts = {}
        for a in actions_taken:
            a_type = a.get("action", "unknown")
            action_counts[a_type] = action_counts.get(a_type, 0) + 1

        if action_type == "restart_service":
            count = action_counts.get("restart_service", 0)
            if count >= self.config.max_restarts_per_incident:
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    rule_name="max_restarts_exceeded",
                    reason=(
                        f"Already restarted {count} time(s) this incident "
                        f"(limit: {self.config.max_restarts_per_incident}). "
                        f"Repeated restarts indicate a deeper issue."
                    ),
                    suggestion="Try a different strategy: rollback, scale, or escalate.",
                )

        if action_type == "rollback_deployment":
            count = action_counts.get("rollback_deployment", 0)
            if count >= self.config.max_rollbacks_per_incident:
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    rule_name="max_rollbacks_exceeded",
                    reason=(
                        f"Already rolled back {count} time(s) this incident "
                        f"(limit: {self.config.max_rollbacks_per_incident}). "
                        f"Multiple rollbacks risk data inconsistency."
                    ),
                    suggestion="Try restart, scaling, or escalate to human operator.",
                )

        return None

    def _check_already_healthy(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        system_state: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Optional[GuardrailResult]:
        """Warn if system is already healthy — action may be unnecessary."""
        if not self.config.block_actions_if_healthy:
            return None

        health_score = system_state.get("health_score", 0.0)
        if health_score >= self.config.healthy_threshold:
            return GuardrailResult(
                verdict=GuardrailVerdict.WARN,
                rule_name="system_already_healthy",
                reason=(
                    f"System health score is {health_score:.3f} "
                    f"(threshold: {self.config.healthy_threshold:.3f}). "
                    f"Action '{action_type}' may be unnecessary."
                ),
                suggestion="Consider skipping this action — system appears recovered.",
            )

        return None

    def get_active_rules_summary(self) -> List[Dict[str, Any]]:
        """Get a summary of all active guardrail rules and their thresholds."""
        return [
            {
                "rule": "min_instances_for_restart",
                "threshold": self.config.min_instances_for_restart,
                "description": f"Block restart if < {self.config.min_instances_for_restart} instances",
            },
            {
                "rule": "min_instances_for_rollback",
                "threshold": self.config.min_instances_for_rollback,
                "description": f"Block rollback if < {self.config.min_instances_for_rollback} instances",
            },
            {
                "rule": "max_horizontal_instances",
                "threshold": self.config.max_horizontal_instances,
                "description": f"Block scaling beyond {self.config.max_horizontal_instances} instances",
            },
            {
                "rule": "max_vertical_cpu",
                "threshold": self.config.max_vertical_cpu,
                "description": f"Block CPU allocation beyond {self.config.max_vertical_cpu} cores",
            },
            {
                "rule": "max_vertical_memory",
                "threshold": self.config.max_vertical_memory,
                "description": f"Block memory allocation beyond {self.config.max_vertical_memory}GB",
            },
            {
                "rule": "timeout_bounds",
                "threshold": f"{self.config.min_timeout_ms}-{self.config.max_timeout_ms}ms",
                "description": f"Block timeout outside {self.config.min_timeout_ms}-{self.config.max_timeout_ms}ms",
            },
            {
                "rule": "cost_budget",
                "threshold": self.config.max_cost_per_incident,
                "description": f"Block actions if cost exceeds ${self.config.max_cost_per_incident:.2f}",
            },
            {
                "rule": "max_restarts",
                "threshold": self.config.max_restarts_per_incident,
                "description": f"Block after {self.config.max_restarts_per_incident} restarts per incident",
            },
            {
                "rule": "max_rollbacks",
                "threshold": self.config.max_rollbacks_per_incident,
                "description": f"Block after {self.config.max_rollbacks_per_incident} rollback(s) per incident",
            },
            {
                "rule": "max_total_actions",
                "threshold": self.config.max_total_actions_per_incident,
                "description": f"Block after {self.config.max_total_actions_per_incident} total actions",
            },
            {
                "rule": "healthy_system_guard",
                "threshold": self.config.healthy_threshold,
                "description": f"Warn if health score >= {self.config.healthy_threshold}",
                "enabled": self.config.block_actions_if_healthy,
            },
        ]