"""
agent/tools/base.py — 统一工具协议

定义两个类型：
  - ToolObservation：工具执行结果（结构化）
  - Tool：所有工具必须实现的 ABC

工具协议要求：
  - name: str          供 registry 索引
  - description: str   供文档/日志
  - schema: dict       litellm/OpenAI function schema，用于向模型层注册工具
  - execute(arguments) -> ToolObservation

不包含具体工具逻辑，也不包含 registry 逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolObservation:
    """工具执行的结构化结果。

    Attributes:
        output:  主输出内容（命令 stdout/文件内容/操作描述等）。
        success: 执行是否成功。
        error:   失败时的错误描述；成功时为 None。
    """

    output: str
    success: bool = True
    error: str | None = None
    def __str__(self) -> str:
        """返回适合写入消息历史的字符串表示。"""
        if not self.success:
            if self.error and self.output:
                return f"Error: {self.error}\n{self.output}"
            if self.error:
                return f"Error: {self.error}"
        return self.output


class Tool(ABC):
    """所有工具的基类。

    子类必须实现 name、description、schema、execute。
    schema 应返回 litellm/OpenAI function schema 格式：
    {
        "type": "function",
        "function": {
            "name": "...",
            "description": "...",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    }
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一名称，registry 用此作 key。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具简短描述，供日志和文档使用。"""
        ...

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """litellm/OpenAI function schema，供 model_kwargs["tools"] 发现使用。"""
        ...

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        """执行工具，返回结构化结果。

        Args:
            arguments: 来自 LLM tool call 的参数 dict。

        Returns:
            ToolObservation，str(observation) 可直接写入消息历史。
        """
        ...
