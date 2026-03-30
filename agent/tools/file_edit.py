"""
agent/tools/file_edit.py -- lightweight deterministic file viewing and editing.

Three commands:
  - view     Read a file with line numbers (optional line range).
  - replace  Find exact text and replace it (fails if not found or ambiguous).
  - create   Write entire file content.

Paths are resolved against work_dir. Paths outside work_dir are rejected.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolObservation

logger = logging.getLogger(__name__)

_VIEW_MAX_LINES = 500  # cap view output to avoid context explosion


class FileEditTool(Tool):
    """Lightweight file viewing and editing tool.

    Provides deterministic text replacement without shell escaping issues.
    Complements bash (which remains available for running commands/tests).
    """

    def __init__(self, work_dir: str | Path | None = None) -> None:
        self._work_dir: Path | None = Path(work_dir).resolve() if work_dir else None

    # ---- Tool protocol ------------------------------------------------

    @property
    def name(self) -> str:
        return "file_edit"

    @property
    def description(self) -> str:
        return (
            "View or edit files deterministically. "
            "Commands: view (read with line numbers), "
            "replace (find exact text and replace it — fails if not found or ambiguous), "
            "create (write entire file). "
            "Prefer replace over shell one-liners for code edits."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "file_edit",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["view", "replace", "create"],
                            "description": "Operation to perform.",
                        },
                        "path": {
                            "type": "string",
                            "description": "File path (relative to work_dir or absolute).",
                        },
                        "old_text": {
                            "type": "string",
                            "description": "[replace] Exact text to find (must match exactly once).",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "[replace] Replacement text.",
                        },
                        "content": {
                            "type": "string",
                            "description": "[create] Full file content to write.",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "[view] Start line number (1-based, default 1).",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "[view] End line number (inclusive, default EOF).",
                        },
                    },
                    "required": ["command", "path"],
                },
            },
        }

    # ---- Path helpers --------------------------------------------------

    def _resolve(self, path_str: str) -> Path:
        """Resolve path_str against work_dir (if set and relative)."""
        p = Path(path_str)
        if not p.is_absolute() and self._work_dir is not None:
            return self._work_dir / p
        return p

    def _check_boundary(self, resolved: Path) -> str | None:
        """Return error message if path escapes work_dir, else None."""
        if self._work_dir is None:
            return None
        try:
            resolved.resolve().relative_to(self._work_dir)
            return None
        except ValueError:
            return (
                f"Path {resolved} is outside workspace {self._work_dir}. "
                "Use a relative path within the workspace."
            )

    # ---- Dispatch ------------------------------------------------------

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        command = arguments.get("command")
        path_str = arguments.get("path", "")
        if not path_str:
            return ToolObservation(output="", success=False, error="Missing required argument 'path'.")

        path = self._resolve(path_str)
        boundary_err = self._check_boundary(path)
        if boundary_err:
            return ToolObservation(output="", success=False, error=boundary_err)

        if command == "view":
            return self._view(path, arguments)
        elif command == "replace":
            return self._replace(path, arguments)
        elif command == "create":
            return self._create(path, arguments)
        else:
            return ToolObservation(
                output="",
                success=False,
                error=f"Unknown command {command!r}. Use: view, replace, create.",
            )

    # ---- Commands ------------------------------------------------------

    def _view(self, path: Path, args: dict) -> ToolObservation:
        """Read file with line numbers, optional line range."""
        if not path.is_file():
            return ToolObservation(output="", success=False, error=f"File not found: {path}")

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolObservation(output="", success=False, error=f"Cannot read {path}: {e}")

        lines = text.splitlines(keepends=True)
        total = len(lines)
        start = max(1, args.get("start_line") or 1)
        end = min(total, args.get("end_line") or total)

        if start > total:
            return ToolObservation(
                output=f"File has {total} lines; start_line={start} is past EOF.",
                success=True,
            )

        # Cap output length
        if end - start + 1 > _VIEW_MAX_LINES:
            end = start + _VIEW_MAX_LINES - 1
            truncated = True
        else:
            truncated = False

        numbered = []
        for i in range(start, end + 1):
            line = lines[i - 1].rstrip("\n").rstrip("\r")
            numbered.append(f"{i:4d} | {line}")

        output = "\n".join(numbered)
        if truncated:
            output += f"\n[... truncated at {_VIEW_MAX_LINES} lines. Use start_line/end_line for remaining.]"

        return ToolObservation(output=output, success=True)

    def _replace(self, path: Path, args: dict) -> ToolObservation:
        """Find exact old_text and replace with new_text. Fail if not found or ambiguous."""
        old_text = args.get("old_text")
        new_text = args.get("new_text")

        if not old_text:
            return ToolObservation(output="", success=False, error="Missing required argument 'old_text'.")
        if new_text is None:
            return ToolObservation(output="", success=False, error="Missing required argument 'new_text'.")
        if not path.is_file():
            return ToolObservation(output="", success=False, error=f"File not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolObservation(output="", success=False, error=f"Cannot read {path}: {e}")

        count = content.count(old_text)
        if count == 0:
            return ToolObservation(
                output="",
                success=False,
                error=f"old_text not found in {path.name}. Use 'view' first to get exact text.",
            )
        if count > 1:
            return ToolObservation(
                output="",
                success=False,
                error=(
                    f"old_text matches {count} locations in {path.name}. "
                    "Provide more surrounding context to make the match unique."
                ),
            )

        new_content = content.replace(old_text, new_text, 1)
        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolObservation(output="", success=False, error=f"Cannot write {path}: {e}")

        return ToolObservation(
            output=f"Replaced 1 occurrence in {path.name}. {len(new_content)} chars written.",
            success=True,
        )

    def _create(self, path: Path, args: dict) -> ToolObservation:
        """Write entire file content."""
        content = args.get("content")
        if content is None:
            return ToolObservation(output="", success=False, error="Missing required argument 'content'.")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            return ToolObservation(output="", success=False, error=f"Cannot write {path}: {e}")

        return ToolObservation(
            output=f"Created {path.name} ({len(content)} chars).",
            success=True,
        )
