"""
agent/tools/bash.py — 无状态本地命令执行工具

每次调用独立，不保留 shell 状态（无 cd / 环境变量持久化）。
"""

from __future__ import annotations

import subprocess
from typing import Any

from agent.tools.base import Tool, ToolObservation

_OUTPUT_MAX = 10_000  # 截断长输出，避免上下文爆炸


class BashTool(Tool):
    """执行 shell 命令并返回 stdout + stderr。"""

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. "
            "Each call is stateless — shell state (cwd, env vars) does NOT persist between calls. "
            "Output is truncated to 10000 characters."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "bash",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute.",
                        }
                    },
                    "required": ["command"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        command = arguments.get("command", "").strip()
        if not command:
            return ToolObservation(
                output="", success=False, error="Missing required argument 'command'."
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return ToolObservation(
                output="", success=False, error="Command timed out after 60 seconds."
            )
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))

        combined = result.stdout + result.stderr
        if len(combined) > _OUTPUT_MAX:
            combined = combined[:_OUTPUT_MAX] + f"\n[... output truncated at {_OUTPUT_MAX} chars ...]"

        return ToolObservation(
            output=combined,
            success=(result.returncode == 0),
            error=None if result.returncode == 0 else f"Exit code {result.returncode}",
        )
