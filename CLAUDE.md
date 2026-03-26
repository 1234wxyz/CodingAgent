# CLAUDE.md

## 环境前提

- 首次克隆后，先执行 `git submodule update --init --recursive`
- 所有参考路径（`mini-swe-agent/`、`software-agent-sdk/`、`deepagents/`、`serena/`、`learn-claude-code/`）都基于已初始化的 submodule
- 如果某个参考路径不存在，先确认 submodule 是否已初始化；再只在对应 submodule 内做小范围定位，不要跨仓库盲搜

## 指令优先级

- 当前 `dayN.md` 是主要任务入口
- `overall.md` 用于看跨天架构、目录树和稳定接口
- 当前代码事实高于文档描述；冲突时优先级为：当前 day 文件 > 当前代码事实 > `overall.md` > 参考仓库

## Day 执行流程

- 开始 Day N 前，先检查 Day N-1 的验收标准是否已满足；读代码确认，不要假设
- 开始 Day N 前，先查看当前项目目录结构和上一天暴露的关键接口文件；如果 `agent/` 已存在，先 `ls agent/` 再读关键文件
- 如果当前是 Day 0，先按 `day0.md` 创建最小项目骨架，再开始实现 `models.py`
- 优先阅读当前 day 文件里“先看哪里”列出的参考路径，以及将被修改的本仓库文件
- 如果当前代码与文档不一致，优先做最小改动来满足当前 day 目标
- 不要为 Day N 提前实现 Day N+1 的完整能力，除非当前 day 被明确阻塞

## 参考项目使用规则

- `mini-swe-agent/`：借鉴薄 loop、model adapter、bash/action execution
- `software-agent-sdk/`：借鉴 tool schema、register/delegate pattern、AgentContext
- `deepagents/`：借鉴 middleware / sub-agent 挂载方式
- `serena/`：借鉴 symbol-first 检索思路
- `learn-claude-code/`：只作概念辅助，不作为实现模板

## 接口稳定性
- 优先维护前一天已经对外暴露的接口；如必须调整，先说明影响的模块和原因
- 不要同时改动超过 3 个模块的对外接口
- 不要把 provider-specific、runtime-specific 或未来天数的逻辑泄漏到当前模块

### 面试导向
- 优先可运行、可测试、可解释的最小闭环，而不是平台化扩张
- 每次交付都要保留“为什么这样取舍、为什么暂时不做更复杂方案”的说明
