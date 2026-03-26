"""
tests/conftest.py — 共享 pytest fixtures

设计原则：
  - 所有 fixture 均离线，不发真实 API 请求
  - make_model(responses) 按序返回预设 assistant_message（支持 tool call 场景）
  - recording_executor 记录调用历史，便于断言工具被正确调用
  - tmp_py_file 创建有生命周期管理的临时 Python 文件
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# assistant_message 构建辅助
# ---------------------------------------------------------------------------

def text_response(content: str, cost: float = 0.001) -> dict[str, Any]:
    """构建文本回复（无 tool calls）的 assistant_message。"""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "cost": cost,
    }


def tool_call_response(
    tool_name: str,
    arguments: dict[str, Any],
    call_id: str = "tc_001",
    cost: float = 0.001,
) -> dict[str, Any]:
    """构建包含单个工具调用的 assistant_message（归一化格式，兼容 core.py fallback）。"""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "name": tool_name, "arguments": arguments}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        "cost": cost,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_model():
    """工厂 fixture：接收预设响应列表，返回按序回复的 mock model。

    用法：
        model = make_model([
            tool_call_response("bash", {"command": "ls"}),
            text_response("Done."),
        ])
    """
    def _factory(responses: list[dict[str, Any]]):
        class _MockModel:
            def __init__(self, resp):
                self._responses = iter(resp)

            def query(self, messages):
                try:
                    return next(self._responses)
                except StopIteration:
                    # 默认：超出预设回复时返回文本完成
                    return text_response("(no more responses)")

        return _MockModel(responses)

    return _factory


@pytest.fixture
def recording_executor():
    """记录工具调用历史的 tool_executor callable。

    属性：
        .calls  → list of {"name": str, "arguments": dict}
        .return_value → 下次调用的返回值（默认 "ok"，可修改）

    用法：
        agent = Agent(model, tool_executor=recording_executor)
        assert recording_executor.calls[0]["name"] == "bash"
    """
    calls = []
    return_value_container = {"value": "ok"}

    def _executor(name: str, arguments: dict) -> str:
        calls.append({"name": name, "arguments": dict(arguments)})
        return return_value_container["value"]

    _executor.calls = calls
    _executor.return_value = return_value_container
    return _executor


@pytest.fixture
def tmp_py_file(tmp_path):
    """返回一个在 tmp_path 下创建 .py 文件的工厂。

    用法：
        path = tmp_py_file("def foo():\n    return 1\n")
        assert path.suffix == ".py"
    """
    created = []

    def _factory(content: str, filename: str = "test_file.py") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        created.append(p)
        return p

    return _factory
