"""
tests/test_middleware.py -- middleware guardrails and compaction.
"""

from pathlib import Path
from types import SimpleNamespace

from agent.middleware import (
    BashSafetyMiddleware,
    ContextCompactionMiddleware,
    Middleware,
    SandboxAwarenessMiddleware,
    SandboxInfo,
    assess_bash_command,
    detect_sandbox,
)


class _SummaryModel:
    def query(self, messages):
        return {"role": "assistant", "content": "summary", "tool_calls": [], "cost": 0.0}


def _sandbox(tmp_path: Path, mode: str = "workspace-write") -> SandboxInfo:
    return SandboxInfo(
        mode=mode,
        source="test",
        shell="powershell",
        workspace_root=tmp_path,
        workspace_writable=True,
        temp_writable=True,
    )


def test_detect_sandbox_prefers_env_signal(tmp_path):
    sandbox = detect_sandbox(
        work_dir=tmp_path,
        env={"CODEX_SANDBOX_MODE": "danger-full-access"},
    )

    assert sandbox.mode == "danger-full-access"
    assert sandbox.source == "env:CODEX_SANDBOX_MODE"


def test_assess_bash_command_blocks_destructive_patterns(tmp_path):
    verdict = assess_bash_command(
        "git reset --hard HEAD~1",
        sandbox=_sandbox(tmp_path),
    )

    assert not verdict.allowed
    assert "git reset" in verdict.reason


def test_bash_safety_middleware_allows_safe_command(tmp_path):
    calls = []

    def executor(name, arguments):
        calls.append((name, arguments))
        return "ok"

    guarded = BashSafetyMiddleware(executor, sandbox_info=_sandbox(tmp_path))
    output = guarded("bash", {"command": "python -c \"print('hello')\""})

    assert output == "ok"
    assert calls == [("bash", {"command": "python -c \"print('hello')\""})]


def test_bash_safety_middleware_blocks_high_risk_command(tmp_path):
    guarded = BashSafetyMiddleware(lambda *_: "should not run", sandbox_info=_sandbox(tmp_path))

    output = guarded("bash", {"command": "rm -rf /"})

    assert "Blocked high-risk bash command" in output


def test_sandbox_awareness_injects_notice_once(tmp_path):
    middleware = SandboxAwarenessMiddleware(_sandbox(tmp_path))
    agent = SimpleNamespace(messages=[{"role": "system", "content": "Base prompt"}])

    middleware.pre_step(agent)
    middleware.pre_step(agent)

    content = agent.messages[0]["content"]
    assert content.count("[Sandbox detection]") == 1
    assert "Base prompt" in content


def test_context_compaction_replaces_old_tool_output(tmp_path):
    middleware = ContextCompactionMiddleware(
        summary_model=_SummaryModel(),
        transcript_dir=tmp_path / ".transcripts",
        keep_recent_tool_results=1,
        compact_above_chars=20,
        condense_threshold_tokens=999_999,
    )
    agent = SimpleNamespace(
        messages=[
            {"role": "assistant", "tool_calls": [{"id": "c1", "name": "bash", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "A" * 120},
            {"role": "assistant", "tool_calls": [{"id": "c2", "name": "task_board", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "c2", "content": "B" * 140},
        ],
        n_steps=0,
    )

    middleware.pre_step(agent)

    assert "Compacted previous tool output from bash" in agent.messages[1]["content"]
    assert agent.messages[3]["content"] == "B" * 140


def test_context_compaction_condenses_when_threshold_hit(tmp_path):
    middleware = ContextCompactionMiddleware(
        summary_model=_SummaryModel(),
        transcript_dir=tmp_path / ".transcripts",
        condense_threshold_tokens=1,
        keep_last=2,
    )
    agent = SimpleNamespace(
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
            {"role": "assistant", "content": "four"},
        ],
        n_steps=0,
    )

    middleware.pre_step(agent)

    assert agent.messages[1]["role"] == "assistant"
    assert "[Condensed history summary]" in agent.messages[1]["content"]
    transcript_files = list((tmp_path / ".transcripts").glob("*.jsonl"))
    assert len(transcript_files) == 1


def test_middleware_pre_post_called(make_model):
    from agent.core import Agent
    from tests.conftest import text_response

    log = []

    class LogMiddleware(Middleware):
        def pre_step(self, agent):
            log.append("pre")

        def post_step(self, agent):
            log.append("post")

    model = make_model([text_response("done")])
    agent = Agent(model, middlewares=[LogMiddleware()])
    agent.run([{"role": "user", "content": "hi"}])

    assert log == ["pre", "post"]


def test_reflection_middleware_injects_once(make_model):
    """ReflectionMiddleware injects self-critique prompt once, then allows finish."""
    from agent.core import Agent
    from agent.middleware import ReflectionMiddleware
    from tests.conftest import text_response

    # Step 1: text (triggers reflection injection) → Step 2: text (finishes)
    model = make_model([
        text_response("I think I'm done."),
        text_response("Confidence 5. All good."),
    ])
    mw = ReflectionMiddleware(max_reflections=1)
    agent = Agent(model, middlewares=[mw])
    result = agent.run([{"role": "user", "content": "fix bug"}])

    assert result["status"] == "Submitted"
    assert result["total_steps"] == 2
    # Check that reflection prompt was injected
    user_msgs = [m for m in agent.messages if m.get("role") == "user"]
    assert any("confidence" in m.get("content", "").lower() for m in user_msgs)
