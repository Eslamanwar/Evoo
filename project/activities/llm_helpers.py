"""Shared LLM client helpers for EVOO.

Provides call_llm() as a plain async function (callable from activities)
and call_llm_activity as a Temporal activity wrapper.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, Optional, Tuple

from temporalio import activity

from agentex.lib.utils.logging import make_logger

logger = make_logger(__name__)


async def call_llm(
    prompt: str,
    system_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 800,
    json_mode: bool = False,
    timeout: float = 60.0,
    max_retries: int = 3,
) -> str:
    """Call LLM via OpenAI SDK with retry and heartbeat support.

    This is a plain async function (not a Temporal activity) so it can be
    called directly from within activities, matching the red-cell pattern.
    """
    from openai import AsyncOpenAI
    import httpx

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    def _heartbeat(msg: str = "Calling LLM..."):
        try:
            activity.heartbeat(msg)
        except Exception:
            pass

    last_error = None
    for attempt in range(max_retries):
        try:
            _heartbeat(f"LLM call attempt {attempt + 1}/{max_retries}...")

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
            )

            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = await client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            _heartbeat("LLM call completed")
            return content

        except asyncio.CancelledError:
            logger.warning(f"LLM call cancelled on attempt {attempt + 1}")
            return '{"error": "cancelled"}'

        except (asyncio.TimeoutError,) as e:
            last_error = f"timeout: {e}"
            logger.warning(f"LLM call timed out on attempt {attempt + 1}/{max_retries}")

        except Exception as e:
            if "httpx" in type(e).__module__:
                last_error = f"http_error: {e}"
                logger.warning(f"LLM HTTP error on attempt {attempt + 1}/{max_retries}: {e}")
            else:
                last_error = str(e)
                logger.warning(f"LLM call failed on attempt {attempt + 1}/{max_retries}: {e}")

        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 2
            _heartbeat(f"Retrying LLM in {wait_time}s...")
            await asyncio.sleep(wait_time)

    logger.error(f"LLM call failed after {max_retries} attempts: {last_error}")
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")


@activity.defn(name="call_llm_activity")
async def call_llm_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Temporal activity wrapper around call_llm."""
    try:
        content = await call_llm(
            prompt=params.get("prompt", ""),
            system_prompt=params.get("system_prompt", ""),
            temperature=params.get("temperature", 0.3),
            max_tokens=params.get("max_tokens", 800),
            json_mode=params.get("json_mode", False),
            timeout=params.get("timeout", 60.0),
            max_retries=params.get("max_retries", 3),
        )
        return {"status": "success", "content": content}
    except Exception as e:
        logger.warning(f"call_llm_activity failed: {e}")
        return {"status": "error", "content": "", "error": str(e)}


def parse_action(response: str) -> Tuple[str, Dict[str, Any]]:
    """Parse LLM response to extract ACTION: tool_name(key=value, ...).

    Ported from red-cell's pentest_agent_loop.py.
    """
    action_match = re.search(r"ACTION:\s*(\w+)\((.*?)\)", response, re.DOTALL)
    if not action_match:
        return "none", {}

    tool_name = action_match.group(1)
    params_str = action_match.group(2).strip()

    params: Dict[str, Any] = {}
    if params_str:
        for match in re.finditer(r'(\w+)\s*=\s*["\']?([^"\',)]+)["\']?', params_str):
            key = match.group(1)
            val = match.group(2).strip()
            try:
                params[key] = int(val)
            except ValueError:
                try:
                    params[key] = float(val)
                except ValueError:
                    params[key] = val

        if not params and params_str:
            params["value"] = params_str

    return tool_name, params


def parse_llm_json(response: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = response.strip()

    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

    logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}")
    return {}


# Tool descriptions for prompts
SRE_AVAILABLE_TOOLS = """Available SRE remediation tools:
1. analyze_logs(service_name, incident_type) - Analyze recent logs for root cause patterns
2. restart_service(service_name) - Gracefully restart the affected service
3. scale_horizontal(target_instances, service_name) - Scale to N instances horizontally
4. scale_vertical(target_cpu, target_memory_gb, service_name) - Increase CPU/memory limits
5. change_timeout(new_timeout_ms, service_name) - Update timeout configuration
6. rollback_deployment(service_name) - Rollback to previous stable deployment
7. clear_cache(service_name, cache_type) - Clear service cache to free memory
8. rebalance_load(service_name) - Rebalance traffic across available instances
9. query_metrics(service_name) - Query current system metrics from observability stack
10. finish() - Remediation complete, proceed to evaluation"""

STRATEGY_DESCRIPTIONS = """Available remediation strategies:
- restart_service: Restart the affected service. Best for crashes, memory leaks.
- scale_horizontal: Add more instances. Best for high load, latency spikes.
- scale_vertical: Increase CPU/memory per instance. Best for CPU spikes, resource exhaustion.
- change_timeout: Adjust timeout configuration. Best for timeout misconfigs, cascading failures.
- rollback_deployment: Roll back to previous version. Best for regression bugs, bad deploys.
- clear_cache: Clear service cache. Best for memory leaks, stale data issues.
- rebalance_load: Redistribute traffic across instances. Best for network issues, load imbalance.
- combined_restart_scale: Restart + scale out. Aggressive approach for severe crashes.
- combined_cache_rebalance: Clear cache + rebalance. For combined memory + network issues.
- combined_rollback_scale: Rollback + scale out. For severe regressions under load."""

VALID_TOOL_NAMES = {
    "analyze_logs", "restart_service", "scale_horizontal", "scale_vertical",
    "change_timeout", "rollback_deployment", "clear_cache", "rebalance_load",
    "query_metrics", "finish",
}

TOOL_TO_ACTIVITY = {
    "analyze_logs": "analyze_logs_activity",
    "restart_service": "restart_service_activity",
    "scale_horizontal": "scale_horizontal_activity",
    "scale_vertical": "scale_vertical_activity",
    "change_timeout": "change_timeout_activity",
    "rollback_deployment": "rollback_deployment_activity",
    "clear_cache": "clear_cache_activity",
    "rebalance_load": "rebalance_load_activity",
    "query_metrics": "query_metrics_tool_activity",
}
