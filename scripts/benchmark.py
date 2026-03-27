"""
scripts/benchmark.py — Lightweight benchmark harness for the coding agent.

Runs self-contained bug-fix instances from benchmarks/, measures pass@1,
and outputs a scorecard.

Usage:
    python scripts/benchmark.py                    # run all instances
    python scripts/benchmark.py dict_merge_overwrite  # run one instance
    python scripts/benchmark.py --dry-run          # list available instances
    python scripts/benchmark.py --step-limit 15 --cost-limit 2.0

Reference:
  - SWE-bench (https://github.com/princeton-nlp/SWE-bench)
  - Aider benchmarks (https://github.com/paul-gauthier/aider)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure UTF-8 output before any print() — fixes Windows box-drawing garble
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.encoding import ensure_utf8_stdio  # noqa: E402
ensure_utf8_stdio()

from dotenv import load_dotenv

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "benchmarks"


@dataclass(slots=True)
class BenchmarkResult:
    name: str
    status: str  # "pass" | "fail" | "error"
    agent_status: str
    steps: int
    cost: float
    wall_time_s: float
    error: str | None = None


def discover_instances(filter_name: str | None = None) -> list[Path]:
    """Find benchmark instance dirs containing instance.json."""
    candidates = sorted(BENCHMARKS_DIR.iterdir()) if BENCHMARKS_DIR.is_dir() else []
    instances = [d for d in candidates if (d / "instance.json").is_file()]
    if filter_name:
        instances = [d for d in instances if d.name == filter_name]
    return instances


def run_instance(
    instance_dir: Path,
    step_limit: int,
    cost_limit: float,
    prompt_version: str | None = None,
) -> BenchmarkResult:
    """Copy instance to temp workspace, run agent, test, return result."""
    from agent.app import AppConfig, LocalCodeAssistantApp

    meta = json.loads((instance_dir / "instance.json").read_text(encoding="utf-8"))
    name = meta["name"]

    # 1. Copy to temp
    work_dir = Path(tempfile.mkdtemp(prefix=f"bench_{name}_"))
    shutil.copytree(instance_dir, work_dir, dirs_exist_ok=True)

    # 2. Build app
    config = AppConfig.from_env(work_dir=work_dir)
    config.step_limit = step_limit
    config.cost_limit = cost_limit
    config.streaming = False
    config.enable_reflection = True
    if prompt_version:
        config.prompt_version = prompt_version

    t0 = time.time()

    try:
        app = LocalCodeAssistantApp.build(config=config, ui=None)
    except Exception as e:
        return BenchmarkResult(
            name=name, status="error", agent_status="build_failed",
            steps=0, cost=0.0, wall_time_s=time.time() - t0, error=str(e),
        )

    history = app.initial_messages()

    # 3. Construct prompt
    targets = ", ".join(meta.get("target_paths", []))
    prompt = (
        f"Bug: {meta['description']}\n"
        f"Target files: {targets}\n"
        f"Fix the bug, then verify with: {meta['test_command']}"
    )

    # 4. Run agent
    try:
        history, result, traj = app.run_turn(history, prompt)
    except Exception as e:
        return BenchmarkResult(
            name=name, status="error", agent_status="exception",
            steps=0, cost=0.0, wall_time_s=time.time() - t0, error=str(e),
        )

    # 5. Run test command
    try:
        verify = subprocess.run(
            meta["test_command"],
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        passed = verify.returncode == 0
        verify_output = (verify.stdout + verify.stderr).strip()
    except Exception as e:
        passed = False
        verify_output = str(e)

    wall_time = time.time() - t0

    return BenchmarkResult(
        name=name,
        status="pass" if passed else "fail",
        agent_status=result.get("status", "unknown"),
        steps=result.get("total_steps", 0),
        cost=result.get("total_cost", 0.0),
        wall_time_s=wall_time,
        error=None if passed else verify_output[:200],
    )


def render_scorecard(results: list[BenchmarkResult]) -> str:
    """Render a Unicode box-drawing scorecard table."""
    name_w = 22
    lines = []
    lines.append(f"╔{'═' * name_w}╦{'═' * 8}╦{'═' * 7}╦{'═' * 9}╦{'═' * 7}╗")
    lines.append(f"║ {'Instance':<{name_w - 2}} ║ Result ║ Steps ║   Cost  ║ Time  ║")
    lines.append(f"╠{'═' * name_w}╬{'═' * 8}╬{'═' * 7}╬{'═' * 9}╬{'═' * 7}╣")

    for r in results:
        icon = " PASS " if r.status == "pass" else " FAIL " if r.status == "fail" else " ERR  "
        lines.append(
            f"║ {r.name:<{name_w - 2}} ║{icon}║ {r.steps:>5} ║ ${r.cost:>5.3f} ║ {r.wall_time_s:>4.0f}s ║"
        )

    lines.append(f"╠{'═' * name_w}╬{'═' * 8}╬{'═' * 7}╬{'═' * 9}╬{'═' * 7}╣")

    passed = sum(1 for r in results if r.status == "pass")
    total = len(results)
    avg_steps = sum(r.steps for r in results) / max(total, 1)
    total_cost = sum(r.cost for r in results)
    total_time = sum(r.wall_time_s for r in results)
    pct = f"{passed / total * 100:.0f}%" if total else "N/A"

    summary = f"{passed}/{total} pass"
    lines.append(
        f"║ {summary:<{name_w - 2}} ║ {pct:>6} ║ {'avg' + str(int(avg_steps)):>5} ║ ${total_cost:>5.3f} ║ {total_time:>4.0f}s ║"
    )
    lines.append(f"╚{'═' * name_w}╩{'═' * 8}╩{'═' * 7}╩{'═' * 9}╩{'═' * 7}╝")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark instances against the agent")
    parser.add_argument("instance", nargs="?", help="Run a specific instance by name")
    parser.add_argument("--dry-run", action="store_true", help="List instances without running")
    parser.add_argument("--step-limit", type=int, default=20, help="Max steps per instance")
    parser.add_argument("--cost-limit", type=float, default=3.0, help="Max cost (USD) per instance")
    parser.add_argument("--prompt-version", type=str, default=None, help="Use versioned prompt")
    args = parser.parse_args()

    load_dotenv(override=False)

    instances = discover_instances(args.instance)
    if not instances:
        print("No benchmark instances found.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Found {len(instances)} benchmark instance(s):")
        for d in instances:
            meta = json.loads((d / "instance.json").read_text(encoding="utf-8"))
            print(f"  {meta['name']}: {meta['description'][:60]}...")
        return 0

    print(f"\n{'=' * 60}")
    print(f"Benchmark: {len(instances)} instance(s)")
    print(f"{'=' * 60}")

    results: list[BenchmarkResult] = []
    for d in instances:
        meta = json.loads((d / "instance.json").read_text(encoding="utf-8"))
        print(f"\n  Running: {meta['name']}...", flush=True)
        r = run_instance(d, step_limit=args.step_limit, cost_limit=args.cost_limit, prompt_version=args.prompt_version)
        results.append(r)
        icon = "PASS" if r.status == "pass" else "FAIL" if r.status == "fail" else "ERR"
        print(f"  [{icon}] {r.name}  steps={r.steps} ${r.cost:.4f} {r.wall_time_s:.1f}s")
        if r.error and r.status != "pass":
            for line in (r.error or "").splitlines()[:3]:
                print(f"    {line}")

    print(f"\n{'=' * 60}")
    print(render_scorecard(results))
    print(f"{'=' * 60}")

    # Save results JSON
    results_dir = BENCHMARKS_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    results_path = results_dir / f"results_{ts}.json"
    results_data = [
        {"name": r.name, "status": r.status, "steps": r.steps, "cost": r.cost, "wall_time_s": r.wall_time_s}
        for r in results
    ]
    results_path.write_text(json.dumps(results_data, indent=2), encoding="utf-8")
    print(f"\nResults saved to {results_path}")

    passed = sum(1 for r in results if r.status == "pass")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
