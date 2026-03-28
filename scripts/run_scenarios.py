"""
scripts/run_scenarios.py -- Run demo/bug_scenarios against a real LLM API.

Usage:
    python scripts/run_scenarios.py                     # run all scenarios
    python scripts/run_scenarios.py zero_division       # run one scenario
    python scripts/run_scenarios.py --dry-run            # show what would run
    python scripts/run_scenarios.py --step-limit 15 --cost-limit 2.0
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "demo" / "bug_scenarios"


@dataclass(slots=True)
class ScenarioResult:
    name: str
    status: str  # "pass" | "fail" | "error"
    agent_status: str
    steps: int
    cost: float
    verify_output: str
    error: str | None = None


def discover_scenarios(filter_name: str | None = None) -> list[Path]:
    """Find scenario dirs containing scenario.json."""
    candidates = sorted(SCENARIOS_DIR.iterdir()) if SCENARIOS_DIR.is_dir() else []
    scenarios = [d for d in candidates if (d / "scenario.json").is_file()]
    if filter_name:
        scenarios = [d for d in scenarios if d.name == filter_name]
    return scenarios


def run_scenario(scenario_dir: Path, step_limit: int, cost_limit: float, prompt_version: str | None = None) -> ScenarioResult:
    """Copy scenario to temp workspace, run agent, verify, return result."""
    from agent.app import AppConfig, LocalCodeAssistantApp

    meta = json.loads((scenario_dir / "scenario.json").read_text(encoding="utf-8"))
    name = meta["name"]

    # 1. Copy to temp workspace
    work_dir = Path(tempfile.mkdtemp(prefix=f"scenario_{name}_"))
    shutil.copytree(scenario_dir, work_dir, dirs_exist_ok=True)

    # 2. Build app with this work_dir
    config = AppConfig.from_env(work_dir=work_dir)
    config.step_limit = step_limit
    config.cost_limit = cost_limit
    if prompt_version:
        config.prompt_version = prompt_version

    try:
        app = LocalCodeAssistantApp.build(config=config, ui=None)
    except Exception as e:
        return ScenarioResult(
            name=name, status="error", agent_status="build_failed",
            steps=0, cost=0.0, verify_output="", error=str(e),
        )

    history = app.initial_messages()

    # 3. Construct prompt
    targets = ", ".join(meta.get("target_paths", []))
    prompt = (
        f"Bug: {meta['description']}\n"
        f"Target files: {targets}\n"
        f"Fix the bug, then verify with: {meta['verify_command']}"
    )

    # 4. Run agent
    try:
        history, result, traj = app.run_turn(history, prompt)
    except Exception as e:
        return ScenarioResult(
            name=name, status="error", agent_status="exception",
            steps=0, cost=0.0, verify_output="", error=str(e),
        )

    # 5. Run verification command
    try:
        verify = subprocess.run(
            meta["verify_command"],
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        verify_passed = verify.returncode == 0
        verify_output = (verify.stdout + verify.stderr).strip()
    except Exception as e:
        verify_passed = False
        verify_output = str(e)

    return ScenarioResult(
        name=name,
        status="pass" if verify_passed else "fail",
        agent_status=result.get("status", "unknown"),
        steps=result.get("total_steps", 0),
        cost=result.get("total_cost", 0.0),
        verify_output=verify_output,
        error=None if verify_passed else verify_output,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run demo bug scenarios against real API")
    parser.add_argument("scenario", nargs="?", help="Run a specific scenario by name")
    parser.add_argument("--dry-run", action="store_true", help="List scenarios without running")
    parser.add_argument("--step-limit", type=int, default=20, help="Max steps per scenario")
    parser.add_argument("--cost-limit", type=float, default=3.0, help="Max cost (USD) per scenario")
    parser.add_argument("--prompt-version", type=str, default=None, help="Use versioned prompt (e.g., v1, v2)")
    args = parser.parse_args()

    load_dotenv(override=False)

    scenarios = discover_scenarios(args.scenario)
    if not scenarios:
        print("No scenarios found.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Found {len(scenarios)} scenario(s):")
        for s in scenarios:
            meta = json.loads((s / "scenario.json").read_text(encoding="utf-8"))
            print(f"  {meta['name']}: {meta['title']}")
        return 0

    results: list[ScenarioResult] = []
    for s in scenarios:
        meta = json.loads((s / "scenario.json").read_text(encoding="utf-8"))
        print(f"\n{'='*60}")
        print(f"Running: {meta['name']} — {meta['title']}")
        print(f"{'='*60}")
        r = run_scenario(s, step_limit=args.step_limit, cost_limit=args.cost_limit, prompt_version=args.prompt_version)
        results.append(r)
        icon = "PASS" if r.status == "pass" else "FAIL" if r.status == "fail" else "ERR"
        print(f"  [{icon}] {r.name}  agent={r.agent_status}  steps={r.steps}  cost=${r.cost:.4f}")
        if r.error and r.status != "pass":
            for line in r.verify_output.splitlines()[:5]:
                print(f"    {line}")

    # Summary
    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r.status == "pass")
    total_cost = sum(r.cost for r in results)
    print(f"Result: {passed}/{len(results)} passed  total_cost=${total_cost:.4f}")
    for r in results:
        icon = "PASS" if r.status == "pass" else "FAIL"
        print(f"  [{icon}] {r.name}: {r.status} (steps={r.steps}, ${r.cost:.4f})")
    print(f"{'='*60}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
