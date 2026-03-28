"""
scripts/dashboard.py — Terminal dashboard for trajectory analysis.

Reads a trajectory JSONL file and renders a structured ASCII dashboard
with step timeline, tool frequency, cost curve, and decision summary.

Pure Python + ANSI colors, zero external dependencies.

Usage:
    python scripts/dashboard.py path/to/trajectory.jsonl
    python scripts/dashboard.py trajectories/              # latest file in dir

Reference: Inspired by phoenix (Arize) trace views and rich panels.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

class _C:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    RED = "\033[31m"
    WHITE = "\033[37m"


def _bar(value: float, max_value: float, width: int = 40, char: str = "█") -> str:
    """Render a horizontal bar of proportional length."""
    if max_value <= 0:
        return ""
    filled = int(round(value / max_value * width))
    return char * min(filled, width)


def _box_top(width: int) -> str:
    return f"╔{'═' * width}╗"


def _box_mid(width: int) -> str:
    return f"╠{'═' * width}╣"


def _box_bot(width: int) -> str:
    return f"╚{'═' * width}╝"


def _box_row(content: str, width: int) -> str:
    padded = content.ljust(width)[:width]
    return f"║{padded}║"


# ---------------------------------------------------------------------------
# Trajectory parsing (enhanced)
# ---------------------------------------------------------------------------

def parse_enhanced_trajectory(path: Path) -> dict:
    """Parse a trajectory JSONL with enhanced observability fields.

    Returns dict with:
        steps: list of step dicts (step, cost, total_cost, wall_time_ms, tool_names, ...)
        exit_status, total_steps, total_cost
        decisions: list of (step_num, action_summary) tuples
    """
    steps: list[dict] = []
    exit_info: dict = {"status": "unknown", "total_steps": 0, "total_cost": 0.0}
    decisions: list[tuple[int, str]] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if "exit" in entry:
            exit_info = entry["exit"]
            continue

        if "step" not in entry:
            continue

        steps.append(entry)

        # Extract decision summary from assistant content
        for msg in entry.get("messages", []):
            if msg.get("role") == "assistant" and msg.get("content"):
                summary = msg["content"][:80].replace("\n", " ").strip()
                decisions.append((entry["step"], summary))
                break
            elif msg.get("role") == "assistant":
                tool_names = entry.get("tool_names", [])
                if tool_names:
                    decisions.append((entry["step"], f"→ {', '.join(tool_names)}"))

    return {
        "steps": steps,
        "exit_status": exit_info.get("status", "unknown"),
        "total_steps": exit_info.get("total_steps", len(steps)),
        "total_cost": exit_info.get("total_cost", 0.0),
        "decisions": decisions,
    }


# ---------------------------------------------------------------------------
# Dashboard sections
# ---------------------------------------------------------------------------

def render_header(path: Path, data: dict, width: int = 60) -> str:
    """Render dashboard header."""
    lines = [
        _box_top(width),
        _box_row(f" {_C.BOLD}{_C.CYAN}Trajectory Dashboard{_C.RESET}", width + 9),
        _box_mid(width),
        _box_row(f" File    : {path.name}", width),
        _box_row(f" Status  : {data['exit_status']}", width),
        _box_row(f" Steps   : {data['total_steps']}", width),
        _box_row(f" Cost    : ${data['total_cost']:.4f}", width),
        _box_bot(width),
    ]
    return "\n".join(lines)


def render_step_timeline(steps: list[dict], width: int = 60) -> str:
    """Render step timeline as horizontal bar chart by wall_time_ms."""
    if not steps:
        return ""
    lines = [f"\n{_C.BOLD}{_C.YELLOW}Step Timeline (wall time){_C.RESET}"]
    max_time = max((s.get("wall_time_ms", 0) for s in steps), default=1) or 1

    for s in steps:
        step_num = s.get("step", "?")
        wall_ms = s.get("wall_time_ms", 0)
        tools = ", ".join(s.get("tool_names", [])) or "text"
        bar = _bar(wall_ms, max_time, width=30)
        lines.append(
            f"  {_C.DIM}#{step_num:>2}{_C.RESET} "
            f"{_C.GREEN}{bar}{_C.RESET} "
            f"{wall_ms:>7.0f}ms "
            f"{_C.DIM}({tools}){_C.RESET}"
        )
    return "\n".join(lines)


def render_tool_frequency(steps: list[dict]) -> str:
    """Render tool call frequency histogram."""
    from collections import Counter
    counter: Counter[str] = Counter()
    for s in steps:
        for name in s.get("tool_names", []):
            counter[name] += 1

    if not counter:
        return ""

    lines = [f"\n{_C.BOLD}{_C.MAGENTA}Tool Frequency{_C.RESET}"]
    max_count = max(counter.values()) if counter else 1
    for name, count in counter.most_common():
        bar = _bar(count, max_count, width=25)
        lines.append(f"  {name:<18} {_C.CYAN}{bar}{_C.RESET} {count}")
    return "\n".join(lines)


def render_cost_curve(steps: list[dict], width: int = 50, height: int = 6) -> str:
    """Render cumulative cost as ASCII line chart."""
    if not steps:
        return ""

    costs = [s.get("total_cost", 0.0) for s in steps]
    if not any(costs):
        return ""

    max_cost = max(costs) or 0.001
    lines = [f"\n{_C.BOLD}{_C.BLUE}Cumulative Cost Curve{_C.RESET}"]

    # Build a simple height x width grid
    grid = [[" "] * width for _ in range(height)]
    for i, cost in enumerate(costs):
        x = int(i / max(len(costs) - 1, 1) * (width - 1))
        y = int(cost / max_cost * (height - 1))
        row = height - 1 - y
        grid[row][x] = "●"
        # Fill below with dots for visual continuity
        for r in range(row + 1, height):
            if grid[r][x] == " ":
                grid[r][x] = "·"

    for r, row in enumerate(grid):
        label = f"${max_cost * (height - 1 - r) / (height - 1):.3f}" if r in (0, height - 1) else "      "
        lines.append(f"  {_C.DIM}{label}{_C.RESET} │{''.join(row)}│")

    step_labels = f"  {'step 1'.ljust(width // 2)}{'step ' + str(len(costs)):>{width // 2}}"
    lines.append(f"         └{'─' * width}┘")
    lines.append(f"  {_C.DIM}{step_labels}{_C.RESET}")
    return "\n".join(lines)


def render_decisions(decisions: list[tuple[int, str]]) -> str:
    """Render decision summary for each step."""
    if not decisions:
        return ""
    lines = [f"\n{_C.BOLD}{_C.WHITE}Decision Summary{_C.RESET}"]
    for step_num, summary in decisions:
        lines.append(f"  {_C.DIM}#{step_num:>2}{_C.RESET} {summary}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_dashboard(path: Path) -> str:
    """Render complete dashboard for a trajectory file."""
    data = parse_enhanced_trajectory(path)
    parts = [
        render_header(path, data),
        render_step_timeline(data["steps"]),
        render_tool_frequency(data["steps"]),
        render_cost_curve(data["steps"]),
        render_decisions(data["decisions"]),
    ]
    return "\n".join(p for p in parts if p)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/dashboard.py <trajectory.jsonl | directory>", file=sys.stderr)
        return 1

    target = Path(sys.argv[1])
    if target.is_dir():
        files = sorted(target.glob("*.jsonl"))
        if not files:
            print(f"No .jsonl files in {target}", file=sys.stderr)
            return 1
        target = files[-1]  # latest

    if not target.is_file():
        print(f"File not found: {target}", file=sys.stderr)
        return 1

    print(render_dashboard(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
