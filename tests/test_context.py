"""
tests/test_context.py -- context assembly and compaction helpers.
"""

from pathlib import Path

from agent.context import (
    ContextBuilder,
    archive_messages,
    build_local_code_assistant_prompt,
    condense_history,
    micro_compact_tool_messages,
)


class _SummaryModel:
    def __init__(self, content: str = "summary ready") -> None:
        self.content = content
        self.calls = []

    def query(self, messages):
        self.calls.append(messages)
        return {"role": "assistant", "content": self.content, "tool_calls": [], "cost": 0.0}


def test_context_builder_injects_claude_file(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Repo guidance", encoding="utf-8")
    builder = ContextBuilder(work_dir=tmp_path)
    builder.add_section("Base section")

    result = builder.build()

    assert "Base section" in result
    assert "# CLAUDE.md" in result
    assert "Repo guidance" in result


def test_build_local_code_assistant_prompt_mentions_shell_first_tools(tmp_path):
    prompt = build_local_code_assistant_prompt(
        work_dir=tmp_path,
        sandbox_summary="sandbox_mode=workspace-write",
    )

    assert "There is no file_editor tool" in prompt
    assert "task_board" in prompt
    assert "semantic_search" in prompt
    assert "Each step must do exactly one of two things" in prompt
    assert "sandbox_mode=workspace-write" in prompt


def test_micro_compact_tool_messages_keeps_recent_results():
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "c1", "name": "bash", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "A" * 200},
        {"role": "assistant", "tool_calls": [{"id": "c2", "name": "semantic_search", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c2", "content": "B" * 220},
        {"role": "assistant", "tool_calls": [{"id": "c3", "name": "task_board", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c3", "content": "C" * 240},
    ]

    compacted = micro_compact_tool_messages(
        messages,
        keep_recent=1,
        compact_above_chars=20,
    )

    assert "Compacted previous tool output from bash" in compacted[1]["content"]
    assert "Compacted previous tool output from semantic_search" in compacted[3]["content"]
    assert compacted[5]["content"] == "C" * 240


def test_archive_messages_writes_jsonl(tmp_path):
    path = archive_messages(
        [{"role": "user", "content": "hello"}],
        directory=tmp_path / ".transcripts",
    )

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert '"role": "user"' in content


def test_condense_history_includes_archive_path(tmp_path):
    model = _SummaryModel("condensed summary")
    archive_path = tmp_path / "history.jsonl"
    archive_path.write_text("", encoding="utf-8")
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
        {"role": "assistant", "content": "fourth"},
    ]

    condensed = condense_history(
        messages,
        model=model,
        keep_last=2,
        archive_path=archive_path,
    )

    assert condensed[1]["role"] == "assistant"
    assert "condensed summary" in condensed[1]["content"]
    assert str(archive_path) in condensed[1]["content"]
