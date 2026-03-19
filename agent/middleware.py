"""
agent/middleware.py -- agent hooks plus execution guardrails.

Responsibilities:
  - Middleware ABC with pre_step / post_step hooks
  - detect_sandbox(): lightweight environment and writeability probe
  - BashSafetyMiddleware: block obviously dangerous shell commands
  - SandboxAwarenessMiddleware: inject sandbox facts into the system prompt once
  - ContextCompactionMiddleware: compact old tool output and summarize history before query
"""

from __future__ import annotations

import logging
import os
import platform
import re
import tempfile
import time
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agent.context import (
    archive_messages,
    condense_history,
    estimate_tokens,
    micro_compact_tool_messages,
)

logger = logging.getLogger(__name__)


class Middleware(ABC):
    """Agent loop step hooks. Subclasses may override either method."""

    def pre_step(self, agent: Any) -> None:
        """Called before each model query."""

    def post_step(self, agent: Any) -> None:
        """Called after dispatch and step persistence."""


@dataclass(slots=True)
class SandboxInfo:
    """Best-effort view of the current runtime constraints."""

    mode: str
    source: str
    shell: str
    workspace_root: Path
    workspace_writable: bool
    temp_writable: bool
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"sandbox_mode={self.mode}",
            f"source={self.source}",
            f"shell={self.shell}",
            f"workspace_root={self.workspace_root}",
            f"workspace_writable={self.workspace_writable}",
            f"temp_writable={self.temp_writable}",
        ]
        if self.notes:
            lines.append("notes=" + "; ".join(self.notes))
        return "\n".join(lines)


@dataclass(slots=True)
class CommandVerdict:
    allowed: bool
    reason: str = ""


_HIGH_RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|[;&|])\s*sudo\b", re.IGNORECASE), "sudo elevation is blocked"),
    (re.compile(r"\brm\s+-rf\s+([/\\]|[A-Za-z]:\\)(\s|$)", re.IGNORECASE), "destructive recursive delete is blocked"),
    (re.compile(r"\b(del|erase)\s+/[a-z]*\s+[A-Za-z]:\\", re.IGNORECASE), "destructive Windows delete is blocked"),
    (re.compile(r"\brmdir\s+/s\b", re.IGNORECASE), "recursive directory deletion is blocked"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "destructive git reset is blocked"),
    (re.compile(r"\bgit\s+clean\s+-f", re.IGNORECASE), "destructive git clean is blocked"),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.IGNORECASE), "system power commands are blocked"),
    (re.compile(r"\bmkfs(\.\w+)?\b", re.IGNORECASE), "disk formatting commands are blocked"),
    (re.compile(r"\bdiskpart\b", re.IGNORECASE), "disk partition commands are blocked"),
    (re.compile(r"\bdd\s+if=", re.IGNORECASE), "raw disk writes are blocked"),
    (re.compile(r"curl\b[^|]*\|\s*(sh|bash|zsh|pwsh|powershell)\b", re.IGNORECASE), "pipe-to-shell install commands are blocked"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE), "fork bomb pattern is blocked"),
]

_WRITE_LIKE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(touch|mkdir|copy|move|ren|echo)\b", re.IGNORECASE),
    re.compile(r"\b(del|erase|rm|rmdir)\b", re.IGNORECASE),
    re.compile(r"\bpython\b.+\b(write_text|open\()", re.IGNORECASE),
    re.compile(r"(>>|>|Out-File|Set-Content|Add-Content)", re.IGNORECASE),
]


def detect_sandbox(
    work_dir: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> SandboxInfo:
    """Best-effort sandbox detection from env vars plus write probes."""
    env = dict(env or os.environ)
    workspace_root = Path(work_dir or ".").resolve()

    explicit_keys = (
        "CODEX_SANDBOX_MODE",
        "CLAUDE_CODE_SANDBOX",
        "SANDBOX_MODE",
        "WORKSPACE_SANDBOX_MODE",
    )
    mode = "unknown"
    source = "heuristic"
    for key in explicit_keys:
        value = env.get(key)
        if value:
            mode = value
            source = f"env:{key}"
            break

    workspace_writable = _probe_write_access(workspace_root)
    temp_writable = _probe_write_access(Path(tempfile.gettempdir()))
    shell = env.get("COMSPEC") or env.get("SHELL") or platform.system()

    notes: list[str] = []
    if env.get("CI"):
        notes.append("ci=true")
    if not workspace_writable:
        notes.append("workspace appears read-only")
    if not temp_writable:
        notes.append("temp directory appears read-only")

    if mode == "unknown":
        if workspace_writable and temp_writable:
            mode = "workspace-write-or-better"
        elif workspace_writable:
            mode = "workspace-write"
        else:
            mode = "read-only"

    return SandboxInfo(
        mode=mode,
        source=source,
        shell=shell,
        workspace_root=workspace_root,
        workspace_writable=workspace_writable,
        temp_writable=temp_writable,
        notes=notes,
    )


def assess_bash_command(command: str, sandbox: SandboxInfo | None = None) -> CommandVerdict:
    """Apply conservative guardrails to shell commands."""
    raw = command.strip()
    if not raw:
        return CommandVerdict(True)

    for pattern, reason in _HIGH_RISK_PATTERNS:
        if pattern.search(raw):
            return CommandVerdict(False, reason)

    if sandbox and sandbox.mode == "read-only":
        for pattern in _WRITE_LIKE_PATTERNS:
            if pattern.search(raw):
                return CommandVerdict(False, "sandbox appears read-only; write-like command blocked")

    return CommandVerdict(True)


def _check_bash_boundary(command: str, work_dir: str) -> str | None:
    """Detect bash commands that clearly reference absolute paths outside work_dir.

    Returns a warning string if suspicious, None otherwise.
    Only flags absolute paths — relative paths are fine (cwd is work_dir).
    Skips common safe system paths (/dev, /tmp, /usr, C:\\Windows, python paths).
    """
    import shlex

    work_dir_norm = os.path.normcase(os.path.abspath(work_dir))

    # Common safe absolute prefixes (not workspace-specific)
    _SAFE_PREFIXES = (
        "/dev", "/tmp", "/usr", "/bin", "/sbin", "/etc/ssl",
        "/proc", "/sys",
    )
    _SAFE_PREFIXES_WIN = (
        "c:\\windows", "c:\\program files", "c:\\users\\",
    )

    # Extract potential absolute paths from the command
    # Simple heuristic: split on whitespace and check tokens
    try:
        tokens = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        tokens = command.split()

    for token in tokens:
        token_norm = os.path.normcase(token)

        # Check if it looks like an absolute path
        is_abs = False
        if token.startswith("/") and not token.startswith("//"):
            is_abs = True
        elif len(token) >= 3 and token[1] == ":" and token[2] in ("/", "\\"):
            is_abs = True

        if not is_abs:
            continue

        # Skip safe system paths
        if any(token_norm.startswith(p) for p in _SAFE_PREFIXES):
            continue
        if os.name == "nt" and any(token_norm.startswith(p) for p in _SAFE_PREFIXES_WIN):
            continue

        # Check if outside work_dir
        if not token_norm.startswith(work_dir_norm):
            return (
                f"Command references path '{token}' outside workspace '{work_dir}'. "
                "Prefer relative paths within the workspace."
            )

    return None


class BashSafetyMiddleware:
    """Wrap tool execution and block high-risk shell commands before they run."""

    def __init__(
        self,
        base_executor: Callable[[str, dict], str],
        sandbox_info: SandboxInfo | None = None,
        work_dir: str | Path | None = None,
    ) -> None:
        self._base = base_executor
        self._sandbox = sandbox_info or detect_sandbox(work_dir=work_dir)
        self._work_dir: str | None = str(Path(work_dir).resolve()) if work_dir else None

    @property
    def sandbox_info(self) -> SandboxInfo:
        return self._sandbox

    def __call__(self, name: str, arguments: dict[str, Any]) -> str:
        if name != "bash":
            return self._base(name, arguments)

        command = str(arguments.get("command", ""))
        verdict = assess_bash_command(command, sandbox=self._sandbox)
        if not verdict.allowed:
            return f"Error: Blocked high-risk bash command. Reason: {verdict.reason}"

        # Workspace boundary warning (non-blocking)
        boundary_warning = None
        if self._work_dir:
            boundary_warning = _check_bash_boundary(command, self._work_dir)

        result = self._base(name, arguments)

        if boundary_warning:
            return f"[WARNING: {boundary_warning}]\n{result}"
        return result


class SandboxAwarenessMiddleware(Middleware):
    """Inject sandbox facts into the system prompt once per agent run."""

    def __init__(self, sandbox_info: SandboxInfo) -> None:
        self._sandbox_info = sandbox_info

    def pre_step(self, agent: Any) -> None:
        if getattr(agent, "_sandbox_notice_injected", False):
            return

        notice = (
            "[Sandbox detection]\n"
            f"{self._sandbox_info.render()}\n"
            "High-risk bash commands may be blocked. Re-check the environment before attempting destructive edits."
        )

        if agent.messages and agent.messages[0].get("role") == "system":
            original = agent.messages[0].get("content") or ""
            agent.messages[0]["content"] = original.rstrip() + "\n\n" + notice
        else:
            agent.messages.insert(0, {"role": "system", "content": notice})

        agent._sandbox_notice_injected = True


class ContextCompactionMiddleware(Middleware):
    """Compact old tool outputs and summarize history before the next model call."""

    def __init__(
        self,
        summary_model: Any,
        transcript_dir: str | Path = ".transcripts",
        keep_recent_tool_results: int = 3,
        compact_above_chars: int = 400,
        condense_threshold_tokens: int = 12_000,
        keep_last: int = 6,
    ) -> None:
        self.summary_model = summary_model
        self.transcript_dir = Path(transcript_dir)
        self.keep_recent_tool_results = keep_recent_tool_results
        self.compact_above_chars = compact_above_chars
        self.condense_threshold_tokens = condense_threshold_tokens
        self.keep_last = keep_last

    def pre_step(self, agent: Any) -> None:
        compacted = micro_compact_tool_messages(
            agent.messages,
            keep_recent=self.keep_recent_tool_results,
            compact_above_chars=self.compact_above_chars,
        )
        agent.messages[:] = compacted

        if estimate_tokens(agent.messages) < self.condense_threshold_tokens:
            return

        archive_path = archive_messages(agent.messages, self.transcript_dir)
        condensed = condense_history(
            agent.messages,
            model=self.summary_model,
            keep_last=self.keep_last,
            archive_path=archive_path,
        )
        agent.messages[:] = condensed
        logger.info("Context condensed before step %s. Transcript: %s", agent.n_steps + 1, archive_path)


class ReflectionMiddleware(Middleware):
    """Auto-review before allowing the agent to finish.

    When the agent produces a text-only response (which normally triggers Submitted),
    this middleware intercepts the first such response and injects a self-critique
    prompt, forcing one more loop iteration. On the second text-only response (or
    after max_reflections), the agent is allowed to finish normally.

    Inspired by Reflexion (Shinn et al. 2023).
    """

    def __init__(self, max_reflections: int = 1) -> None:
        self._max_reflections = max_reflections
        self._reflections_done = 0

    def pre_step(self, agent: Any) -> None:
        if agent.n_steps == 0:
            self._reflections_done = 0

    def post_step(self, agent: Any) -> None:
        if self._reflections_done >= self._max_reflections:
            return

        # Check if the latest assistant message has no tool calls (about to Submitted)
        if not agent.messages:
            return
        last = agent.messages[-1]
        if last.get("role") != "assistant":
            return
        has_tool_calls = bool(
            last.get("_normalized_tool_calls") or last.get("tool_calls")
        )
        if has_tool_calls:
            return

        # This is a text-only response — inject reflection prompt
        self._reflections_done += 1
        reflection_prompt = (
            "Before finishing, review your work:\n"
            "1. Did you verify the fix actually works (ran the test/command)?\n"
            "2. Are there edge cases you haven't considered?\n"
            "3. Did you introduce any new issues?\n"
            "4. Rate your confidence 1-5.\n\n"
            "If confidence < 4, continue fixing. "
            "If confidence >= 4, provide your final summary."
        )
        agent.messages.append({"role": "user", "content": reflection_prompt})
        logger.info("ReflectionMiddleware: injected self-critique (round %d)", self._reflections_done)


def _probe_write_access(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".sandbox_probe_{time.time_ns()}"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False
