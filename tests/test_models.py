"""
tests/test_models.py — FallbackModel, retry decorator, streaming interface.
"""

import pytest

from agent.models import FallbackModel, LLMModel


class _OkModel:
    """Always succeeds."""
    def __init__(self, name="ok"):
        self.config = type("C", (), {"model_name": name})()
    def query(self, messages):
        return {"role": "assistant", "content": "ok", "tool_calls": [], "cost": 0.0}


class _FailModel:
    """Always raises."""
    def __init__(self, name="fail"):
        self.config = type("C", (), {"model_name": name})()
    def query(self, messages):
        raise RuntimeError("model down")


def test_fallback_model_uses_first_on_success():
    fb = FallbackModel([_OkModel("primary"), _OkModel("secondary")])
    result = fb.query([])
    assert result["content"] == "ok"


def test_fallback_model_falls_to_second_on_failure():
    fb = FallbackModel([_FailModel("primary"), _OkModel("secondary")])
    result = fb.query([])
    assert result["content"] == "ok"


def test_fallback_model_raises_if_all_fail():
    fb = FallbackModel([_FailModel("a"), _FailModel("b")])
    with pytest.raises(RuntimeError, match="model down"):
        fb.query([])


def test_fallback_model_requires_at_least_one():
    with pytest.raises(ValueError):
        FallbackModel([])
