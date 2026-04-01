# Coding Agent

一个从零构建的 Python Coding Agent —— 核心循环仅 ~340 行，通过 middleware 实现安全与上下文管理，通过 tool-calling 扩展能力，具备完整的评测、观测和多 Agent 协作支持。

<!-- 项目演示 GIF 占位 -->
<!-- 建议素材：录制一次 loyalty_checkout 场景的完整修复过程（从 python main.py --task ... 到 verify.py 通过），约 30-60 秒，展示 streaming 输出、工具调用、最终总结 -->

---

## 特性一览

- **极简内核** — Agent 循环 ~340 行，职责单一：query → dispatch → trajectory
- **混合编辑** — `file_edit`（确定性文本替换）+ `bash`（Shell 执行），兼顾精确与灵活
- **Middleware 安全** — 12 条 bash 风险规则、沙箱感知、上下文自动压缩，全部通过 hook 注入，不侵入循环
- **多 Agent 协作** — `delegate` 工具支持 explorer / reviewer / tester 三种角色的子 Agent
- **结构化符号搜索** — 基于 tree-sitter 的 Python 符号级搜索，无需启动 LSP
- **完整评测体系** — 6 个 Demo 场景 + 5 个 Benchmark 实例 + Trajectory Dashboard + Prompt A/B 对比
- **API 韧性** — 指数退避重试 + 模型降级链 + Streaming 输出
- **跨平台** — Windows / macOS / Linux，自动处理 UTF-8 编码和平台差异化 Shell 规则

---

## 快速开始

### 环境配置

```bash
# 创建 conda 环境
conda create -n coding-agent python=3.11 -y
conda activate coding-agent

# 安装项目
git clone https://github.com/1234wxyz/CodingAgent.git
cd CodingAgent
pip install -e ".[dev]"
```

### 配置 API Key

```bash
# 在项目根目录创建 .env 文件
# 支持 DeepSeek、Claude 等 litellm 兼容的模型
cat > .env <<'EOF'
MODEL_NAME=deepseek/deepseek-chat
DEEPSEEK_API_KEY=your_key_here
EOF
```

### 运行

```bash
python main.py                   # 交互模式（streaming 输出）
```

---

## 使用方式

### 交互模式

```bash
python main.py
```

输入任务描述，Agent 自动调用工具、编辑代码、运行测试、输出总结。支持 token 级 streaming 实时输出。

### 单任务模式

```bash
python main.py --task "Fix the ZeroDivisionError in calculator.py" \
               --work-dir ./demo/bug_scenarios/zero_division
```

### Demo 场景验证

```bash
python scripts/run_scenarios.py                      # 运行全部 6 个场景
python scripts/run_scenarios.py zero_division         # 运行单个场景
python scripts/run_scenarios.py --prompt-version v2   # 指定 prompt 版本
python scripts/run_scenarios.py --dry-run             # 仅列出可用场景
```

### Benchmark 评测

```bash
python scripts/benchmark.py                           # 运行全部 5 个实例
python scripts/benchmark.py csv_quoting               # 运行单个实例
python scripts/benchmark.py --dry-run                 # 列出可用实例
```

<!-- Benchmark 结果截图占位 -->
<!-- 建议素材：运行 python scripts/benchmark.py 后的终端输出截图，展示 5/5 pass 的表格和耗时 -->

### Trajectory Dashboard

```bash
python scripts/dashboard.py trajectories/             # 查看最新轨迹
python scripts/dashboard.py path/to/trajectory.jsonl  # 查看指定轨迹
```

<!-- Dashboard 截图占位 -->
<!-- 建议素材：dashboard.py 输出的终端截图，展示 step timeline、tool 频率直方图、cost 曲线 -->

### Prompt A/B 对比

```bash
python scripts/compare_prompts.py v1 v2               # 对比两个 prompt 版本
python scripts/compare_prompts.py v1 v2 --dry-run     # 预览对比方案
```

---

## 项目架构

<p align="center">
  <img src="assets/architecture.svg" alt="项目架构图" width="780">
</p>

### 文件结构

```
agent/                          # Agent 核心
├── core.py                     # 执行循环（~340 行）
├── app.py                      # 应用组装、CLI、UI、Streaming
├── context.py                  # Prompt 构建、YAML 加载、上下文压缩
├── middleware.py                # 安全拦截、沙箱感知、上下文管理
├── models.py                   # LLM 适配器（litellm）、重试、降级
├── encoding.py                 # Windows UTF-8 编码处理
└── tools/
    ├── file_edit.py            # 确定性文件编辑（view/replace/create）
    ├── bash.py                 # 跨平台 Shell 执行
    ├── semantic_search.py      # tree-sitter Python 符号搜索
    ├── task_board.py           # 持久化多步任务追踪
    ├── delegate.py             # 角色化子 Agent 委派
    └── registry.py             # 工具注册与 Schema 分发

scripts/                        # 评测与观测工具
├── benchmark.py                # Benchmark 评测（pass@1 记分卡）
├── run_scenarios.py            # Demo 场景自动验证
├── dashboard.py                # 终端 ASCII Dashboard
├── analyze.py                  # Trajectory 统计分析
├── compare_prompts.py          # Prompt 版本 A/B 对比
└── generate_architecture.py    # 架构图 SVG 生成

prompts/                        # 版本化 System Prompt（YAML）
├── v1.yaml                     # 标准工作流（5 步 + 可选扩展检查）
└── v2.yaml                     # 严格精简变体

demo/bug_scenarios/             # 6 个 Bug 修复场景（含 verify.py）
benchmarks/                     # 5 个 Benchmark 实例（含自动评测）
tests/                          # 115 个离线测试（无需 API Key）
```

---

## 关键设计

### 极简循环 + Middleware 分离

`core.py` 仅负责 `run → step → query → dispatch → trajectory`，所有安全策略和上下文管理通过 middleware 的 `pre_step` / `post_step` hook 注入：

| Middleware | 职责 |
|-----------|------|
| **BashSafety** | 拦截 `rm -rf /`、`sudo`、`git reset --hard` 等 12 类危险命令 |
| **SandboxAwareness** | 探测运行环境，将约束信息注入 system prompt |
| **ContextCompaction** | token 超限时自动压缩历史（LLM 摘要 + 旧输出截断 + 存档） |
| **Reflection** | 完成前自我审查（默认关闭，`AGENT_REFLECTION=1` 启用） |

### 混合编辑策略

结合两种编辑路径，取长补短：

- **`file_edit`** — 确定性文本查找替换，处理多行编辑不会出现 Shell 转义问题
- **`bash`** — 运行测试、执行命令、处理复杂文件操作

prompt 引导 Agent 优先使用 `file_edit replace` 进行代码修改，用 `bash` 运行验证命令。

### 工作流纪律

System prompt 强制执行严格的操作顺序，每步只做一件事：

```
1. ANALYZE  → 阅读代码，定位问题
2. REPRODUCE → 运行失败的验证命令
3. FIX      → 最小化修改
4. VERIFY   → 重新运行验证命令
5. FINISH   → 验证通过即结束，总结修复内容
```

**可选**：仅在原始验证遗留具体风险时才运行额外检查。

### 多 Agent 协作

`delegate` 工具支持将子问题委派给隔离上下文的子 Agent：

| 角色 | 职责 |
|------|------|
| `explorer` | 代码调查：查找文件、梳理调用链 |
| `reviewer` | 质量审查：正确性、边界情况、副作用 |
| `tester` | 测试执行：运行测试、验证覆盖率 |

### 工作区边界保护

所有工具（`file_edit`、`semantic_search`、`bash`）的路径操作都受 `work_dir` 约束。相对路径基于工作目录解析，访问外部路径会收到警告或拒绝，防止 Agent 在临时工作区运行时发生路径漂移。

### Prompt 版本化

System prompt 以 YAML 文件存储在 `prompts/` 目录，运行时通过 `AGENT_PROMPT_VERSION=v2` 或 `--prompt-version v2` 切换。`compare_prompts.py` 支持两个版本在同一场景集上的 A/B 对比。

---

## 评测能力

### Demo 场景

6 个精心设计的 bug 修复场景，覆盖常见 Python 错误类型：

| 场景 | 错误类型 | 描述 |
|------|---------|------|
| `zero_division` | 运行时异常 | `average([])` 应返回 `0.0`，而非抛出 ZeroDivisionError |
| `trailing_window` | Off-by-one | `trailing_window(items, 3)` 应返回 3 个元素 |
| `loyalty_checkout` | 多文件逻辑 | 未知客户等级不应获得折扣 |
| `type_error` | 类型错误 | `int + str` 拼接失败 |
| `import_cycle` | 循环导入 | 多文件循环依赖 |
| `missing_return` | 控制流 | 函数缺少 return 语句 |

### Benchmark 实例

5 个源自真实开源模式的 benchmark 实例：

| 实例 | Bug 类型 | 来源模式 |
|------|---------|---------|
| `dict_merge_overwrite` | 浅拷贝变异 | Django settings 合并 |
| `csv_quoting` | 缺少字段引号 | 数据处理库 |
| `datetime_edge` | 日期边界 | 调度库 |
| `regex_escape` | 正则特殊字符 | 搜索工具 |
| `recursion_depth` | 递归深度限制 | 数据转换 |

### 测试

```bash
pytest tests/ -v                  # 115 个离线测试（无需 API Key）
python scripts/run_scenarios.py   # 6 个 Demo 场景（需 API Key）
python scripts/benchmark.py       # 5 个 Benchmark 实例（需 API Key）
```

---

## 项目数据

| 指标 | 数值 |
|------|------|
| 核心循环 (core.py) | ~340 行 |
| Agent 总代码量 | ~1,950 行 |
| 工具数 | 6（file_edit, bash, semantic_search, task_board, delegate, registry） |
| Middleware 数 | 4（BashSafety, SandboxAwareness, ContextCompaction, Reflection） |
| 离线测试 | 115 |
| Demo 场景 | 6 |
| Benchmark 实例 | 5 |
| Prompt 版本 | 2（YAML 格式，支持 A/B 对比） |

---

## 当前局限

- **仅支持 Python 符号搜索** — `semantic_search` 基于 tree-sitter-python，不支持其他语言
- **LLM 依赖** — 上下文压缩和历史摘要需要 LLM 调用，离线场景不可用
- **单文件编辑粒度** — `file_edit replace` 要求精确匹配，对大范围重构支持有限
- **无持久化会话** — 交互模式下退出后历史不保留（但 trajectory 和 task 已持久化）
- **Benchmark 规模有限** — 当前仅 5 个实例，不构成统计显著的评测集

---

## 后续规划

- [ ] 支持更多语言的符号搜索（TypeScript、Go、Rust）
- [ ] 接入 SWE-bench Lite 作为外部 benchmark
- [ ] 支持 MCP (Model Context Protocol) 工具扩展
- [ ] 添加会话持久化与恢复
- [ ] Web UI / VS Code 插件
- [ ] 更细粒度的 cost 控制与 budget 预警

---

## 运行时产物

| 路径 | 内容 |
|------|------|
| `trajectories/*.jsonl` | 每步轨迹（耗时、工具、cost、token） |
| `.tasks/*.json` | 多步任务状态（跨上下文压缩保留） |
| `.transcripts/*.jsonl` | 完整历史存档（LLM 摘要前备份） |
| `benchmarks/results/*.json` | Benchmark 评测记分卡 |

---

## 参考项目

| 项目 | 借鉴方面 |
|------|---------|
| [SWE-agent / mini-swe-agent](https://github.com/SWE-agent/SWE-agent) | 工作流优先的 prompt 设计思路、README 的工程项目呈现风格 |
| [Aider](https://github.com/Aider-AI/aider) | README 信息层级、特性一览的展示方式、快速开始的组织结构 |
| [Reflexion](https://github.com/noahshinn/reflexion) | 自我反思循环的设计模式 |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 角色化多 Agent 协作模式 |
| [promptfoo](https://github.com/promptfoo/promptfoo) | Prompt 版本管理与 A/B 测试方法论 |
| [SWE-bench](https://github.com/princeton-nlp/SWE-bench) | Benchmark 评测方法论 |
| [litellm](https://github.com/BerriAI/litellm) | 统一 LLM 适配器、路由与降级 |
| [phoenix (Arize)](https://github.com/Arize-ai/phoenix) | LLM trace 可观测性思路 |
| [serena](https://github.com/oraios/serena) | 符号优先的代码搜索策略 |

---

## License

MIT
