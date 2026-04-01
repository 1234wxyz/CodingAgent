# Day 4: 实现 semantic_search.py + analyze.py（给 Claude Code）

## 目标

两件事：

1. `tools/semantic_search.py`：用 tree-sitter 做 Python 符号级检索（本日主体）
2. `scripts/analyze.py`：轨迹分析小工具（收尾任务）

## 先看哪里

**semantic_search.py：**
- `serena/README.md`（理解 symbol-first 检索的设计理念，但不要照搬它的 LSP 架构）
- `serena/src/serena/tools/symbol_tools.py`（看它暴露了哪些操作：find_symbol, find_referencing_symbols 等）

**analyze.py：**
- 读 Day 1 实现中 trajectory 的 JSONL 格式，了解每条记录长什么样

## 依赖提醒

- `tree-sitter` 的 Python binding 在不同版本间 API 有差异，2025-2026 的示例常混用新旧写法
- 如果你需要把依赖写进 `pyproject.toml`，请选择彼此兼容的 `tree-sitter` 与 `tree-sitter-python` 版本组合
- 以你最终采用的那套 API 为准，不要同时参考两套初始化方式

## 边界

### semantic_search.py 应该负责

- 用 `tree-sitter` + `tree-sitter-python` 解析 Python 源文件
- 暴露能力（建议但不限于）：
  - 列出某个文件里的所有函数 / 类定义（名称、行号、签名）
  - 按名称搜索符号定义（跨目录）
  - 返回某行所在函数 / 类的完整上下文
- 注册为标准 Tool（和 bash / file_editor 同级）

### semantic_search.py 不应该负责

- 支持 Python 以外的语言（这一版明确只做 Python）
- 做完整的 LSP / language server
- 做 PageRank / 权重排序
- 做代码编辑（那是 file_editor 的事）
- 构建全仓索引缓存（先做无状态的按需解析）

### analyze.py 应该负责

- 读取 `trajectories/*.jsonl`
- 输出有用的统计：总步数、工具调用分布、token 消耗、exit 状态
- 可以作为 CLI 脚本直接运行

### analyze.py 不应该负责

- 实时监控
- Web UI
- 修改 trajectory 数据

## 对 Claude 的要求

你可以自由决定：

- tree-sitter 的 query 怎么写（用 S-expression 还是遍历 AST）
- 符号提取粒度（函数级 / 类级 / 方法级 / 装饰器是否包含）
- semantic_search 暴露几个 action（一个大 action 带子命令，还是多个独立 action）
- analyze.py 的输出格式（表格 / JSON / 纯文本）

但请保证这些外部约束成立：

1. `semantic_search` 走标准工具注册，和其他 tool 同协议。
2. 只依赖 `tree-sitter` 和 `tree-sitter-python`，不引入 LSP 或 IDE 级依赖。
3. 对不是 Python 的文件，优雅跳过或返回空结果，不报错。
4. analyze.py 不依赖 agent 运行时，它读静态 JSONL 文件。

## 输出结果应满足

- 给定一个 Python 项目目录，能列出所有符号定义
- 给定一个符号名，能定位到它在哪个文件哪一行
- `analyze.py` 能读取已有的 trajectory 并输出统计

## 完成前必须执行的验证

- 运行 `python -m py_compile agent/tools/semantic_search.py scripts/analyze.py`
- 在当前仓库上跑一次 `semantic_search` 冒烟：至少验证列符号、找符号、取上下文三类能力
- 为 `analyze.py` 准备一条最小 JSONL 样本并实际运行一次 CLI；如果已有真实 trajectory，可二选一
- 确认最终选用的 `tree-sitter` / `tree-sitter-python` 组合能在本地实际解析 Python 文件

## 验收标准

- `semantic_search` 可被主 agent 通过 tool call 调用
- 在一个真实 Python 项目上测试通过（可以用本项目自身）
- `analyze.py` 对一条非空 trajectory 能输出可读统计
