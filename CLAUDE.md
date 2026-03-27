# CLAUDE.md

This repository is a shell-first local coding assistant, not a file-editor-first agent.

## Core Facts

- `core.py` only knows two runtime interfaces:
  - `model.query(messages) -> assistant_message`
  - `tool_executor(name, arguments) -> str`
- `context.py` owns runtime prompt assembly, repo-context injection, tool-result compaction helpers, transcript archiving, and history summarization.
- `middleware.py` owns bash risk interception, sandbox detection/injection, and middleware-triggered context compaction.
- `bash.py` is the only general-purpose mutation path. There is no `file_editor.py`.
- `task_board.py` persists multi-step work to `.tasks/` so plans survive context compression.
- `app.py` assembles the runnable local coding assistant and `main.py` is the CLI entry.

## Working Rules

- Prefer current code facts over historical day docs when they disagree.
- Keep the loop thin: extend behavior through tools, prompt construction, and middleware rather than bloating `core.py`.
- When behavior changes, update tests in the same pass.
- After each meaningful phase, run targeted validation instead of waiting until the end.
- Do not reintroduce a standalone file editor abstraction unless the repo direction explicitly changes.

## Runtime Shape

- The system prompt should follow a strict action-oriented style similar in spirit to `default.yaml`, but adapted to Python tool-calling:
  - each step should either call tools or finish
  - prefer one focused move per step
  - verify after edits
  - keep the final answer concise
- Use `semantic_search` before broad shell greps when Python structure matters.
- Use `task_board` when work spans multiple meaningful steps, multiple files, or has dependencies.
- Use `delegate` only for bounded subproblems that benefit from isolated context.

## Testing Notes

- `test_context.py` covers prompt/context helpers and compaction primitives.
- `test_middleware.py` covers sandbox detection, bash guardrails, and compaction middleware.
- `test_task_board.py` covers persistent multi-step task behavior.
- `test_core.py` remains the contract test for the loop itself.

## Prompt Scaffold For This Refactor

If you continue this repository refactor in Claude Code, inspect these files first:

@context.py
@middleware.py
@app.py
@main.py
@bash.py
@task_board.py
@delegate.py
@README.md
@test_context.py
@test_middleware.py
@test_task_board.py
@test_analyze.py

Use this intent framing:

1. Treat the repo as a shell-first local code assistant.
2. Preserve the thin `core.py` contract.
3. Route safety and context hygiene through middleware.
4. Route multi-step persistence through `task_board`.
5. Keep the prompt strict: one decisive move per step, verify before finishing.
6. Update tests alongside behavior and run them before closing the task.
