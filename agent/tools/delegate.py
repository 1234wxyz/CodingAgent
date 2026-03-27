"""
agent/tools/delegate.py — 子 Agent 委托工具

对主 agent 来说，delegate 就是一个普通工具（和 bash/semantic_search/task_board 同级）。
主 agent 通过 tool call 触发，传入任务描述，DelegateTool 同步阻塞执行，返回摘要。

设计约束：
  - 子 agent 使用全新的 Agent 实例，消息历史与父 agent 完全隔离
  - 子 agent 可以有自己的 tool_executor（可以是父 agent 工具的子集）
  - 不做并行执行，不做 agent 编排策略，不共享上下文
  - 通过 registry.register(DelegateTool(model)) 注册为标准工具
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from agent.tools.base import Tool, ToolObservation

logger = logging.getLogger(__name__)


class DelegateTool(Tool):
    """把子 agent 暴露为一个普通工具。

    用法：
        registry = ToolRegistry()
        registry.register(BashTool())
        registry.register(DelegateTool(
            model=model,
            sub_tool_executor=registry.execute,  # 子 agent 可用工具
            step_limit=10,
        ))

        # 主 agent 发起 tool call：
        # {"name": "delegate", "arguments": {"task": "list all .py files"}}
    """

    def __init__(
        self,
        model: Any,
        sub_tool_executor: Callable[[str, dict], str] | None = None,
        step_limit: int = 10,
        cost_limit: float = 1.0,
    ) -> None:
        """
        Args:
            model:             子 agent 使用的模型（通常与父 agent 相同）。
            sub_tool_executor: 子 agent 的工具执行器；None 表示子 agent 无工具。
            step_limit:        子 agent 的最大步数，防止无限循环。
            cost_limit:        子 agent 的最大费用（USD）。
        """
        self._model = model
        self._sub_tool_executor = sub_tool_executor
        self._step_limit = step_limit
        self._cost_limit = cost_limit

    @property
    def name(self) -> str:
        return "delegate"

    @property
    def description(self) -> str:
        return (
            "Delegate a self-contained sub-task to a specialized sub-agent. "
            "The sub-agent runs with an isolated message history and returns a text summary. "
            "Use this for tasks that benefit from a fresh context, such as exploration or analysis."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "delegate",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "The complete, self-contained task description for the sub-agent. "
                                "Include all necessary context — the sub-agent has no access to the "
                                "parent agent's conversation history."
                            ),
                        },
                        "context": {
                            "type": "string",
                            "description": (
                                "Optional additional context or constraints for the sub-agent "
                                "(e.g., working directory, file paths to focus on)."
                            ),
                        },
                    },
                    "required": ["task"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        """同步执行子 agent，返回其最终文本输出作为 observation。

        子 agent 的消息历史与父 agent 完全隔离（新 Agent 实例）。
        """
        # 延迟导入，避免循环依赖（delegate.py 在 tools/ 下，core.py 在 agent/ 下）
        from agent.core import Agent

        task = arguments.get("task", "").strip()
        if not task:
            return ToolObservation(
                output="", success=False, error="Missing required argument 'task'."
            )

        context = arguments.get("context", "").strip()
        user_content = task
        if context:
            user_content = f"{task}\n\nAdditional context:\n{context}"

        initial_messages = [{"role": "user", "content": user_content}]

        logger.debug("DelegateTool: starting sub-agent for task: %.100s", task)

        sub_agent = Agent(
            model=self._model,
            tool_executor=self._sub_tool_executor,
            step_limit=self._step_limit,
            cost_limit=self._cost_limit,
        )

        try:
            result = sub_agent.run(initial_messages)
        except Exception as e:
            logger.warning("Sub-agent raised an unexpected exception: %s", e)
            return ToolObservation(
                output="",
                success=False,
                error=f"Sub-agent failed with exception: {e}",
            )

        status = result.get("status", "unknown")
        final_content = result.get("final_content") or ""
        total_steps = result.get("total_steps", 0)
        total_cost = result.get("total_cost", 0.0)

        if status == "Submitted" and final_content:
            output = final_content
            success = True
        else:
            # 子 agent 未正常完成，返回状态摘要
            lines = [
                f"Sub-agent finished: status={status}, steps={total_steps}, cost=${total_cost:.4f}",
            ]
            if final_content:
                lines.append(final_content)
            output = "\n".join(lines)
            success = status == "Submitted"

        logger.debug(
            "DelegateTool: sub-agent done. status=%s steps=%d cost=%.4f",
            status, total_steps, total_cost,
        )
        return ToolObservation(output=output, success=success)
