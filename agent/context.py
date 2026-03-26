"""
agent/context.py — System prompt 组装与上下文工程

对外主要接口：
  - ContextBuilder：多段拼接 + AGENTS.md/CLAUDE.md 自动注入
  - ContextBuilder.build() -> str   可直接塞进 messages[0]["content"]
  - truncate_output(text, max_chars) -> str   工具输出截断（头+尾）
  - condense_history(messages, model, keep_last) -> list   LLM 历史压缩

不负责：主 loop、工具选择、模型调用调度、prompt 具体内容（那是 config/ 的事）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# AGENTS.md / CLAUDE.md 的候选文件名（优先级从高到低）
_AGENT_CONTEXT_FILES = ["AGENTS.md", "CLAUDE.md"]

# 截断时各侧保留的字符数
_TRUNCATE_HEAD = 5_000
_TRUNCATE_TAIL = 5_000


# ---------------------------------------------------------------------------
# ContextBuilder
# ---------------------------------------------------------------------------

class ContextBuilder:
    """以 section 为单位渐进组装 system prompt。

    使用方式：
        ctx = ContextBuilder(work_dir=Path("."))
        ctx.add_section("You are a helpful coding assistant.")
        ctx.add_section("Always explain your reasoning.")
        system_prompt = ctx.build()
        messages = [{"role": "system", "content": system_prompt}, ...]
    """

    def __init__(
        self,
        sections: list[str] | None = None,
        work_dir: str | Path | None = None,
    ) -> None:
        self._sections: list[str] = list(sections) if sections else []
        self._work_dir: Path | None = Path(work_dir) if work_dir else None

    def add_section(self, text: str) -> "ContextBuilder":
        """追加一个 section 片段（支持链式调用）。"""
        if text and text.strip():
            self._sections.append(text.strip())
        return self

    def build(self) -> str:
        """组装并返回完整的 system prompt 字符串。

        流程：
          1. 收集所有 section 文本
          2. 若指定了 work_dir，检测 AGENTS.md / CLAUDE.md 并注入
          3. 用双换行分隔各 section，返回拼接结果
        """
        parts: list[str] = list(self._sections)

        injected = self._load_context_file()
        if injected:
            parts.append(injected)

        return "\n\n".join(parts)

    def _load_context_file(self) -> str:
        """尝试从 work_dir 读取 AGENTS.md 或 CLAUDE.md。

        文件不存在时静默跳过，不 raise。
        """
        if self._work_dir is None:
            return ""

        for filename in _AGENT_CONTEXT_FILES:
            candidate = self._work_dir / filename
            if candidate.is_file():
                try:
                    content = candidate.read_text(encoding="utf-8").strip()
                    if content:
                        header = f"# {filename}\n\n"
                        logger.debug("Injecting %s into system prompt.", filename)
                        return header + content
                except Exception as e:
                    logger.warning("Failed to read %s: %s", candidate, e)

        return ""


# ---------------------------------------------------------------------------
# 工具输出截断
# ---------------------------------------------------------------------------

def truncate_output(
    text: str,
    max_chars: int = _TRUNCATE_HEAD + _TRUNCATE_TAIL,
    head: int = _TRUNCATE_HEAD,
    tail: int = _TRUNCATE_TAIL,
) -> str:
    """截断过长的工具输出，保留头尾各若干字符。

    输出长度 <= max_chars 时原样返回。
    超出时返回 head 个字符 + 省略提示 + tail 个字符。

    Args:
        text:      原始输出字符串。
        max_chars: 触发截断的阈值。
        head:      保留前面的字符数。
        tail:      保留末尾的字符数。
    """
    if len(text) <= max_chars:
        return text

    omitted = len(text) - head - tail
    separator = f"\n\n[... {omitted} characters omitted ...]\n\n"
    return text[:head] + separator + text[-tail:]


# ---------------------------------------------------------------------------
# 历史压缩（轻量 condenser）
# ---------------------------------------------------------------------------

_CONDENSE_SYSTEM = (
    "You are a concise summarizer. "
    "The user will give you a sequence of conversation messages. "
    "Summarize them into a single, compact assistant message that preserves all "
    "key facts, decisions, and file changes. Be brief but complete."
)


def condense_history(
    messages: list[dict[str, Any]],
    model: Any,
    keep_last: int = 6,
) -> list[dict[str, Any]]:
    """用 LLM 把旧消息压缩成一条摘要，保留最近 keep_last 条消息原样。

    Args:
        messages:  完整消息历史（含 system message）。
        model:     LLMModel 实例，需暴露 query(messages)。
        keep_last: 末尾保留的消息数量（不压缩）。

    Returns:
        压缩后的消息列表：
          messages[0] (system, 若有) + [summary_message] + messages[-keep_last:]
    """
    if len(messages) <= keep_last + 1:
        return messages  # 不需要压缩

    # 分离 system message
    if messages and messages[0].get("role") == "system":
        system_msg = messages[0]
        history = messages[1:]
    else:
        system_msg = None
        history = messages

    to_condense = history[:-keep_last] if keep_last > 0 else history
    to_keep = history[-keep_last:] if keep_last > 0 else []

    if not to_condense:
        return messages

    # 把待压缩消息转成可读文本
    condensed_input = _format_messages_for_condensing(to_condense)
    prompt = [
        {"role": "system", "content": _CONDENSE_SYSTEM},
        {"role": "user", "content": condensed_input},
    ]

    try:
        summary_msg = model.query(prompt)
        summary_content = summary_msg.get("content") or "(summary unavailable)"
    except Exception as e:
        logger.warning("History condensation failed: %s. Keeping original messages.", e)
        return messages

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


def _format_messages_for_condensing(messages: list[dict[str, Any]]) -> str:
    """把消息列表格式化为文本，供 LLM 压缩。"""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""
        tool_calls = msg.get("_normalized_tool_calls") or msg.get("tool_calls") or []

        if role == "tool":
            lines.append(f"[tool result] {content[:500]}")
        elif tool_calls:
            tool_names = [
                tc.get("name") or tc.get("function", {}).get("name", "?")
                for tc in tool_calls
            ]
            lines.append(f"[assistant] called tools: {tool_names}")
            if content:
                lines.append(f"  content: {content[:200]}")
        else:
            lines.append(f"[{role}] {content[:500]}")

    return "\n".join(lines)
