"""
agent/context.py -- system prompt assembly and reusable context helpers.

Provides:
  - ContextBuilder: compose a system prompt from sections + inject AGENTS.md / CLAUDE.md
  - micro_compact_tool_messages(): shrink old tool results in-place-friendly form
  - condense_history(): summarize older history with an LLM while keeping the tail
"""

from __future__ import annotations

import copy
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AGENT_CONTEXT_FILES = ["AGENTS.md", "CLAUDE.md"]
_TRUNCATE_HEAD = 5_000
_TRUNCATE_TAIL = 5_000

_CONDENSE_SYSTEM = (
    "Summarize the conversation into a structured status report:\n"
    "1. GOAL: What the user asked for\n"
    "2. COMPLETED: What has been done (files modified, tests passed)\n"
    "3. IN PROGRESS: Current step and its state\n"
    "4. BLOCKED/RISKS: Any issues or concerns\n"
    "5. KEY FILES: File paths that were read or modified\n"
    "6. PENDING: What still needs to be done\n"
    "Be concise but preserve all actionable details."
)


class ContextBuilder:
    """Build a system prompt from sections and optional repo-level context files."""

    def __init__(
        self,
        sections: list[str] | None = None,
        work_dir: str | Path | None = None,
    ) -> None:
        self._sections: list[str] = list(sections) if sections else []
        self._work_dir: Path | None = Path(work_dir).resolve() if work_dir else None

    def add_section(self, text: str) -> "ContextBuilder":
        if text and text.strip():
            self._sections.append(text.strip())
        return self

    @classmethod # 类方法封装了实例化类的逻辑，从yaml文件创建 ContextBuilder 对象。
    def from_yaml(
        cls,
        yaml_path: str | Path,
        work_dir: str | Path | None = None,
        sandbox_summary: str = "",
    ) -> "ContextBuilder":
        """Load prompt sections from a versioned YAML file.

        The YAML file should have a 'sections' mapping where each key is a
        section name and the value is the prompt text. Supports {work_dir}
        placeholder substitution.

        Reference: inspired by promptfoo's YAML-first prompt management.
        """
        import yaml

        yaml_path = Path(yaml_path)
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        work_dir_str = str(Path(work_dir).resolve()) if work_dir else "."
        builder = cls(work_dir=work_dir)

        sections = data.get("sections", {})
        for name, text in sections.items():

            if text and isinstance(text, str):
                rendered = text.replace("{work_dir}", work_dir_str) # 没有占位符就透传
                builder.add_section(rendered)

        if sandbox_summary.strip():
            builder.add_section("Execution environment:\n" + sandbox_summary.strip())

        return builder

    def build(self) -> str:
        ''' Assemble the final system prompt, including injected context from files if available.'''
        parts: list[str] = list(self._sections) # 深复制一份，避免修改原始列表
        injected = self._load_context_file()
        if injected:
            parts.append(injected)
        return "\n\n".join(parts)

    def _load_context_file(self) -> str:
        ''' Check for AGENTS.md or CLAUDE.md in the work directory and inject its content if found.'''
        if self._work_dir is None:
            return ""

        for filename in _AGENT_CONTEXT_FILES:
            candidate = self._work_dir / filename
            if not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.warning("Failed to read %s: %s", candidate, e)
                continue

            if content:
                header = f"# {filename}\n\n"
                logger.debug("Injecting %s into system prompt.", filename)
                return header + content

        return ""


def build_local_code_assistant_prompt(
    work_dir: str | Path,
    sandbox_summary: str = "",
) -> str:
    """Build the runtime system prompt for the interactive local coding assistant."""
    work_dir = Path(work_dir).resolve()
    builder = ContextBuilder(work_dir=work_dir)

    builder.add_section(
        f"You are a local coding assistant working inside {work_dir}. "
        "Use tools to inspect code, edit files through shell commands, run tests, "
        "track multi-step work, and explain your results clearly."
    )
    builder.add_section(
        "Workflow (follow this order for code changes):\n"
        "1. ANALYZE — Read the scenario/task and inspect only the most relevant files.\n"
        "2. REPRODUCE — Run the failing verification command first.\n"
        "3. FIX — Make the smallest change that solves the confirmed problem.\n"
        "4. VERIFY — Re-run the original failing command or test.\n"
        "5. FINISH — The original verification command is the primary success signal. "
        "If it passes, finish immediately. Stop calling tools and summarize the fix.\n"
        "\n"
        "Optional:\n"
        "- EXTRA CHECKS — Only if you identified a specific concrete suspected regression "
        "before running VERIFY. General curiosity is not sufficient reason."
    )
    builder.add_section(
        "Tool preferences:\n"
        "- file_edit view to read files with line numbers, file_edit replace for targeted text changes.\n"
        "- Prefer file_edit replace over shell one-liners for code edits — it handles multi-line text reliably.\n"
        "- bash for running commands, tests, and complex operations.\n"
        "- semantic_search before bash grep when you need Python symbols: list_symbols (file overview), "
        "find_symbol (cross-file name search), get_context (enclosing function/class of a line).\n"
        "- task_board for multi-step plans.\n"
        "- delegate for bounded sub-tasks with role selection: 'explorer' (code investigation, default), "
        "'reviewer' (quality/edge-case review), 'tester' (run tests and report coverage)."
    )
    builder.add_section(
        "Response contract:\n"
        "- Each step must do exactly one of two things: request tool work, or return the final answer.\n"
        "- Do not mix a long narrative with tool calls.\n"
        "- Prefer one focused tool call per step; if multiple shell actions belong together, combine them into one bash command.\n"
        "- The original verification command is the primary success signal. "
        "If it passes, finish immediately unless you identified a specific unresolved issue.\n"
        "- Only stop calling tools when you have either verified the result or clearly cannot proceed."
    )
    if sys.platform == "win32":
        builder.add_section(
            "Shell rules:\n"
            "- The `bash` tool is stateless: env vars and shell variables do NOT persist between calls.\n"
            f"- The working directory is already set to {work_dir}. No need to `cd` unless accessing paths outside it.\n"
            "- Use `file_edit` for reading and editing files. Use `bash` for running commands and tests.\n"
            "- List files: `dir /b` (flat) or `dir /s /b *.py` (recursive .py files).\n"
            "- Search text in files: `findstr /s /n \"pattern\" *.py` (not grep).\n"
            "- Do NOT use `sed -i`, `grep`, `find . -name`, `xargs`, heredocs (`cat > file <<'EOF'`), or other Unix-specific syntax.\n"
            "- Old tool outputs may be compacted. Re-run a command if exact output matters."
        )
    builder.add_section(
        "Task rules:\n"
        "- `task_board` stores persistent work items in `.tasks/` so plans survive context compression.\n"
        "- Only use task_board when 3+ files must be modified, 3+ concrete edits are required, "
        "or the work has dependency ordering.\n"
        "- Do NOT create tasks for single-file bugs or simple fixes. Just fix them directly.\n"
        "- Do NOT create tasks as a first step. Analyze and reproduce first, then decide if tasks are needed.\n"
        "- Mark tasks in progress when you start them and completed when verification is done."
    )
    if sandbox_summary.strip():
        builder.add_section("Execution environment:\n" + sandbox_summary.strip())
    return builder.build()


def truncate_output(
    text: str,
    max_chars: int = _TRUNCATE_HEAD + _TRUNCATE_TAIL,
    head: int = _TRUNCATE_HEAD,
    tail: int = _TRUNCATE_TAIL,
) -> str:
    """Trim long text to head + tail with an omission marker.
        For UI display of long tool outputs."""
    if len(text) <= max_chars:
        return text

    omitted = len(text) - head - tail
    separator = f"\n\n[... {omitted} characters omitted ...]\n\n"
    return text[:head] + separator + text[-tail:]


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap token estimate using serialized character count."""
    try:
        payload = json.dumps(messages, ensure_ascii=False, default=str) # 以 JSON 格式序列化消息列表，得到一个字符串表示
    except Exception:
        payload = str(messages)
    return max(1, len(payload) // 4)


def micro_compact_tool_messages(
    messages: list[dict[str, Any]],
    keep_recent: int = 3,
    compact_above_chars: int = 400,
) -> list[dict[str, Any]]:
    """Replace older long tool outputs with short placeholders."""
    if keep_recent < 0:
        raise ValueError("keep_recent must be >= 0")

    # --- 轻量预扫描：在原始列表上判断是否有需要 compact 的消息 ---
    tool_indexes = [
        idx for idx, msg in enumerate(messages)
        if msg.get("role") == "tool" and isinstance(msg.get("content"), str)
    ]
    if len(tool_indexes) <= keep_recent:
        return messages  # 无需 compact，直接返回原列表，跳过 deepcopy

    candidates = tool_indexes[:-keep_recent] if keep_recent > 0 else tool_indexes
    needs_compact = any(
        len(messages[idx].get("content") or "") > compact_above_chars
        for idx in candidates
    )
    if not needs_compact:
        return messages  # 候选消息均未超长，跳过 deepcopy

    # --- 需要修改，执行 deepcopy ---
    compacted = copy.deepcopy(messages)
    # 因为工具调用消息可能没有直接的工具名称，所以构建 tool_call_id 到工具名称的映射
    tool_name_map = _extract_tool_name_map(compacted)

    for idx in candidates:
        msg = compacted[idx]
        content = msg.get("content") or ""
        if len(content) <= compact_above_chars:
            continue
        tool_call_id = msg.get("tool_call_id", "")
        tool_name = tool_name_map.get(tool_call_id, "tool")
        msg["content"] = (
            f"[Compacted previous tool output from {tool_name}; "
            f"original length={len(content)} chars.]"
        )

    return compacted


def archive_messages(
    messages: list[dict[str, Any]],
    directory: str | Path,
) -> Path:
    """Persist the full message history as JSONL before summarization."""
    base_dir = Path(directory)
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"transcript_{time.time_ns()}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for msg in messages:
            handle.write(json.dumps(msg, ensure_ascii=False, default=str) + "\n")
    return path


def condense_history(
    messages: list[dict[str, Any]],
    model: Any,
    keep_last: int = 6,
    archive_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Summarize older history with an LLM and keep the most recent tail intact."""
    if len(messages) <= keep_last + 1:
        return messages

    if messages and messages[0].get("role") == "system":
        system_msg = dict(messages[0])
        history = messages[1:]
    else:
        system_msg = None
        history = list(messages)

    to_condense = history[:-keep_last] if keep_last > 0 else history
    to_keep = history[-keep_last:] if keep_last > 0 else []

    if not to_condense:
        return messages

    prompt = [
        {"role": "system", "content": _CONDENSE_SYSTEM},
        {"role": "user", "content": _format_messages_for_condensing(to_condense)},
    ]

    try:
        summary_msg = model.query(prompt)
        summary_content = summary_msg.get("content") or "(summary unavailable)"
    except Exception as e:
        logger.warning("History condensation failed: %s. Keeping original messages.", e)
        return messages

    if archive_path:
        summary_content = (
            f"{summary_content}\n\n"
            f"[Full transcript archived at: {Path(archive_path)}]"
        )

    summary = {
        "role": "assistant",
        "content": f"[Condensed history summary]\n{summary_content}",
    }

    result: list[dict[str, Any]] = []
    # 拼接系统消息、总结消息和要保留的最近消息，形成新的消息列表
    if system_msg:
        result.append(system_msg)
    result.append(summary)
    result.extend(to_keep)
    return result


def _extract_tool_name_map(messages: list[dict[str, Any]]) -> dict[str, str]:
    '''Build a mapping from tool_call_id to tool name for better compaction placeholders.'''
    mapping: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue

        for tool_call in msg.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = tool_call.get("id")
            if not tool_call_id:
                continue
            if "name" in tool_call:
                mapping[tool_call_id] = tool_call["name"]
            elif "function" in tool_call:
                mapping[tool_call_id] = tool_call["function"].get("name", "tool")

    return mapping


def _format_messages_for_condensing(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""
        tool_calls = msg.get("_normalized_tool_calls") or msg.get("tool_calls") or []

        if role == "tool": # 工具输出
            lines.append(f"[tool result] {truncate_output(str(content), max_chars=800)}")
        elif tool_calls: # 调用工具
            tool_names = [
                tc.get("name") or tc.get("function", {}).get("name", "?")
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
            lines.append(f"[assistant] called tools: {tool_names}")
            if content:
                lines.append(f"  content: {truncate_output(str(content), max_chars=400)}")
        else:  # 普通消息
            lines.append(f"[{role}] {truncate_output(str(content), max_chars=800)}")

    return "\n".join(lines)
