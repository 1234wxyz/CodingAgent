"""
agent/tools/semantic_search.py — Python 符号级语义检索工具

依赖：tree-sitter==0.21.3, tree-sitter-python==0.21.0

只做 Python，按需解析（无状态，无全局缓存），注册为标准 Tool。

支持三个 command：
  - list_symbols  列出文件中所有函数/类/方法定义
  - find_symbol   在目录里按名称搜索符号定义（跨文件）
  - get_context   返回某行所在函数/类的完整代码块

非 Python 文件或解析失败时返回空结果，不报错。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolObservation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# tree-sitter 懒加载（避免 import 时报错影响整包加载）
# ---------------------------------------------------------------------------

_parser = None
_language = None


def _get_parser():
    """懒加载并缓存 tree-sitter parser（模块级单例）。"""
    global _parser, _language
    if _parser is not None:
        return _parser, _language
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        _language = Language(tspython.language(), "python")
        _parser = Parser()
        _parser.set_language(_language)
    except Exception as e:
        raise ImportError(
            f"tree-sitter not available: {e}. "
            "Install with: pip install tree-sitter==0.21.3 tree-sitter-python==0.21.0"
        ) from e
    return _parser, _language


# ---------------------------------------------------------------------------
# 核心解析工具函数
# ---------------------------------------------------------------------------

def _parse_file(path: Path):
    """解析 Python 文件，返回 (tree, source_bytes)。失败返回 (None, None)。"""
    if not path.is_file() or path.suffix != ".py":
        return None, None
    try:
        parser, _ = _get_parser()
        source = path.read_bytes()
        tree = parser.parse(source)
        return tree, source
    except Exception as e:
        logger.debug("Failed to parse %s: %s", path, e)
        return None, None


def _node_name(node) -> str:
    name_node = node.child_by_field_name("name")
    return name_node.text.decode("utf-8") if name_node else "?"


def _node_signature(node, source: bytes) -> str:
    """提取函数的 parameters 或类的 superclasses 作为签名（单行截断）。"""
    if node.type == "function_definition":
        params = node.child_by_field_name("parameters")
        if not params:
            return "()"
        text = params.text.decode("utf-8")
        # 压缩多行参数为单行
        text = " ".join(text.split())
        return text if len(text) <= 60 else text[:57] + "..."
    elif node.type == "class_definition":
        args = node.child_by_field_name("superclasses")
        return f"({args.text.decode('utf-8')})" if args else ""
    return ""


def _kind_label(node_type: str, is_method: bool) -> str:
    if node_type == "class_definition":
        return "class"
    return "method" if is_method else "function"


def _collect_symbols(node, source: bytes, is_method: bool = False) -> list[dict]:
    """从 AST 节点收集函数/类/方法定义。"""
    symbols = []
    for child in node.children:
        if child.type in ("function_definition", "class_definition"):
            name = _node_name(child)
            sig = _node_signature(child, source)
            kind = _kind_label(child.type, is_method)
            line = child.start_point[0] + 1  # 1-based
            end_line = child.end_point[0] + 1
            symbols.append({
                "name": name,
                "kind": kind,
                "line": line,
                "end_line": end_line,
                "signature": sig,
            })
            # 递归收集类内方法（只深入一层：类内的函数定义）
            if child.type == "class_definition":
                body = child.child_by_field_name("body")
                if body:
                    symbols.extend(_collect_symbols(body, source, is_method=True))
    return symbols


def _find_enclosing_node(root_node, target_line_0based: int):
    """找到包含 target_line 的最内层 function/class 节点。"""
    best = None
    best_size = float("inf")

    def walk(node):
        nonlocal best, best_size
        if node.type in ("function_definition", "class_definition"):
            start = node.start_point[0]
            end = node.end_point[0]
            if start <= target_line_0based <= end:
                size = end - start
                if size < best_size:
                    best_size = size
                    best = node
        for child in node.children:
            walk(child)

    walk(root_node)
    return best


# ---------------------------------------------------------------------------
# SemanticSearchTool
# ---------------------------------------------------------------------------

class SemanticSearchTool(Tool):
    """Python 符号级语义检索工具（tree-sitter backed）。"""

    def __init__(self, work_dir: Path | None = None) -> None:
        self._work_dir = Path(work_dir).resolve() if work_dir else None

    def _resolve(self, path_str: str) -> Path:
        """Resolve path_str against work_dir (if set), else leave as-is."""
        p = Path(path_str)
        if not p.is_absolute() and self._work_dir is not None:
            return self._work_dir / p
        return p

    @property
    def name(self) -> str:
        return "semantic_search"

    @property
    def description(self) -> str:
        return (
            "Python symbol-level search using tree-sitter. "
            "Commands: list_symbols (list all functions/classes in a file), "
            "find_symbol (search by name across a directory), "
            "get_context (get the function/class body containing a given line). "
            "Only supports Python files (.py). Non-Python files are silently skipped."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "semantic_search",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["list_symbols", "find_symbol", "get_context"],
                            "description": "Operation to perform.",
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "[list_symbols / get_context] Path to a Python file."
                            ),
                        },
                        "name": {
                            "type": "string",
                            "description": (
                                "[find_symbol] Symbol name to search for (exact or partial match)."
                            ),
                        },
                        "directory": {
                            "type": "string",
                            "description": (
                                "[find_symbol] Directory to search recursively. Defaults to '.'."
                            ),
                        },
                        "line": {
                            "type": "integer",
                            "description": (
                                "[get_context] Line number (1-based) to find enclosing function/class."
                            ),
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolObservation:
        command = arguments.get("command")
        if command == "list_symbols":
            return self._list_symbols(arguments)
        elif command == "find_symbol":
            return self._find_symbol(arguments)
        elif command == "get_context":
            return self._get_context(arguments)
        else:
            return ToolObservation(
                output="",
                success=False,
                error=f"Unknown command {command!r}. Use: list_symbols, find_symbol, get_context.",
            )

    # ------------------------------------------------------------------
    # list_symbols
    # ------------------------------------------------------------------

    def _list_symbols(self, args: dict) -> ToolObservation:
        path_str = args.get("path", "")
        if not path_str:
            return ToolObservation(output="", success=False, error="Missing argument 'path'.")

        path = self._resolve(path_str)
        tree, source = _parse_file(path)
        if tree is None:
            # 非 Python 或解析失败 → 返回空，不报错
            return ToolObservation(
                output=f"No symbols found (file is not Python or could not be parsed): {path_str}",
                success=True,
            )

        symbols = _collect_symbols(tree.root_node, source)
        if not symbols:
            return ToolObservation(output=f"No symbols found in {path_str}.", success=True)

        lines = [f"Symbols in {path_str}:"]
        for s in symbols:
            indent = "  " if s["kind"] == "method" else ""
            sig = s["signature"] if s["kind"] != "class" else (s["signature"] or "")
            lines.append(f"{indent}{s['kind']} {s['name']}{sig}  (line {s['line']})")

        return ToolObservation(output="\n".join(lines), success=True)

    # ------------------------------------------------------------------
    # find_symbol
    # ------------------------------------------------------------------

    def _find_symbol(self, args: dict) -> ToolObservation:
        symbol_name = args.get("name", "").strip()
        if not symbol_name:
            return ToolObservation(output="", success=False, error="Missing argument 'name'.")

        directory = self._resolve(args.get("directory", "."))
        if not directory.is_dir():
            return ToolObservation(
                output="", success=False, error=f"Directory not found: {directory}"
            )

        results: list[str] = []
        py_files = [
            p for p in directory.rglob("*.py")
            if "__pycache__" not in p.parts and ".git" not in p.parts
        ]

        for py_file in sorted(py_files):
            tree, source = _parse_file(py_file)
            if tree is None:
                continue
            symbols = _collect_symbols(tree.root_node, source)
            for s in symbols:
                if symbol_name.lower() in s["name"].lower():
                    results.append(
                        f"{py_file}:{s['line']}  {s['kind']} {s['name']}{s['signature']}"
                    )

        if not results:
            return ToolObservation(
                output=f"Symbol {symbol_name!r} not found in {directory}.", success=True
            )

        header = f"Found {len(results)} result(s) for {symbol_name!r} in {directory}:"
        return ToolObservation(output=header + "\n" + "\n".join(results), success=True)

    # ------------------------------------------------------------------
    # get_context
    # ------------------------------------------------------------------

    def _get_context(self, args: dict) -> ToolObservation:
        path_str = args.get("path", "")
        line_1based = args.get("line")

        if not path_str:
            return ToolObservation(output="", success=False, error="Missing argument 'path'.")
        if line_1based is None:
            return ToolObservation(output="", success=False, error="Missing argument 'line'.")

        path = self._resolve(path_str)
        tree, source = _parse_file(path)
        if tree is None:
            return ToolObservation(
                output=f"Cannot parse {path_str} as Python.", success=True
            )

        target_line_0 = int(line_1based) - 1
        node = _find_enclosing_node(tree.root_node, target_line_0)

        if node is None:
            return ToolObservation(
                output=f"Line {line_1based} in {path_str} is not inside any function or class.",
                success=True,
            )

        name = _node_name(node)
        kind = _kind_label(node.type, False)  # top-level kind for header
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        # 提取源文本
        source_lines = source.decode("utf-8", errors="replace").splitlines()
        body_lines = source_lines[node.start_point[0]: node.end_point[0] + 1]
        body_text = "\n".join(body_lines)

        header = f"[{kind} {name!r} at lines {start_line}-{end_line} in {path_str}]"
        return ToolObservation(output=f"{header}\n{body_text}", success=True)
