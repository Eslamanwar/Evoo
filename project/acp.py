"""ACP server configuration for the EVOO agent."""
import os

from temporalio.contrib.openai_agents import OpenAIAgentsPlugin

from agentex.lib.sdk.fastacp.fastacp import FastACP
from agentex.lib.types.fastacp import TemporalACPConfig
from agentex.lib.core.temporal.plugins.openai_agents.models.temporal_streaming_model import (
    TemporalStreamingModelProvider,
)
from agentex.lib.core.temporal.plugins.openai_agents.interceptors.context_interceptor import (
    ContextInterceptor,
)

context_interceptor = ContextInterceptor()
temporal_streaming_model_provider = TemporalStreamingModelProvider()

acp = FastACP.create(
    acp_type="async",
    config=TemporalACPConfig(
        type="temporal",
        temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        plugins=[OpenAIAgentsPlugin(model_provider=temporal_streaming_model_provider)],
        interceptors=[context_interceptor],
    ),
)
