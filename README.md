# coding-agent

> A minimal, shell-first Python coding agent with a thin explainable loop,
> middleware-based safety, and persistent multi-step task tracking.

一个面向本地代码库的极简 Python Coding Agent —— shell-first 架构，薄 loop 设计，中间件安全，持久化任务追踪。

---

## 快速开始

```bash
# 1. 克隆与安装
git clone <repo>
cd codingAgentProject
pip install -e ".[dev]"          # 需要 Python >= 3.11

# 2. 配置 .env
cat > .env <<'EOF'
MODEL_NAME=deepseek/deepseek-chat
DEEPSEEK_API_KEY=your_key_here
EOF

# 3. 启动
python main.py                   # 交互式本地代码助手
```

---

## 使用方式

### 交互模式

```bash
python main.py
```

进入 REPL，输入任务描述，agent 会调用工具、修改文件、运行测试，完成后给出摘要。

### 单次任务模式

```bash
python main.py --task "修复 calculator.py 中空列表的 ZeroDivisionError" --work-dir ./demo/bug_scenarios/zero_division
```

执行单个任务后退出，适合脚本集成。

### 场景验收 (真实 API)

```bash
python scripts/run_scenarios.py                    # 运行全部 demo 场景
python scripts/run_scenarios.py zero_division       # 运行单个场景
python scripts/run_scenarios.py --dry-run            # 仅列出可用场景
python scripts/run_scenarios.py --step-limit 15 --cost-limit 2.0
```

场景验收流程：复制 bug 场景到临时目录 → 启动 agent 修复 → 运行 `verify.py` 验收 → 汇总 pass/fail。

### 端到端示例

```bash
python examples/fix_bug.py       # 单文件 bug 修复 demo
```

---

## 架构

```text
agent/
├── app.py              # 应用装配：prompt、工具注册、中间件、CLI
├── core.py             # Agent loop：run → step → query → dispatch → trajectory
├── context.py          # System prompt 组装、输出截断、上下文压缩、历史总结
├── middleware.py        # 沙箱探测、bash 护栏、上下文压缩中间件
├── models.py           # litellm 统一适配层 (DeepSeek / Anthropic)
└── tools/
    ├── base.py             # Tool ABC + ToolObservation
    ├── bash.py             # Shell 执行 (stateless, cross-platform)
    ├── delegate.py         # 子 agent 隔离委托
    ├── registry.py         # 工具注册与分发
    ├── semantic_search.py  # Python 符号搜索 (tree-sitter)
    └── task_board.py       # 持久化多步任务板 (.tasks/)

scripts/
├── analyze.py          # 轨迹 JSONL 统计分析
└── run_scenarios.py    # Demo 场景自动化验收

demo/bug_scenarios/     # Bug 场景模板 (带 verify.py)
examples/fix_bug.py     # 端到端 demo
main.py                 # CLI 入口
```

---

## 关键设计

### 1. Shell-first

没有独立的 `file_editor` 工具。所有文件操作通过 `bash` 完成 —— 用 `sed`、`cat <<'EOF'`、或内联 `python -c` 编辑文件。Prompt 提供跨平台编辑示例。

### 2. 6 步工作流

运行时 prompt 强制模型按严格顺序执行，迁移自 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) 的 workflow-first 思想：

```
1. ANALYZE   — 阅读相关文件、搜索符号
2. REPRODUCE — 先跑失败用例，看到具体报错
3. FIX       — 做最小修改
4. VERIFY    — 重跑失败用例确认修复
5. EDGE CASES — 测试边界条件
6. FINISH    — 总结变更，停止调用工具
```

### 3. 中间件安全

`middleware.py` 负责三件事，不侵入 `core.py`：

| 中间件 | 职责 |
|--------|------|
| `BashSafetyMiddleware` | 拦截 `rm -rf /`、`sudo`、`git reset --hard` 等高风险命令 |
| `SandboxAwarenessMiddleware` | 探测运行环境并注入约束信息到 prompt |
| `ContextCompactionMiddleware` | 压缩旧工具输出，阈值触发时归档到 `.transcripts/` 并总结历史 |

### 4. 多步任务持久化

`task_board` 将任务写入 `.tasks/*.json`，支持依赖图。上下文压缩后计划不会丢失。

### 5. 格式错误自恢复

当模型产生无效工具调用时，`core.py` 会注入纠正反馈让模型重试（最多 2 次），而非直接终止。

---

## Demo 场景

| 场景 | 类型 | 描述 |
|------|------|------|
| `zero_division` | 运行时异常 | `average([])` 应返回 0.0 而非 ZeroDivisionError |
| `trailing_window` | Off-by-one | `trailing_window(items, 3)` 应返回 3 个元素 |
| `loyalty_checkout` | 多文件业务错误 | 未知客户等级应无折扣 |

每个场景包含 `scenario.json`（描述 + 验收命令）、业务源码、`verify.py`。

---

## 测试

```bash
pytest tests/ -v                         # 58 项离线测试，无需 API key
python scripts/analyze.py trajectories/  # 轨迹统计
```

---

## 运行产物

| 路径 | 内容 |
|------|------|
| `trajectories/*.jsonl` | 每轮 step / exit 轨迹 |
| `.tasks/*.json` | 多步任务状态 |
| `.transcripts/*.jsonl` | 上下文压缩前的完整历史 |

---

## 参考项目

- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — workflow-first prompt 节奏
- [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk) — tool schema / delegate pattern
- [DeepAgents](https://github.com/deepseek-ai/DeepAgents) — middleware 组合方式
- [serena](https://github.com/oraios/serena) — symbol-first 检索思路
