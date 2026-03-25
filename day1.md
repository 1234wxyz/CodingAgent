# Day 1: 实现 `agent/core.py`（给 Claude Code）

## 目标

实现一个极薄的 agent loop。

核心只需要稳定跑通这条链路：

`run -> step -> query -> execute -> append history -> save trajectory`

## 先看哪里

请优先阅读这些位置：

- `mini-swe-agent/src/minisweagent/agents/default.py`
- `overall.md` 里 `agent/core.py` 的位置说明
- `day0.md`，了解 `models.py` 对外暴露什么接口

如果只看一个参考文件，就看 `default.py`。

## 可迁移的内容

可以直接借鉴这些高层模式：

- 极薄主循环
- 线性消息历史
- 异常式控制流
- 每步保存 trajectory
- loop 与 environment / model 解耦

## 边界

`core.py` 应该负责：

- 保存 `messages`
- 调用模型
- 把模型输出交给执行层
- 把 observation / exit 写回历史
- 保存 trajectory

`core.py` 不应该负责：

- 具体工具实现
- tool registry
- 模型厂商适配
- prompt 资产管理
- memory / planner / task graph
- sub-agent runtime

## 对 Claude 的要求

这里约束的是边界，不是实现细节。

你可以自由决定：

- 类和函数如何命名
- 异常怎么组织
- trajectory 的内部序列化结构
- step / cost 统计放在哪一层

但请保证这些外部约束成立：

1. 主循环要短，不要变成 orchestrator 大文件。
2. 所有消息保持线性 append。
3. “结束”和“错误”都能写回轨迹。
4. `core.py` 不直接处理 provider-specific 逻辑。
5. 无论成功还是失败，都能保存 trajectory。

## 建议参考接口

只要求外部关系，不要求你照抄实现：

- `model.query(messages) -> assistant_message`
- `env.execute(assistant_message) -> observation_messages`

只要这两个边界稳定，内部实现可自由调整。

## 输出结果应满足

- 能跑通单轮和多轮 loop
- assistant / observation / exit 都进入同一条历史
- 超限和格式错误能变成可记录事件
- 替换模型层或工具层时，不需要重写 loop

## 验收标准

- mock model + mock env 可以完整跑通
- `messages` 是单一线性历史
- 格式错误不会悄悄吞掉
- 退出状态能落到 trajectory
- trajectory 在异常时也会保存
