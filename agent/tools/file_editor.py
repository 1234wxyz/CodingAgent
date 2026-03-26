"""
agent/tools/file_editor.py — 最小可靠文本编辑工具

支持三个命令：
  - str_replace：精确唯一匹配替换（0次→错误+相似行提示，>1次→错误）
  - view：读取文件（可选行范围，1-based）
  - create：创建或覆盖文件
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolObservation


class FileEditorTool(Tool):
    """文件查看与编辑工具。"""

    @property
    def name(self) -> str:
        return "file_editor"

    @property
    def description(self) -> str:
        return (
            "View, create, or edit files. "
            "Use 'str_replace' for targeted edits (old_str must be unique in the file), "
            "'view' to read a file, 'create' to write a new file."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "file_editor",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["str_replace", "view", "create"],
                            "description": "Operation to perform.",
                        },
                        "path": {
                            "type": "string",
                            "description": "File path (absolute or relative).",
                        },
                        "old_str": {
                            "type": "string",
                            "description": "[str_replace] Exact string to find (must appear exactly once).",
                        },
                        "new_str": {
                            "type": "string",
                            "description": "[str_replace] Replacement string.",
                        },
                        "content": {
                            "type": "string",
                            "description": "[create] File content to write.",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "[view] First line to show (1-based, inclusive).",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "[view] Last line to show (1-based, inclusive).",
                        },
                    },
                    "required": ["command", "path"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        command = arguments.get("command")
        if command == "str_replace":
            return self._str_replace(arguments)
        elif command == "view":
            return self._view(arguments)
        elif command == "create":
            return self._create(arguments)
        else:
            return ToolObservation(
                output="",
                success=False,
                error=f"Unknown command {command!r}. Use: str_replace, view, create.",
            )

    # ------------------------------------------------------------------
    # str_replace
    # ------------------------------------------------------------------

    def _str_replace(self, args: dict[str, Any]) -> ToolObservation:
        path = args.get("path", "")
        old_str = args.get("old_str")
        new_str = args.get("new_str", "")

        if old_str is None:
            return ToolObservation(output="", success=False, error="Missing argument 'old_str'.")

        try:
            content = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolObservation(output="", success=False, error=f"File not found: {path}")
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))

        count = content.count(old_str)
        if count == 0:
            hint = self._similar_lines_hint(content, old_str)
            msg = f"old_str not found in {path}."
            return ToolObservation(output=hint, success=False, error=msg)
        if count > 1:
            return ToolObservation(
                output="",
                success=False,
                error=f"old_str found {count} times in {path}; must be unique. Provide more context.",
            )

        new_content = content.replace(old_str, new_str, 1)
        try:
            Path(path).write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))

        return ToolObservation(output=f"str_replace applied successfully to {path}.", success=True)

    def _similar_lines_hint(self, content: str, old_str: str) -> str:
        """返回内容中与 old_str 首行相似的行，帮助排查匹配失败原因。"""
        target_lines = old_str.splitlines()
        if not target_lines:
            return ""
        first_line = target_lines[0].strip().lower()
        if not first_line:
            return ""

        similar: list[str] = []
        for i, line in enumerate(content.splitlines(), start=1):
            if first_line in line.strip().lower():
                similar.append(f"  Line {i}: {line}")
            if len(similar) >= 5:
                break

        if similar:
            return "Similar lines in file:\n" + "\n".join(similar)
        return ""

    # ------------------------------------------------------------------
    # view
    # ------------------------------------------------------------------

    def _view(self, args: dict[str, Any]) -> ToolObservation:
        path = args.get("path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        try:
            raw = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolObservation(output="", success=False, error=f"File not found: {path}")
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))

        lines = raw.splitlines()

        if start_line is not None or end_line is not None:
            s = (int(start_line) - 1) if start_line is not None else 0
            e = int(end_line) if end_line is not None else len(lines)
            s = max(0, s)
            e = min(len(lines), e)
            lines = lines[s:e]
            # 带行号显示
            output = "\n".join(f"{s + i + 1}: {line}" for i, line in enumerate(lines))
        else:
            # 全文带行号
            output = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))

        return ToolObservation(output=output, success=True)

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    def _create(self, args: dict[str, Any]) -> ToolObservation:
        path = args.get("path", "")
        content = args.get("content", "")

        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))

        return ToolObservation(output=f"File created: {path}", success=True)
