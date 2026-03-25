# 本文档说明 Day 2 要构建的工具层如何与 Day 0 / Day 1 的模块交互。Claude 在开始 Day 2 之前应阅读此文件。
## 关键接口边界

### models.py → core.py

参考 `mini-swe-agent`，Day 0 / Day 1 的主调用关系保持：

- `model.query(messages) -> assistant_message`

也就是说，`core.py` 主要依赖的是“给一段线性历史，拿回一个统一 assistant message”。

工具层仍然需要提供：

- 每个工具的 JSON schema（供模型层或 agent 装配阶段使用）
- 工具名称（给 registry 查找用）

但这不强制你把模型接口改成 `query(messages, tool_schemas)`。
如果需要把 schema 交给模型，可以在模型初始化、agent 组装，或 `core.py` 的单点适配处处理。

### core.py → 工具层

`mini-swe-agent` 的默认形态是：

1. `model.query(messages)` 返回带 action 的 assistant message
2. agent 从 message 中取出 action
3. 调用 `env.execute(action)`
4. 把 observation append 回历史

本项目在这里做的改造是：

1. `model.query(messages)` 返回带标准化 tool call 的 assistant message
2. `core.py` 从 message 中提取 `tool_name` 和 `arguments`
3. 通过 registry 找到对应工具
4. 调用工具，拿到 observation
5. 把 observation 格式化为消息 append 到 history

也就是说，我们借的是 mini-swe-agent 的 `query -> execute -> append history` 主链路，
但把单一 `env.execute(action)` 换成了更适合多工具项目的 `registry -> tool.execute(...)`。

工具层不需要知道 core.py 怎么管理 history。
core.py 不需要知道工具内部怎么执行。

### 工具协议

每个工具至少需要向外暴露：

- 名称（字符串，registry 用）
- JSON schema（给 LLM 描述参数，models.py 用）
- 执行方法（接收参数 dict，返回 observation）

具体用类还是函数、用 Pydantic 还是 dataclass，由你决定。

## 注意

- Day 2 不需要关心 delegate.py（Day 3）和 semantic_search.py（Day 4）
- 但 base.py 的协议设计要为它们留扩展空间——不是提前实现，而是不要在协议里写死假设
- 比如：不要假设所有工具都是"执行 shell 命令"，observation 不要写死成 stdout 字符串
