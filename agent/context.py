"""
agent/context.py -- system prompt assembly and reusable context helpers.

Provides:
  - ContextBuilder: compose a system prompt from sections + inject AGENTS.md / CLAUDE.md
  - build_local_code_assistant_prompt(): runtime prompt for the local coding assistant
  - truncate_output(): keep head/tail for long tool output
  - estimate_tokens(): cheap message-size heuristic
  - micro_compact_tool_messages(): shrink old tool results in-place-friendly form
  - archive_messages(): persist full message history before summarization
  - condense_history(): summarize older history with an LLM while keeping the tail
"""

from __future__ import annotations

import copy
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AGENT_CONTEXT_FILES = ["AGENTS.md", "CLAUDE.md"]
_TRUNCATE_HEAD = 5_000
_TRUNCATE_TAIL = 5_000

_CONDENSE_SYSTEM = (
    "You are a concise summarizer. "
    "The user will provide a sequence of conversation messages. "
    "Summarize them into a single compact assistant message that preserves "
    "completed work, current state, key files, pending risks, task status, "
    "and anything needed to continue safely."
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

    def build(self) -> str:
        parts: list[str] = list(self._sections)
        injected = self._load_context_file()
        if injected:
            parts.append(injected)
        return "\n\n".join(parts)

    def _load_context_file(self) -> str:
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
        "1. ANALYZE — Understand the problem scope. Read relevant files, search for symbols with semantic_search.\n"
        "2. REPRODUCE — If a bug, run the failing case first to see the exact error.\n"
        "3. FIX — Make the minimal edit needed. Use bash with inline Python or shell commands.\n"
        "4. VERIFY — Run the original failing command or test to confirm the fix.\n"
        "5. EDGE CASES — Consider and test boundary conditions.\n"
        "6. FINISH — Summarize what changed and why. Stop calling tools."
    )
    builder.add_section(
        "Tool preferences:\n"
        "- semantic_search for Python structure, bash for reading/editing/testing, "
        "task_board for multi-step plans, delegate for bounded exploration.\n"
        "- If the job spans multiple meaningful steps, multiple files, or has dependencies, "
        "create/update tasks before large edits."
    )
    builder.add_section(
        "Response contract:\n"
        "- Each step must do exactly one of two things: request tool work, or return the final answer.\n"
        "- Do not mix a long narrative with tool calls.\n"
        "- Prefer one focused tool call per step; if multiple shell actions belong together, combine them into one bash command.\n"
        "- Only stop calling tools when you have either verified the result or clearly cannot proceed."
    )
    builder.add_section(
        "Shell rules:\n"
        "- The `bash` tool is stateless: cwd, env vars, and shell variables do NOT persist between calls.\n"
        "- Combine related commands: `cd /path && command1 && command2`\n"
        "- There is no file_editor tool. Use shell commands or inline Python for file changes:\n"
        '  - Create file: `python -c "from pathlib import Path; Path(\'f.py\').write_text(\'content\')"`\n'
        "  - Create file (bash): `cat > file.py <<'EOF'\\ncontents\\nEOF`\n"
        "  - Targeted edit: `sed -i 's/old/new/g' file.py` (Unix) or inline Python for portability\n"
        '  - View with line numbers: `python -c "for i,l in enumerate(open(\'f.py\'),1): print(f\'{i:4d} {l}\', end=\'\')"`\n'
        "- Old tool outputs may be compacted. Re-run a command if exact output matters."
    )
    builder.add_section(
        "Task rules:\n"
        "- `task_board` stores persistent work items in `.tasks/` so plans survive context compression.\n"
        "- Mark tasks in progress when you start them and completed when verification is done.\n"
        "- Keep the task list lightweight and factual."
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
    """Trim long text to head + tail with an omission marker."""
    if len(text) <= max_chars:
        return text

    omitted = len(text) - head - tail
    separator = f"\n\n[... {omitted} characters omitted ...]\n\n"
    return text[:head] + separator + text[-tail:]


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap token estimate using serialized character count."""
    try:
        payload = json.dumps(messages, ensure_ascii=False, default=str)
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

    compacted = copy.deepcopy(messages)
    tool_name_map = _extract_tool_name_map(compacted)

    tool_indexes = [
        idx for idx, msg in enumerate(compacted)
        if msg.get("role") == "tool" and isinstance(msg.get("content"), str)
    ]
    if len(tool_indexes) <= keep_recent:
        return compacted

    for idx in tool_indexes[:-keep_recent]:
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
        "tool_calls": [],
    }

    result: list[dict[str, Any]] = []
    if system_msg:
        result.append(system_msg)
    result.append(summary)
    result.extend(to_keep)
    return result


def _extract_tool_name_map(messages: list[dict[str, Any]]) -> dict[str, str]:
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

        for tool_call in msg.get("_normalized_tool_calls") or []:
            if isinstance(tool_call, dict) and tool_call.get("id"):
                mapping[tool_call["id"]] = tool_call.get("name", "tool")

    return mapping


def _format_messages_for_condensing(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""
        tool_calls = msg.get("_normalized_tool_calls") or msg.get("tool_calls") or []

        if role == "tool":
            lines.append(f"[tool result] {truncate_output(str(content), max_chars=800)}")
        elif tool_calls:
            tool_names = [
                tc.get("name") or tc.get("function", {}).get("name", "?")
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
            lines.append(f"[assistant] called tools: {tool_names}")
            if content:
                lines.append(f"  content: {truncate_output(str(content), max_chars=400)}")
        else:
            lines.append(f"[{role}] {truncate_output(str(content), max_chars=800)}")

    return "\n".join(lines)
