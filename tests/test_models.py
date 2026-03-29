"""
tests/test_models.py — FallbackModel, retry decorator, streaming interface, sanitizer.
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


# ---------------------------------------------------------------------------
# Bug 1: _sanitize_messages
# ---------------------------------------------------------------------------

def test_sanitize_removes_empty_tool_calls():
    msgs = [
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]
    cleaned = LLMModel._sanitize_messages(msgs)
    assert "tool_calls" not in cleaned[0]


def test_sanitize_preserves_nonempty_tool_calls():
    tc = [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]
    msgs = [
        {"role": "assistant", "content": None, "tool_calls": tc},
    ]
    cleaned = LLMModel._sanitize_messages(msgs)
    assert cleaned[0]["tool_calls"] == tc


def test_sanitize_strips_internal_fields():
    msgs = [
        {
            "role": "assistant",
            "content": "hi",
            "tool_calls": [],
            "_normalized_tool_calls": [{"id": "c1", "name": "bash", "arguments": {}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "cost": 0.001,
        },
    ]
    cleaned = LLMModel._sanitize_messages(msgs)
    assert "_normalized_tool_calls" not in cleaned[0]
    assert "usage" not in cleaned[0]
    assert "cost" not in cleaned[0]
    # Empty tool_calls also removed
    assert "tool_calls" not in cleaned[0]


# ---------------------------------------------------------------------------
# Bug 2: StreamingModelWrapper error handling
# ---------------------------------------------------------------------------

def test_streaming_wrapper_fallback_on_connection_error():
    """Transport error before any output → fallback to non-streaming."""
    from agent.app import StreamingModelWrapper

    class _StreamFailModel:
        def query(self, messages):
            return {"role": "assistant", "content": "non-stream ok", "cost": 0.0}
        def query_stream(self, messages):
            raise ConnectionError("stream broken")

    class _NullUI:
        def print_stream_chunk(self, chunk): pass
        def end_stream(self): pass

    wrapper = StreamingModelWrapper(_StreamFailModel(), _NullUI())
    result = wrapper.query([])
    assert result["content"] == "non-stream ok"


def test_streaming_wrapper_propagates_api_errors():
    """Provider errors (not transport) must propagate, not fallback."""
    from agent.app import StreamingModelWrapper

    class _BadRequestModel:
        def query(self, messages):
            return {"role": "assistant", "content": "should not reach", "cost": 0.0}
        def query_stream(self, messages):
            raise ValueError("400 Bad Request")

    class _NullUI:
        def print_stream_chunk(self, chunk): pass
        def end_stream(self): pass

    wrapper = StreamingModelWrapper(_BadRequestModel(), _NullUI())
    with pytest.raises(ValueError, match="400"):
        wrapper.query([])


def test_streaming_wrapper_raises_after_partial_output():
    """If chunks already printed, transport error must re-raise (not double-fire)."""
    from agent.app import StreamingModelWrapper

    class _PartialStreamModel:
        def query(self, messages):
            return {"role": "assistant", "content": "should not reach", "cost": 0.0}
        def query_stream(self, messages):
            final_msg = {"role": "assistant", "content": None, "cost": 0.0}
            def _chunks():
                yield "partial"
                raise ConnectionError("mid-stream break")
            return final_msg, _chunks()

    printed = []

    class _TrackingUI:
        def print_stream_chunk(self, chunk):
            printed.append(chunk)
        def end_stream(self): pass

    wrapper = StreamingModelWrapper(_PartialStreamModel(), _TrackingUI())
    with pytest.raises(ConnectionError):
        wrapper.query([])
    assert printed == ["partial"]
