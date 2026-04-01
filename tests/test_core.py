"""
tests/test_core.py — agent/core.py 单测（全离线，无真实 API）

覆盖场景：
  - 单轮文本回复 → Submitted
  - 多轮 tool call → tool result → 文本 → Submitted
  - step_limit 触发 LimitsExceeded
  - cost_limit 触发 LimitsExceeded
  - tool_executor=None + tool_calls → FormatError
  - trajectory 成功时写入 step + exit 条目
  - trajectory 失败时（LimitsExceeded）仍写入 exit 条目
  - middleware pre_step / post_step 顺序
"""

import json

import pytest

from agent.core import Agent, FormatError, LimitsExceeded, Submitted
from tests.conftest import text_response, tool_call_response


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_jsonl(path):
    """读取 JSONL 文件，返回条目列表。"""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_single_round_submitted(make_model):
    """无 tool_calls 的文本回复 → run() 返回 Submitted；messages 长度正确。"""
    model = make_model([text_response("Done.")])
    agent = Agent(model)

    initial = [{"role": "user", "content": "Hello"}]
    result = agent.run(initial)

    assert result["status"] == "Submitted"
    assert result["total_steps"] == 1
    # initial user + assistant
    assert len(agent.messages) == 2
    assert agent.messages[-1]["role"] == "assistant"
    assert agent.messages[-1]["content"] == "Done."


def test_multi_round_with_tools(make_model, recording_executor):
    """tool call → tool result → text 三轮，messages 线性 append，status Submitted。"""
    model = make_model([
        tool_call_response("bash", {"command": "ls"}, call_id="c1"),
        text_response("All done."),
    ])
    agent = Agent(model, tool_executor=recording_executor)

    result = agent.run([{"role": "user", "content": "List files"}])

    assert result["status"] == "Submitted"
    assert result["total_steps"] == 2
    # user + assistant(tool_call) + tool_result + assistant(text)
    assert len(agent.messages) == 4
    assert recording_executor.calls[0]["name"] == "bash"
    assert recording_executor.calls[0]["arguments"] == {"command": "ls"}


def test_step_limit_exceeded(make_model, recording_executor):
    """step_limit=1 → 第 2 步 _check_limits 触发 LimitsExceeded。"""
    # 第 1 步返回 tool_call（让 loop 继续），第 2 步会因 step_limit 提前终止
    model = make_model([
        tool_call_response("bash", {"command": "echo hi"}, call_id="c1"),
        tool_call_response("bash", {"command": "echo hi"}, call_id="c2"),
    ])
    agent = Agent(model, tool_executor=recording_executor, step_limit=1)

    result = agent.run([{"role": "user", "content": "start"}])

    assert result["status"] == "LimitsExceeded"
    assert result["total_steps"] == 1


def test_cost_limit_exceeded(make_model, recording_executor):
    """累计 cost 超限 → LimitsExceeded。"""
    # 每步 cost=0.001，cost_limit=0.001 → 第 1 步后 total_cost=0.001，
    # 第 2 步 _check_limits 检测 0.001 >= 0.001 → 触发
    model = make_model([
        tool_call_response("bash", {"command": "x"}, cost=0.001),
        tool_call_response("bash", {"command": "x"}, cost=0.001),
    ])
    agent = Agent(model, tool_executor=recording_executor, cost_limit=0.001)

    result = agent.run([{"role": "user", "content": "start"}])

    assert result["status"] == "LimitsExceeded"
    assert result["total_steps"] == 1


def test_format_error_no_executor(make_model):
    """tool_executor=None + tool_call → 立即 FormatError，不重试。"""
    model = make_model([
        tool_call_response("bash", {"command": "ls"}, call_id="c1"),
    ])
    agent = Agent(model, tool_executor=None)

    result = agent.run([{"role": "user", "content": "run something"}])

    assert result["status"] == "FormatError"
    assert agent.n_steps == 1


def test_trajectory_saved_on_success(make_model, recording_executor, tmp_path):
    """成功完成时 trajectory JSONL 存在 step 条目和 exit 条目。"""
    traj_path = tmp_path / "traj.jsonl"
    model = make_model([
        tool_call_response("bash", {"command": "ls"}, call_id="c1"),
        text_response("Done."),
    ])
    agent = Agent(
        model,
        tool_executor=recording_executor,
        trajectory_path=traj_path,
    )
    result = agent.run([{"role": "user", "content": "go"}])

    assert result["status"] == "Submitted"
    assert traj_path.exists()

    entries = _read_jsonl(traj_path)
    # 有 step 条目（含 "step" key）和 exit 条目（含 "exit" key）
    step_entries = [e for e in entries if "step" in e]
    exit_entries = [e for e in entries if "exit" in e]
    assert len(step_entries) == 2  # 2 steps
    assert len(exit_entries) == 1
    assert exit_entries[0]["exit"]["status"] == "Submitted"


def test_trajectory_saved_on_failure(make_model, recording_executor, tmp_path):
    """LimitsExceeded 时 trajectory 仍落盘，exit 条目状态为 LimitsExceeded。"""
    traj_path = tmp_path / "traj_fail.jsonl"
    model = make_model([
        tool_call_response("bash", {"command": "x"}, call_id="c1"),
        tool_call_response("bash", {"command": "x"}, call_id="c2"),
    ])
    agent = Agent(
        model,
        tool_executor=recording_executor,
        step_limit=1,
        trajectory_path=traj_path,
    )
    result = agent.run([{"role": "user", "content": "go"}])

    assert result["status"] == "LimitsExceeded"
    assert traj_path.exists()

    entries = _read_jsonl(traj_path)
    exit_entries = [e for e in entries if "exit" in e]
    assert len(exit_entries) == 1
    assert exit_entries[0]["exit"]["status"] == "LimitsExceeded"


def test_trajectory_includes_timing_fields(make_model, recording_executor, tmp_path):
    """Trajectory entries include wall_time_ms and tool_names fields."""
    traj_path = tmp_path / "traj_timing.jsonl"
    model = make_model([
        tool_call_response("bash", {"command": "ls"}, call_id="c1"),
        text_response("Done."),
    ])
    agent = Agent(
        model,
        tool_executor=recording_executor,
        trajectory_path=traj_path,
    )
    agent.run([{"role": "user", "content": "go"}])

    entries = _read_jsonl(traj_path)
    step_entries = [e for e in entries if "step" in e]
    assert len(step_entries) == 2

    # First step has tool call
    assert "wall_time_ms" in step_entries[0]
    assert isinstance(step_entries[0]["wall_time_ms"], (int, float))
    assert step_entries[0]["tool_names"] == ["bash"]

    # Second step has no tool calls
    assert step_entries[1]["tool_names"] == []


def test_middleware_hooks_order(make_model, recording_executor):
    """pre_step 在 query 前，post_step 在 dispatch 后；均被调用。"""
    from agent.middleware import Middleware

    order = []

    class TrackingMiddleware(Middleware):
        def pre_step(self, agent):
            # pre_step 时 n_steps 还未递增
            order.append(("pre", agent.n_steps))

        def post_step(self, agent):
            # post_step 时 dispatch 已完成，messages 已更新
            order.append(("post", agent.n_steps, len(agent.messages)))

    model = make_model([text_response("hi")])
    mw = TrackingMiddleware()
    agent = Agent(model, middlewares=[mw])
    agent.run([{"role": "user", "content": "go"}])

    assert order[0] == ("pre", 0)    # pre_step 时 n_steps=0（尚未递增）
    # post_step: n_steps=1，messages=[user, assistant]
    assert order[1][0] == "post"
    assert order[1][1] == 1
    assert order[1][2] == 2
