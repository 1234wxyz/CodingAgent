# coding-agent

一个极简 LLM 驱动的 Python 编程 Agent，用于演示可解释的工具调用循环设计。

---

## 安装

```bash
git clone <repo>
cd codingAgentProject
pip install -e ".[dev]"
# 或使用 uv
uv sync --dev
```

---

## 配置

在项目根目录创建 `.env`：

```
DEEPSEEK_API_KEY=your_key_here
# 或使用其他 litellm 支持的 provider
# ANTHROPIC_API_KEY=...
# OPENAI_API_KEY=...
```

---

## 快速运行

**离线测试（无需 API key）：**

```bash
pytest tests/ -v
```

**端到端演示（需要 DeepSeek API key）：**

```bash
python examples/fix_bug.py
```

Agent 会自动读取一个包含 ZeroDivisionError 的函数，并通过工具调用完成修复。

---

## 架构概览

```
agent/
├── core.py          # Agent loop：run → step → query → dispatch → trajectory
├── models.py        # LLM 适配层（litellm 统一接口，返回归一化 assistant_message）
├── middleware.py    # Step 级别钩子（Middleware ABC + SyntaxCheckMiddleware）
├── context.py       # System prompt 组装（ContextBuilder + 历史压缩）
└── tools/
    ├── base.py          # Tool ABC + ToolObservation
    ├── registry.py      # ToolRegistry（注册 / 查找 / 执行）
    ├── bash.py          # BashTool（subprocess，无状态）
    ├── file_editor.py   # FileEditorTool（str_replace / view / create）
    ├── delegate.py      # DelegateTool（子 Agent 隔离执行）
    └── semantic_search.py  # SemanticSearchTool（tree-sitter AST 检索）

scripts/
└── analyze.py      # Trajectory JSONL 分析工具

examples/
└── fix_bug.py      # DeepSeek 端到端演示

tests/
├── conftest.py          # 共享 fixtures（make_model / recording_executor）
├── test_core.py         # Agent loop 单测（8 场景，全离线）
├── test_file_editor.py  # FileEditorTool 单测（7 场景）
└── test_middleware.py   # Middleware 单测（5 场景）
```

**关键接线点：**

| 接口 | 类型 | 说明 |
|------|------|------|
| `model.query(messages)` | `list[dict] -> dict` | 返回 `assistant_message`（含归一化 `tool_calls`） |
| `tool_executor(name, arguments)` | `(str, dict) -> str` | Agent 调用工具的唯一入口 |
| `registry.execute` | 实现上述签名 | 直接传给 `Agent(tool_executor=registry.execute)` |

---

## 核心设计决策

**1. 极薄的 core.py，不做平台化**

`Agent` 只做四件事：检查限制、调用模型、分发工具调用、写 trajectory。
所有扩展（工具注册、prompt 管理、中间件）通过注入完成，不侵入主循环。

*为什么：* 面试场景下可解释性 > 平台化。每一行都能追溯到一个明确的设计理由。

**2. 异常驱动的控制流**

`Submitted`、`LimitsExceeded`、`FormatError` 是异常，不是返回码。
`run()` 用 `try/except/finally` 统一处理，保证 trajectory 在任何情况下都会落盘。

*为什么：* 避免 `if/else` 状态机在多层调用中传递 sentinel 值，break/continue 语义更清晰。

**3. tool_executor 作为接线点，而不是 registry 直接注入 core**

`Agent` 只知道一个 `(name, arguments) -> str` 的 callable，不知道 `ToolRegistry`。
这让 `SyntaxCheckMiddleware` 可以用包装器模式零侵入地增强工具执行，而不需要改 `core.py`。

**4. 两种格式共存：OpenAI raw vs 归一化**

litellm 的 tool_calls 是 OpenAI 格式（`function.name`、`function.arguments` 是 JSON 字符串）。
`models.py` 额外返回 `_normalized_tool_calls`（`{id, name, arguments dict}`）供 `core.py` 直接使用。
mock 测试通过 `tool_calls` 字段直接传归一化格式（fallback 分支），无需模拟完整的 litellm 响应。

---

## 参考项目

- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — 薄 loop 设计
- [software-agent-sdk](https://github.com/anthropics/claude-agent-sdk) — tool schema 协议
- [deepagents](https://github.com/deepseek-ai/DeepAgents) — middleware 挂载模式
- [serena](https://github.com/oraios/serena) — symbol-first 代码检索思路
