# syntax=docker/dockerfile:1.3
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.6.4 /uv /uvx /bin/

# Install system dependencies
RUN apt-get update && apt-get install -y \
    htop \
    vim \
    curl \
    tar \
    python3-dev \
    build-essential \
    gcc \
    cmake \
    netcat-openbsd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install tctl (Temporal CLI)
RUN curl -L https://github.com/temporalio/tctl/releases/download/v1.18.1/tctl_1.18.1_linux_arm64.tar.gz -o /tmp/tctl.tar.gz && \
    tar -xzf /tmp/tctl.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/tctl && \
    rm /tmp/tctl.tar.gz

RUN uv pip install --system --upgrade pip setuptools wheel

ENV UV_HTTP_TIMEOUT=1000

# Copy pyproject.toml and README.md
COPY pyproject.toml /app/evoo/pyproject.toml
COPY README.md /app/evoo/README.md

WORKDIR /app/evoo

# Copy the project code
COPY project /app/evoo/project

# Install dependencies
RUN uv pip install --system --no-cache agentex-sdk temporalio litellm python-dotenv termcolor pydantic httpx uvicorn

WORKDIR /app/evoo

ENV PYTHONPATH=/app/evoo

# Set agent environment variables
ENV AGENT_NAME=evoo-agent

# Create memory storage directory
RUN mkdir -p /tmp/evoo_memory

# Run the ACP server using uvicorn
CMD ["uvicorn", "project.acp:acp", "--host", "0.0.0.0", "--port", "8000"]

# When deploying the worker, replace CMD with:
# CMD ["python", "-m", "project.run_worker"]
