# Day 0: 实现 `agent/models.py`（给 Claude Code）

## 目标

实现一个轻量的模型适配层，给 `core.py` 提供统一的 `query(messages)` 主调用接口。

当前阶段只需要支持：

- `anthropic/claude-*`
- `deepseek/*`

## 前置：创建项目骨架

在写 `models.py` 之前，先创建以下最小基础结构：

- `agent/__init__.py`
- `pyproject.toml`（用 uv；至少声明 `litellm`、`pydantic`。如果 Day 0 代码直接读取模板或 YAML，再按需补 `jinja2`、`pyyaml`）
- `.env.example`（API key 占位）
- `trajectories/.gitkeep`

参考 `overall.md` 开头的目录树。
只创建 Day 0 需要的文件；`config/`、`tests/`、`examples/` 等留给后续 day。

## 先看哪里

请优先阅读这些位置，不要在整个仓库里盲搜：

- `mini-swe-agent/src/minisweagent/models/litellm_model.py`
- `mini-swe-agent/src/minisweagent/models/README.md`
- `overall.md` 里 `agent/models.py` 的位置说明

如果只想快速抓核心，先看第一个文件。

## 可迁移的内容

可以借这些思路：

- 用 `litellm` 做统一封装
- 向上暴露一个稳定的 `query(messages)` 接口
- 把 usage / cost 放进返回结果
- 在模型层处理厂商响应格式差异
- 参考 mini-swe-agent：主 agent 只依赖 `model.query(messages)`，不要过早把模型层扩成复杂 orchestrator API

## 边界

`models.py` 应该负责：

- 接收模型配置
- 调用 `litellm`
- 把响应归一化成项目内部 message
- 提取文本、tool calls、usage、cost

`models.py` 不应该负责：

- 主 loop
- prompt 拼装
- 工具执行
- registry
- fallback / router / 多模型编排
- streaming

## 下游依赖
Day 1 的 `core.py` 会通过 `model.query(messages)` 调用你。
请确保这个主调用关系稳定后再进入 Day 1。
如果 Day 2 需要 tool schema，优先通过模型初始化、对象状态或 agent 装配阶段接入；
不要为了后续天数，提前把这里强行改成 `query(messages, tool_schemas)`。

## 对 Claude 的要求

重点约束边界，不约束具体实现。

你可以自由决定：

- 用一个类还是少量辅助函数
- 内部方法如何拆分
- config 的具体字段组织
- 如何做轻量错误处理

但请保证这些外部约束成立：

1. `core.py` 只需要调用 `query(messages)`。
2. Claude 和 DeepSeek 的差异收敛在 `models.py` 内部。
3. 返回值里要能拿到文本、tool calls、usage、cost。
4. 不支持的模型名前缀应尽早失败。

## 输出结果应满足

- 能接收线性 `messages`
- 能返回统一 assistant message
- 能记录 token / cost
- 不把 provider-specific 细节泄漏到 `core.py`

## 完成前必须执行的验证

- 运行 `python -m py_compile agent/models.py`
- 运行一个无网络 smoke（可用临时脚本或最小测试）：mock `litellm` 响应，验证 `query(messages)` 返回统一 assistant message，且能读取 text / tool calls / usage / cost
- 验证不支持的模型前缀会尽早失败
- 确认 `agent/__init__.py`、`pyproject.toml`、`.env.example`、`trajectories/.gitkeep` 已创建

## 验收标准

- `anthropic/claude-*` 可正常初始化
- `deepseek/*` 可正常初始化
- 不支持的模型前缀会失败
- `query(messages)` 返回统一格式
- usage / cost 可被上层读取
