"""
agent/models.py — 统一 LLM 适配层

对外只暴露一个稳定接口：model.query(messages) -> assistant_message

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

不负责：主 loop、prompt 拼装、工具执行、registry、streaming。
"""

import json
import logging
from typing import Any, Literal

import litellm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

SUPPORTED_PREFIXES = ("anthropic/", "deepseek/")


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

    def query(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """调用 LLM，返回归一化的 assistant message。

        Args:
            messages: OpenAI 格式的消息列表，[{"role": ..., "content": ...}, ...]

        Returns:
            统一 assistant_message dict，包含 role/content/tool_calls/usage/cost。
        """
        response = litellm.completion(
            model=self.config.model_name,
            messages=messages,
            **self.config.model_kwargs,
        )
        return self._normalize(response)

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
