"""
examples/fix_bug.py — 端到端演示：用 DeepSeek 自动修复一个 Python bug

场景：
  有一个 calculate_average() 函数，当传入空列表时会触发 ZeroDivisionError。
  Agent 会通过 view + str_replace 完成修复，无需人工介入。

运行前提：
  在项目根目录创建 .env 文件，写入：
    DEEPSEEK_API_KEY=your_key_here

运行方式：
  python examples/fix_bug.py
"""

import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. 加载 .env（内嵌，无需额外安装 python-dotenv）
# ---------------------------------------------------------------------------

def _load_dotenv(dotenv_path: Path | None = None) -> None:
    """从 .env 文件加载环境变量（简单 key=value 解析，支持行注释）。"""
    if dotenv_path is None:
        # 从当前文件向上查找 .env
        dotenv_path = Path(__file__).parent.parent / ".env"
    if not dotenv_path.is_file():
        return
    with dotenv_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


# ---------------------------------------------------------------------------
# 2. 导入 agent 模块
# ---------------------------------------------------------------------------

# 确保项目根目录在 sys.path 中（直接运行脚本时需要）
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent.core import Agent
from agent.models import LLMModel
from agent.tools.file_editor import FileEditorTool
from agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 3. 准备带 bug 的示例文件
# ---------------------------------------------------------------------------

BUGGY_CODE = '''\
def calculate_average(numbers):
    """计算列表平均值。"""
    total = sum(numbers)
    return total / len(numbers)  # bug: 空列表时 ZeroDivisionError


if __name__ == "__main__":
    print(calculate_average([1, 2, 3]))
    print(calculate_average([]))   # 会崩溃
'''


def _create_bug_file() -> Path:
    """在系统临时目录创建带 bug 的示例文件，返回路径。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="coding_agent_demo_"))
    bug_file = tmp_dir / "bug_example.py"
    bug_file.write_text(BUGGY_CODE, encoding="utf-8")
    return bug_file


# ---------------------------------------------------------------------------
# 4. 组装消息与 Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a Python debugging assistant. When asked to fix a bug:
1. First use file_editor (view) to read the file.
2. Then use file_editor (str_replace) to apply the fix.
3. Finally, confirm the fix with a brief explanation.
Keep your edits minimal and correct.
"""


def _build_messages(bug_file: Path) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Please fix the bug in: {bug_file}\n\n"
                "Problem: calculate_average([]) raises ZeroDivisionError "
                "because it divides by len([]) which is 0.\n"
                "Expected fix: return 0.0 when the input list is empty."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[ERROR] DEEPSEEK_API_KEY not found. Create a .env file with DEEPSEEK_API_KEY=...")
        sys.exit(1)

    # 创建带 bug 的文件
    bug_file = _create_bug_file()
    print(f"[Demo] Bug file created at: {bug_file}")
    print(f"[Demo] Original content:\n{'-' * 40}")
    print(bug_file.read_text(encoding="utf-8"))
    print("-" * 40)

    # 初始化工具注册表（只需要 file_editor，无需 bash）
    registry = ToolRegistry()
    registry.register(FileEditorTool())

    # 初始化 LLM（deepseek/deepseek-chat，工具 schema 注入）
    model = LLMModel(
        model_name="deepseek/deepseek-chat",
        model_kwargs={"tools": registry.get_schemas()},
    )

    # 组装 Agent（step_limit=10 防止意外死循环，trajectory 可选）
    agent = Agent(
        model,
        tool_executor=registry.execute,
        step_limit=10,
        cost_limit=1.0,
    )

    # 运行
    messages = _build_messages(bug_file)
    print("[Demo] Running agent...")
    result = agent.run(messages)

    print(f"\n[Demo] Agent finished: status={result['status']}, "
          f"steps={result['total_steps']}, cost=${result['total_cost']:.4f}")

    if result["final_content"]:
        print(f"\n[Demo] Agent says:\n{result['final_content']}")

    # 展示修复后的文件内容
    print(f"\n[Demo] Fixed content:\n{'-' * 40}")
    print(bug_file.read_text(encoding="utf-8"))
    print("-" * 40)


if __name__ == "__main__":
    main()
