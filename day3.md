# Day 3: 实现 delegate.py / context.py / middleware.py（给 Claude Code）

## 目标

三件事，按优先级排：

1. `context.py`：让主 agent 的 system prompt 可组装、可注入外部知识
2. `middleware.py`：给 agent loop 加 pre/post 钩子
3. `tools/delegate.py`：把子 agent 暴露为一个普通工具

三者互相独立，可以按任意顺序实现。

## 先看哪里

按主题分：

**context.py：**
- `software-agent-sdk/examples/01_standalone_sdk/03_activate_skill.py`（看 AgentContext / system_message_suffix 怎么注入）
- `software-agent-sdk/openhands-sdk/openhands/sdk/context/agent_context.py`（看 AgentContext 的真实定义）
- `mini-swe-agent/src/minisweagent/config/default.yaml`（看 system_template / instance_template 怎么拼）

**middleware.py：**
- `deepagents/libs/deepagents/deepagents/middleware/`（看中间件的挂载方式）

**delegate.py：**
- `deepagents/libs/deepagents/deepagents/middleware/subagents.py`（核心参考）
- `software-agent-sdk/openhands-tools/openhands/tools/delegate/definition.py`（看 DelegateTool 的定义）
- `software-agent-sdk/examples/01_standalone_sdk/42_file_based_subagents.py`（看 DelegateTool 的使用方式）

## 边界

### context.py 应该负责

- 组装 system prompt（支持从多个片段拼接）
- 检测并加载工作目录下的 `AGENTS.md` / `CLAUDE.md`
- 输出截断（过长的 tool output 取头尾）
- 提供一个"压缩历史"的能力（用便宜模型总结旧消息）

### context.py 不应该负责

- 主 loop
- 工具选择
- 模型调用
- prompt 的具体内容（那是 config/prompts/ 的事）

### middleware.py 应该负责

- 定义钩子协议（在 step 之前 / 之后可以插入逻辑）
- `SyntaxCheckMiddleware`：文件写入后 `python -m py_compile`，失败时返回 observation 而不是静默
- `AutoCommitMiddleware`：agent 结束或到达某个间隔时，`git add -A && git commit` ，实现这个类，但不要在当前开发任务中主动启用它或执行 git commit

### middleware.py 不应该负责

- 改变 agent 的决策逻辑
- 替代工具层的执行
- 做复杂的事件系统

### delegate.py 应该负责

- 注册为一个标准 Tool（和 bash/file_editor 同级）
- 接收任务描述和子 agent 类型
- 创建子 agent（新的消息历史，隔离上下文）
- 同步阻塞执行，返回子 agent 的最终文本摘要
- 子 agent 可以限制可用工具集（比如 explorer 只有 bash + read）

### delegate.py 不应该负责

- 并行执行
- agent 编排策略
- 共享上下文

## 对 Claude 的要求

你可以自由决定：

- context 的组装是用 Jinja2 还是 f-string 还是字符串拼接
- middleware 是 Protocol / ABC / 还是简单回调函数
- delegate 的子 agent 怎么复用 core.py 的 loop（推荐直接实例化一个新 Agent）
- 压缩历史时用哪个便宜模型、总结 prompt 怎么写

但请保证这些外部约束成立：

1. `context.py` 的输出是一个可以直接塞进 `messages[0]` 的 system prompt 字符串。
2. 中间件不改变 agent loop 的核心签名——它是钩子，不是拦截器。
3. delegate 对主 agent 来说就是一个普通工具调用，不引入新的执行模型。
4. 子 agent 的消息历史和父 agent 完全隔离。
5. `AGENTS.md` 不存在时静默跳过，不报错。

## 输出结果应满足

- system prompt 可以从多个来源组装
- 存在 `AGENTS.md` 的项目目录下，内容会被注入
- 文件写入后 syntax check 能拦截语法错误
- delegate 能完成一次同步委托并返回摘要

## 完成前必须执行的验证

- 运行 `python -m py_compile agent/context.py agent/middleware.py agent/tools/delegate.py`
- 对 `context.py` 跑两个 smoke：有 `AGENTS.md` / `CLAUDE.md` 的注入场景，以及文件不存在时的静默跳过场景
- 对 `SyntaxCheckMiddleware` 跑一个语法错误文件场景，确认返回 observation 而不是静默
- 对 `delegate.py` 跑一个 fake sub-agent smoke，确认能同步返回摘要且父子历史隔离
- 不要在验收阶段真实启用 `AutoCommitMiddleware` 执行 `git commit`

## 验收标准

- context 组装可被 core.py 直接使用
- middleware 可挂载到 agent loop 而不需要改 loop 代码
- delegate 走标准工具注册，agent 通过 tool call 发起委托
- 三个模块各自可独立测试
