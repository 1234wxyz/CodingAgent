# coding-agent

一个面向本地代码库的极简 Python Coding Agent。它保留了可解释的薄 loop 设计，但现在改成了更贴近真实使用的 shell-first 形态：

- 文件读写统一走 `bash`
- 中间件负责 bash 风险拦截、沙箱感知、上下文压缩
- 多步工作通过持久化 `task_board` 追踪
- `main.py` 提供一个带 ANSI 高亮的本地代码助手入口

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

```env
MODEL_NAME=deepseek/deepseek-chat
DEEPSEEK_API_KEY=your_key_here

# 如果要切到 Claude / Anthropic，可改成：
# MODEL_NAME=anthropic/your-model
# ANTHROPIC_API_KEY=...
```

---

## 快速运行

离线测试：

```bash
pytest tests/ -v
```

交互式本地代码助手：

```bash
python main.py
```

端到端示例：

```bash
python examples/fix_bug.py
```

---

## 架构概览

```text
agent/
├── app.py           # 本地代码助手装配：prompt、工具、中间件、CLI 交互
├── core.py          # Agent loop：run -> step -> query -> dispatch -> trajectory
├── context.py       # System prompt 组装、输出截断、工具结果压缩、历史总结
├── middleware.py    # 沙箱探测、bash 护栏、上下文压缩中间件
├── models.py        # litellm 统一适配层
└── tools/
    ├── base.py          # Tool ABC + ToolObservation
    ├── bash.py          # Host shell execution（工具名保留为 bash）
    ├── delegate.py      # 子 agent 隔离执行
    ├── registry.py      # ToolRegistry
    ├── semantic_search.py  # Python symbol search via tree-sitter
    └── task_board.py    # 持久化多步任务板（.tasks/）

examples/
└── fix_bug.py       # 用完整助手栈修复一个 Python bug

main.py              # 交互式 CLI 入口

tests/
├── test_analyze.py
├── test_context.py
├── test_core.py
├── test_delegate.py
├── test_middleware.py
├── test_semantic_search.py
└── test_task_board.py
```

---

## 关键设计

### 1. Shell-first，而不是 file_editor-first

仓库不再维护 `file_editor`。统一通过 `bash` 执行读取、修改、测试命令，提示词会明确告诉模型：需要编辑文件时使用 shell 命令或内联 Python。

### 2. 中间件负责安全与上下文卫生

`middleware.py` 现在主要做三件事：

- `detect_sandbox()`：探测运行环境与写权限
- `BashSafetyMiddleware`：拦截高风险命令，例如 `rm -rf /`、`git reset --hard`
- `ContextCompactionMiddleware`：在 LLM 调用前压缩旧工具结果，并在阈值触发时写入 `.transcripts/` 后总结历史

### 3. 多步任务落盘，避免被压缩丢失

`task_board` 把任务保存到 `.tasks/`。当需求跨越多个重要步骤、多文件或存在依赖关系时，模型应该先建 task，再推进实现和验证。

### 4. Prompt 借鉴 mini-swe-agent 的节奏感

运行时 prompt 没有照搬 `default.yaml` 的单命令代码块格式，但保留了它的几个核心思想：

- 每一步只做一个清晰动作
- 先理解再修改
- 修改后必须验证
- 完成时输出简洁总结

---

## 轨迹与压缩产物

- `trajectories/*.jsonl`：每轮运行的 step / exit 轨迹
- `.tasks/`：多步任务 JSON
- `.transcripts/`：上下文压缩前保存的完整历史

使用 `python scripts/analyze.py trajectories/` 可以查看轨迹统计。

---

## 参考项目

- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — workflow-first prompt 节奏
- [software-agent-sdk](https://github.com/anthropics/claude-agent-sdk) — tool schema / delegate pattern
- [deepagents](https://github.com/deepseek-ai/DeepAgents) — middleware 组合方式
- [serena](https://github.com/oraios/serena) — symbol-first 检索思路
