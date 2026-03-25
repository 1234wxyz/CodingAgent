'''
coding-agent/
├── README.md                     # 项目说明 + 面试亮点 + 设计决策
├── pyproject.toml                # uv 依赖管理
├── .env.example                  # API Key 配置
│
├── agent/
│   ├── __init__.py
│   │
│   ├── core.py                   # [Day 1] Agent Loop
│   │   │                          参考：mini-swe-agent DefaultAgent
│   │   │                          - run() → while: step() → query() → execute()
│   │   │                          - 线性消息历史（list append）
│   │   │                          - 异常控制流（FormatError/Submitted/LimitsExceeded）
│   │   │                          - 不处理厂商 API 细节，模型调用委托给 models.py
│   │   └                          - ~150 行核心代码
│   │
│   ├── models.py                 # [Day 0] LLM 封装
│   │   │                          参考：mini-swe-agent litellm_model.py
│   │   │                          - 统一封装 litellm
│   │   │                          - 支持 anthropic/claude-* 与 deepseek/*
│   │   │                          - 统一 query(messages) 接口
│   │   │                          - 提取 tool calls / 文本输出
│   │   └                          - token 计数 + 成本追踪
│   │
│   ├── tools/                    # [Day 2] 工具系统
│   │   ├── registry.py           # 参考：OpenHands V1 register_tool() 全局注册
│   │   ├── base.py               # Action → Executor → Observation 三件套
│   │   ├── bash.py               # 无状态 subprocess.run（mini-swe-agent 模式）
│   │   ├── file_editor.py        # str_replace 精确匹配 + 空白容错（2级够用）
│   │   ├── delegate.py           # sub-agent as tool（参考 deepagents）
│   │   └── semantic_search.py    - 只做 Python，不做 130 种语言 (参考serena)
│   │   │                           - tree-sitter + tree-sitter-python
│   │   │                           -list_symbols(file)：列出函数/类定义 + 行号 + docstring
│   │   │                           - find_symbol(name)：跨文件搜索符号定义和引用
│   │   │                           - get_context(file, line)：返回某行所在函数/类的完整上下文
│   │   └                           - 注册为标准 Tool（Action/Observation 模式）
│   │   
│   ├── scripts/analyze.py       # [Day 2] 轨迹分析工具
│   │   │                           - 读取 trajectories/*.jsonl
│   │   │                           - 统计：总步数、工具调用分布、token 消耗、成功/失败
│   │   └                           - 面试加分：展示你关注 Agent 的可观测性
│   │
│   ├── context.py                # [Day 3] 上下文工程
│   │   │                          参考：open-swe prompt.py
│   │   │                          - 模块化 system prompt（分段常量组装）
│   │   │                          - AGENTS.md / CLAUDE.md 自动注入
│   │   │                          - 输出截断（>10k 字符取头尾各 5k）
│   │   └                          - LLM 总结压缩（OpenHands V1 Condenser 模式）
│   │
│   ├── middleware.py             # [Day 3] 中间件
│       │                          参考：open-swe middleware/
│       │                          - pre_step / post_step 钩子协议
│       │                          - SyntaxCheckMiddleware（python -m py_compile）
│       └                          - AutoCommitMiddleware（git add + commit）
│   
│   
│
├── config/
│   ├── default.yaml              # Agent 配置（step_limit, cost_limit, model）
│   └── prompts/
│       ├── system.md             # 系统提示模板（Jinja2）
│       └── instance.md           # 任务提示模板
│
├── tests/
│   ├── test_core.py              # Agent loop 单测
│   ├── test_file_editor.py       # str_replace 匹配测试
│   ├── test_middleware.py        # 中间件测试
│   └── conftest.py               # mock LLM 调用
│
├── examples/
│   ├── fix_bug.py                # 场景1：修 bug
│   ├── code_qa.py                # 场景2：代码问答
│   └── multi_agent.py            # 场景3：sub-agent 协作
│
└── trajectories/                 # 保存运行轨迹（JSONL）
    └── .gitkeep
'''
