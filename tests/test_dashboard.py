"""
tests/test_dashboard.py — dashboard rendering and enhanced trajectory parsing.
"""

import json
from pathlib import Path

from scripts.dashboard import parse_enhanced_trajectory, render_dashboard, _bar


def test_bar_renders_proportionally():
    assert len(_bar(50, 100, width=10)) == 5
    assert len(_bar(100, 100, width=10)) == 10
    assert _bar(0, 100, width=10) == ""


def test_bar_handles_zero_max():
    assert _bar(50, 0, width=10) == ""


def test_parse_enhanced_trajectory(tmp_path):
    traj = tmp_path / "test.jsonl"
    entries = [
        {"step": 1, "messages": [{"role": "assistant", "content": "checking"}],
         "cost": 0.001, "total_cost": 0.001, "wall_time_ms": 150.5, "tool_names": ["bash"]},
        {"step": 2, "messages": [{"role": "assistant", "content": "done"}],
         "cost": 0.002, "total_cost": 0.003, "wall_time_ms": 200.0, "tool_names": []},
        {"exit": {"status": "Submitted", "total_steps": 2, "total_cost": 0.003}},
    ]
    traj.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    data = parse_enhanced_trajectory(traj)

    assert data["exit_status"] == "Submitted"
    assert data["total_steps"] == 2
    assert len(data["steps"]) == 2
    assert data["steps"][0]["wall_time_ms"] == 150.5
    assert data["steps"][0]["tool_names"] == ["bash"]
    assert len(data["decisions"]) >= 1


def test_render_dashboard_does_not_crash(tmp_path):
    traj = tmp_path / "test.jsonl"
    entries = [
        {"step": 1, "messages": [{"role": "assistant", "content": "hi"}],
         "cost": 0.001, "total_cost": 0.001, "wall_time_ms": 100, "tool_names": ["bash"]},
        {"exit": {"status": "Submitted", "total_steps": 1, "total_cost": 0.001}},
    ]
    traj.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    output = render_dashboard(traj)
    assert "Dashboard" in output
    assert "Submitted" in output
