# EVOO — Evolutionary Operations Optimizer

<div align="center">

```
    ╔═══════════════════════════════════════════════════════════════════════╗
    ║                                                                       ║
    ║   ███████╗██╗   ██╗ ██████╗  ██████╗                                 ║
    ║   ██╔════╝██║   ██║██╔═══██╗██╔═══██╗                                ║
    ║   █████╗  ██║   ██║██║   ██║██║   ██║                                ║
    ║   ██╔══╝  ╚██╗ ██╔╝██║   ██║██║   ██║                                ║
    ║   ███████╗ ╚████╔╝ ╚██████╔╝╚██████╔╝                                ║
    ║   ╚══════╝  ╚═══╝   ╚═════╝  ╚═════╝                                 ║
    ║                                                                       ║
    ║   Evolutionary Operations Optimizer                                   ║
    ║   An Autonomous AI SRE Agent with Reward-Based Learning              ║
    ╚═══════════════════════════════════════════════════════════════════════╝
```

**Version 2.0.0** | Built with [scale-agentex](../../agentex) and OpenAI SDK ADK

</div>

---

## 🎯 Overview

EVOO is an **autonomous AI agent** that behaves like a real Site Reliability Engineer (SRE). It continuously improves its incident remediation strategy over time using:

- **Feedback** from remediation outcomes
- **Memory** of past experiences
- **Strategy optimization** via reward-based learning

Unlike traditional rule-based incident response systems, EVOO **learns from its mistakes** and **gets better over time**.

---

## 🧠 Core Capabilities

| Capability | Description |
|------------|-------------|
| **Incident Detection** | Detects production incidents in a simulated system |
| **Strategy Selection** | Uses epsilon-greedy exploration with experience-based exploitation |
| **Tool Execution** | Calls remediation tools (restart, scale, rollback, etc.) |
| **Outcome Measurement** | Collects before/after metrics to measure effectiveness |
| **Reward Scoring** | Calculates numeric reward + LLM judge evaluation |
| **Memory Storage** | Persists experience tuples for future reference |
| **Learning Loop** | Improves decision-making based on accumulated experience |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EVOO Learning Loop                              │
└─────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────┐
    │ INCIDENT         │──────────► Simulated Production System
    │ DETECTION        │             generates random incidents
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ PLANNER AGENT    │──────────► Memory Retrieval
    │ (LLM-powered)    │             + Epsilon-Greedy Selection
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ EXECUTOR AGENT   │──────────► Remediation Tools
    │                  │             (restart, scale, rollback...)
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ EVALUATOR AGENT  │──────────► Reward Function
    │ (LLM Judge)      │             + Qualitative Assessment
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ STRATEGY MANAGER │──────────► Update Rankings
    │                  │             + Store Experience
    └────────┬─────────┘
             │
             └──────────────────► Loop back to INCIDENT DETECTION
```

---

## 📊 Incident Types Supported

| Incident Type | Typical Metrics | Best Strategies |
|---------------|-----------------|-----------------|
| `service_crash` | High error rate, low availability | restart_service, rollback_deployment |
| `high_latency` | P99 > 2000ms, elevated CPU | scale_horizontal, rebalance_load |
| `cpu_spike` | CPU > 85%, request throttling | scale_vertical, scale_horizontal |
| `memory_leak` | Memory > 88%, OOMKiller risk | restart_service, clear_cache |
| `network_degradation` | Packet loss, latency spikes | rebalance_load, scale_horizontal |
| `timeout_misconfiguration` | Cascading timeouts | change_timeout, rollback_deployment |

---

## 🔧 Available Remediation Tools

### Core Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `restart_service()` | Graceful service restart | service_name |
| `scale_horizontal()` | Add/remove instances | target_instances |
| `scale_vertical()` | Adjust CPU/memory limits | target_cpu, target_memory |
| `change_timeout()` | Update timeout configuration | new_timeout_ms |
| `rollback_deployment()` | Revert to previous version | target_version |
| `clear_cache()` | Free memory by clearing caches | cache_type |
| `rebalance_load()` | Redistribute traffic | algorithm |

### Advanced Tools

| Tool | Description |
|------|-------------|
| `analyze_logs()` | Identify root cause patterns in logs |
| `predict_incident_type()` | Heuristic prediction from metrics |
| `query_metrics()` | Query observability stack |
| `apply_previous_successful_strategy()` | Retrieve best historical strategy |

---

## 📈 Reward Function

The reward function scores each remediation action:

```python
reward = 0.0

# Positive factors
if service_restored:
    reward += 100.0
reward += latency_improvement * 0.1
reward += availability_improvement * 30.0
reward += cpu_improvement * 0.05

# Negative factors
reward -= recovery_time_seconds * 0.5
reward -= infrastructure_cost * 0.2
reward -= error_rate_after * 50.0
if unnecessary_scaling:
    reward -= 10.0
```

Additionally, an **LLM-based judge** provides qualitative evaluation:

- Score: 0-10
- Verdict: excellent | good | adequate | poor | failed
- Analysis: 2-sentence explanation
- Better strategy suggestion

---

## 🧬 Learning Loop

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   Early Runs (exploration phase):                                       │
│   ├─ Agent tries random strategies                                      │
│   ├─ Recovery time: HIGH                                                │
│   ├─ Reward: LOW                                                        │
│   └─ Building experience database                                       │
│                                                                         │
│   Later Runs (exploitation phase):                                      │
│   ├─ Agent selects optimal strategies based on history                  │
│   ├─ Recovery time: LOW                                                 │
│   ├─ Reward: HIGH                                                       │
│   └─ Continuous improvement measurable                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Epsilon-Greedy Strategy Selection

- With probability ε (default 0.2): **EXPLORE** new strategies
- With probability 1-ε: **EXPLOIT** best known strategy

---

## 💾 Memory Model

Experiences are stored as tuples:

```json
{
  "id": "abc12345",
  "incident_type": "high_latency",
  "metrics_before": {
    "latency_ms": 5420,
    "cpu_percent": 72.3,
    "availability": 0.68
  },
  "strategy_used": "scale_horizontal",
  "tools_called": ["query_metrics_tool_activity", "scale_horizontal_activity"],
  "metrics_after": {
    "latency_ms": 142,
    "cpu_percent": 31.2,
    "availability": 0.998
  },
  "recovery_time_seconds": 24.3,
  "reward": 85.7,
  "llm_evaluation": "Excellent recovery. Horizontal scaling effectively addressed...",
  "success": true,
  "timestamp": "2026-02-14T08:15:00Z",
  "run_index": 42
}
```

---

## 🚀 Quick Start

### Standalone Mode (No Platform Required)

```bash
cd agents/evoo

# Install dependencies
pip install -e .

# Run the learning loop (30 cycles)
python run_evoo_standalone.py --runs 30 --explore 0.2

# With OpenAI LLM judge
python run_evoo_standalone.py --runs 50 --openai-key sk-your-key
```

### With AgentEx Platform

```bash
# Start the Temporal worker
python project/run_worker.py

# The agent will be available at the configured endpoint
# Create a task via the AgentEx API to start the learning loop
```

---

## ⚙️ Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MAX_LEARNING_RUNS` | 50 | Number of learning cycles |
| `EXPLORATION_RATE` | 0.2 | Epsilon for exploration |
| `OPENAI_API_KEY` | - | For LLM judge (optional) |
| `OPENAI_MODEL` | gpt-4o-mini | LLM model for reasoning |
| `MEMORY_FILE_PATH` | /tmp/evoo_memory.json | Experience storage |
| `STRATEGY_FILE_PATH` | /tmp/evoo_strategies.json | Strategy rankings |

---

## 📊 Observability

EVOO provides comprehensive observability:

### Logged Events
- All agent decisions
- Tool call inputs/outputs
- Reward calculations
- Strategy ranking updates

### Metrics Tracked
- Average recovery time per incident type
- Reward over time (with trend)
- Strategy success rate
- Learning improvement (early vs late runs)

### Milestone Reports
Every 10 runs, EVOO emits a detailed summary:
- Reward metrics (average, best)
- Recovery time metrics
- Most used strategies
- Learning trend analysis

---

## 🧪 Example Output

```
╔══════════════════════════════════════════════════════════════════╗
║   EVOO — Evolutionary Operations Optimizer (Standalone Mode)    ║
╠══════════════════════════════════════════════════════════════════╣
║  Runs: 30     Exploration: 0.2    OpenAI: YES                   ║
╚══════════════════════════════════════════════════════════════════╝

──────────────────────────────────────────────────────────────────────
  Run   1/30
──────────────────────────────────────────────────────────────────────
  INCIDENT : service_crash
  STRATEGY : restart_service [EXPLORE]
  RESULT   : ✓ RESTORED | Recovery: 18.2s
  REWARD   : +72.45
  LLM JUDGE: GOOD
  METRICS  : Latency 8234ms → 145ms (↓8089ms) | Availability 12% → 99.8%

──────────────────────────────────────────────────────────────────────
  Run  30/30
──────────────────────────────────────────────────────────────────────
  INCIDENT : cpu_spike
  STRATEGY : scale_vertical [EXPLOIT]
  RESULT   : ✓ RESTORED | Recovery: 12.1s
  REWARD   : +89.23
  LLM JUDGE: EXCELLENT

══════════════════════════════════════════════════════════════════════
  EVOO LEARNING COMPLETE — FINAL REPORT
══════════════════════════════════════════════════════════════════════

  Metric                              Value
  ──────────────────────────────────────────────────
  Total Runs                             30
  Average Reward (all)                 68.45
  Average Reward (first 5)             52.12
  Average Reward (last 5)              84.78
  Net Improvement                     +32.66 (IMPROVED ✓)
  Best Reward                          94.21
  Avg Recovery Time                    22.3s
  Best Recovery Time                    8.4s

  Strategy Rankings Learned:
  service_crash          restart_service(78.2) > rollback_deployment(71.5)
  high_latency           scale_horizontal(82.1) > rebalance_load(68.9)
  cpu_spike              scale_vertical(85.4) > scale_horizontal(79.2)
```

---

## 📁 Project Structure

```
agents/evoo/
├── project/
│   ├── __init__.py
│   ├── acp.py                    # ACP server configuration
│   ├── constants.py              # Configuration constants
│   ├── run_worker.py             # Temporal worker entry
│   ├── workflow.py               # Main workflow orchestration
│   │
│   ├── activities/               # Temporal activities
│   │   ├── simulation_activities.py   # Production system simulator
│   │   ├── remediation_activities.py  # Tool implementations
│   │   ├── memory_activities.py       # Experience persistence
│   │   ├── reward_activities.py       # Reward function + LLM judge
│   │   └── strategy_activities.py     # Epsilon-greedy selection
│   │
│   ├── models/                   # Data models
│   │   ├── incident.py           # Incident, SystemMetrics
│   │   └── experience.py         # Experience, StrategyRecord
│   │
│   ├── state_machines/           # State machine definition
│   │   └── evoo_agent.py         # EVOOState, EVOOData
│   │
│   └── workflows/                # State workflows
│       ├── idle/
│       │   └── waiting_for_incident.py
│       ├── planning/
│       │   └── planning_remediation.py    # Planner Agent
│       ├── execution/
│       │   └── executing_remediation.py   # Executor Agent
│       ├── evaluation/
│       │   └── evaluating_outcome.py      # Evaluator Agent
│       ├── learning/
│       │   └── updating_strategy.py       # Strategy Manager
│       └── terminal_states.py
│
├── run_evoo_standalone.py        # Standalone demo script
├── manifest.yaml                 # Agent manifest
├── pyproject.toml                # Python dependencies
├── Dockerfile                    # Container build
└── README.md                     # This file
```

---

## 🔬 Technical Details

### OpenAI SDK ADK Integration

EVOO uses OpenAI SDK ADK for:

1. **Planner reasoning**: Explains why a strategy was selected
2. **Evaluator judgment**: Qualitative assessment of remediation effectiveness
3. **Strategy suggestions**: Recommends better alternatives when appropriate

### scale-agentex Framework

Built on scale-agentex patterns:
- State machine-based workflow orchestration
- Activity-based tool execution
- Persistent state across workflow steps
- Signal handling for runtime control

---

## 🎓 Success Criteria

EVOO demonstrates success when:

- [x] Agent improves remediation performance over time
- [x] Agent selects best strategies based on experience
- [x] Reward improves measurably over runs
- [x] Recovery time decreases over runs
- [x] Agent demonstrates autonomous learning

---

## 📄 License

MIT License — See [LICENSE](../../LICENSE)

---

<div align="center">

**Built with ❤️ for autonomous SRE operations**

*EVOO learns so you don't have to be on-call at 3 AM*

</div>
