#!/usr/bin/env python3
"""
EVOO Standalone Run Script — demonstrates the full learning loop
without requiring the AgentEx platform.

This script runs EVOO directly using the core activities as Python functions,
bypassing Temporal workflow orchestration. Use this for:
- Local development and testing
- Demonstrating the learning loop behavior
- Debugging reward functions and strategy selection

Usage:
    python run_evoo_standalone.py [--runs 30] [--explore 0.2] [--openai-key sk-...]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

# Configure minimal env before imports
os.environ.setdefault("MEMORY_FILE_PATH", "/tmp/evoo_standalone_memory.json")
os.environ.setdefault("STRATEGY_FILE_PATH", "/tmp/evoo_standalone_strategies.json")

from project.activities.simulation_activities import (
    generate_incident_activity,
    apply_remediation_to_simulation_activity,
)
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
)
from project.activities.memory_activities import (
    store_experience_activity,
    retrieve_best_strategy_activity,
    get_memory_summary_activity,
)
from project.activities.reward_activities import (
    calculate_reward_activity,
    llm_evaluate_remediation_activity,
)
from project.activities.strategy_activities import (
    select_strategy_activity,
    update_strategy_record_activity,
    get_strategy_rankings_activity,
)
from project.models.incident import Incident, SystemMetrics


# ---------------------------------------------------------------------------
# ANSI color helpers
# ---------------------------------------------------------------------------
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    DIM = "\033[2m"


def cprint(text: str, color: str = Colors.RESET) -> None:
    print(f"{color}{text}{Colors.RESET}")


def print_separator(char: str = "─", width: int = 70) -> None:
    cprint(char * width, Colors.DIM)


# ---------------------------------------------------------------------------
# Tool dispatcher (simulates Temporal activity dispatch)
# ---------------------------------------------------------------------------

async def call_tool(tool_name: str, service_name: str, task_id: str, params: dict, incident_type: str) -> dict:
    """Dispatch to the appropriate activity function."""
    if tool_name == "restart_service_activity":
        return await restart_service_activity(service_name, task_id, task_id)
    elif tool_name == "scale_horizontal_activity":
        return await scale_horizontal_activity(params.get("target_instances", 3), service_name, task_id, task_id)
    elif tool_name == "scale_vertical_activity":
        return await scale_vertical_activity(params.get("target_cpu", 2.0), params.get("target_memory_gb", 4.0), service_name, task_id, task_id)
    elif tool_name == "change_timeout_activity":
        return await change_timeout_activity(params.get("new_timeout", 15000), service_name, task_id, task_id)
    elif tool_name == "rollback_deployment_activity":
        return await rollback_deployment_activity(service_name, task_id, task_id)
    elif tool_name == "clear_cache_activity":
        return await clear_cache_activity(service_name, task_id, task_id)
    elif tool_name == "rebalance_load_activity":
        return await rebalance_load_activity(service_name, task_id, task_id)
    elif tool_name == "query_metrics_tool_activity":
        return await query_metrics_tool_activity(service_name, task_id, task_id)
    elif tool_name == "analyze_logs_activity":
        return await analyze_logs_activity(service_name, incident_type, task_id, task_id)
    else:
        return {"tool": tool_name, "status": "skipped"}


# ---------------------------------------------------------------------------
# Single learning cycle
# ---------------------------------------------------------------------------

async def run_single_cycle(run_index: int, explore_rate: float, openai_key: str) -> Dict[str, Any]:
    """Execute one complete detect→plan→execute→evaluate→learn cycle."""
    task_id = f"standalone-run-{run_index:03d}"

    # ── 1. DETECT ──────────────────────────────────────────────────
    incident_data = await generate_incident_activity(run_index)
    incident = Incident(**incident_data)
    itype = incident.incident_type.value
    metrics_before = incident.metrics_at_detection

    # ── 2. PLAN ────────────────────────────────────────────────────
    strategy_sel = await select_strategy_activity(itype, run_index, False)
    strategy = strategy_sel["strategy"]
    tools_to_call = strategy_sel["tools_to_call"]
    tool_params = strategy_sel["tool_parameters"]
    is_explore = strategy_sel["is_exploratory"]

    # ── 3. EXECUTE ─────────────────────────────────────────────────
    system_state = {
        "service_name": incident.affected_service,
        "is_healthy": False,
        "current_incident": incident_data,
    }
    tool_results = []
    for tool_name in tools_to_call:
        result = await call_tool(tool_name, incident.affected_service, task_id, tool_params, itype)
        tool_results.append(result)

    sim_result = await apply_remediation_to_simulation_activity(system_state, strategy, tool_params)
    metrics_after = SystemMetrics(**sim_result["metrics_after"])
    recovery_time = sim_result["recovery_time_seconds"]
    service_restored = sim_result["service_restored"]
    infra_cost = sim_result["infrastructure_cost"]

    # ── 4. EVALUATE ────────────────────────────────────────────────
    reward_result = await calculate_reward_activity(
        metrics_before.model_dump(mode="json"),
        metrics_after.model_dump(mode="json"),
        recovery_time,
        service_restored,
        infra_cost,
        strategy,
        itype,
    )
    reward = reward_result["reward"]

    # LLM judge (optional)
    llm_verdict = "skipped"
    llm_analysis = "LLM evaluation skipped (no API key)"
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
        llm_eval = await llm_evaluate_remediation_activity(
            itype, strategy,
            metrics_before.model_dump(mode="json"),
            metrics_after.model_dump(mode="json"),
            tool_results, recovery_time, reward, task_id, task_id,
        )
        evaluation = llm_eval.get("evaluation", {})
        llm_verdict = evaluation.get("verdict", "unknown")
        llm_analysis = evaluation.get("analysis", "")

    # ── 5. LEARN ───────────────────────────────────────────────────
    experience = {
        "incident_type": itype,
        "metrics_before": metrics_before.model_dump(mode="json"),
        "strategy_used": strategy,
        "tools_called": tools_to_call,
        "tool_results": tool_results,
        "metrics_after": metrics_after.model_dump(mode="json"),
        "recovery_time": recovery_time,
        "reward": reward,
        "llm_evaluation": llm_analysis,
        "success": service_restored,
        "run_index": run_index,
    }
    await store_experience_activity(experience)
    await update_strategy_record_activity(itype, strategy, reward, service_restored)

    return {
        "run_index": run_index,
        "incident_type": itype,
        "severity": incident.severity,
        "strategy": strategy,
        "is_explore": is_explore,
        "tools": tools_to_call,
        "recovery_time": recovery_time,
        "service_restored": service_restored,
        "reward": reward,
        "llm_verdict": llm_verdict,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
    }


# ---------------------------------------------------------------------------
# Main learning loop
# ---------------------------------------------------------------------------

async def main(num_runs: int, explore_rate: float, openai_key: str) -> None:
    os.environ["EXPLORATION_RATE"] = str(explore_rate)

    print()
    cprint("╔══════════════════════════════════════════════════════════════════╗", Colors.CYAN)
    cprint("║   EVOO — Evolutionary Operations Optimizer (Standalone Mode)    ║", Colors.CYAN)
    cprint("╠══════════════════════════════════════════════════════════════════╣", Colors.CYAN)
    cprint(f"║  Runs: {num_runs:<5}  Exploration: {explore_rate:<5}  OpenAI: {'YES' if openai_key else 'NO (fallback)'}             ║", Colors.CYAN)
    cprint("╚══════════════════════════════════════════════════════════════════╝", Colors.CYAN)
    print()

    reward_history: List[float] = []
    recovery_history: List[float] = []
    strategy_history: List[str] = []

    start_time = time.time()

    for run_index in range(num_runs):
        print_separator()
        cprint(f"  Run {run_index + 1:>3}/{num_runs}", Colors.BOLD)
        print_separator()

        cycle_start = time.time()
        result = await run_single_cycle(run_index, explore_rate, openai_key)
        cycle_time = time.time() - cycle_start

        reward_history.append(result["reward"])
        recovery_history.append(result["recovery_time"])
        strategy_history.append(result["strategy"])

        # Display run results
        incident_color = Colors.RED if result["severity"] == "critical" else Colors.YELLOW
        restore_icon = Colors.GREEN + "✓ RESTORED" if result["service_restored"] else Colors.RED + "✗ FAILED"
        explore_tag = f"{Colors.MAGENTA}[EXPLORE]{Colors.RESET}" if result["is_explore"] else f"{Colors.BLUE}[EXPLOIT]{Colors.RESET}"

        cprint(f"  INCIDENT : {result['incident_type']}", incident_color)
        print(f"  STRATEGY : {Colors.CYAN}{result['strategy']}{Colors.RESET} {explore_tag}")
        print(f"  RESULT   : {restore_icon}{Colors.RESET} | Recovery: {result['recovery_time']:.1f}s")
        print(f"  REWARD   : {Colors.GREEN if result['reward'] > 50 else Colors.YELLOW}{result['reward']:+.2f}{Colors.RESET}")
        if result["llm_verdict"] != "skipped":
            print(f"  LLM JUDGE: {result['llm_verdict'].upper()}")

        # Metrics delta
        mb = result["metrics_before"]
        ma = result["metrics_after"]
        lat_delta = mb.latency_ms - ma.latency_ms
        avail_delta = ma.availability - mb.availability
        print(f"  METRICS  : Latency {mb.latency_ms:.0f}ms → {ma.latency_ms:.0f}ms "
              f"({Colors.GREEN}↓{lat_delta:.0f}ms{Colors.RESET if lat_delta > 0 else Colors.RED}) | "
              f"Availability {mb.availability:.1%} → {ma.availability:.1%}")

        # Rolling stats every 5 runs
        if len(reward_history) >= 5 and (run_index + 1) % 5 == 0:
            recent_avg = sum(reward_history[-5:]) / 5
            overall_avg = sum(reward_history) / len(reward_history)
            trend = "↑" if recent_avg > overall_avg else "↓"
            cprint(
                f"\n  ── Progress: Recent avg reward {recent_avg:.2f} {trend} "
                f"(overall {overall_avg:.2f}) ──",
                Colors.DIM,
            )

        # Small delay to make output readable
        await asyncio.sleep(0.1)

    # ── FINAL REPORT ───────────────────────────────────────────────
    total_time = time.time() - start_time
    print()
    cprint("═" * 70, Colors.CYAN)
    cprint("  EVOO LEARNING COMPLETE — FINAL REPORT", Colors.BOLD + Colors.CYAN)
    cprint("═" * 70, Colors.CYAN)

    avg_all = sum(reward_history) / len(reward_history) if reward_history else 0
    avg_early = sum(reward_history[:5]) / min(5, len(reward_history))
    avg_late = sum(reward_history[-5:]) / min(5, len(reward_history))
    improvement = avg_late - avg_early
    avg_recovery = sum(recovery_history) / len(recovery_history) if recovery_history else 0
    best_recovery = min(recovery_history) if recovery_history else 0

    print(f"\n  {'Metric':<35} {'Value':>15}")
    print(f"  {'─'*50}")
    print(f"  {'Total Runs':<35} {num_runs:>15}")
    print(f"  {'Average Reward (all)':<35} {avg_all:>15.2f}")
    print(f"  {'Average Reward (first 5)':<35} {avg_early:>15.2f}")
    print(f"  {'Average Reward (last 5)':<35} {avg_late:>15.2f}")
    improvement_str = f"{improvement:+.2f} ({'IMPROVED ✓' if improvement > 0 else 'NEEDS MORE'})"
    print(f"  {'Net Improvement':<35} {improvement_str:>15}")
    print(f"  {'Best Reward':<35} {max(reward_history, default=0):>15.2f}")
    print(f"  {'Avg Recovery Time':<35} {avg_recovery:>14.1f}s")
    print(f"  {'Best Recovery Time':<35} {best_recovery:>14.1f}s")
    print(f"  {'Total Wall Time':<35} {total_time:>14.1f}s")

    # Strategy rankings
    print()
    cprint("  Strategy Rankings Learned:", Colors.BOLD)
    rankings = await get_strategy_rankings_activity(None)
    for incident_type, records in list(rankings.get("rankings", {}).items())[:6]:
        top = records[:3]
        top_str = " > ".join([f"{r['strategy']}({r['avg_reward']:.1f})" for r in top])
        print(f"  {incident_type:<35} {top_str}")

    # Memory file location
    print()
    cprint(f"  Memory stored at: {os.environ['MEMORY_FILE_PATH']}", Colors.DIM)
    cprint(f"  Strategies at:    {os.environ['STRATEGY_FILE_PATH']}", Colors.DIM)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EVOO Standalone Learning Loop")
    parser.add_argument("--runs", type=int, default=30, help="Number of learning cycles (default: 30)")
    parser.add_argument("--explore", type=float, default=0.2, help="Epsilon exploration rate (default: 0.2)")
    parser.add_argument("--openai-key", type=str, default="", help="OpenAI API key for LLM judge")
    args = parser.parse_args()

    asyncio.run(main(args.runs, args.explore, args.openai_key))
