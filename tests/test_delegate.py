"""
tests/test_delegate.py — agent/tools/delegate.py 单测（全离线）

覆盖场景：
  - 缺少 task 参数 → success=False
  - 子 agent 正常完成（Submitted）→ output 是 final_content，success=True
  - 子 agent LimitsExceeded → success=False，状态摘要在 output
  - 父子消息历史隔离：子 agent 只收到 task 消息，不共享父 agent 历史
  - context 参数附加到 task 内容中
"""

import pytest

from agent.tools.delegate import DelegateTool
from tests.conftest import text_response, tool_call_response


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _simple_executor(name, arguments):
    return "ok"


class _CapturingModel:
    """记录收到的 messages 列表，返回预设响应。"""

    def __init__(self, response=None):
        self.received: list[list[dict]] = []
        self._response = response or text_response("child done")

    def query(self, messages):
        self.received.append(list(messages))
        return self._response


# ---------------------------------------------------------------------------
# 缺少 task
# ---------------------------------------------------------------------------

def test_missing_task_returns_failure(make_model):
    """task 参数缺失 → success=False，error 含 'task'。"""
    model = make_model([text_response("hi")])
    tool = DelegateTool(model=model)

    obs = tool.execute({})

    assert not obs.success
    assert obs.error
    assert "task" in obs.error.lower()


def test_empty_task_returns_failure(make_model):
    """task 为空字符串 → success=False。"""
    model = make_model([text_response("hi")])
    tool = DelegateTool(model=model)

    obs = tool.execute({"task": "   "})

    assert not obs.success


# ---------------------------------------------------------------------------
# 子 agent 正常完成
# ---------------------------------------------------------------------------

def test_successful_delegation(make_model):
    """子 agent Submitted + final_content → output=final_content，success=True。"""
    model = make_model([text_response("Analysis complete.")])
    tool = DelegateTool(model=model)

    obs = tool.execute({"task": "Summarize the project."})

    assert obs.success
    assert "Analysis complete." in obs.output


# ---------------------------------------------------------------------------
# 子 agent LimitsExceeded
# ---------------------------------------------------------------------------

def test_limits_exceeded_returns_status_summary(make_model):
    """子 agent step_limit=1 触发 LimitsExceeded → success=False，output 含 'LimitsExceeded'。"""
    model = make_model([
        tool_call_response("bash", {"command": "x"}, call_id="c1"),
        tool_call_response("bash", {"command": "x"}, call_id="c2"),
    ])
    tool = DelegateTool(
        model=model,
        sub_tool_executor=_simple_executor,
        step_limit=1,
    )

    obs = tool.execute({"task": "run something"})

    assert not obs.success
    assert "LimitsExceeded" in obs.output


# ---------------------------------------------------------------------------
# 消息历史隔离
# ---------------------------------------------------------------------------

def test_child_history_isolated_from_parent():
    """子 agent 只收到 task 消息，不包含父 agent 的历史。"""
    cap = _CapturingModel()
    tool = DelegateTool(model=cap)

    obs = tool.execute({"task": "do something"})

    assert obs.success
    # 子 agent 第一次 query 时应有 system prompt + user task
    first_query_messages = cap.received[0]
    assert len(first_query_messages) == 2
    assert first_query_messages[0]["role"] == "system"
    assert first_query_messages[1]["role"] == "user"
    assert first_query_messages[1]["content"] == "do something"


# ---------------------------------------------------------------------------
# context 参数
# ---------------------------------------------------------------------------

def test_context_appended_to_task():
    """传入 context → 子 agent 的 user 消息包含 task 和 context。"""
    cap = _CapturingModel()
    tool = DelegateTool(model=cap)

    tool.execute({"task": "Analyze files.", "context": "Focus on /tmp/src"})

    user_content = cap.received[0][1]["content"]
    assert "Analyze files." in user_content
    assert "Focus on /tmp/src" in user_content


# ---------------------------------------------------------------------------
# role 参数
# ---------------------------------------------------------------------------

def test_role_parameter_sets_system_prompt():
    """role='reviewer' → 子 agent 收到 reviewer 专属 system prompt。"""
    cap = _CapturingModel()
    tool = DelegateTool(model=cap)

    tool.execute({"task": "Review the fix.", "role": "reviewer"})

    # First message should be system with reviewer prompt
    system_msg = cap.received[0][0]
    assert system_msg["role"] == "system"
    assert "code reviewer" in system_msg["content"].lower()


def test_role_default_is_explorer():
    """不指定 role → 默认 explorer。"""
    cap = _CapturingModel()
    tool = DelegateTool(model=cap)

    obs = tool.execute({"task": "Look around."})

    system_msg = cap.received[0][0]
    assert system_msg["role"] == "system"
    assert "explorer" in system_msg["content"].lower()

    # Output is prefixed with role
    assert "[explorer]" in obs.output
