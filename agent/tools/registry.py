"""
agent/tools/registry.py — 工具注册表

只做工具目录，不做调度策略。

对外暴露：
  - ToolRegistry.register(tool)
  - ToolRegistry.get(name) -> Tool        （名称不存在时 raise KeyError）
  - ToolRegistry.list_tools() -> list
  - ToolRegistry.get_schemas() -> list    （供 model_kwargs["tools"]）
  - ToolRegistry.execute(name, arguments) -> str   （core.py tool_executor 接线点）
"""

from __future__ import annotations

import logging
from typing import Any

from agent.tools.base import Tool, ToolObservation

logger = logging.getLogger(__name__)


class ToolRegistry:
    """轻量工具注册表。

    使用示例（接入 core.py）：

        registry = ToolRegistry()
        registry.register(BashTool())
        registry.register(TaskBoardTool())

        agent = Agent(model, tool_executor=registry.execute)
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具。同名工具会覆盖旧的（以最后一次注册为准）。"""
        if tool.name in self._tools:
            logger.warning("Tool %r already registered; overwriting.", tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """按名称获取工具。

        Raises:
            KeyError: 工具未注册。
        """
        if name not in self._tools:
            available = list(self._tools)
            raise KeyError(
                f"Tool {name!r} not found. Available tools: {available}"
            )
        return self._tools[name]

    def list_tools(self) -> list[Tool]:
        """返回所有已注册工具的列表（顺序为注册顺序）。"""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        """返回所有工具的 litellm/OpenAI schema 列表。

        可直接传给 LLMModel：
            model = LLMModel("anthropic/...", model_kwargs={"tools": registry.get_schemas()})
        """
        return [tool.schema for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """按名称执行工具，返回字符串 observation。

        这是 core.py tool_executor 的接线点：
            agent = Agent(model, tool_executor=registry.execute)

        工具未找到时返回错误字符串而非 raise，保持 agent loop 可继续运行。
        工具内部异常同样捕获并返回错误字符串。
        """
        try:
            tool = self.get(name)
        except KeyError as e:
            logger.warning("Tool lookup failed: %s", e)
            return str(ToolObservation(output="", success=False, error=str(e)))

        try:
            obs = tool.execute(arguments)
        except Exception as e:
            logger.warning("Tool %r raised an exception: %s", name, e)
            obs = ToolObservation(output="", success=False, error=f"Unexpected error: {e}")

        return str(obs)
