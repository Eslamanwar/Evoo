"""Constants for EVOO - Evolutionary Operations Optimizer Agent."""
import os


# LLM Configuration - matches other agents pattern (red-cell, aws-hero, dr-nova-science)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek/deepseek-r1-0528")


# Memory Configuration
EVOO_MEMORY_PATH = os.getenv("EVOO_MEMORY_PATH", "/tmp/evoo_memory")

# Learning Loop Configuration
EVOO_MAX_INCIDENTS = int(os.getenv("EVOO_MAX_INCIDENTS", "10"))
EVOO_EXPLORATION_RATE = float(os.getenv("EVOO_EXPLORATION_RATE", "0.3"))
EVOO_EXPLORATION_DECAY = float(os.getenv("EVOO_EXPLORATION_DECAY", "0.95"))
EVOO_MIN_EXPLORATION_RATE = float(os.getenv("EVOO_MIN_EXPLORATION_RATE", "0.05"))

# Max iterations for agentic loops
MAX_AGENT_ITERATIONS = 15

# Activity timeouts (seconds)
TIMEOUTS = {
    "llm_call": 120,
    "remediation_action": 60,
    "metrics_query": 30,
    "simulation": 30,
    "activity_default": 60,
}