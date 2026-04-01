"""
tests/test_task_board.py -- persistent multi-step task board.
"""

import json

from agent.tools.task_board import TaskBoardTool


def test_task_board_create_and_get(tmp_path):
    tool = TaskBoardTool(tasks_dir=tmp_path / ".tasks")

    created = tool.execute({"command": "create", "subject": "Inspect project"})
    assert created.success
    payload = json.loads(created.output)
    assert payload["subject"] == "Inspect project"

    fetched = tool.execute({"command": "get", "task_id": payload["id"]})
    assert fetched.success
    assert json.loads(fetched.output)["id"] == payload["id"]


def test_task_board_blocked_by(tmp_path):
    tool = TaskBoardTool(tasks_dir=tmp_path / ".tasks")
    first = json.loads(tool.execute({"command": "create", "subject": "Step 1"}).output)
    second = json.loads(tool.execute({"command": "create", "subject": "Step 2"}).output)

    updated = tool.execute(
        {
            "command": "update",
            "task_id": second["id"],
            "add_blocked_by": [first["id"]],
        }
    )

    assert updated.success
    second_state = json.loads(tool.execute({"command": "get", "task_id": second["id"]}).output)
    assert first["id"] in second_state["blocked_by"]


def test_task_board_completed_task_unblocks_dependents(tmp_path):
    tool = TaskBoardTool(tasks_dir=tmp_path / ".tasks")
    first = json.loads(tool.execute({"command": "create", "subject": "Plan"}).output)
    second = json.loads(tool.execute({"command": "create", "subject": "Implement"}).output)
    tool.execute(
        {
            "command": "update",
            "task_id": second["id"],
            "add_blocked_by": [first["id"]],
        }
    )

    tool.execute(
        {
            "command": "update",
            "task_id": first["id"],
            "status": "completed",
        }
    )

    second_state = json.loads(tool.execute({"command": "get", "task_id": second["id"]}).output)
    assert second_state["blocked_by"] == []


def test_task_board_ready_lists_only_unblocked_tasks(tmp_path):
    tool = TaskBoardTool(tasks_dir=tmp_path / ".tasks")
    first = json.loads(tool.execute({"command": "create", "subject": "A"}).output)
    second = json.loads(tool.execute({"command": "create", "subject": "B"}).output)
    tool.execute(
        {
            "command": "update",
            "task_id": second["id"],
            "add_blocked_by": [first["id"]],
        }
    )

    ready = tool.execute({"command": "ready"})

    assert ready.success
    assert f"#{first['id']}" in ready.output
    assert f"#{second['id']}" not in ready.output
