"""
tests/test_semantic_search.py — agent/tools/semantic_search.py 单测（全离线）

覆盖场景：
  - list_symbols：能列出函数/类定义
  - list_symbols：非 Python 文件 → 优雅返回，不 crash
  - find_symbol：跨目录找到符号
  - find_symbol：缺少 name 参数 → success=False
  - get_context：返回目标行所在函数/类的代码块
  - get_context：行号不在任何函数/类内 → success=True，提示信息
  - 未知 command → success=False
"""

import pytest

from agent.tools.semantic_search import SemanticSearchTool


@pytest.fixture
def tool():
    return SemanticSearchTool()


# ---------------------------------------------------------------------------
# list_symbols
# ---------------------------------------------------------------------------

def test_list_symbols_functions_and_classes(tool, tmp_path):
    """含函数和类的 .py 文件 → output 包含符号名称。"""
    src = tmp_path / "sample.py"
    src.write_text(
        "class Foo:\n    def method(self):\n        pass\n\ndef bar():\n    return 1\n",
        encoding="utf-8",
    )

    obs = tool.execute({"command": "list_symbols", "path": str(src)})

    assert obs.success
    assert "Foo" in obs.output
    assert "bar" in obs.output


def test_list_symbols_non_py_file(tool, tmp_path):
    """非 .py 文件 → success=True，不报错，返回提示。"""
    txt = tmp_path / "readme.txt"
    txt.write_text("hello", encoding="utf-8")

    obs = tool.execute({"command": "list_symbols", "path": str(txt)})

    assert obs.success
    assert "[SyntaxCheck]" not in obs.output  # 不触发语法检查附加信息
    # 输出应该友好地说明文件不是 Python 或没有找到符号
    assert obs.output  # 不为空


def test_list_symbols_missing_path(tool):
    """path 为空 → success=False，error 含提示。"""
    obs = tool.execute({"command": "list_symbols", "path": ""})

    assert not obs.success
    assert obs.error


# ---------------------------------------------------------------------------
# find_symbol
# ---------------------------------------------------------------------------

def test_find_symbol_across_directory(tool, tmp_path):
    """在目录下的多个 .py 文件中找到符号。"""
    (tmp_path / "a.py").write_text("def calculate():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class Calculator:\n    pass\n", encoding="utf-8")

    obs = tool.execute({"command": "find_symbol", "name": "calculate", "directory": str(tmp_path)})

    assert obs.success
    # 'calculate' 应匹配 calculate (function) 和 Calculator (class, partial match)
    assert "calculate" in obs.output.lower()


def test_find_symbol_missing_name(tool, tmp_path):
    """缺少 name 参数 → success=False。"""
    obs = tool.execute({"command": "find_symbol", "directory": str(tmp_path)})

    assert not obs.success
    assert obs.error


def test_find_symbol_not_found(tool, tmp_path):
    """目录里没有匹配符号 → success=True，提示未找到。"""
    (tmp_path / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")

    obs = tool.execute({"command": "find_symbol", "name": "nonexistent_xyz", "directory": str(tmp_path)})

    assert obs.success
    assert "not found" in obs.output.lower() or "nonexistent_xyz" in obs.output


# ---------------------------------------------------------------------------
# get_context
# ---------------------------------------------------------------------------

def test_get_context_inside_function(tool, tmp_path):
    """目标行在函数体内 → 返回函数定义代码块。"""
    src = tmp_path / "code.py"
    src.write_text(
        "def greet(name):\n    return f'Hello, {name}'\n\nx = 1\n",
        encoding="utf-8",
    )

    # line 2 is inside greet()
    obs = tool.execute({"command": "get_context", "path": str(src), "line": 2})

    assert obs.success
    assert "greet" in obs.output
    assert "Hello" in obs.output


def test_get_context_outside_any_symbol(tool, tmp_path):
    """目标行在模块顶层（不在任何函数/类内）→ success=True，提示不在任何符号内。"""
    src = tmp_path / "code.py"
    src.write_text("x = 1\ny = 2\n\ndef foo():\n    pass\n", encoding="utf-8")

    # line 1 (x = 1) is at module level
    obs = tool.execute({"command": "get_context", "path": str(src), "line": 1})

    assert obs.success
    assert "not inside" in obs.output.lower() or "no" in obs.output.lower()


def test_get_context_missing_line(tool, tmp_path):
    """缺少 line 参数 → success=False。"""
    src = tmp_path / "code.py"
    src.write_text("def foo():\n    pass\n", encoding="utf-8")

    obs = tool.execute({"command": "get_context", "path": str(src)})

    assert not obs.success
    assert obs.error


# ---------------------------------------------------------------------------
# unknown command
# ---------------------------------------------------------------------------

def test_unknown_command(tool):
    """未知 command → success=False，error 含说明。"""
    obs = tool.execute({"command": "explode"})

    assert not obs.success
    assert obs.error
