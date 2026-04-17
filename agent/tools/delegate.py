"""
agent/tools/delegate.py — 角色化子 Agent 委托工具

对主 agent 来说，delegate 就是一个普通工具（和 bash/semantic_search/task_board 同级）。
主 agent 通过 tool call 触发，传入任务描述和可选的角色，DelegateTool 同步阻塞执行，返回摘要。

角色化设计（Multi-Agent Orchestration）：
  - role="explorer" (默认): 通用子 agent，用于代码探索和信息收集
  - role="reviewer": 代码审查员，关注质量、边界条件、安全问题
  - role="tester": 测试员，关注测试覆盖和验证

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


# ---------------------------------------------------------------------------
# Role system prompts
# ---------------------------------------------------------------------------

_ROLE_PROMPTS: dict[str, str] = {
    "explorer": (
        "You are a code explorer. Your job is to investigate the codebase, "
        "find relevant files, symbols, and patterns, then report your findings "
        "clearly and concisely. Focus on facts, not speculation."
    ),
    "reviewer": (
        "You are a code reviewer. Examine the changes or code provided and evaluate:\n"
        "1. Correctness — does the fix actually solve the problem?\n"
        "2. Edge cases — what inputs could still fail?\n"
        "3. Side effects — does the change break anything else?\n"
        "4. Code quality — is the solution clean and maintainable?\n\n"
        "Be specific. If you find issues, describe them with file paths and line numbers. "
        "If the code is good, say so with confidence."
    ),
    "tester": (
        "You are a test engineer. Your job is to:\n"
        "1. Identify what tests are needed for the given code or change.\n"
        "2. Run existing tests and report results.\n"
        "3. Suggest or write missing test cases.\n"
        "4. Verify edge cases and error handling.\n\n"
        "Always run tests before reporting. Report exact pass/fail counts."
    ),
}


class DelegateTool(Tool):
    """把角色化子 agent 暴露为一个普通工具。

    用法：
        registry = ToolRegistry()
        registry.register(BashTool())
        registry.register(DelegateTool(
            model=model,
            sub_tool_executor=registry.execute,
            step_limit=10,
        ))

        # 主 agent 发起 tool call：
        # {"name": "delegate", "arguments": {"task": "review the fix", "role": "reviewer"}}
    """

    def __init__(
        self,
        model: Any,
        sub_tool_executor: Callable[[str, dict], str] | None = None,
        step_limit: int = 10,
        cost_limit: float = 1.0,
    ) -> None:
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
            "Delegate a sub-task to a specialized sub-agent with an optional role. "
            "Roles: explorer (default, codebase investigation), "
            "reviewer (code quality & correctness review), "
            "tester (test execution & coverage). "
            "Always give a complete, self-contained task description."
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
                        "role": {
                            "type": "string",
                            "enum": ["explorer", "reviewer", "tester"],
                            "description": (
                                "The role of the sub-agent. "
                                "'explorer' for code investigation (default), "
                                "'reviewer' for code quality review, "
                                "'tester' for test execution and coverage."
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
        """同步执行角色化子 agent，返回其最终文本输出作为 observation。"""
        from agent.core import Agent

        task = arguments.get("task", "").strip()
        if not task:
            return ToolObservation(
                output="", success=False, error="Missing required argument 'task'."
            )

        role = arguments.get("role", "explorer").strip().lower()
        context = arguments.get("context", "").strip()

        # Build system prompt from role
        role_prompt = _ROLE_PROMPTS.get(role, _ROLE_PROMPTS["explorer"])

        # Build user message
        user_content = task
        if context:
            user_content = f"{task}\n\nAdditional context:\n{context}"

        initial_messages = [
            {"role": "system", "content": role_prompt},
            {"role": "user", "content": user_content},
        ]

        logger.debug(
            "DelegateTool: starting sub-agent (role=%s) for task: %.100s",
            role, task,
        )
        # Create a new Agent instance for the sub-agent, with isolated message history and its own tool executor
        # new 一个 Agent，它的消息历史、步数、成本都是独立的
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
            output = f"[{role}] {final_content}"
            success = True
        else:
            lines = [
                f"Sub-agent ({role}) finished: status={status}, steps={total_steps}, cost=${total_cost:.4f}",
            ]
            if final_content:
                lines.append(final_content)
            output = "\n".join(lines)
            success = status == "Submitted" # 无论如何都把 sub-agent 的输出当作成功的结果返回，除非它完全没有输出或者抛出了异常

        logger.debug(
            "DelegateTool: sub-agent done. role=%s status=%s steps=%d cost=%.4f",
            role, status, total_steps, total_cost,
        )
        return ToolObservation(output=output, success=success)
