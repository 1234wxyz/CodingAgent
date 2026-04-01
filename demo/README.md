# Demo Scenarios

这个目录用于放置可复制、可复现、可验收的 bug 场景。

设计目标：

- 每个场景都足够小，便于 agent 快速理解和修复
- 每个场景都代表一种不同类型的问题
- 每个场景都自带 `verify.py`，便于后续让 `main.py` / `app.py` 走真实 API 进行验收

当前包含：

- `zero_division`：运行时异常
- `trailing_window`：off-by-one 逻辑 bug
- `loyalty_checkout`：多文件业务规则 bug

建议约定：

- `scenario.json`：场景元信息
- 业务源码：最小必要文件
- `verify.py`：修复后的验收脚本
