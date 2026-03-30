"""
tests/test_bash.py -- BashTool unit tests: cwd, env overrides, output truncation.
"""

import sys

from agent.tools.bash import BashTool, _build_clean_env


def test_cwd_is_respected(tmp_path):
    """BashTool(work_dir=X) should run commands inside X."""
    tool = BashTool(work_dir=tmp_path)
    obs = tool.execute({"command": 'python -c "import os; print(os.getcwd())"'})
    assert obs.success
    assert str(tmp_path.resolve()) in obs.output.strip()


def test_env_overrides_pip_progress_bar():
    """PIP_PROGRESS_BAR=off should always be set, regardless of platform."""
    env = _build_clean_env()
    assert env["PIP_PROGRESS_BAR"] == "off"
    assert env["TQDM_DISABLE"] == "1"
    assert env["NO_COLOR"] == "1"


def test_env_overrides_pager_unix():
    """On non-Windows, PAGER/GIT_PAGER/MANPAGER should be set to 'cat'."""
    if sys.platform == "win32":
        env = _build_clean_env()
        assert env.get("GIT_PAGER") == ""
    else:
        env = _build_clean_env()
        assert env["PAGER"] == "cat"
        assert env["GIT_PAGER"] == "cat"


def test_long_output_truncated_with_head_and_tail(tmp_path):
    """Output exceeding _OUTPUT_MAX should have head + <warning> + tail."""
    tool = BashTool(work_dir=tmp_path)
    # Generate output well over 10000 chars
    obs = tool.execute({"command": 'python -c "print(\'A\' * 20000)"'})
    assert obs.success
    assert "<warning>" in obs.output
    assert "omitted" in obs.output
    # Should contain beginning (all A's)
    assert obs.output.startswith("A")
    # Should contain end (all A's after warning)
    assert obs.output.rstrip().endswith("A")


def test_default_cwd_when_no_work_dir():
    """BashTool() without work_dir should still work (inherit process cwd)."""
    tool = BashTool()
    obs = tool.execute({"command": 'python -c "print(1+1)"'})
    assert obs.success
    assert "2" in obs.output
