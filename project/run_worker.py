"""Temporal worker for the EVOO agent.

Registers all activities (simulation, remediation tools, memory,
reward function, strategy manager) and starts the Temporal worker.
"""
import asyncio

from temporalio.contrib.openai_agents import OpenAIAgentsPlugin

from agentex.lib.core.temporal.activities import get_all_activities
from agentex.lib.core.temporal.workers.worker import AgentexWorker
from agentex.lib.environment_variables import EnvironmentVariables
from agentex.lib.utils.debug import setup_debug_if_enabled
from agentex.lib.utils.logging import make_logger
from agentex.lib.core.temporal.plugins.openai_agents.hooks.activities import stream_lifecycle_content
from agentex.lib.core.temporal.plugins.openai_agents.models.temporal_streaming_model import (
    TemporalStreamingModelProvider,
)
from agentex.lib.core.temporal.plugins.openai_agents.interceptors.context_interceptor import (
    ContextInterceptor,
)

# ---- Simulation activities (production system simulator) ----
from project.activities.simulation_activities import (
    generate_incident_activity,
    get_incident_state_activity,
    query_metrics_activity,
    apply_remediation_to_simulation_activity,
)

# ---- Remediation tool activities ----
from project.activities.remediation_activities import (
    restart_service_activity,
    scale_horizontal_activity,
    scale_vertical_activity,
    change_timeout_activity,
    rollback_deployment_activity,
    clear_cache_activity,
    rebalance_load_activity,
    query_metrics_tool_activity,
    analyze_logs_activity,
    predict_incident_type_activity,
    mark_strategy_success_activity,
    mark_strategy_failure_activity,
)

# ---- Memory activities ----
from project.activities.memory_activities import (
    store_experience_activity,
    retrieve_best_strategy_activity,
    retrieve_recent_experiences_activity,
    get_memory_summary_activity,
    apply_previous_successful_strategy_activity,
)

# ---- Reward evaluation activities ----
from project.activities.reward_activities import (
    calculate_reward_activity,
    llm_evaluate_remediation_activity,
)

# ---- Strategy manager activities ----
from project.activities.strategy_activities import (
    select_strategy_activity,
    update_strategy_record_activity,
    get_strategy_rankings_activity,
)

# ---- LLM / Agentic loop activities ----
from project.activities.llm_helpers import call_llm_activity
from project.activities.sre_agent_loop import run_sre_agent_loop_activity

# ---- Workflow ----
from project.workflow import EVOOWorkflow

logger = make_logger(__name__)

environment_variables = EnvironmentVariables.refresh()
setup_debug_if_enabled()

task_queue_name = environment_variables.WORKFLOW_TASK_QUEUE or "evoo-queue"

context_interceptor = ContextInterceptor()
temporal_streaming_model_provider = TemporalStreamingModelProvider()


async def main():
    """Start the EVOO Temporal worker."""
    logger.info(f"Starting EVOO worker on queue: {task_queue_name}")

    worker = AgentexWorker(
        task_queue=task_queue_name,
        plugins=[OpenAIAgentsPlugin(model_provider=temporal_streaming_model_provider)],
        interceptors=[context_interceptor],
    )

    # All EVOO-specific activities
    evoo_activities = [
        # Simulation
        generate_incident_activity,
        get_incident_state_activity,
        query_metrics_activity,
        apply_remediation_to_simulation_activity,
        # Remediation tools
        restart_service_activity,
        scale_horizontal_activity,
        scale_vertical_activity,
        change_timeout_activity,
        rollback_deployment_activity,
        clear_cache_activity,
        rebalance_load_activity,
        query_metrics_tool_activity,
        analyze_logs_activity,
        predict_incident_type_activity,
        mark_strategy_success_activity,
        mark_strategy_failure_activity,
        # Memory
        store_experience_activity,
        retrieve_best_strategy_activity,
        retrieve_recent_experiences_activity,
        get_memory_summary_activity,
        apply_previous_successful_strategy_activity,
        # Reward
        calculate_reward_activity,
        llm_evaluate_remediation_activity,
        # Strategy manager
        select_strategy_activity,
        update_strategy_record_activity,
        get_strategy_rankings_activity,
        # LLM / Agentic loop
        call_llm_activity,
        run_sre_agent_loop_activity,
        # AgentEx default hook
        stream_lifecycle_content,
    ]

    await worker.run(
        workflows=[EVOOWorkflow],
        activities=[*get_all_activities(), *evoo_activities],
    )


if __name__ == "__main__":
    asyncio.run(main())
