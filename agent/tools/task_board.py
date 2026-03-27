"""
agent/tools/task_board.py -- persistent task tracking for multi-step work.

Tasks are stored as JSON files in .tasks/ so they survive context compaction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolObservation


class TaskStore:
    """File-backed task store with a lightweight dependency graph."""

    def __init__(self, tasks_dir: str | Path = ".tasks") -> None:
        self.dir = Path(tasks_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def create(self, subject: str, description: str = "") -> dict[str, Any]:
        task = {
            "id": self._next_id(),
            "subject": subject,
            "description": description,
            "status": "pending",
            "blocked_by": [],
            "blocks": [],
        }
        self._save(task)
        return task

    def get(self, task_id: int) -> dict[str, Any]:
        path = self._path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[dict[str, Any]]:
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.dir.glob("task_*.json"))
        ]

    def ready(self) -> list[dict[str, Any]]:
        return [
            task
            for task in self.list_all()
            if task["status"] != "completed" and not task.get("blocked_by")
        ]

    def update(
        self,
        task_id: int,
        status: str | None = None,
        add_blocked_by: list[int] | None = None,
        add_blocks: list[int] | None = None,
    ) -> dict[str, Any]:
        task = self.get(task_id)

        if status is not None:
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Invalid status: {status}")
            task["status"] = status

        if add_blocked_by:
            task["blocked_by"] = sorted(set(task["blocked_by"] + list(add_blocked_by)))

        if add_blocks:
            task["blocks"] = sorted(set(task["blocks"] + list(add_blocks)))
            for blocked_id in add_blocks:
                blocked = self.get(blocked_id)
                if task_id not in blocked["blocked_by"]:
                    blocked["blocked_by"].append(task_id)
                    blocked["blocked_by"] = sorted(set(blocked["blocked_by"]))
                    self._save(blocked)

        self._save(task)

        if status == "completed":
            self._clear_dependency(task_id)

        return self.get(task_id)

    def _clear_dependency(self, completed_id: int) -> None:
        for task in self.list_all():
            if completed_id in task.get("blocked_by", []):
                task["blocked_by"] = [
                    dep for dep in task["blocked_by"] if dep != completed_id
                ]
                self._save(task)

    def _next_id(self) -> int:
        ids = [
            int(path.stem.split("_")[1])
            for path in self.dir.glob("task_*.json")
            if "_" in path.stem
        ]
        return (max(ids) + 1) if ids else 1

    def _path(self, task_id: int) -> Path:
        return self.dir / f"task_{task_id}.json"

    def _save(self, task: dict[str, Any]) -> None:
        self._path(task["id"]).write_text(
            json.dumps(task, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )


class TaskBoardTool(Tool):
    """Create, inspect, and update persistent multi-step tasks."""

    def __init__(self, tasks_dir: str | Path = ".tasks") -> None:
        self._store = TaskStore(tasks_dir=tasks_dir)

    @property
    def name(self) -> str:
        return "task_board"

    @property
    def description(self) -> str:
        return (
            "Persistent task tracking for multi-step work. "
            "Commands: create, list, get, ready, update. "
            "Use this when the job spans multiple meaningful steps or dependencies."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "task_board",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["create", "list", "get", "ready", "update"],
                            "description": "Task board operation.",
                        },
                        "task_id": {
                            "type": "integer",
                            "description": "[get/update] Task id.",
                        },
                        "subject": {
                            "type": "string",
                            "description": "[create] Short task title.",
                        },
                        "description": {
                            "type": "string",
                            "description": "[create] Optional task details.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                            "description": "[update] New status.",
                        },
                        "add_blocked_by": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "[update] Task ids that block this task.",
                        },
                        "add_blocks": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "[update] Task ids blocked by this task.",
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        command = arguments.get("command")

        try:
            if command == "create":
                subject = str(arguments.get("subject", "")).strip()
                if not subject:
                    return ToolObservation(output="", success=False, error="Missing argument 'subject'.")
                task = self._store.create(
                    subject=subject,
                    description=str(arguments.get("description", "")).strip(),
                )
                return ToolObservation(output=_format_task_json(task), success=True)

            if command == "list":
                tasks = self._store.list_all()
                return ToolObservation(output=_format_task_list(tasks), success=True)

            if command == "ready":
                tasks = self._store.ready()
                return ToolObservation(output=_format_task_list(tasks), success=True)

            if command == "get":
                task_id = arguments.get("task_id")
                if task_id is None:
                    return ToolObservation(output="", success=False, error="Missing argument 'task_id'.")
                task = self._store.get(int(task_id))
                return ToolObservation(output=_format_task_json(task), success=True)

            if command == "update":
                task_id = arguments.get("task_id")
                if task_id is None:
                    return ToolObservation(output="", success=False, error="Missing argument 'task_id'.")
                task = self._store.update(
                    task_id=int(task_id),
                    status=arguments.get("status"),
                    add_blocked_by=[int(v) for v in arguments.get("add_blocked_by") or []],
                    add_blocks=[int(v) for v in arguments.get("add_blocks") or []],
                )
                return ToolObservation(output=_format_task_json(task), success=True)

            return ToolObservation(
                output="",
                success=False,
                error=f"Unknown command {command!r}. Use: create, list, get, ready, update.",
            )
        except Exception as e:
            return ToolObservation(output="", success=False, error=str(e))


def _format_task_json(task: dict[str, Any]) -> str:
    return json.dumps(task, indent=2, ensure_ascii=True)


def _format_task_list(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "No tasks."

    lines: list[str] = []
    marker_map = {
        "pending": "[ ]",
        "in_progress": "[>]",
        "completed": "[x]",
    }
    for task in tasks:
        marker = marker_map.get(task.get("status"), "[?]")
        blocked = task.get("blocked_by") or []
        suffix = f" blocked_by={blocked}" if blocked else ""
        lines.append(f"{marker} #{task['id']} {task['subject']}{suffix}")
    return "\n".join(lines)
