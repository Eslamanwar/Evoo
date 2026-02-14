"""Temporal worker for the EVOO agent."""

import asyncio

from agentex.lib.core.temporal.activities import get_all_activities
from agentex.lib.core.temporal.workers.worker import AgentexWorker
from agentex.lib.environment_variables import EnvironmentVariables
from agentex.lib.utils.debug import setup_debug_if_enabled
from agentex.lib.utils.logging import make_logger

from project.activities.remediation_tools import (
    restart_service,
    scale_horizontal,
    scale_vertical,
    change_timeout,
    rollback_deployment,
    clear_cache,
    rebalance_load,
    query_metrics,
    get_incident_state,
    set_production_system,
)
from project.activities.analysis_tools import (
    analyze_logs,
    predict_incident_type,
    apply_previous_successful_strategy,
    set_experience_store as set_analysis_store,
)
from project.activities.evaluation_tools import (
    calculate_reward,
    evaluate_remediation_with_llm,
)
from project.activities.planning_tools import (
    plan_remediation,
    get_strategy_recommendation,
    set_shared_instances as set_planning_instances,
)
from project.activities.simulation_tools import (
    generate_incident,
    reset_production_system,
)
from project.guardrails.safety_rules import GuardrailEngine, GuardrailConfig
from project.memory.experience_store import ExperienceStore
from project.simulation.production_system import ProductionSystem
from project.strategy.strategy_manager import StrategyManager
from project.workflow import EvooWorkflow
from project.workflows.execution.execution_workflow import set_guardrail_engine
from project.workflows.idle.idle_workflow import set_idle_instances
from project.workflows.learning.learning_workflow import set_learning_instances

environment_variables = EnvironmentVariables.refresh()

logger = make_logger(__name__)


async def main():
    """Run the Temporal worker for EVOO."""
    # Setup debug mode if enabled
    setup_debug_if_enabled()

    task_queue_name = environment_variables.WORKFLOW_TASK_QUEUE
    if task_queue_name is None:
        raise ValueError("WORKFLOW_TASK_QUEUE is not set")

    # Initialize shared instances
    production_system = ProductionSystem()
    experience_store = ExperienceStore()
    strategy_manager = StrategyManager(experience_store)
    guardrail_engine = GuardrailEngine(GuardrailConfig())

    # Set shared instances for activities and workflows
    set_production_system(production_system)
    set_analysis_store(experience_store)
    set_planning_instances(experience_store, strategy_manager)
    set_learning_instances(experience_store, strategy_manager)
    set_idle_instances(experience_store, strategy_manager)
    set_guardrail_engine(guardrail_engine)

    logger.info("EVOO worker initialized with shared instances")
    logger.info(f"Experience store: {experience_store.get_experience_count()} existing experiences")
    logger.info(f"Guardrails enabled: {guardrail_engine.config.enabled}")
    logger.info(f"Guardrail rules: min_instances_for_restart={guardrail_engine.config.min_instances_for_restart}, "
                f"max_cost={guardrail_engine.config.max_cost_per_incident}, "
                f"max_restarts={guardrail_engine.config.max_restarts_per_incident}")

    # Create a worker
    worker = AgentexWorker(
        task_queue=task_queue_name,
    )

    # Combine default activities with EVOO activities
    all_activities = get_all_activities() + [
        # Core remediation tools
        restart_service,
        scale_horizontal,
        scale_vertical,
        change_timeout,
        rollback_deployment,
        clear_cache,
        rebalance_load,
        query_metrics,
        get_incident_state,
        # Analysis tools
        analyze_logs,
        predict_incident_type,
        apply_previous_successful_strategy,
        # Evaluation tools
        calculate_reward,
        evaluate_remediation_with_llm,
        # Planning tools
        plan_remediation,
        get_strategy_recommendation,
        # Simulation tools
        generate_incident,
        reset_production_system,
    ]

    await worker.run(
        activities=all_activities,
        workflow=EvooWorkflow,
    )


if __name__ == "__main__":
    asyncio.run(main())
