"""
examples/fix_bug.py -- end-to-end demo using the local coding assistant stack.

Scenario:
  - Create a Python file with a ZeroDivisionError bug.
  - Ask the assistant to inspect, fix, and verify it.

Environment:
  - Set MODEL_NAME plus the matching provider key in .env
  - Example:
      MODEL_NAME=deepseek/deepseek-chat
      DEEPSEEK_API_KEY=your_key_here
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv

from agent.app import AppConfig, LocalCodeAssistantApp

load_dotenv(override=False)


BUGGY_CODE = """\
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)


if __name__ == "__main__":
    print(calculate_average([1, 2, 3]))
    print(calculate_average([]))
"""


def _create_bug_file() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="coding_agent_demo_"))
    bug_file = tmp_dir / "bug_example.py"
    bug_file.write_text(BUGGY_CODE, encoding="utf-8")
    return bug_file


def main() -> None:
    bug_file = _create_bug_file()
    print(f"[demo] bug file: {bug_file}")
    print("[demo] original content")
    print("-" * 40)
    print(bug_file.read_text(encoding="utf-8"))
    print("-" * 40)

    app = LocalCodeAssistantApp.build(
        config=AppConfig.from_env(work_dir=Path.cwd()),
        ui=None,
    )
    history = app.initial_messages()
    request = (
        f"Fix the bug in {bug_file}. "
        "The function crashes on an empty list. "
        "Use task_board if you need a multi-step plan, verify the fix, and then explain what changed."
    )
    history, result, trajectory_path = app.run_turn(history, request)

    print(
        f"[demo] finished status={result['status']} "
        f"steps={result['total_steps']} cost=${result['total_cost']:.4f}"
    )
    print(f"[demo] trajectory={trajectory_path}")
    if result.get("final_content"):
        print("[demo] assistant summary")
        print(result["final_content"])

    print("[demo] fixed content")
    print("-" * 40)
    print(bug_file.read_text(encoding="utf-8"))
    print("-" * 40)


if __name__ == "__main__":
    main()
