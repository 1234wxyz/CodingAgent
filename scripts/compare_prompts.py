"""
scripts/compare_prompts.py -- A/B comparison of prompt versions across benchmarks.

Runs benchmark instances with two different prompt versions and outputs a
side-by-side comparison table showing pass/fail, steps, cost, and timing.

Usage:
    python scripts/compare_prompts.py v1 v2
    python scripts/compare_prompts.py v1 v2 --dry-run
    python scripts/compare_prompts.py v1 v2 --instance zero_division

Reference: Inspired by promptfoo (https://github.com/promptfoo/promptfoo).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from scripts.benchmark import BenchmarkResult, discover_instances, run_instance

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def list_versions() -> list[str]:
    """List available prompt versions from prompts/ directory."""
    if not PROMPTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.yaml"))


def run_version(
    version: str,
    instances: list[Path],
    step_limit: int,
    cost_limit: float,
) -> list[BenchmarkResult]:
    """Run all benchmark instances with a specific prompt version."""
    results = []
    for instance_dir in instances:
        meta = json.loads((instance_dir / "instance.json").read_text(encoding="utf-8"))
        print(f"  [{version}] {meta['name']}...", end=" ", flush=True)
        t0 = time.time()
        result = run_instance(
            instance_dir,
            step_limit=step_limit,
            cost_limit=cost_limit,
            prompt_version=version,
        )
        elapsed = time.time() - t0
        icon = "PASS" if result.status == "pass" else "FAIL"
        print(f"{icon} ({elapsed:.1f}s)")
        results.append(result)
    return results


def render_comparison(
    version_a: str,
    results_a: list[BenchmarkResult],
    version_b: str,
    results_b: list[BenchmarkResult],
) -> str:
    """Render side-by-side comparison table."""
    lines = []
    col_w = 28
    name_w = 24

    header = f"{'Instance':<{name_w}} | {version_a:^{col_w}} | {version_b:^{col_w}}"
    sep = f"{'-' * name_w}-+-{'-' * col_w}-+-{'-' * col_w}"
    lines.append("")
    lines.append(header)
    lines.append(sep)

    for left, right in zip(results_a, results_b):
        def _fmt(result: BenchmarkResult) -> str:
            icon = "PASS" if result.status == "pass" else "FAIL"
            return f"{icon}  steps={result.steps:<3} ${result.cost:.4f}"

        lines.append(f"{left.name:<{name_w}} | {_fmt(left):^{col_w}} | {_fmt(right):^{col_w}}")

    lines.append(sep)

    pass_a = sum(1 for result in results_a if result.status == "pass")
    pass_b = sum(1 for result in results_b if result.status == "pass")
    cost_a = sum(result.cost for result in results_a)
    cost_b = sum(result.cost for result in results_b)
    total_a = f"{pass_a}/{len(results_a)} pass  ${cost_a:.4f}"
    total_b = f"{pass_b}/{len(results_b)} pass  ${cost_b:.4f}"
    lines.append(f"{'TOTAL':<{name_w}} | {total_a:^{col_w}} | {total_b:^{col_w}}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two prompt versions across benchmark instances")
    parser.add_argument("version_a", help="First prompt version (e.g. v1)")
    parser.add_argument("version_b", help="Second prompt version (e.g. v2)")
    parser.add_argument("--instance", help="Run only this benchmark instance")
    parser.add_argument("--step-limit", type=int, default=20)
    parser.add_argument("--cost-limit", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    args = parser.parse_args()

    load_dotenv(override=False)

    available = list_versions()
    for version in [args.version_a, args.version_b]:
        if version not in available:
            print(f"Prompt version '{version}' not found. Available: {available}", file=sys.stderr)
            return 1

    instances = discover_instances(args.instance)
    if not instances:
        print("No benchmark instances found.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Would compare {args.version_a} vs {args.version_b} on {len(instances)} benchmark instance(s):")
        for instance_dir in instances:
            meta = json.loads((instance_dir / "instance.json").read_text(encoding="utf-8"))
            print(f"  {meta['name']}: {meta['description'][:60]}...")
        print(f"Available prompt versions: {available}")
        return 0

    print(f"\n=== Running with {args.version_a} ===")
    results_a = run_version(args.version_a, instances, args.step_limit, args.cost_limit)

    print(f"\n=== Running with {args.version_b} ===")
    results_b = run_version(args.version_b, instances, args.step_limit, args.cost_limit)

    print(render_comparison(args.version_a, results_a, args.version_b, results_b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
