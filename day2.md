# Day 2: 实现 `agent/tools/`（给 Claude Code）

## 目标

搭一个轻量工具层，让主 agent 可以稳定完成：

- 选择工具
- 校验输入
- 执行工具
- 返回结构化结果

当前阶段先追求“边界清楚、容易扩展、容易调试”，不是一次做全。

## 先看哪里

请优先阅读这些位置：

- `software-agent-sdk/examples/01_standalone_sdk/02_custom_tools.py`
- `software-agent-sdk/openhands-tools/openhands/tools/apply_patch/definition.py`
- `mini-swe-agent/src/minisweagent/agents/default.py`
- `deepagents/libs/deepagents/deepagents/middleware/subagents.py`
- `serena/README.md`
- `overall.md` 里 `agent/tools/` 的位置说明

建议按主题看：

- 工具协议与注册：前两个 `software-agent-sdk` 文件
- bash 工具的轻量执行风格：`mini-swe-agent` 的 loop 与 shell 思路
- delegate：`deepagents/.../subagents.py`
- semantic search：`serena/README.md`

## 当前阶段要做什么

优先完成这些：

- `tools/base.py`
- `tools/registry.py`
- `tools/bash.py`
- `tools/file_editor.py`

如果前四个稳定，再继续：

- `tools/delegate.py`
- `tools/semantic_search.py`

## 可迁移的内容

可以借这些高层模式：

- `software-agent-sdk` 的 `Action -> Executor -> Observation`
- 显式 registry
- `mini-swe-agent` 的无状态命令执行
- `deepagents` 的 `sub-agent as tool`
- `serena` 的 symbol-first 检索思路

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
- LSP / IDE 集成
- 多 agent 编排系统
- 过早的通用抽象

## 对 Claude 的要求

这一天的文档只约束边界，不强压实现细节。

你可以自由决定：

- `Tool` / `ToolDefinition` 的具体命名
- registry 是类还是模块级函数
- `file_editor` 内部如何做最小文本替换
- `semantic_search` 用 `tree-sitter` 还是先用 `ast` 起步

但请保证这些外部约束成立：

1. 每个工具都有清晰输入输出。
2. 主 agent 能按名字拿到工具。
3. 工具返回结构化 observation，而不是随意文本。
4. `bash` 保持无状态。
5. `delegate` 如果实现，先做同步阻塞式。
6. `semantic_search` 如果实现，第一版只做 Python，优先解决“定位”而不是“编辑”。

## 各文件的边界

### `tools/base.py`

只定义统一协议，不写具体工具逻辑。

### `tools/registry.py`

只是工具目录，不做调度策略。

### `tools/bash.py`

提供稳定的本地命令执行能力，强调每次调用独立。

### `tools/file_editor.py`

提供最小可靠文本编辑，不要求一开始就做 AST 级编辑。

### `tools/delegate.py`

把子 agent 暴露为工具，但当前阶段只需要最小可用形态。

### `tools/semantic_search.py`

提供代码结构检索；第一版只要对 Python 有帮助即可，不需要做 Serena 全量能力。

## 输出结果应满足

- agent 能列出可用工具
- registry 能按名称定位工具
- `bash` 可执行命令并返回结构化结果
- `file_editor` 可完成确定性的最小编辑
- `delegate` 若实现，可完成一次同步委托
- `semantic_search` 若实现，可辅助定位 Python 符号

## 验收标准

- 工具层可被主 agent 接入
- 输入校验和输出结构清晰
- 更换具体工具实现时，不需要改主 loop
- 第一版代码保持轻量，不提前长成“大平台”
