"""
tests/test_middleware.py — agent/middleware.py 单测（全离线）

覆盖场景：
  - SyntaxCheckMiddleware：合法 .py → observation 不变
  - SyntaxCheckMiddleware：语法错误 .py → observation 末尾含 [SyntaxCheck] ERROR
  - SyntaxCheckMiddleware：非 .py 文件 → observation 不变
  - SyntaxCheckMiddleware：bash 工具 → observation 不变
  - Middleware 子类：pre_step / post_step 均被调用
"""

import pytest

from agent.middleware import Middleware, SyntaxCheckMiddleware


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------

def _make_executor(response="ok"):
    """创建固定返回值的 mock executor，模拟 file_editor 调用。"""
    def _exec(name, arguments):
        return response
    return _exec


# ---------------------------------------------------------------------------
# SyntaxCheckMiddleware
# ---------------------------------------------------------------------------

def test_syntax_check_valid_py(tmp_py_file):
    """合法 .py 文件 → observation 不变，不含 [SyntaxCheck]。"""
    path = tmp_py_file("def foo():\n    return 1\n")
    executor = _make_executor("written ok")
    checker = SyntaxCheckMiddleware(executor)

    obs = checker("file_editor", {"command": "create", "path": str(path)})

    assert obs == "written ok"
    assert "[SyntaxCheck]" not in obs


def test_syntax_check_invalid_py(tmp_py_file):
    """语法错误 .py 文件 → observation 末尾追加 [SyntaxCheck] ERROR。"""
    path = tmp_py_file("def foo(:\n    pass\n")  # 故意语法错误
    executor = _make_executor("written ok")
    checker = SyntaxCheckMiddleware(executor)

    obs = checker("file_editor", {"command": "create", "path": str(path)})

    assert "[SyntaxCheck] ERROR" in obs


def test_syntax_check_skips_non_py(tmp_path):
    """非 .py 文件 → observation 不变，不触发语法检查。"""
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("hello", encoding="utf-8")
    executor = _make_executor("written ok")
    checker = SyntaxCheckMiddleware(executor)

    obs = checker("file_editor", {"command": "create", "path": str(txt_file)})

    assert obs == "written ok"
    assert "[SyntaxCheck]" not in obs


def test_syntax_check_skips_bash():
    """bash 工具（非 file_editor）→ observation 不变。"""
    executor = _make_executor("bash output")
    checker = SyntaxCheckMiddleware(executor)

    obs = checker("bash", {"command": "ls"})

    assert obs == "bash output"
    assert "[SyntaxCheck]" not in obs


# ---------------------------------------------------------------------------
# Middleware ABC — pre_step / post_step
# ---------------------------------------------------------------------------

def test_middleware_pre_post_called(make_model):
    """自定义 Middleware 子类，pre_step / post_step 均被调用且顺序正确。"""
    from agent.core import Agent
    from tests.conftest import text_response

    log = []

    class LogMiddleware(Middleware):
        def pre_step(self, agent):
            log.append("pre")

        def post_step(self, agent):
            log.append("post")

    model = make_model([text_response("done")])
    agent = Agent(model, middlewares=[LogMiddleware()])
    agent.run([{"role": "user", "content": "hi"}])

    assert log == ["pre", "post"]
