"""Parallel Modal/OpenAI agent orchestration.

This module is intentionally independent from pcbnew. KiCad design mutations
remain in the local MCP worker, while agents produce plans, checks, and review
notes that can safely run in parallel locally or remotely on Modal.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_MODEL = os.environ.get("KICAD_MCP_AGENT_MODEL", "gpt-4.1-mini")

try:  # pragma: no cover - optional dependency
    import modal  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    modal = None  # type: ignore

if modal is not None:  # pragma: no cover - requires Modal client/auth
    _MODAL_IMAGE = modal.Image.debian_slim().pip_install("openai-agents>=0.2.0")
    _MODAL_SECRET_NAME = os.environ.get("MODAL_OPENAI_SECRET")
    _MODAL_SECRETS = [modal.Secret.from_name(_MODAL_SECRET_NAME)] if _MODAL_SECRET_NAME else []
    _MODAL_APP = modal.App("kicad-mcp-parallel-agents")
else:
    _MODAL_APP = None


@dataclass
class AgentSpec:
    name: str
    role: str
    instructions: str


@dataclass
class AgentResult:
    name: str
    role: str
    backend: str
    model: str
    elapsed_s: float
    output: str
    success: bool = True
    error: Optional[str] = None


DEFAULT_AGENTS = [
    AgentSpec(
        name="schematic_architect",
        role="Schematic architecture",
        instructions=(
            "Review the requested PCB change from a schematic and interface-contract "
            "perspective. Identify required sheets, symbols, nets, power rails, labels, "
            "and verification steps. Return concrete KiCad MCP actions."
        ),
    ),
    AgentSpec(
        name="layout_engineer",
        role="PCB layout and routing",
        instructions=(
            "Review the requested PCB change from a layout, footprint, placement, "
            "clearance, and routing perspective. Return concrete KiCad MCP actions "
            "and risks before fabrication."
        ),
    ),
    AgentSpec(
        name="dfm_reviewer",
        role="DFM and validation",
        instructions=(
            "Review the requested PCB change for manufacturability, ERC/DRC, connector "
            "pinout, BOM, assembly, and documentation concerns. Return checks that "
            "should be run before accepting the design."
        ),
    ),
]


def dependency_status() -> Dict[str, Any]:
    """Return dependency status without importing optional packages eagerly."""
    return {
        "modal_installed": importlib.util.find_spec("modal") is not None,
        "openai_agents_installed": importlib.util.find_spec("agents") is not None,
        "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "default_model": DEFAULT_MODEL,
        "modal_secret": os.environ.get("MODAL_OPENAI_SECRET", ""),
    }


def _coerce_agents(raw_agents: Optional[Iterable[Dict[str, Any]]]) -> List[AgentSpec]:
    if not raw_agents:
        return DEFAULT_AGENTS

    agents: List[AgentSpec] = []
    for raw in raw_agents:
        name = str(raw.get("name", "")).strip()
        role = str(raw.get("role", "")).strip()
        instructions = str(raw.get("instructions", "")).strip()
        if not name or not role:
            raise ValueError("Each agent must include non-empty 'name' and 'role'")
        agents.append(
            AgentSpec(
                name=name,
                role=role,
                instructions=instructions
                or f"Act as the {role} reviewer for a KiCad PCB design task.",
            )
        )

    return agents


def _agent_prompt(agent: AgentSpec, task: str, context: str) -> str:
    return (
        f"Task:\n{task.strip()}\n\n"
        f"Project context:\n{context.strip() or 'No additional context provided.'}\n\n"
        "Return a concise engineering response with: findings, recommended KiCad MCP "
        "tool calls, validation checks, and open questions. Prefer concrete net names, "
        "component references, footprints, and file paths when they are known."
    )


def _run_openai_agent(
    agent: AgentSpec,
    task: str,
    context: str,
    model: str,
    backend_label: str,
) -> AgentResult:
    started = time.monotonic()
    try:
        from agents import Agent, Runner  # type: ignore

        openai_agent = Agent(
            name=agent.name,
            model=model,
            instructions=f"{agent.role}\n\n{agent.instructions}",
        )
        result = Runner.run_sync(openai_agent, _agent_prompt(agent, task, context))
        output = getattr(result, "final_output", str(result))
        return AgentResult(
            name=agent.name,
            role=agent.role,
            backend=backend_label,
            model=model,
            elapsed_s=round(time.monotonic() - started, 3),
            output=str(output),
        )
    except Exception as exc:  # pragma: no cover - depends on optional SDK/API
        return AgentResult(
            name=agent.name,
            role=agent.role,
            backend=backend_label,
            model=model,
            elapsed_s=round(time.monotonic() - started, 3),
            output="",
            success=False,
            error=str(exc),
        )


def _run_local_heuristic_agent(
    agent: AgentSpec,
    task: str,
    context: str,
    model: str,
) -> AgentResult:
    started = time.monotonic()
    task_l = task.lower()
    focus_items = [
        "Open or snapshot the active KiCad project before making changes.",
        "Inspect affected schematic sheets and board footprints before editing.",
        "Apply changes through MCP tools, then run ERC/DRC or export checks.",
    ]

    if "usb" in task_l or "connector" in task_l:
        focus_items.append("Verify connector pin mapping, duplicated pins, shield, CC resistors, and VBUS.")
    if "radio" in task_l or "ltm" in task_l:
        focus_items.append("Check radio interface nets, antenna paths, power budget, and host command buses.")
    if "modal" in task_l or "agent" in task_l:
        focus_items.append("Keep local KiCad mutation serialized; parallelize only analysis and planning.")

    context_hint = f" Context length: {len(context)} characters." if context else ""
    output = (
        f"{agent.role} review for '{task}'.{context_hint}\n"
        + "\n".join(f"- {item}" for item in focus_items)
        + "\nRecommended next MCP actions: list project info, inspect relevant schematic/board views, "
        "make scoped edits, save, then run validation exports/checks."
    )
    return AgentResult(
        name=agent.name,
        role=agent.role,
        backend="local-thread",
        model=model,
        elapsed_s=round(time.monotonic() - started, 3),
        output=output,
    )


def _run_one_agent(
    agent: AgentSpec,
    task: str,
    context: str,
    model: str,
    openai_mode: str,
    backend_label: str,
) -> AgentResult:
    status = dependency_status()
    can_use_openai = status["openai_agents_installed"] and status["openai_api_key_present"]
    if openai_mode == "required" and not can_use_openai:
        return AgentResult(
            name=agent.name,
            role=agent.role,
            backend=backend_label,
            model=model,
            elapsed_s=0,
            output="",
            success=False,
            error="OpenAI Agents SDK and OPENAI_API_KEY are required but not available",
        )
    if openai_mode != "off" and can_use_openai:
        return _run_openai_agent(agent, task, context, model, backend_label)
    return _run_local_heuristic_agent(agent, task, context, model)


if _MODAL_APP is not None:  # pragma: no cover - requires Modal client/auth

    @_MODAL_APP.function(image=_MODAL_IMAGE, secrets=_MODAL_SECRETS, timeout=300)
    def _run_remote_agent(
        agent_payload: Dict[str, str],
        remote_task: str,
        remote_context: str,
        remote_model: str,
        remote_openai_mode: str,
    ) -> Dict[str, Any]:
        agent = AgentSpec(**agent_payload)
        result = _run_one_agent(
            agent,
            remote_task,
            remote_context,
            remote_model,
            remote_openai_mode,
            "modal",
        )
        return asdict(result)
else:
    _run_remote_agent = None  # type: ignore


def _run_local(
    agents: List[AgentSpec],
    task: str,
    context: str,
    model: str,
    openai_mode: str,
    max_workers: int,
) -> List[AgentResult]:
    workers = max(1, min(max_workers, len(agents)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_run_one_agent, agent, task, context, model, openai_mode, "local-thread")
            for agent in agents
        ]
        return [future.result() for future in futures]


def _run_modal(
    agents: List[AgentSpec],
    task: str,
    context: str,
    model: str,
    openai_mode: str,
    timeout_s: int,
) -> List[AgentResult]:
    if modal is None or _MODAL_APP is None or _run_remote_agent is None:
        raise RuntimeError("Modal is not installed or importable")

    inputs = [(asdict(agent), task, context, model, openai_mode) for agent in agents]
    remote_agent = _run_remote_agent.with_options(timeout=timeout_s)
    with _MODAL_APP.run():
        raw_results = list(remote_agent.starmap(inputs, order_outputs=True))
    return [AgentResult(**raw) for raw in raw_results]


def _summarize(results: List[AgentResult]) -> Dict[str, Any]:
    successful = [result for result in results if result.success]
    failed = [result for result in results if not result.success]
    return {
        "success_count": len(successful),
        "failure_count": len(failed),
        "backends": sorted({result.backend for result in results}),
        "recommended_flow": [
            "Review agent findings for conflicts and missing assumptions.",
            "Execute KiCad MCP edits locally in a serialized order.",
            "Save the project and run ERC/DRC/export validation.",
        ],
    }


def run_parallel_agents(payload: Dict[str, Any]) -> Dict[str, Any]:
    task = str(payload.get("task", "")).strip()
    if not task:
        raise ValueError("'task' is required")

    context = str(payload.get("context", ""))
    backend = str(payload.get("backend", "auto")).lower()
    openai_mode = str(payload.get("openai", "auto")).lower()
    model = str(payload.get("model", DEFAULT_MODEL))
    timeout_s = int(payload.get("timeout_s", 300))
    max_workers = int(payload.get("max_workers", 4))
    agents = _coerce_agents(payload.get("agents"))

    if backend not in {"auto", "local", "modal"}:
        raise ValueError("backend must be one of: auto, local, modal")
    if openai_mode not in {"auto", "off", "required"}:
        raise ValueError("openai must be one of: auto, off, required")

    status = dependency_status()
    selected_backend = "modal" if backend == "modal" or (backend == "auto" and status["modal_installed"]) else "local"
    started = time.monotonic()

    try:
        if selected_backend == "modal":
            results = _run_modal(agents, task, context, model, openai_mode, timeout_s)
        else:
            results = _run_local(agents, task, context, model, openai_mode, max_workers)
    except Exception as exc:
        if backend == "modal":
            raise
        selected_backend = "local"
        results = _run_local(agents, task, context, model, openai_mode, max_workers)
        status["modal_fallback_reason"] = str(exc)

    return {
        "success": all(result.success for result in results),
        "backend": selected_backend,
        "elapsed_s": round(time.monotonic() - started, 3),
        "dependency_status": status,
        "summary": _summarize(results),
        "agents": [asdict(result) for result in results],
    }


def handle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    command = payload.get("command", "run_parallel_agents")
    params = payload.get("params", payload)
    if command == "dependency_status":
        return {"success": True, **dependency_status()}
    if command == "run_parallel_agents":
        return run_parallel_agents(params)
    raise ValueError(f"Unknown command: {command}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run KiCAD MCP parallel agents")
    parser.add_argument("--status", action="store_true", help="Print dependency status")
    args = parser.parse_args()

    try:
        if args.status:
            response = {"success": True, **dependency_status()}
        else:
            raw = os.read(0, 10 * 1024 * 1024).decode("utf-8")
            payload = json.loads(raw or "{}")
            response = handle_payload(payload)
    except Exception as exc:
        response = {"success": False, "message": str(exc)}

    print(json.dumps(response))


if __name__ == "__main__":
    main()
