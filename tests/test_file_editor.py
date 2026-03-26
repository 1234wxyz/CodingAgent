"""
tests/test_file_editor.py — agent/tools/file_editor.py 单测（全离线）

覆盖场景：
  - str_replace 精确替换
  - str_replace old_str 不存在 → success=False, error 含 "not found"
  - str_replace old_str 出现多次 → success=False, error 含次数信息
  - view 全文带行号
  - view 行范围限制
  - create 创建文件
  - 未知 command → success=False
"""

import pytest

from agent.tools.file_editor import FileEditorTool


@pytest.fixture
def editor():
    return FileEditorTool()


# ---------------------------------------------------------------------------
# str_replace
# ---------------------------------------------------------------------------

def test_str_replace_success(editor, tmp_py_file):
    path = tmp_py_file("def foo():\n    return 1\n")
    obs = editor.execute({
        "command": "str_replace",
        "path": str(path),
        "old_str": "return 1",
        "new_str": "return 42",
    })
    assert obs.success
    assert path.read_text(encoding="utf-8") == "def foo():\n    return 42\n"


def test_str_replace_not_found(editor, tmp_py_file):
    path = tmp_py_file("def foo():\n    return 1\n")
    obs = editor.execute({
        "command": "str_replace",
        "path": str(path),
        "old_str": "return 999",
        "new_str": "return 0",
    })
    assert not obs.success
    assert "not found" in (obs.error or "").lower()


def test_str_replace_multiple_matches(editor, tmp_py_file):
    path = tmp_py_file("x = 1\nx = 1\n")
    obs = editor.execute({
        "command": "str_replace",
        "path": str(path),
        "old_str": "x = 1",
        "new_str": "x = 2",
    })
    assert not obs.success
    # error 里应包含出现次数信息（"2 times" 或 "found 2"）
    assert "2" in (obs.error or "")


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------

def test_view_full_file(editor, tmp_py_file):
    path = tmp_py_file("line one\nline two\nline three\n")
    obs = editor.execute({"command": "view", "path": str(path)})
    assert obs.success
    # 全文应包含行号前缀
    assert "1:" in obs.output
    assert "3:" in obs.output
    assert "line one" in obs.output
    assert "line three" in obs.output


def test_view_line_range(editor, tmp_py_file):
    path = tmp_py_file("a\nb\nc\nd\ne\n")
    obs = editor.execute({
        "command": "view",
        "path": str(path),
        "start_line": 2,
        "end_line": 4,
    })
    assert obs.success
    lines = obs.output.splitlines()
    # 只有 3 行（b, c, d）
    assert len(lines) == 3
    assert "b" in obs.output
    assert "d" in obs.output
    assert "a" not in obs.output
    assert "e" not in obs.output


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def test_create_file(editor, tmp_path):
    target = tmp_path / "new_file.py"
    obs = editor.execute({
        "command": "create",
        "path": str(target),
        "content": "print('hello')\n",
    })
    assert obs.success
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


# ---------------------------------------------------------------------------
# unknown command
# ---------------------------------------------------------------------------

def test_unknown_command(editor, tmp_py_file):
    path = tmp_py_file("")
    obs = editor.execute({"command": "delete", "path": str(path)})
    assert not obs.success
