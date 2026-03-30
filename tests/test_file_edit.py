"""
tests/test_file_edit.py -- FileEditTool: view, replace, create with boundary checks.
"""

from pathlib import Path

from agent.tools.file_edit import FileEditTool


def test_view_shows_line_numbers(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "view", "path": "hello.py"})

    assert obs.success
    assert "   1 | line1" in obs.output
    assert "   2 | line2" in obs.output
    assert "   3 | line3" in obs.output


def test_view_line_range(tmp_path):
    f = tmp_path / "nums.py"
    f.write_text("\n".join(f"L{i}" for i in range(1, 11)), encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "view", "path": "nums.py", "start_line": 3, "end_line": 5})

    assert obs.success
    assert "   3 | L3" in obs.output
    assert "   5 | L5" in obs.output
    assert "L1" not in obs.output
    assert "L6" not in obs.output


def test_view_missing_file(tmp_path):
    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "view", "path": "nonexistent.py"})

    assert not obs.success
    assert "not found" in obs.error.lower()


def test_replace_exact_match(tmp_path):
    f = tmp_path / "calc.py"
    f.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "replace",
        "path": "calc.py",
        "old_text": "return a - b",
        "new_text": "return a + b",
    })

    assert obs.success
    assert "Replaced 1 occurrence" in obs.output
    assert f.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"


def test_replace_not_found(tmp_path):
    f = tmp_path / "calc.py"
    f.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "replace",
        "path": "calc.py",
        "old_text": "return a * b",
        "new_text": "return a / b",
    })

    assert not obs.success
    assert "not found" in obs.error.lower()


def test_replace_ambiguous(tmp_path):
    f = tmp_path / "dup.py"
    f.write_text("x = 1\nx = 1\n", encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "replace",
        "path": "dup.py",
        "old_text": "x = 1",
        "new_text": "x = 2",
    })

    assert not obs.success
    assert "2 locations" in obs.error
    # File should be unchanged
    assert f.read_text(encoding="utf-8") == "x = 1\nx = 1\n"


def test_replace_multiline(tmp_path):
    f = tmp_path / "multi.py"
    f.write_text(
        "def foo():\n    if True:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "replace",
        "path": "multi.py",
        "old_text": "    if True:\n        return 1\n    return 0",
        "new_text": "    return 42",
    })

    assert obs.success
    assert f.read_text(encoding="utf-8") == "def foo():\n    return 42\n"


def test_create_new_file(tmp_path):
    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "create",
        "path": "new_file.py",
        "content": "print('hello')\n",
    })

    assert obs.success
    assert (tmp_path / "new_file.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_create_overwrites(tmp_path):
    f = tmp_path / "old.py"
    f.write_text("old content", encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "create",
        "path": "old.py",
        "content": "new content",
    })

    assert obs.success
    assert f.read_text(encoding="utf-8") == "new content"


def test_boundary_rejects_escape(tmp_path):
    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({
        "command": "view",
        "path": "../../../etc/passwd",
    })

    assert not obs.success
    assert "outside workspace" in obs.error.lower()


def test_boundary_allows_relative(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "mod.py").write_text("x = 1\n", encoding="utf-8")

    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "view", "path": "src/mod.py"})

    assert obs.success
    assert "x = 1" in obs.output


def test_replace_missing_old_text_arg(tmp_path):
    (tmp_path / "f.py").write_text("x = 1\n", encoding="utf-8")
    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "replace", "path": "f.py", "new_text": "x = 2"})

    assert not obs.success
    assert "old_text" in obs.error.lower()


def test_create_missing_content_arg(tmp_path):
    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "create", "path": "f.py"})

    assert not obs.success
    assert "content" in obs.error.lower()


def test_unknown_command(tmp_path):
    tool = FileEditTool(work_dir=tmp_path)
    obs = tool.execute({"command": "delete", "path": "f.py"})

    assert not obs.success
    assert "Unknown command" in obs.error
