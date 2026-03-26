"""
agent/middleware.py — Agent Loop 钩子协议与内置中间件

提供两种模式：

1. Middleware ABC（step 级别钩子）
   - pre_step(agent) — 每步 query 之前调用
   - post_step(agent) — 每步 dispatch 完成之后调用
   - 用法：Agent(model, tool_executor=..., middlewares=[MyMiddleware()])

2. SyntaxCheckMiddleware（tool_executor 包装器）
   - 包装 tool_executor，在 file_editor 写 .py 文件后运行 py_compile
   - 语法错误时把错误信息追加到 observation，保证 LLM 可见
   - 用法：Agent(model, tool_executor=SyntaxCheckMiddleware(registry.execute))
   - 零侵入 core.py（兼容没有 middlewares 参数的老版本）

3. AutoCommitMiddleware（继承 Middleware，使用 post_step）
   - 每 N 步运行 git add -A && git commit
   - 只定义，不在当前项目开发任务中主动启用

边界：
  - 不改变 agent 的决策逻辑
  - 不替代工具层的执行
  - 不做复杂事件系统
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# file_editor 中写文件的命令名
_WRITE_COMMANDS = {"str_replace", "create"}


# ---------------------------------------------------------------------------
# Middleware 基类
# ---------------------------------------------------------------------------

class Middleware(ABC):
    """Agent loop step 级别钩子协议。

    子类只需要覆盖需要的方法，不需要覆盖两者。
    默认实现均为空操作（空 pass），不影响 loop 行为。
    """

    def pre_step(self, agent: Any) -> None:
        """每步开始前（_check_limits 之前）调用。

        Args:
            agent: 当前运行的 Agent 实例，可读取 agent.messages / agent.n_steps 等。
        """

    def post_step(self, agent: Any) -> None:
        """每步结束后（dispatch + trajectory 落盘之后）调用。

        Args:
            agent: 当前运行的 Agent 实例，此时最新的消息已追加到 agent.messages。
        """


# ---------------------------------------------------------------------------
# SyntaxCheckMiddleware — tool_executor 包装器
# ---------------------------------------------------------------------------

class SyntaxCheckMiddleware:
    """包装 tool_executor，在 file_editor 写 .py 文件后运行 py_compile。

    语法错误时把错误信息追加到 observation 末尾，让 LLM 立刻看到并修正。

    用法（包装 registry.execute）：
        agent = Agent(model, tool_executor=SyntaxCheckMiddleware(registry.execute))

    或单独用于测试：
        checker = SyntaxCheckMiddleware(my_executor)
        obs = checker("file_editor", {"command": "create", "path": "foo.py", "content": "def f(:\n"})
        # obs 末尾含 "[SyntaxCheck] ERROR: ..."
    """

    def __init__(self, base_executor: Callable[[str, dict], str]) -> None:
        self._base = base_executor

    def __call__(self, name: str, arguments: dict[str, Any]) -> str:
        """执行工具，如果是 .py 文件写操作则追加语法检查结果。"""
        observation = self._base(name, arguments)

        if name == "file_editor" and arguments.get("command") in _WRITE_COMMANDS:
            path = arguments.get("path", "")
            if path.endswith(".py"):
                syntax_note = self._check_syntax(path)
                if syntax_note:
                    observation = observation + "\n\n" + syntax_note

        return observation

    def _check_syntax(self, path: str) -> str:
        """运行 python -m py_compile 检查语法。

        Returns:
            空字符串表示语法正确；否则返回含错误信息的字符串。
        """
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                error_msg = (result.stderr or result.stdout).strip()
                return f"[SyntaxCheck] ERROR in {path}:\n{error_msg}"
        except FileNotFoundError:
            logger.debug("File %s not found for syntax check (may not exist yet).", path)
        except subprocess.TimeoutExpired:
            logger.warning("Syntax check timed out for %s.", path)
        except Exception as e:
            logger.warning("Syntax check failed for %s: %s", path, e)
        return ""


# ---------------------------------------------------------------------------
# AutoCommitMiddleware — step 级别钩子
# ---------------------------------------------------------------------------

class AutoCommitMiddleware(Middleware):
    """每 N 步运行 git add -A && git commit。

    注意：此类已定义实现，但不应在当前项目开发任务中主动启用，
    以避免干扰开发工作流。

    用法：
        mw = AutoCommitMiddleware(commit_interval=5, work_dir=".")
        agent = Agent(model, tool_executor=..., middlewares=[mw])
    """

    def __init__(
        self,
        commit_interval: int = 5,
        work_dir: str | Path | None = None,
        commit_message_prefix: str = "auto: agent step",
    ) -> None:
        self.commit_interval = commit_interval
        self.work_dir = str(work_dir) if work_dir else None
        self.commit_message_prefix = commit_message_prefix
        self._steps_since_commit: int = 0

    def post_step(self, agent: Any) -> None:
        """每 commit_interval 步提交一次。"""
        self._steps_since_commit += 1
        if self._steps_since_commit < self.commit_interval:
            return

        self._steps_since_commit = 0
        self._run_git_commit(step=agent.n_steps)

    def _run_git_commit(self, step: int) -> None:
        """执行 git add -A && git commit。失败时只记录日志，不 raise。"""
        msg = f"{self.commit_message_prefix} {step}"
        cwd = self.work_dir
        try:
            add_result = subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            if add_result.returncode != 0:
                logger.warning("git add failed: %s", add_result.stderr)
                return

            commit_result = subprocess.run(
                ["git", "commit", "-m", msg],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            if commit_result.returncode == 0:
                logger.info("AutoCommit: %s", msg)
            else:
                # returncode=1 + "nothing to commit" is not an error
                stderr = commit_result.stderr or commit_result.stdout
                if "nothing to commit" not in stderr:
                    logger.warning("git commit failed: %s", stderr)
        except Exception as e:
            logger.warning("AutoCommitMiddleware error: %s", e)
