# coding-agent

> A from-scratch Python coding agent with a thin explainable loop,
> middleware-based safety, self-reflection, multi-agent orchestration,
> structured observability, and benchmark evaluation.

一个从零实现的可评测、可自省、可观测的 Python Coding Agent。

核心 loop 仅 ~300 行，通过 middleware 分离安全与上下文管理，通过 tool-calling 扩展能力，
支持角色化多 Agent 协作、自省纠错、持久化任务追踪、prompt 版本化和终端 Dashboard。

---

## Quick Start

```bash
# 1. Clone & install
git clone <repo>
cd codingAgentProject
pip install -e ".[dev]"          # Python >= 3.11

# 2. Configure .env
cat > .env <<'EOF'
MODEL_NAME=deepseek/deepseek-chat
DEEPSEEK_API_KEY=your_key_here
EOF

# 3. Run
python main.py                   # Interactive mode (streaming output)
```

---

## Usage

### Interactive Mode

```bash
python main.py
```

Enter task descriptions; the agent calls tools, edits files, runs tests, then summarizes.
Token-by-token streaming output keeps the terminal responsive.

### Single-shot Mode

```bash
python main.py --task "Fix the ZeroDivisionError in calculator.py" --work-dir ./demo/bug_scenarios/zero_division
```

### Scenario Verification (Real API)

```bash
python scripts/run_scenarios.py                     # Run all 6 demo scenarios
python scripts/run_scenarios.py zero_division        # Run one scenario
python scripts/run_scenarios.py --prompt-version v2  # Use versioned prompt
python scripts/run_scenarios.py --dry-run            # List available scenarios
```

### Benchmark Evaluation

```bash
python scripts/benchmark.py                          # Run all 5 benchmark instances
python scripts/benchmark.py dict_merge_overwrite     # Run one instance
python scripts/benchmark.py --dry-run                # List instances
```

### Trajectory Dashboard

```bash
python scripts/dashboard.py trajectories/            # Latest trajectory
python scripts/dashboard.py path/to/trajectory.jsonl # Specific file
```

### Prompt A/B Comparison

```bash
python scripts/compare_prompts.py v1 v2              # Compare two prompt versions
python scripts/compare_prompts.py v1 v2 --dry-run    # Preview what would run
```

---

## Architecture

```text
User Request
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  System Prompt  (context.py / prompts/*.yaml)       │
│  ┌─────────────────────────────────────────────┐    │
│  │  Agent Loop  (core.py, ~300 lines)          │    │
│  │  run → step → query → dispatch → trajectory │    │
│  │       ↑                    │                │    │
│  │  Middleware Hooks     Tool Executor          │    │
│  │  (pre_step/post_step)     │                │    │
│  └───────────────────────────┼────────────────┘    │
│                              ▼                      │
│  ┌──────────┬──────────────┬───────────┬─────────┐ │
│  │   bash   │semantic_search│task_board │delegate │ │
│  │  (shell) │ (tree-sitter)│(.tasks/)  │(sub-agent)│
│  └──────────┴──────────────┴───────────┴─────────┘ │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Middleware Chain                                     │
│  ┌───────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │BashSafety     │ │ContextCompact│ │ Reflection │ │
│  │(12 risk rules)│ │(LLM summary) │ │(self-review)│ │
│  └───────────────┘ └──────────────┘ └────────────┘ │
└─────────────────────────────────────────────────────┘
    │
    ▼
  Trajectory JSONL  →  Dashboard  →  Benchmark Scorecard
```

### File Map

```
agent/
├── app.py              # App assembly: prompt, tools, middleware, streaming, CLI
├── core.py             # Agent loop (~300 lines): run → step → query → dispatch
├── context.py          # System prompt assembly, YAML loading, output truncation, compaction
├── middleware.py        # BashSafety, SandboxAwareness, ContextCompaction, Reflection
├── models.py           # litellm adapter: query, streaming, retry, fallback chain
└── tools/
    ├── base.py             # Tool ABC + ToolObservation
    ├── bash.py             # Stateless shell execution (cross-platform)
    ├── delegate.py         # Role-based sub-agent delegation (explorer/reviewer/tester)
    ├── registry.py         # Tool registration and JSON schema dispatch
    ├── semantic_search.py  # Python symbol search (tree-sitter)
    └── task_board.py       # Persistent multi-step task board (.tasks/)

scripts/
├── analyze.py          # Trajectory JSONL statistics
├── benchmark.py        # Benchmark evaluation harness (pass@1 scorecard)
├── compare_prompts.py  # Prompt version A/B comparison
├── dashboard.py        # Terminal ASCII dashboard for trajectories
└── run_scenarios.py    # Demo scenario automated verification

prompts/                # Versioned system prompts (YAML)
├── v1.yaml             # Original 6-step workflow
└── v2.yaml             # Strict minimal variant

demo/bug_scenarios/     # 6 bug scenario templates (with verify.py)
benchmarks/             # 5 self-contained benchmark instances
tests/                  # 74 offline tests (no API key needed)
main.py                 # CLI entry point
```

---

## Key Design Decisions

### 1. Shell-first (no file_editor)

No standalone `file_editor` tool. All file read/write goes through `bash` — using `sed`, `cat <<'EOF'`, or inline `python -c`. The prompt provides cross-platform editing examples.

**Why:** Migrated from [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)'s philosophy — one general-purpose mutation tool beats multiple specialized ones. Fewer tools = fewer schema errors = more reliable agent behavior.

### 2. 6-Step Workflow Discipline

The system prompt enforces a strict action order:

```
1. ANALYZE   — Read files, search symbols
2. REPRODUCE — Run the failing case, see the exact error
3. FIX       — Minimal edit via shell
4. VERIFY    — Re-run the failing command
5. EDGE CASES — Test boundaries
6. FINISH    — Summarize, stop calling tools
```

Each step must do **exactly one thing**: call a tool or return the final answer. No mixing narrative with tool calls.

### 3. Middleware Safety (not in the loop)

All safety and context management lives in `middleware.py` via `pre_step`/`post_step` hooks. `core.py` stays at ~300 lines.

| Middleware | Responsibility |
|-----------|---------------|
| `BashSafetyMiddleware` | Block `rm -rf /`, `sudo`, `git reset --hard`, etc. (12 regex patterns) |
| `SandboxAwarenessMiddleware` | Probe runtime environment, inject constraints into prompt |
| `ContextCompactionMiddleware` | Compact old tool outputs, LLM-summarize history, archive transcripts |
| `ReflectionMiddleware` | Self-critique before finishing (inspired by [Reflexion](https://github.com/noahshinn/reflexion)) |

### 4. Self-Reflection

When the agent is about to finish (text-only response, no tool calls), `ReflectionMiddleware` intercepts and injects a self-critique prompt: "Did you verify? Edge cases? Rate confidence 1-5." The agent gets one more iteration to catch shallow patches.

### 5. Multi-Agent Orchestration

`DelegateTool` supports role-based sub-agents without a complex framework:

| Role | Focus |
|------|-------|
| `explorer` (default) | Code investigation, find files and patterns |
| `reviewer` | Quality check: correctness, edge cases, side effects |
| `tester` | Test execution, coverage, verification |

Each role gets a specialized system prompt. Sub-agents run in isolated context. Inspired by [CrewAI](https://github.com/crewAIInc/crewAI)'s role-based approach, but implemented as a single tool call.

### 6. Structured Observability

Trajectory JSONL includes per-step timing (`wall_time_ms`), tool names, and token breakdown. The terminal dashboard (`scripts/dashboard.py`) renders:

- Step timeline (ASCII bar chart by wall time)
- Tool frequency histogram
- Cumulative cost curve
- Decision summary

### 7. API Resilience

- **Retry with exponential backoff** (tenacity): handles `RateLimitError`, `ServiceUnavailableError`, `Timeout`
- **Model fallback chain** (`FallbackModel`): primary model fails → try secondary. Same `query()` interface, `core.py` is unaware.
- **Streaming output**: token-by-token terminal display via `litellm.completion(stream=True)`, UI-only — loop contract unchanged.

### 8. Prompt Versioning

System prompts are stored as YAML files in `prompts/`. Runtime selection via `AGENT_PROMPT_VERSION=v2` or `--prompt-version v2`. Cross-version comparison with `scripts/compare_prompts.py`.

---

## Demo Scenarios

| Scenario | Type | Description |
|----------|------|-------------|
| `zero_division` | Runtime exception | `average([])` should return 0.0, not ZeroDivisionError |
| `trailing_window` | Off-by-one | `trailing_window(items, 3)` should return 3 elements |
| `loyalty_checkout` | Multi-file logic | Unknown customer tier should get no discount |
| `type_error` | Type error | `int + str` concatenation failure |
| `import_cycle` | Circular import | Multi-file circular dependency |
| `missing_return` | Control flow | Function missing return statement |

### Benchmark Instances

| Instance | Bug Type | Source Pattern |
|----------|----------|---------------|
| `dict_merge_overwrite` | Shallow copy mutation | Django settings merging |
| `csv_quoting` | Missing field quoting | Data processing libraries |
| `datetime_edge` | Off-by-one in date math | Scheduling libraries |
| `regex_escape` | Unescaped regex specials | Search utilities |
| `recursion_depth` | RecursionError on deep input | Data transformation |

---

## Testing

```bash
pytest tests/ -v                                # 74 offline tests, no API key needed
python scripts/run_scenarios.py                 # 6/6 scenarios against real API
python scripts/benchmark.py                     # 5-instance benchmark scorecard
python scripts/dashboard.py trajectories/       # Terminal dashboard
python scripts/analyze.py trajectories/         # Trajectory statistics
```

---

## Runtime Artifacts

| Path | Content |
|------|---------|
| `trajectories/*.jsonl` | Per-step trajectory (timing, tools, cost, tokens) |
| `.tasks/*.json` | Multi-step task state (survives context compression) |
| `.transcripts/*.jsonl` | Full history archived before LLM summarization |
| `benchmarks/results/*.json` | Benchmark scorecard results |

---

## Metrics

| Metric | Value |
|--------|-------|
| Core loop (core.py) | ~300 lines |
| Total agent code | ~2800 lines |
| Tests | 74 (all offline) |
| Tools | 4 (bash, semantic_search, task_board, delegate) |
| Middleware | 4 (safety, sandbox, compaction, reflection) |
| Demo scenarios | 6 |
| Benchmark instances | 5 |
| Prompt versions | 2 (YAML-based, A/B comparable) |

---

## References

| Project | Influence |
|---------|-----------|
| [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | Workflow-first prompt discipline |
| [Reflexion](https://github.com/noahshinn/reflexion) | Self-reflection loop design |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Role-based multi-agent pattern |
| [promptfoo](https://github.com/promptfoo/promptfoo) | Prompt versioning & A/B testing |
| [SWE-bench](https://github.com/princeton-nlp/SWE-bench) | Benchmark evaluation methodology |
| [phoenix (Arize)](https://github.com/Arize-AI/phoenix) | LLM trace observability |
| [litellm](https://github.com/BerriAI/litellm) | Unified LLM adapter, router/fallback |
| [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk) | Tool schema / delegate pattern |
| [serena](https://github.com/oraios/serena) | Symbol-first code search |
