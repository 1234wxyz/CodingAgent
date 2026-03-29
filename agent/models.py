"""
agent/models.py — 统一 LLM 适配层

对外暴露两个接口：
  - model.query(messages) -> assistant_message         # 阻塞式
  - model.query_stream(messages) -> Iterator[chunk]    # 流式

支持模型前缀：
  - anthropic/claude-*
  - deepseek/*

返回统一 assistant_message 结构：
  {
    "role": "assistant",
    "content": str | None,
    "tool_calls": OpenAI 格式（litellm 历史 round-trip 用），
    "_normalized_tool_calls": [{"id": str, "name": str, "arguments": dict}],
    "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
    "cost": float,
  }

  tool_calls 保持 litellm/OpenAI 原始格式，存入消息历史后可再次传给 litellm。
  _normalized_tool_calls 是 core.py dispatch 用的归一化格式。

不负责：主 loop、prompt 拼装、工具执行、registry。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator, Literal

import litellm
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

SUPPORTED_PREFIXES = ("anthropic/", "deepseek/")

# Keys that LLM providers actually accept in message dicts.
_PROVIDER_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})


class ModelConfig(BaseModel):
    model_name: str
    model_kwargs: dict[str, Any] = {}
    cost_tracking: Literal["default", "ignore_errors"] = "default"


class LLMModel:
    """轻量 LLM 适配器，封装 litellm，对外暴露 query(messages)。"""

    def __init__(
        self,
        model_name: str,
        model_kwargs: dict[str, Any] | None = None,
        cost_tracking: Literal["default", "ignore_errors"] = "default",
    ):
        if not model_name.startswith(SUPPORTED_PREFIXES):
            raise ValueError(
                f"Unsupported model: {model_name!r}. "
                f"Model name must start with one of: {SUPPORTED_PREFIXES}"
            )
        self.config = ModelConfig(
            model_name=model_name,
            model_kwargs=model_kwargs or {},
            cost_tracking=cost_tracking,
        )

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip internal fields and empty tool_calls before sending to provider."""
        cleaned = []
        for msg in messages:
            out = {k: v for k, v in msg.items() if k in _PROVIDER_KEYS}
            if "tool_calls" in out and not out["tool_calls"]:
                del out["tool_calls"]
            cleaned.append(out)
        return cleaned

    @retry(
        retry=retry_if_exception_type((
            litellm.RateLimitError,
            litellm.ServiceUnavailableError,
            litellm.Timeout,
        )),
        wait=wait_exponential(min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def query(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """调用 LLM，返回归一化的 assistant message。

        自带指数退避重试（最多 3 次），覆盖 RateLimitError / ServiceUnavailable / Timeout。

        Args:
            messages: OpenAI 格式的消息列表，[{"role": ..., "content": ...}, ...]

        Returns:
            统一 assistant_message dict，包含 role/content/tool_calls/usage/cost。
        """
        clean = self._sanitize_messages(messages)
        response = litellm.completion(
            model=self.config.model_name,
            messages=clean,
            **self.config.model_kwargs,
        )
        return self._normalize(response)

    def query_stream(
        self, messages: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], Iterator[str]]:
        """流式调用 LLM，返回 (final_message, text_chunk_iterator)。

        调用方需完整消费 iterator 才能得到最终 tool_calls/usage/cost。
        final_message 在 iterator 耗尽后自动填充完整信息。

        Returns:
            (message_holder, chunk_iter):
              - message_holder: 最终将被填充的 assistant_message dict
              - chunk_iter: 产出 text content chunks 的迭代器
        """
        clean = self._sanitize_messages(messages)
        response = litellm.completion(
            model=self.config.model_name,
            messages=clean,
            stream=True,
            stream_options={"include_usage": True},
            **self.config.model_kwargs,
        )

        # 用一个可变容器在 iterator 结束后填充完整结果
        final_msg: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": [],
            "_normalized_tool_calls": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "cost": 0.0,
        }

        def _iter_chunks() -> Iterator[str]:
            content_parts: list[str] = []
            raw_tool_calls_map: dict[int, dict[str, Any]] = {}
            last_chunk = None

            for chunk in response:
                last_chunk = chunk
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Text content
                if delta.content:
                    content_parts.append(delta.content)
                    yield delta.content

                # Streaming tool calls (accumulated by index)
                if getattr(delta, "tool_calls", None):
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in raw_tool_calls_map:
                            raw_tool_calls_map[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = raw_tool_calls_map[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if getattr(tc_delta, "function", None):
                            if tc_delta.function.name:
                                entry["function"]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["function"]["arguments"] += tc_delta.function.arguments

            # Fill final message
            final_msg["content"] = "".join(content_parts) if content_parts else None
            raw_tcs = [raw_tool_calls_map[k] for k in sorted(raw_tool_calls_map)]
            final_msg["tool_calls"] = raw_tcs

            # Normalize tool_calls
            normalized = []
            for tc in raw_tcs:
                try:
                    args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                normalized.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": args,
                })
            final_msg["_normalized_tool_calls"] = normalized

            # Extract usage from the final streaming chunk
            if last_chunk and hasattr(last_chunk, "usage") and last_chunk.usage:
                usage = last_chunk.usage
                final_msg["usage"] = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                }

            # Build synthetic ModelResponse for completion_cost
            try:
                if final_msg["usage"]["total_tokens"] > 0:
                    synthetic = litellm.ModelResponse()
                    synthetic.usage = litellm.Usage(
                        prompt_tokens=final_msg["usage"]["prompt_tokens"],
                        completion_tokens=final_msg["usage"]["completion_tokens"],
                        total_tokens=final_msg["usage"]["total_tokens"],
                    )
                    cost = litellm.completion_cost(
                        completion_response=synthetic,
                        model=self.config.model_name,
                    )
                    final_msg["cost"] = float(cost) if cost else 0.0
            except Exception:
                final_msg["cost"] = 0.0

        return final_msg, _iter_chunks()

    def _normalize(self, response: Any) -> dict[str, Any]:
        """将 litellm 响应归一化为项目内部统一格式。

        返回两种 tool_calls 表示：
          - tool_calls: OpenAI 原始格式，用于存入消息历史（litellm round-trip）
          - _normalized_tool_calls: [{id, name, arguments}]，用于 core.py dispatch
        """
        choice = response.choices[0]
        message = choice.message

        content = message.content
        raw_tool_calls = self._extract_raw_tool_calls(message)
        normalized_tool_calls = self._extract_tool_calls(message)
        usage = self._extract_usage(response)
        cost = self._calculate_cost(response)

        return {
            "role": "assistant",
            "content": content,
            "tool_calls": raw_tool_calls,              # OpenAI 格式，供 litellm 消费
            "_normalized_tool_calls": normalized_tool_calls,  # 归一化格式，供 dispatch
            "usage": usage,
            "cost": cost,
        }

    def _extract_raw_tool_calls(self, message: Any) -> list[dict[str, Any]]:
        """提取 litellm/OpenAI 原始格式的 tool calls（arguments 保持 JSON 字符串）。"""
        raw = getattr(message, "tool_calls", None) or []
        result = []
        for tc in raw:
            arguments = getattr(getattr(tc, "function", None), "arguments", "") or ""
            result.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": arguments,  # 保持字符串，litellm 期望此格式
                },
            })
        return result

    def _extract_tool_calls(self, message: Any) -> list[dict[str, Any]]:
        """从 message 中提取并归一化 tool calls。"""
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        result = []
        for tc in raw_tool_calls:
            try:
                arguments = tc.function.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning("Failed to parse tool call arguments: %s", e)
                arguments = {}
            result.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": arguments,
            })
        return result

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """从响应中提取 token 使用量。"""
        usage = getattr(response, "usage", None)
        if usage is None:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }

    def _calculate_cost(self, response: Any) -> float:
        """计算本次调用费用（USD）。失败时 fallback 到 0.0。"""
        try:
            cost = litellm.completion_cost(
                completion_response=response,
                model=self.config.model_name,
            )
            return float(cost) if cost is not None else 0.0
        except Exception as e:
            if self.config.cost_tracking != "ignore_errors":
                logger.warning(
                    "Cost calculation failed for model %r: %s. "
                    "Use cost_tracking='ignore_errors' to suppress this warning.",
                    self.config.model_name,
                    e,
                )
            return 0.0


class FallbackModel:
    """多模型降级链：依次尝试，第一个成功的返回结果。

    对外暴露与 LLMModel 相同的 query(messages) 接口，core.py 无感知。
    降级事件通过 logger.warning 记录，可在 trajectory 中追溯。

    用法：
        primary = LLMModel("deepseek/deepseek-chat", ...)
        fallback = LLMModel("deepseek/deepseek-reasoner", ...)
        model = FallbackModel([primary, fallback])
    """

    def __init__(self, models: list[LLMModel]) -> None:
        if not models:
            raise ValueError("FallbackModel requires at least one model.")
        self._models = models

    def query(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        last_error: Exception | None = None
        for i, model in enumerate(self._models):
            try:
                result = model.query(messages)
                if i > 0:
                    logger.warning(
                        "FallbackModel: succeeded on model #%d (%s) after %d failure(s).",
                        i, model.config.model_name, i,
                    )
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "FallbackModel: model #%d (%s) failed: %s. Trying next.",
                    i, model.config.model_name, e,
                )
        raise last_error  # type: ignore[misc]
