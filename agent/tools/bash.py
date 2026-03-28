"""
agent/tools/bash.py -- stateless local command execution.

Tool name stays `bash` for compatibility, but execution happens through the
host shell configured by Python's subprocess layer.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolObservation

_OUTPUT_MAX = 10_000  # 截断长输出，避免上下文爆炸


def _build_clean_env() -> dict[str, str]:
    """Build a subprocess env that suppresses pagers and progress bars.

    Cross-platform: only sets PAGER/MANPAGER on Unix where ``cat`` exists.
    """
    env = dict(os.environ)
    # Universal overrides (safe on all platforms)
    env.update({
        "PIP_PROGRESS_BAR": "off",
        "TQDM_DISABLE": "1",
        "NO_COLOR": "1",
    })
    if sys.platform == "win32":
        # git-for-windows respects GIT_PAGER; empty string disables paging.
        env["GIT_PAGER"] = ""
    else:
        env.update({
            "PAGER": "cat",
            "GIT_PAGER": "cat",
            "MANPAGER": "cat",
            "LESS": "-FRX",
        })
    return env


class BashTool(Tool):
    """执行 shell 命令并返回 stdout + stderr。"""

    def __init__(self, work_dir: str | Path | None = None) -> None:
        self._work_dir: str | None = str(Path(work_dir).resolve()) if work_dir else None

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a host shell command. "
            "The tool name is `bash` for compatibility, but each call is stateless: "
            "shell state (cwd, env vars) does NOT persist between calls. "
            "Use inline Python or shell redirection for file edits when needed. "
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
                cwd=self._work_dir,
                env=_build_clean_env(),
            )
        except subprocess.TimeoutExpired:
            return ToolObservation(
                output="", success=False, error="Command timed out after 60 seconds."
            )
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))

        combined = result.stdout + result.stderr
        if len(combined) > _OUTPUT_MAX:
            half = _OUTPUT_MAX // 2
            omitted = len(combined) - _OUTPUT_MAX
            combined = (
                combined[:half]
                + "\n<warning>\n"
                f"Output too long ({omitted} characters omitted). "
                "Try a more selective command: pipe through head/tail, "
                "redirect to a file and search it, or use grep to filter.\n"
                "</warning>\n"
                + combined[-half:]
            )

        return ToolObservation(
            output=combined,
            success=(result.returncode == 0),
            error=None if result.returncode == 0 else f"Exit code {result.returncode}",
        )
