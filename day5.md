# Day 5: 最终测试 + 示例 + 文档（给 Claude Code）

## 目标

让项目达到"可展示"状态：

1. 关键模块有测试
2. 有可运行的端到端示例
3. README 能让人 3 分钟理解项目

## 先看哪里

- Day 0–4 实现的所有代码（先 `ls` 整个 `agent/` 目录，了解当前实际结构）
- `overall.md`（了解设计意图）
- `mini-swe-agent/README.md`（看一个好的 agent 项目 README 长什么样）

## 当前阶段要做什么

按优先级：

1. `tests/conftest.py` + 至少 `test_core.py` 和 `test_file_editor.py`
2. `examples/fix_bug.py`（最小端到端演示）
3. `README.md`
4. 时间允许再做 `examples/code_qa.py` 和 `examples/multi_agent.py`

## 边界

### 测试应该覆盖

- core.py：mock model + mock registry / tool executor → loop 能跑通、能终止、异常能记录
- file_editor：精确匹配成功 / 匹配失败返回有用错误 / 空白容错（如果 Day 2 实现了）
- middleware：SyntaxCheck 能拦截语法错误（如果 Day 3 实现了）

### 测试不需要覆盖

- 真实 LLM 调用（所有测试应可离线运行）
- 网络、Docker、远程 sandbox
- 100% 覆盖率

### conftest.py 应该提供

- 一种方式让测试代码不发真实 API 请求
- mock model 返回预设的 assistant message（包含 tool call）
- mock tool executor 返回预设的 observation

### examples/ 应该满足

- 每个例子是独立可运行的脚本
- `fix_bug.py`：提供一个有 bug 的 Python 文件 + 错误描述，agent 修复它
- 例子里应有清晰的注释说明在演示什么
- 需要真实 API key（在 .env 中配置）

### README.md 应该包含

- 一句话说清项目是什么
- 快速开始（安装、配置、运行）
- 架构概览（核心模块关系，不需要特别详细）
- 参考项目列表
- 设计决策（为什么选择极简架构）

### README.md 不应该包含

- 完整的 API 文档
- 每个文件的逐行解释
- 与面试无关的营销文案

## 对 Claude 的要求

你可以自由决定：

- 测试框架用 pytest 还是 unittest（推荐 pytest）
- mock 策略（monkeypatch / unittest.mock / 自定义 fixture）
- README 的排版风格
- 例子里的具体 bug 是什么

但请保证这些外部约束成立：

1. `pytest` 可以在无 API key 的环境下通过所有测试。
2. `examples/fix_bug.py` 端到端可运行（需要配置 API key）。
3. README 包含"设计决策"一节，解释为什么选极简架构。
4. 不要在测试中引入测试以外的新依赖。

## 完成前必须执行的验证

- 运行 `pytest tests/`
- 对 `examples/` 下将交付的脚本逐个执行 `python -m py_compile <file>`
- 如果已经配置 API key，运行 `python examples/fix_bug.py`
- 如果没有 API key，至少完成示例脚本的静态检查，并在最终说明里明确“在线端到端未验证”

## 验收标准

- `pytest tests/` 全部通过，无需网络
- `python examples/fix_bug.py` 可演示完整流程
- README 读完能理解项目定位和运行方式
