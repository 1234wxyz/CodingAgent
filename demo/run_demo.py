"""Demo runner that copies a scenario to a temp workspace and launches the agent.

Usage:
    python demo/run_demo.py
    python demo/run_demo.py --auto
    python demo/run_demo.py --scenario gateway --auto
    python demo/run_demo.py --list
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MAIN_PY = PROJECT_ROOT / "main.py"
DEMO_ROOT = Path(__file__).parent

SCENARIOS = {
    "inventory": "inventory_system",
    "gateway": "http_gateway_system",
}

DEFAULT_TASKS = {
    "inventory": (
        "This is an inventory management system with a bug. "
        "Fix the bug, and verify all tests pass with `python test_system.py`."
    ),
    "gateway": (
        "This is a multi-module FastAPI HTTP gateway incident. "
        "Reproduce the startup failure with `python start_gateway.py`, "
        "fix the root cause, then verify the gateway with `python smoke_check.py`."
    ),
}


def load_metadata(scenario_key: str) -> dict:
    scenario_dir = DEMO_ROOT / SCENARIOS[scenario_key]
    meta_path = scenario_dir / "instance.json"
    if not meta_path.is_file():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def build_task(scenario_key: str, metadata: dict) -> str:
    if metadata.get("auto_task"):
        return str(metadata["auto_task"])
    return DEFAULT_TASKS[scenario_key]


def scenario_dir_for(scenario_key: str) -> Path:
    return DEMO_ROOT / SCENARIOS[scenario_key]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch a demo scenario in a temp workspace."
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="inventory",
        help="Demo scenario to launch.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Single-shot mode with a pre-filled task.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenarios and exit.",
    )
    args = parser.parse_args()

    if args.list:
        for key, folder in SCENARIOS.items():
            metadata = load_metadata(key)
            title = metadata.get("title") or metadata.get("description") or folder
            print(f"{key:10s} -> {folder:20s} {title}")
        return 0

    metadata = load_metadata(args.scenario)
    demo_src = scenario_dir_for(args.scenario)
    task = build_task(args.scenario, metadata)

    tmp = Path(tempfile.mkdtemp(prefix="coding_agent_demo_"))
    work_dir = tmp / demo_src.name
    shutil.copytree(demo_src, work_dir)

    print(f"=== Scenario: {args.scenario} ===")
    if metadata.get("title"):
        print(metadata["title"])
    #if metadata.get("description"):
        #print(metadata["description"])
    if metadata.get("entry_command"):
        print(f"Reproduce with: {metadata['entry_command']}")
    if metadata.get("verify_command"):
        print(f"Verify with:    {metadata['verify_command']}")
    print(f"=== Demo workspace created: {work_dir} ===")
    # print("=== Original demo/ is untouched ===\n")

    env = os.environ.copy()
    # if args.scenario == "gateway" and "AGENT_PROMPT_VERSION" not in env:
    #     env["AGENT_PROMPT_VERSION"] = "v2"
    #     print("Using prompt version: v2")

    cmd = [sys.executable, str(MAIN_PY), "--work-dir", str(work_dir)]
    if args.auto:
        cmd += ["--task", task]

    #print(f"Running: {' '.join(cmd)}\n")
    print("=" * 60)

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n\nDemo interrupted.")
    finally:
        print(f"\n{'=' * 60}")
        print(f"Temp workspace: {work_dir}")
        answer = input("Delete temp workspace? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            shutil.rmtree(tmp, ignore_errors=True)
            print("Cleaned up.")
        else:
            print(f"Kept at: {work_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
