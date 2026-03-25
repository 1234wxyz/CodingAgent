```text
coding-agent/
├── README.md                     # 项目说明 + 面试亮点 + 设计决策
├── pyproject.toml                # uv 依赖管理
├── .env.example                  # API Key 配置
│
├── agent/
│   ├── __init__.py
│   │
│   ├── core.py                   # [Day 1] Agent Loop
│   │   ├── 参考：mini-swe-agent/src/minisweagent/agents/default.py
│   │   ├── run() → while step() → query() → dispatch tool calls
│   │   ├── 线性消息历史（list append）
│   │   ├── 异常控制流（FormatError / Submitted / LimitsExceeded）
│   │   └── 不处理厂商 API 细节，模型调用委托给 models.py
│   │
│   ├── models.py                 # [Day 0] LLM 封装
│   │   ├── 参考：mini-swe-agent/src/minisweagent/models/litellm_model.py
│   │   ├── 统一封装 litellm
│   │   ├── 支持 anthropic/claude-* 与 deepseek/*
│   │   ├── 对外保持 query(messages) 主调用关系
│   │   └── 提取 tool calls / 文本输出 / token / cost
│   │
│   ├── tools/                    # [Day 2] 工具系统
│   │   ├── registry.py           # 参考：software-agent-sdk 的 register_tool 模式
│   │   ├── base.py               # Action → Executor → Observation 三件套
│   │   ├── bash.py               # 无状态 subprocess.run（mini-swe-agent 模式）
│   │   ├── file_editor.py        # str_replace 精确匹配 + 空白容错（2 级够用）
│   │   ├── delegate.py           # [Day 3] sub-agent as tool（参考 deepagents / OpenHands）
│   │   └── semantic_search.py    # [Day 4] 只做 Python，不做多语言 LSP（参考 serena）
│   │       ├── tree-sitter + tree-sitter-python
│   │       ├── list_symbols(file)
│   │       ├── find_symbol(name)
│   │       ├── get_context(file, line)
│   │       └── 注册为标准 Tool（Action/Observation 模式）
│   │
│   ├── context.py                # [Day 3] 上下文工程
│   │   ├── 参考：software-agent-sdk AgentContext
│   │   ├── 模块化 system prompt（分段常量组装）
│   │   ├── AGENTS.md / CLAUDE.md 自动注入
│   │   ├── 输出截断（>10k 字符取头尾各 5k）
│   │   └── LLM 总结压缩（轻量 condenser 模式）
│   │
│   └── middleware.py             # [Day 3] 中间件
│       ├── 参考：deepagents/libs/deepagents/deepagents/middleware/
│       ├── pre_step / post_step 钩子协议
│       ├── SyntaxCheckMiddleware（python -m py_compile）
│       └── AutoCommitMiddleware（git add + commit）
│
├── scripts/
│   └── analyze.py                # [Day 4] 轨迹分析工具
│       ├── 读取 trajectories/*.jsonl
│       ├── 统计：总步数、工具调用分布、token 消耗、成功/失败
│       └── 面试加分：展示你关注 Agent 的可观测性
│
├── config/
│   ├── default.yaml              # Agent 配置（step_limit, cost_limit, model）
│   └── prompts/
│       ├── system.md             # 系统提示模板（Jinja2 或等价方案）
│       └── instance.md           # 任务提示模板
│
├── tests/
│   ├── test_core.py              # Agent loop 单测
│   ├── test_file_editor.py       # str_replace 匹配测试
│   ├── test_middleware.py        # 中间件测试
│   └── conftest.py               # mock LLM 调用
│
├── examples/
│   ├── fix_bug.py                # 场景 1：修 bug
│   ├── code_qa.py                # 场景 2：代码问答
│   └── multi_agent.py            # 场景 3：sub-agent 协作
│
└── trajectories/                 # 保存运行轨迹（JSONL）
    └── .gitkeep
```

## 跨天稳定接口总表

| 边界 | 稳定接口 / 约束 | 说明 |
| --- | --- | --- |
| Day 0 `models.py` → Day 1 `core.py` | `model.query(messages) -> assistant_message` | 主 agent 对模型层只依赖这一条主调用关系，不提前扩成复杂 orchestrator API。 |
| `assistant_message` 结构 | 至少包含 `role`、`content`、标准化工具调用信息、`usage`、`cost` | 工具调用字段名可自定，但 Day 0、Day 1、Day 2 必须一致。 |
| Day 1 `core.py` → Day 2 `tools/` | `core.py` 从 assistant message 提取工具调用，再通过 registry 分发到具体 tool | 本项目用 registry-backed tools 取代 mini-swe-agent 里的单一 `env.execute(action)`。 |
| Day 2 工具协议 | 每个 tool 至少暴露：`name`、schema、`execute(arguments) -> observation` | schema 可供模型层或 agent 装配阶段使用，但不强制改成 `query(messages, tool_schemas)`。 |
| 观测写回 | tool observation 会被格式化后 append 回同一条 `messages` 历史 | 保持线性历史，方便 trajectory 和后续压缩。 |
| trajectory | 成功、失败、超限、格式错误都要可落盘 | Day 1 定义基础记录格式，Day 4 的 `scripts/analyze.py` 只读它，不反向依赖 runtime。 |
| Day 3 `context.py` | 输出是一个可直接塞入 `messages[0]` 的 system prompt 字符串 | prompt 片段、AGENTS/CLAUDE 注入、压缩都收敛在这里。 |
| Day 3 `middleware.py` | 只提供 pre/post hooks，不改变 `core.py` 的核心签名 | 是挂钩层，不是新的 orchestrator。 |
| Day 3 `delegate.py` | 对主 agent 来说只是一个普通工具 | 子 agent 独立消息历史，不共享父 agent 运行时上下文。 |
| Day 4 `semantic_search.py` | 走和 bash / file_editor 一致的工具协议 | 先做 Python-only、按需解析，不引入完整 LSP。 |

## 实现原则

- 约束能力边界，不强压实现细节。
- 优先保持跨天接口稳定；如果必须调整，先在对应 day 文件里明确影响范围。
- 借鉴参考仓库的局部模式，不照搬整个运行时或平台结构。
