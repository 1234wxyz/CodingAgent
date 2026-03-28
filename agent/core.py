"""
agent/core.py — 极薄的 Agent Loop

核心链路：run → step → query → dispatch tool calls → append history → save trajectory

边界：
  - 只负责主循环、历史管理、工具分发调用、trajectory 落盘
  - 不负责 prompt 资产管理、模型厂商适配、工具实现、registry 逻辑本身

工具执行接线点（Day 2 兼容）：
  tool_executor: Callable[[str, dict], str] | None
  Day 2 注入时传入：lambda name, args: registry.get(name).execute(args)
"""

import json
import logging
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 控制流异常
# ---------------------------------------------------------------------------

class AgentFinished(Exception):
    """所有正常 / 可预期退出的基类。"""


class Submitted(AgentFinished):
    """模型返回 text-only 回复（无 tool_calls）→ 任务完成。"""


class LimitsExceeded(AgentFinished):
    """超出 step 或 cost 限制。"""


class FormatError(Exception):
    """工具调用不可执行（tool_executor 为 None 或执行失败）。"""


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    step_limit: int = 30
    """最大步数（0 = 不限制）。"""
    cost_limit: float = 3.0
    """最大花费 USD（0.0 = 不限制）。"""
    trajectory_path: Path | None = None
    """trajectory JSONL 文件路径；None 表示不落盘。"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Agent:
    """极薄的 agent loop。

    Args:
        model: 已初始化的 LLMModel，需暴露 query(messages) -> assistant_message。
        tool_executor: 可选的工具执行器，签名 (name: str, arguments: dict) -> str。
                       为 None 时，遇到 tool_calls 会 raise FormatError。
        **config_kwargs: 透传给 AgentConfig（step_limit, cost_limit, trajectory_path）。
    """

    def __init__(
        self,
        model: Any,
        tool_executor: Callable[[str, dict], str] | None = None,
        middlewares: list[Any] | None = None,
        **config_kwargs: Any,
    ):
        self.model = model
        self.tool_executor = tool_executor
        self.middlewares: list[Any] = list(middlewares) if middlewares else []
        self.config = AgentConfig(**config_kwargs)

        self.messages: list[dict[str, Any]] = []
        self.total_cost: float = 0.0
        self.n_steps: int = 0
        self._no_executor_retries: int = 0

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def run(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """运行 agent loop 直到退出。

        Args:
            messages: 初始消息列表（system + user prompt 由调用方组装）。

        Returns:
            exit info dict：{"status": str, "total_steps": int, "total_cost": float,
                             "final_content": str | None}
        """
        self.messages = list(messages)
        self.total_cost = 0.0
        self.n_steps = 0
        self._no_executor_retries = 0

        exit_status = "unknown"
        exit_exc: Exception | None = None

        try:
            while True:
                self.step()
        except Submitted as e:
            exit_status = "Submitted"
            exit_exc = e
        except LimitsExceeded as e:
            exit_status = "LimitsExceeded"
            exit_exc = e
        except FormatError as e:
            exit_status = "FormatError"
            exit_exc = e
            logger.error("FormatError: %s", e)
        except Exception as e:
            exit_status = type(e).__name__
            exit_exc = e
            logger.error("Unexpected error: %s\n%s", e, traceback.format_exc())
        finally:
            self._append_trajectory_exit(exit_status, exit_exc)

        final_content = None
        if self.messages:
            last = self.messages[-1]
            if last.get("role") == "assistant":
                final_content = last.get("content")

        return {
            "status": exit_status,
            "total_steps": self.n_steps,
            "total_cost": self.total_cost,
            "final_content": final_content,
        }

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def step(self) -> None:
        """执行一步：检查限制 → query → dispatch。"""
        for mw in self.middlewares:
            mw.pre_step(self)

        self._check_limits()
        self.n_steps += 1

        t0 = time.perf_counter()

        assistant_msg = self.model.query(self.messages)
        cost = assistant_msg.get("cost", 0.0)
        self.total_cost += cost

        # Extract token breakdown before discarding usage
        token_breakdown = assistant_msg.get("usage") or {}

        # 归一化：确保 messages 里存入的 assistant 消息不含 cost/usage 冗余字段
        # 保留 role / content / tool_calls / _normalized_tool_calls，供下游消费
        clean_msg = {
            "role": assistant_msg["role"],
            "content": assistant_msg.get("content"),
            "tool_calls": assistant_msg.get("tool_calls", []),
        }
        if "_normalized_tool_calls" in assistant_msg:
            clean_msg["_normalized_tool_calls"] = assistant_msg["_normalized_tool_calls"]
        self.messages.append(clean_msg)

        step_new_messages = [clean_msg]
        submitted = False
        try:
            self._dispatch(clean_msg, step_new_messages)
        except Submitted:
            submitted = True
        finally:
            wall_ms = (time.perf_counter() - t0) * 1000
            # Extract tool names called this step
            tool_calls = (
                clean_msg.get("_normalized_tool_calls")
                or clean_msg.get("tool_calls")
                or []
            )
            tool_names = [
                tc.get("name") or tc.get("function", {}).get("name", "unknown")
                for tc in tool_calls if isinstance(tc, dict)
            ]
            # 无论 _dispatch 是否 raise（含 Submitted / FormatError），step 都落盘
            self._append_trajectory_step(
                step_new_messages, cost,
                wall_time_ms=round(wall_ms, 1),
                tool_names=tool_names,
                token_breakdown=token_breakdown,
            )
            msg_count_before = len(self.messages)
            for mw in self.middlewares:
                mw.post_step(self)
            msg_count_after = len(self.messages)

        # If a middleware injected new messages (e.g. ReflectionMiddleware),
        # suppress Submitted so the loop continues with the new messages.
        if submitted:
            if msg_count_after > msg_count_before:
                logger.debug("Submitted suppressed: middleware injected %d new message(s).",
                             msg_count_after - msg_count_before)
                return  # continue loop
            raise Submitted("No tool calls — task complete.")

    def _check_limits(self) -> None:
        """在 query 前检查 step / cost 限制。超限则 raise LimitsExceeded。"""
        if self.config.step_limit > 0 and self.n_steps >= self.config.step_limit:
            raise LimitsExceeded(
                f"Step limit reached: {self.n_steps} >= {self.config.step_limit}"
            )
        if self.config.cost_limit > 0.0 and self.total_cost >= self.config.cost_limit:
            raise LimitsExceeded(
                f"Cost limit reached: ${self.total_cost:.4f} >= ${self.config.cost_limit}"
            )

    def _dispatch(
        self,
        assistant_msg: dict[str, Any],
        step_new_messages: list[dict[str, Any]],
    ) -> None:
        """从 assistant_message 提取 tool_calls，执行并 append observations。

        无 tool_calls → raise Submitted（任务完成）。
        tool_executor 为 None 但有 tool_calls → raise FormatError。
        """
        # 优先用 _normalized_tool_calls（真实 litellm 响应，来自 models.py）
        # fallback 到 tool_calls（兼容 Day 1 mock 模型，直接返回归一化格式）
        tool_calls = assistant_msg.get("_normalized_tool_calls") or assistant_msg.get("tool_calls") or []

        if not tool_calls:
            raise Submitted("No tool calls — task complete.")

        if self.tool_executor is None:
            self._no_executor_retries += 1
            if self._no_executor_retries > 2:
                raise FormatError(
                    f"Model requested tool calls but tool_executor is None "
                    f"(after {self._no_executor_retries} retries). "
                    f"Tools requested: {[tc.get('name') for tc in tool_calls]}"
                )
            for tc in tool_calls:
                feedback = {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": "ERROR: No tools are available. Please respond with text only.",
                }
                self.messages.append(feedback)
                step_new_messages.append(feedback)
            return

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            arguments = tc.get("arguments", {})
            tool_call_id = tc.get("id", "")

            try:
                observation = self.tool_executor(tool_name, arguments)
            except Exception as e:
                observation = f"ERROR: {e}"
                logger.warning("Tool %r failed: %s", tool_name, e)

            tool_result = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": str(observation),
            }
            self.messages.append(tool_result)
            step_new_messages.append(tool_result)

    # ------------------------------------------------------------------
    # Trajectory
    # ------------------------------------------------------------------

    def _append_trajectory_step(
        self,
        new_messages: list[dict[str, Any]],
        step_cost: float,
        *,
        wall_time_ms: float = 0.0,
        tool_names: list[str] | None = None,
        token_breakdown: dict[str, Any] | None = None,
    ) -> None:
        """追加本步 trajectory 条目（JSONL），含可观测性字段。"""
        if not self.config.trajectory_path:
            return
        entry: dict[str, Any] = {
            "step": self.n_steps,
            "messages": new_messages,
            "cost": step_cost,
            "total_cost": self.total_cost,
            "wall_time_ms": wall_time_ms,
            "tool_names": tool_names or [],
        }
        if token_breakdown:
            entry["token_breakdown"] = token_breakdown
        self._write_jsonl_line(entry)

    def _append_trajectory_exit(
        self,
        status: str,
        exc: Exception | None,
    ) -> None:
        """追加 exit 条目（JSONL），无论成功还是异常都会调用。"""
        if not self.config.trajectory_path:
            return
        entry: dict[str, Any] = {
            "exit": {
                "status": status,
                "total_steps": self.n_steps,
                "total_cost": self.total_cost,
            }
        }
        if exc is not None:
            entry["exit"]["error"] = str(exc)
        self._write_jsonl_line(entry)

    def _write_jsonl_line(self, entry: dict[str, Any]) -> None:
        """追加一行 JSON 到 trajectory 文件。"""
        path = self.config.trajectory_path
        assert path is not None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception as e:
            logger.error("Failed to write trajectory to %s: %s", path, e)
