# HTTP Gateway Demo

这个场景模拟一个多模块 FastAPI HTTP 网关在启动阶段直接报错的线上事故。

推荐演示流程：

1. 先启动 agent，并把工作目录指向这个场景。
2. 让 agent 先复现 `python start_gateway.py` 的启动失败。
3. 再让 agent 修复根因，最后用 `python smoke_check.py` 做轻量验证。

预期故障现象：

- `python start_gateway.py` 会在导入或装配阶段失败。
- 典型症状是 FastAPI 网关还没启动就抛出 import 或 dependency 相关错误。

修复成功信号：

- `python start_gateway.py` 可以正常启动应用。
- `python smoke_check.py` 输出 `SMOKE PASS`。
