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
    assert "primary success signal" in prompt
    assert "sandbox_mode=workspace-write" in prompt


def test_build_prompt_has_explicit_workflow_steps(tmp_path):
    prompt = build_local_code_assistant_prompt(work_dir=tmp_path)

    assert "ANALYZE" in prompt
    assert "REPRODUCE" in prompt
    assert "VERIFY" in prompt
    assert "FINISH" in prompt
    assert "Workflow" in prompt
    # EDGE CASES removed as mandatory step; extra checks are optional
    assert "EXTRA CHECKS" in prompt
    assert "Optional" in prompt
    assert "primary success signal" in prompt
    assert "General curiosity" in prompt


def test_build_prompt_has_shell_edit_examples(tmp_path):
    import sys
    prompt = build_local_code_assistant_prompt(work_dir=tmp_path)

    if sys.platform == "win32":
        assert "python -c" in prompt
        assert "Do NOT use" in prompt
    else:
        assert "sed -i" in prompt
        assert "cat >" in prompt
    assert "stateless" in prompt.lower()


def test_build_prompt_windows_no_sed(tmp_path, monkeypatch):
    import agent.context
    monkeypatch.setattr(agent.context.sys, "platform", "win32")
    prompt = build_local_code_assistant_prompt(work_dir=tmp_path)

    # sed -i should only appear in the "Do NOT use" warning, not as an instruction
    assert "Do NOT use" in prompt
    assert "Targeted edit: `sed" not in prompt
    assert "python -c" in prompt
    # Windows-specific alternatives should be present
    assert "dir /b" in prompt
    assert "findstr" in prompt
    # Unix-specific commands should be forbidden
    assert "find . -name" in prompt  # mentioned in "Do NOT use" list
    assert "xargs" in prompt  # mentioned in "Do NOT use" list


def test_build_prompt_unix_has_sed(tmp_path, monkeypatch):
    import agent.context
    monkeypatch.setattr(agent.context.sys, "platform", "linux")
    prompt = build_local_code_assistant_prompt(work_dir=tmp_path)

    assert "sed -i" in prompt


def test_context_builder_from_yaml(tmp_path):
    yaml_content = (
        'version: "test"\n'
        'name: "test-prompt"\n'
        'sections:\n'
        '  role: |\n'
        '    You are a helper in {work_dir}.\n'
        '  rules: |\n'
        '    Do one thing per step.\n'
    )
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    builder = ContextBuilder.from_yaml(yaml_path, work_dir=tmp_path)
    prompt = builder.build()

    assert str(tmp_path) in prompt
    assert "Do one thing per step" in prompt


def test_context_builder_from_yaml_with_sandbox(tmp_path):
    yaml_content = (
        'version: "test"\n'
        'sections:\n'
        '  role: |\n'
        '    Hello.\n'
    )
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    builder = ContextBuilder.from_yaml(yaml_path, work_dir=tmp_path, sandbox_summary="mode=test")
    prompt = builder.build()

    assert "Hello" in prompt
    assert "mode=test" in prompt


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
    # Bug 1 secondary: condensed summary should NOT have empty tool_calls
    assert "tool_calls" not in condensed[1]


def test_build_prompt_task_rules_conservative(tmp_path):
    """Task rules should discourage task_board for trivial fixes."""
    prompt = build_local_code_assistant_prompt(work_dir=tmp_path)
    assert "3+" in prompt
    assert "single-file" in prompt or "single-edit" in prompt


def test_from_yaml_skips_wrong_platform_shell_rules(tmp_path, monkeypatch):
    """Bug 4: from_yaml skips shell_rules_unix on win32."""
    import agent.context
    monkeypatch.setattr(agent.context.sys, "platform", "win32")

    yaml_content = (
        'version: "test"\n'
        'sections:\n'
        '  role: |\n'
        '    Hello.\n'
        '  shell_rules_unix: |\n'
        '    Use sed -i for edits.\n'
        '  shell_rules_win32: |\n'
        '    Use python -c for edits.\n'
    )
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")

    builder = ContextBuilder.from_yaml(yaml_path, work_dir=tmp_path)
    prompt = builder.build()

    assert "python -c" in prompt
    assert "sed -i" not in prompt
