# Day 2: 实现 `agent/tools/` 基础层（给 Claude Code）

## 目标

搭一个轻量工具层，让主 agent 可以稳定完成：

- 选择工具
- 校验输入
- 执行工具
- 返回结构化结果

当前阶段只做 4 个文件。delegate 和 semantic_search 在后续天数。

## 先看哪里

请优先阅读这些位置：

- `software-agent-sdk/examples/01_standalone_sdk/02_custom_tools.py`
- `software-agent-sdk/openhands-tools/openhands/tools/apply_patch/definition.py`
- `mini-swe-agent/src/minisweagent/agents/default.py`（看它如何调用 bash）
- `mini-swe-agent/src/minisweagent/models/utils/actions_toolcall.py`（看模型侧如何把 tool call 归一成可执行 action）
- `overall.md` 里 `agent/tools/` 的位置说明
- `day2-reference.md`（**必读**，说明了工具层与 core.py / models.py 的数据流）

建议按主题看：

- 工具协议与注册：前两个 `software-agent-sdk` 文件
- bash 工具的轻量执行风格：`mini-swe-agent` 的 loop 与 shell 思路

## 当前阶段要做什么

只做这些：

- `tools/base.py`
- `tools/registry.py`
- `tools/bash.py`
- `tools/file_editor.py`

不要做 delegate.py 和 semantic_search.py，它们在 Day 3 / Day 4。

## 可迁移的内容

可以借这些高层模式：

- `software-agent-sdk` 的 `Action -> Executor -> Observation`
- 显式 registry
- `mini-swe-agent` 的 `query -> parsed actions -> execute` 链路
- `mini-swe-agent` 的无状态命令执行

## 边界

工具层应该负责：

- 定义统一工具协议
- 校验输入
- 执行具体能力
- 返回结构化 observation

工具层不应该负责：

- 主 loop
- 策略决策
- 复杂远程 runtime
- 多 agent 编排系统
- 过早的通用抽象

## 对 Claude 的要求

这一天的文档只约束边界，不强压实现细节。

你可以自由决定：

- `Tool` / `ToolDefinition` 的具体命名
- registry 是类还是模块级函数
- `file_editor` 内部如何做最小文本替换
- observation 的具体字段组织

但请保证这些外部约束成立：

1. 每个工具都有清晰输入输出。
2. 主 agent 能按名字拿到工具。
3. 工具返回结构化 observation，而不是随意文本。
4. `bash` 保持无状态。
5. 工具注册发生在 `registry.py`，不散落在各处。
6. 不要为了 Day 2 强行把 Day 0 的主调用关系改成 `query(messages, tool_schemas)`；如果 schema 需要传给模型，请集中在一处接线。

## 各文件的边界

### `tools/base.py`

只定义统一协议，不写具体工具逻辑。

### `tools/registry.py`

只是工具目录，不做调度策略。

### `tools/bash.py`

提供稳定的本地命令执行能力，强调每次调用独立。

### `tools/file_editor.py`

提供最小可靠文本编辑，不要求一开始就做 AST 级编辑。
至少支持精确匹配；空白容错为可选增强。
编辑失败时应返回有帮助的错误信息（如相似行提示）。

## 输出结果应满足

- agent 能列出可用工具
- registry 能按名称定位工具
- `bash` 可执行命令并返回结构化结果
- `file_editor` 可完成确定性的最小编辑

## 验收标准

- 工具层可被主 agent 接入
- 输入校验和输出结构清晰
- 更换具体工具实现时，不需要改主 loop
- 第一版代码保持轻量，不提前长成"大平台"
