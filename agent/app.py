"""
agent/app.py -- interactive local coding assistant assembly.

Streaming support:
  - When streaming=True (default for interactive mode), model responses print
    token-by-token to the terminal. core.py still receives the full message
    after the stream completes — streaming is UI-only and does not change the
    agent loop contract.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import litellm as _litellm_mod  # for exception types
from dotenv import load_dotenv

from agent.context import ContextBuilder, build_local_code_assistant_prompt, truncate_output
from agent.core import Agent
from agent.middleware import (
    BashSafetyMiddleware,
    ContextCompactionMiddleware,
    ReflectionMiddleware,
    SandboxAwarenessMiddleware,
    detect_sandbox,
)
from agent.tools.bash import BashTool
from agent.tools.delegate import DelegateTool
from agent.tools.registry import ToolRegistry
from agent.tools.semantic_search import SemanticSearchTool
from agent.tools.task_board import TaskBoardTool


@dataclass(slots=True)
class AppConfig:
    model_name: str
    work_dir: Path
    trajectory_dir: Path
    transcript_dir: Path
    tasks_dir: Path
    step_limit: int = 20
    cost_limit: float = 3.0
    delegate_step_limit: int = 8
    delegate_cost_limit: float = 1.0
    compact_threshold_tokens: int = 12_000
    fallback_model_name: str | None = None
    streaming: bool = True
    enable_reflection: bool = False
    prompt_version: str | None = None

    @classmethod
    def from_env(cls, work_dir: str | Path | None = None) -> "AppConfig":
        work_dir_path = Path(work_dir or Path.cwd()).resolve()
        model_name = os.getenv("MODEL_NAME", "deepseek/deepseek-chat")
        return cls(
            model_name=model_name,
            work_dir=work_dir_path,
            trajectory_dir=work_dir_path / "trajectories",
            transcript_dir=work_dir_path / ".transcripts",
            tasks_dir=work_dir_path / ".tasks",
            step_limit=int(os.getenv("AGENT_STEP_LIMIT", "20")),
            cost_limit=float(os.getenv("AGENT_COST_LIMIT", "3.0")),
            delegate_step_limit=int(os.getenv("AGENT_DELEGATE_STEP_LIMIT", "8")),
            delegate_cost_limit=float(os.getenv("AGENT_DELEGATE_COST_LIMIT", "1.0")),
            compact_threshold_tokens=int(os.getenv("AGENT_COMPACT_THRESHOLD_TOKENS", "12000")),
            fallback_model_name=os.getenv("FALLBACK_MODEL_NAME"),
            streaming=os.getenv("AGENT_STREAMING", "1") not in ("0", "false", "no"),
            enable_reflection=os.getenv("AGENT_REFLECTION", "1") not in ("0", "false", "no"),
            prompt_version=os.getenv("AGENT_PROMPT_VERSION"),
        )


class Ansi:
    reset = "\033[0m"
    bold = "\033[1m"
    cyan = "\033[36m"
    green = "\033[32m"
    yellow = "\033[33m"
    magenta = "\033[35m"
    blue = "\033[34m"
    red = "\033[31m"
    dim = "\033[2m"


class TerminalUI:
    """Minimal ANSI-based UI with live tool traces."""

    def print_banner(self, config: AppConfig, sandbox_summary: str) -> None:
        print(f"{Ansi.bold}{Ansi.cyan}Local Code Assistant{Ansi.reset}")
        print(f"{Ansi.dim}model={config.model_name}{Ansi.reset}")
        print(f"{Ansi.dim}workspace={config.work_dir}{Ansi.reset}")
        for line in sandbox_summary.splitlines():
            print(f"{Ansi.dim}{line}{Ansi.reset}")
        print(f"{Ansi.dim}Type 'exit' or 'quit' to leave.{Ansi.reset}\n")

    def prompt(self) -> str:
        return input(f"{Ansi.bold}{Ansi.blue}assistant >> {Ansi.reset}")

    def print_tool_start(self, name: str, arguments: dict[str, Any]) -> None:
        arg_text = truncate_output(str(arguments), max_chars=200, head=120, tail=60)
        print(f"{Ansi.yellow}[tool]{Ansi.reset} {name} {Ansi.dim}{arg_text}{Ansi.reset}")

    def print_tool_result(self, name: str, observation: str) -> None:
        preview = truncate_output(str(observation), max_chars=500, head=280, tail=120)
        print(f"{Ansi.magenta}[result:{name}]{Ansi.reset} {preview}")

    def print_assistant(self, content: str) -> None:
        print(f"{Ansi.green}{content}{Ansi.reset}\n")

    def print_stream_chunk(self, text: str) -> None:
        """Print a streaming text chunk without newline (inline update)."""
        sys.stdout.write(f"{Ansi.green}{text}{Ansi.reset}")
        sys.stdout.flush()

    def end_stream(self) -> None:
        """Finish a streaming line."""
        print(Ansi.reset)

    def print_status(self, result: dict[str, Any], trajectory_path: Path | None) -> None:
        traj = str(trajectory_path) if trajectory_path else "(disabled)"
        print(
            f"{Ansi.dim}[status] {result['status']} | steps={result['total_steps']} "
            f"| cost=${result['total_cost']:.4f} | trajectory={traj}{Ansi.reset}"
        )

    def print_error(self, message: str) -> None:
        print(f"{Ansi.red}{message}{Ansi.reset}")


class TracingToolExecutor:
    """Tool executor wrapper that mirrors tool activity to the terminal UI."""

    def __init__(self, base_executor, ui: TerminalUI | None = None) -> None:
        self._base = base_executor
        self._ui = ui

    def __call__(self, name: str, arguments: dict[str, Any]) -> str:
        if self._ui:
            self._ui.print_tool_start(name, arguments)
        observation = self._base(name, arguments)
        if self._ui:
            self._ui.print_tool_result(name, observation)
        return observation


# Streaming-transport errors that are safe to retry non-streaming.
_STREAM_TRANSPORT_ERRORS = (
    ConnectionError,
    OSError,
    _litellm_mod.Timeout,
    _litellm_mod.ServiceUnavailableError,
)


class StreamingModelWrapper:
    """Transparently intercept model.query() to stream text chunks to the UI.

    If the underlying model supports query_stream(), use it to print tokens
    live. Falls back to non-streaming query() only for transport-level errors
    and only when no content has been printed yet.
    The agent loop always receives the full completed message — streaming
    is purely a UI concern.
    """

    def __init__(self, model: Any, ui: TerminalUI) -> None:
        self._model = model
        self._ui = ui

    def query(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if not hasattr(self._model, "query_stream"):
            return self._model.query(messages)
        has_content = False
        try:
            final_msg, chunks = self._model.query_stream(messages)
            for chunk in chunks:
                if chunk:
                    has_content = True
                    self._ui.print_stream_chunk(chunk)
            if has_content:
                self._ui.end_stream()
            return final_msg
        except _STREAM_TRANSPORT_ERRORS as e:
            if has_content:
                # Already printed partial output — don't double-fire
                raise
            logger.warning(
                "Streaming transport failed (%s), falling back to non-streaming.",
                type(e).__name__,
            )
            return self._model.query(messages)


class LocalCodeAssistantApp:
    """Owns tool wiring, runtime prompt, and per-turn execution."""

    def __init__(
        self,
        config: AppConfig,
        agent: Agent,
        system_prompt: str,
        sandbox_summary: str,
    ) -> None:
        self.config = config
        self.agent = agent
        self.system_prompt = system_prompt
        self.sandbox_summary = sandbox_summary
        self._session_id = time.strftime("%Y%m%d_%H%M%S")
        self._turn_index = 0

    @classmethod
    def build(
        cls,
        config: AppConfig,
        ui: TerminalUI | None = None,
    ) -> "LocalCodeAssistantApp":
        load_dotenv(override=False)
        from agent.models import FallbackModel, LLMModel

        sandbox = detect_sandbox(config.work_dir)
        sandbox_summary = sandbox.render()

        # Prompt version: use YAML file if specified, otherwise built-in
        if config.prompt_version:
            prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
            yaml_path = prompts_dir / f"{config.prompt_version}.yaml"
            if yaml_path.is_file():
                builder = ContextBuilder.from_yaml(
                    yaml_path, work_dir=config.work_dir, sandbox_summary=sandbox_summary,
                )
                system_prompt = builder.build()
            else:
                logger.warning("Prompt version %s not found at %s, using default.", config.prompt_version, yaml_path)
                system_prompt = build_local_code_assistant_prompt(
                    work_dir=config.work_dir, sandbox_summary=sandbox_summary,
                )
        else:
            system_prompt = build_local_code_assistant_prompt(
                work_dir=config.work_dir,
                sandbox_summary=sandbox_summary,
            )

        main_registry = ToolRegistry()
        main_registry.register(BashTool(work_dir=config.work_dir))
        main_registry.register(SemanticSearchTool(work_dir=config.work_dir))
        main_registry.register(TaskBoardTool(tasks_dir=config.tasks_dir))

        sub_registry = ToolRegistry()
        sub_registry.register(BashTool(work_dir=config.work_dir))
        sub_registry.register(SemanticSearchTool(work_dir=config.work_dir))
        sub_registry.register(TaskBoardTool(tasks_dir=config.tasks_dir))

        sub_model = LLMModel(
            model_name=config.model_name,
            model_kwargs={"tools": sub_registry.get_schemas()},
            cost_tracking="ignore_errors",
        )
        sub_executor = BashSafetyMiddleware(
            sub_registry.execute,
            sandbox_info=sandbox,
            work_dir=config.work_dir,
        )
        main_registry.register(
            DelegateTool(
                model=sub_model,
                sub_tool_executor=sub_executor,
                step_limit=config.delegate_step_limit,
                cost_limit=config.delegate_cost_limit,
            )
        )

        # Primary model
        primary_model = LLMModel(
            model_name=config.model_name,
            model_kwargs={"tools": main_registry.get_schemas()},
            cost_tracking="ignore_errors",
        )
        # Fallback chain: wrap primary with fallback if configured
        if config.fallback_model_name:
            fallback_llm = LLMModel(
                model_name=config.fallback_model_name,
                model_kwargs={"tools": main_registry.get_schemas()},
                cost_tracking="ignore_errors",
            )
            main_model: Any = FallbackModel([primary_model, fallback_llm])
        else:
            main_model = primary_model

        summary_model = LLMModel(
            model_name=config.model_name,
            model_kwargs={},
            cost_tracking="ignore_errors",
        )

        guarded_executor = BashSafetyMiddleware(
            main_registry.execute,
            sandbox_info=sandbox,
            work_dir=config.work_dir,
        )
        tool_executor = TracingToolExecutor(guarded_executor, ui=ui)

        middlewares: list[Any] = [
            SandboxAwarenessMiddleware(sandbox),
            ContextCompactionMiddleware(
                summary_model=summary_model,
                transcript_dir=config.transcript_dir,
                condense_threshold_tokens=config.compact_threshold_tokens,
            ),
        ]
        if config.enable_reflection:
            middlewares.append(ReflectionMiddleware(max_reflections=1))

        # Streaming wrapper: intercepts model.query to show tokens live
        if config.streaming and ui:
            main_model = StreamingModelWrapper(main_model, ui)

        agent = Agent(
            model=main_model,
            tool_executor=tool_executor,
            middlewares=middlewares,
            step_limit=config.step_limit,
            cost_limit=config.cost_limit,
        )
        return cls(
            config=config,
            agent=agent,
            system_prompt=system_prompt,
            sandbox_summary=sandbox_summary,
        )

    def initial_messages(self) -> list[dict[str, Any]]:
        return [{"role": "system", "content": self.system_prompt}]

    def run_turn(
        self,
        history: list[dict[str, Any]],
        user_text: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
        messages = list(history)
        messages.append({"role": "user", "content": user_text})

        trajectory_path = self._next_trajectory_path()
        self.agent.config.trajectory_path = trajectory_path
        result = self.agent.run(messages)
        return list(self.agent.messages), result, trajectory_path

    def _next_trajectory_path(self) -> Path:
        self._turn_index += 1
        self.config.trajectory_dir.mkdir(parents=True, exist_ok=True)
        return self.config.trajectory_dir / (
            f"{self._session_id}_turn_{self._turn_index:02d}.jsonl"
        )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Local coding assistant")
    parser.add_argument("--task", help="Single-shot task (non-interactive mode)")
    parser.add_argument("--work-dir", help="Working directory (default: cwd)")
    args = parser.parse_args()

    config = AppConfig.from_env(work_dir=args.work_dir)
    ui = TerminalUI()

    try:
        app = LocalCodeAssistantApp.build(config=config, ui=ui)
    except Exception as e:
        ui.print_error(f"Failed to start assistant: {e}")
        return 1

    # Single-shot mode: run one task and exit
    if args.task:
        history = app.initial_messages()
        try:
            history, result, trajectory_path = app.run_turn(history, args.task)
        except Exception as e:
            ui.print_error(f"Run failed: {e}")
            return 1
        ui.print_status(result, trajectory_path)
        if result.get("final_content"):
            ui.print_assistant(result["final_content"])
        return 0 if result.get("status") == "Submitted" else 1

    # Interactive mode
    ui.print_banner(config, app.sandbox_summary)
    history = app.initial_messages()

    while True:
        try:
            user_text = ui.prompt().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            return 0

        try:
            history, result, trajectory_path = app.run_turn(history, user_text)
        except Exception as e:
            ui.print_error(f"Run failed: {e}")
            continue

        ui.print_status(result, trajectory_path)
        if result.get("final_content"):
            ui.print_assistant(result["final_content"])
        else:
            ui.print_error("No assistant summary was produced.")


if __name__ == "__main__":
    raise SystemExit(main())
