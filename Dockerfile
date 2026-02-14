FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy project files
COPY pyproject.toml ./
COPY project ./project

# Install Python dependencies (agentex-sdk comes from PyPI)
RUN pip install --no-cache-dir -e .

# Create memory storage directory
RUN mkdir -p /tmp/evoo_data

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV MEMORY_FILE_PATH=/tmp/evoo_data/evoo_memory.json
ENV STRATEGY_FILE_PATH=/tmp/evoo_data/evoo_strategies.json
ENV MAX_LEARNING_RUNS=50
ENV EXPLORATION_RATE=0.2

# Start the Temporal worker
CMD ["python", "-m", "project.run_worker"]
