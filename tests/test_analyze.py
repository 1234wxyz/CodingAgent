"""
tests/test_analyze.py — scripts/analyze.py 单测（全离线）

覆盖场景：
  - parse_trajectory：最小 JSONL 样本（step + exit）→ exit_status/steps/cost 正确
  - parse_trajectory：归一化 tool_calls 格式 → tool_calls Counter 更新
  - parse_trajectory：OpenAI raw tool_calls 格式 → 同上
  - parse_trajectory：含坏 JSON 行 → errors 列表有记录，不 crash
  - parse_trajectory：无 exit 记录 → total_cost 从 step cost 累加
  - format_report：输出包含关键统计字段
  - format_summary：单条轨迹 → 返回空字符串
  - format_summary：多条轨迹 → 包含条数和状态汇总
"""

import json

import pytest

from scripts.analyze import format_report, format_summary, parse_trajectory


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path, entries: list[dict]) -> None:
    """把 entries 列表写成 JSONL 文件。"""
    path.write_text(
        "\n".join(json.dumps(e) for e in entries),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# parse_trajectory — 基本解析
# ---------------------------------------------------------------------------

def test_parse_trajectory_minimal(tmp_path):
    """最小 JSONL（1 个 step + 1 个 exit）→ 正确解析 exit_status/total_steps/total_cost。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {"step": 1, "messages": [], "cost": 0.001, "total_cost": 0.001},
        {"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.001}},
    ])

    stats = parse_trajectory(traj)

    assert stats["exit_status"] == "Submitted"
    assert stats["total_steps"] == 1
    assert abs(stats["total_cost"] - 0.001) < 1e-9
    assert stats["errors"] == []


def test_parse_trajectory_normalized_tool_calls(tmp_path):
    """归一化 tool_calls 格式 → tool_calls Counter 正确更新。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {
            "step": 1,
            "messages": [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "c1", "name": "bash", "arguments": {}}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "content": "output",
                },
            ],
            "cost": 0.001,
        },
        {"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.001}},
    ])

    stats = parse_trajectory(traj)

    assert stats["tool_calls"]["bash"] == 1
    assert stats["errors"] == []


def test_parse_trajectory_openai_raw_tool_calls(tmp_path):
    """OpenAI raw 格式（function.name）→ tool_calls Counter 正确更新。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {
            "step": 1,
            "messages": [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {"name": "task_board", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "c2",
                    "content": "ok",
                },
            ],
            "cost": 0.002,
        },
        {"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.002}},
    ])

    stats = parse_trajectory(traj)

    assert stats["tool_calls"]["task_board"] == 1
    assert stats["errors"] == []


# ---------------------------------------------------------------------------
# parse_trajectory — 边界场景
# ---------------------------------------------------------------------------

def test_parse_trajectory_bad_json_line(tmp_path):
    """含坏 JSON 行 → errors 列表有记录，不 crash，其他行正常解析。"""
    traj = tmp_path / "run.jsonl"
    traj.write_text(
        '{"step": 1, "messages": [], "cost": 0.001}\n'
        "THIS IS NOT JSON\n"
        '{"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.001}}\n',
        encoding="utf-8",
    )

    stats = parse_trajectory(traj)

    assert len(stats["errors"]) == 1
    assert "JSON" in stats["errors"][0] or "parse" in stats["errors"][0].lower()
    # 其他行仍被正确解析
    assert stats["exit_status"] == "Submitted"


def test_parse_trajectory_no_exit_record(tmp_path):
    """无 exit 记录 → total_cost 从各 step cost 累加，exit_status 保持默认 'unknown'。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {"step": 1, "messages": [], "cost": 0.003, "total_cost": 0.003},
        {"step": 2, "messages": [], "cost": 0.002, "total_cost": 0.005},
    ])

    stats = parse_trajectory(traj)

    assert stats["exit_status"] == "unknown"
    # total_cost 从 step records 累加
    assert abs(stats["total_cost"] - 0.005) < 1e-9


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------

def test_format_report_contains_required_fields(tmp_path):
    """format_report 输出包含 path、exit_status、steps、cost。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {"step": 1, "messages": [], "cost": 0.001},
        {"exit": {"status": "LimitsExceeded", "total_steps": 5, "total_cost": 0.05}},
    ])

    stats = parse_trajectory(traj)
    report = format_report(stats)

    assert "LimitsExceeded" in report
    assert "5" in report          # total_steps
    assert "0.0500" in report     # total_cost


def test_format_report_tool_calls_shown(tmp_path):
    """有工具调用时，format_report 输出工具分布。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {
            "step": 1,
            "messages": [
                {"role": "assistant", "tool_calls": [{"id": "c1", "name": "bash", "arguments": {}}]},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            ],
            "cost": 0.001,
        },
        {"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.001}},
    ])

    stats = parse_trajectory(traj)
    report = format_report(stats)

    assert "bash" in report
    assert "Tool calls" in report


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------

def test_format_summary_single_entry_returns_empty(tmp_path):
    """只有 1 条轨迹 → format_summary 返回空字符串。"""
    traj = tmp_path / "run.jsonl"
    _write_jsonl(traj, [
        {"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.001}},
    ])
    stats = parse_trajectory(traj)

    assert format_summary([stats]) == ""


def test_format_summary_multiple_entries(tmp_path):
    """多条轨迹 → 汇总包含条数、状态分布。"""
    def _make_stats(status, steps, cost):
        traj = tmp_path / f"run_{status}.jsonl"
        _write_jsonl(traj, [
            {"exit": {"status": status, "total_steps": steps, "total_cost": cost}},
        ])
        return parse_trajectory(traj)

    all_stats = [
        _make_stats("Submitted", 3, 0.01),
        _make_stats("Submitted", 2, 0.02),
        _make_stats("LimitsExceeded", 10, 0.05),
    ]

    summary = format_summary(all_stats)

    assert "3" in summary           # 3 trajectories
    assert "Submitted" in summary
    assert "LimitsExceeded" in summary
