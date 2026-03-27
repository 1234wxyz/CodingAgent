"""
scripts/analyze.py — Trajectory 分析工具

读取 trajectories/*.jsonl（或指定路径），输出统计：
  - exit 状态、总步数、总花费
  - 工具调用分布
  - Token 消耗（如 trajectory 包含 usage 字段）

JSONL 格式（来自 agent/core.py）：
  step 记录：{"step": N, "messages": [...], "cost": float, "total_cost": float}
  exit 记录：{"exit": {"status": str, "total_steps": int, "total_cost": float}}

用法：
  python scripts/analyze.py                    # 扫描 trajectories/*.jsonl
  python scripts/analyze.py path/to/run.jsonl  # 指定单文件
  python scripts/analyze.py trajectories/      # 指定目录
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# 解析单条 JSONL 轨迹
# ---------------------------------------------------------------------------

def parse_trajectory(path: Path) -> dict:
    """读取并解析一个 JSONL trajectory 文件。

    Returns:
        {
            "path": str,
            "exit_status": str,
            "total_steps": int,
            "total_cost": float,
            "tool_calls": Counter({tool_name: count}),
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
            "errors": list[str],
        }
    """
    result = {
        "path": str(path),
        "exit_status": "unknown",
        "total_steps": 0,
        "total_cost": 0.0,
        "tool_calls": Counter(),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "errors": [],
    }

    # tool_call_id → tool_name 映射（从 assistant messages 的 tool_calls 字段构建）
    id_to_name: dict[str, str] = {}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        result["errors"].append(f"Cannot read file: {e}")
        return result

    for lineno, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            result["errors"].append(f"Line {lineno}: JSON parse error: {e}")
            continue

        # --- exit 记录 ---
        if "exit" in entry:
            ex = entry["exit"]
            result["exit_status"] = ex.get("status", "unknown")
            result["total_steps"] = ex.get("total_steps", result["total_steps"])
            result["total_cost"] = ex.get("total_cost", result["total_cost"])
            continue

        # --- step 记录 ---
        if "step" not in entry:
            continue

        step_cost = entry.get("cost", 0.0)
        if result["total_cost"] == 0.0 and step_cost:
            pass  # total_cost 优先从 exit 记录获取

        messages = entry.get("messages", [])
        for msg in messages:
            role = msg.get("role", "")

            # 收集 tool_call_id → tool_name 映射
            # assistant 消息里可能有 tool_calls（OpenAI 格式或我们的归一化格式）
            if role == "assistant":
                _extract_tool_names(msg, id_to_name)
                # 如果有 usage 字段（部分 trajectory 可能附带）
                usage = msg.get("usage", {})
                if usage:
                    result["prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
                    result["completion_tokens"] += usage.get("completion_tokens", 0) or 0
                    result["total_tokens"] += usage.get("total_tokens", 0) or 0

            # tool result 消息记录工具调用次数
            elif role == "tool":
                tc_id = msg.get("tool_call_id", "")
                tool_name = id_to_name.get(tc_id, "unknown")
                result["tool_calls"][tool_name] += 1

    # 如果 total_cost 仍然是 0（没有 exit 记录），从各 step cost 累加
    if result["total_cost"] == 0.0:
        total_from_steps = sum(
            json.loads(l).get("cost", 0.0)
            for l in lines
            if l.strip() and "step" in json.loads(l)
        )
        if total_from_steps:
            result["total_cost"] = total_from_steps

    return result


def _extract_tool_names(msg: dict, id_to_name: dict) -> None:
    """从 assistant message 的 tool_calls 字段提取 id → name 映射。

    同时处理 OpenAI 格式（{"id", "function": {"name": ...}}）
    和我们的归一化格式（{"id", "name": ...}）。
    """
    tool_calls = msg.get("tool_calls") or []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        tc_id = tc.get("id", "")
        if not tc_id:
            continue
        # 归一化格式
        if "name" in tc:
            id_to_name[tc_id] = tc["name"]
        # OpenAI 格式
        elif "function" in tc:
            id_to_name[tc_id] = tc["function"].get("name", "unknown")

    # 也处理 _normalized_tool_calls
    norm = msg.get("_normalized_tool_calls") or []
    for tc in norm:
        if isinstance(tc, dict) and tc.get("id"):
            id_to_name[tc["id"]] = tc.get("name", "unknown")


# ---------------------------------------------------------------------------
# 格式化输出
# ---------------------------------------------------------------------------

def format_report(stats: dict) -> str:
    lines = [f"=== Trajectory: {stats['path']} ==="]
    lines.append(f"  Exit status    : {stats['exit_status']}")
    lines.append(f"  Total steps    : {stats['total_steps']}")
    lines.append(f"  Total cost     : ${stats['total_cost']:.4f}")

    total_calls = sum(stats["tool_calls"].values())
    if total_calls:
        call_parts = ", ".join(
            f"{name}: {cnt}"
            for name, cnt in stats["tool_calls"].most_common()
        )
        lines.append(f"  Tool calls     : {total_calls} ({call_parts})")
    else:
        lines.append("  Tool calls     : 0")

    if stats["total_tokens"]:
        lines.append(
            f"  Token usage    : prompt={stats['prompt_tokens']}, "
            f"completion={stats['completion_tokens']}, "
            f"total={stats['total_tokens']}"
        )

    if stats["errors"]:
        lines.append(f"  Warnings       : {len(stats['errors'])} parse warning(s)")
        for err in stats["errors"][:3]:
            lines.append(f"    - {err}")

    return "\n".join(lines)


def format_summary(all_stats: list[dict]) -> str:
    if len(all_stats) <= 1:
        return ""
    total_cost = sum(s["total_cost"] for s in all_stats)
    total_steps = sum(s["total_steps"] for s in all_stats)
    status_counts = Counter(s["exit_status"] for s in all_stats)
    all_tools: Counter = Counter()
    for s in all_stats:
        all_tools.update(s["tool_calls"])

    lines = [
        "",
        f"=== Summary ({len(all_stats)} trajectories) ===",
        f"  Total cost     : ${total_cost:.4f}",
        f"  Total steps    : {total_steps}",
        f"  Exit statuses  : {dict(status_counts)}",
    ]
    if all_tools:
        call_parts = ", ".join(f"{n}: {c}" for n, c in all_tools.most_common(5))
        lines.append(f"  Top tools      : {call_parts}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def collect_jsonl_files(target: str) -> list[Path]:
    """从路径参数收集所有 .jsonl 文件。"""
    p = Path(target)
    if p.is_file() and p.suffix == ".jsonl":
        return [p]
    if p.is_dir():
        files = sorted(p.glob("*.jsonl"))
        if not files:
            print(f"No .jsonl files found in {p}", file=sys.stderr)
        return files
    print(f"Path not found or not a .jsonl file: {target}", file=sys.stderr)
    return []


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]

    if args:
        paths: list[Path] = []
        for arg in args:
            paths.extend(collect_jsonl_files(arg))
    else:
        # 默认：扫描 trajectories/ 目录
        default_dir = Path("trajectories")
        if default_dir.is_dir():
            paths = sorted(default_dir.glob("*.jsonl"))
        else:
            print("No trajectories/ directory found. Pass a path as argument.", file=sys.stderr)
            return

    if not paths:
        print("No trajectory files to analyze.")
        return

    all_stats = []
    for path in paths:
        stats = parse_trajectory(path)
        all_stats.append(stats)
        print(format_report(stats))
        print()

    summary = format_summary(all_stats)
    if summary:
        print(summary)


if __name__ == "__main__":
    main()
