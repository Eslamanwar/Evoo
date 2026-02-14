"""Constants and configuration for the EVOO agent."""
from __future__ import annotations

import os

# Agent identity
AGENT_NAME = os.getenv("AGENT_NAME", "evoo")
WORKFLOW_NAME = os.getenv("WORKFLOW_NAME", "EVOOWorkflow")
TASK_QUEUE = os.getenv("WORKFLOW_TASK_QUEUE", "evoo-queue")

# LLM configuration
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Learning loop configuration
MAX_LEARNING_RUNS = int(os.getenv("MAX_LEARNING_RUNS", "50"))
EXPLORATION_RATE = float(os.getenv("EXPLORATION_RATE", "0.2"))   # epsilon-greedy
LEARNING_RUNS_BEFORE_OPTIMIZE = int(os.getenv("LEARNING_RUNS_BEFORE_OPTIMIZE", "3"))

# Memory storage
MEMORY_FILE_PATH = os.getenv("MEMORY_FILE_PATH", "/tmp/evoo_memory.json")
STRATEGY_FILE_PATH = os.getenv("STRATEGY_FILE_PATH", "/tmp/evoo_strategies.json")

# Simulation settings
INCIDENT_INTERVAL_SECONDS = int(os.getenv("INCIDENT_INTERVAL_SECONDS", "5"))
MAX_INSTANCES = int(os.getenv("MAX_INSTANCES", "10"))
MIN_INSTANCES = int(os.getenv("MIN_INSTANCES", "1"))

# LLM agent loop configuration
MAX_AGENT_LOOP_ITERATIONS = int(os.getenv("MAX_AGENT_LOOP_ITERATIONS", "8"))
LLM_TEMPERATURE_PLANNING = float(os.getenv("LLM_TEMPERATURE_PLANNING", "0.3"))
LLM_TEMPERATURE_EXECUTION = float(os.getenv("LLM_TEMPERATURE_EXECUTION", "0.2"))
LLM_MAX_TOKENS_PLANNING = int(os.getenv("LLM_MAX_TOKENS_PLANNING", "800"))
LLM_MAX_TOKENS_EXECUTION = int(os.getenv("LLM_MAX_TOKENS_EXECUTION", "500"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60.0"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Reward weights
REWARD_SERVICE_RESTORED = 100.0
REWARD_RECOVERY_TIME_PENALTY = 0.5
REWARD_INFRASTRUCTURE_COST_PENALTY = 0.2
REWARD_ERROR_RATE_PENALTY = 50.0
REWARD_LATENCY_IMPROVEMENT_BONUS = 0.1
REWARD_UNNECESSARY_SCALE_PENALTY = 10.0
