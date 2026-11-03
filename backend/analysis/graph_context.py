from __future__ import annotations

import ast
from typing import Any

import networkx as nx
from pydantic import BaseModel

from .qualified_symbols import FileSymbolTable, QualifiedSymbol, analyze_file_symbols

TAINT_SOURCES = {
    "request.args",
    "request.form",
    "request.json",
    "request.data",
    "request.files",
    "request.headers",
    "request.cookies",
    "request.values",
    "request.GET",
    "request.POST",
    "request.query_params",
    "sys.argv",
    "os.environ",
}

SQL_SINKS = {"execute", "executemany", "raw", "cursor.execute"}
CMD_SINKS = {"system", "popen", "run", "Popen", "call", "check_output"}
PATH_SINKS = {"open", "send_file", "send_from_directory"}
HTML_SINKS = {"render_template_string", "mark_safe"}


class TaintCheckResult(BaseModel):
    is_vulnerable: bool
    sink_type: str  # "sql", "command", "path", "html", "unknown"
    is_parameterized: bool = False
    is_constant: bool = False
    has_sanitizer: bool = False
    details: str = ""


def inspect_call_safety(call_node: ast.Call, source_text: str) -> TaintCheckResult:
    """Analyze AST call node to check for parameterization vs string formatting."""
    func_name = ""
    if isinstance(call_node.func, ast.Name):
        func_name = call_node.func.id
    elif isinstance(call_node.func, ast.Attribute):
        func_name = call_node.func.attr

    # 1. SQL Sinks: execute(sql, params)
    if func_name in {"execute", "executemany", "raw"}:
        args = call_node.args
        if not args:
            return TaintCheckResult(is_vulnerable=False, sink_type="sql", details="execute with no args")

        # Check if parameterized (second argument is tuple, list, dict, or name)
        if len(args) >= 2:
            second_arg = args[1]
            if isinstance(second_arg, (ast.Tuple, ast.List, ast.Dict, ast.Name)):
                return TaintCheckResult(
                    is_vulnerable=False,
                    sink_type="sql",
                    is_parameterized=True,
                    details="Parameterized SQL query with parameter binding",
                )

        first_arg = args[0]
        # Check if first arg is a pure constant string without user interpolation
        if isinstance(first_arg, ast.Constant):
            return TaintCheckResult(
                is_vulnerable=False,
                sink_type="sql",
                is_constant=True,
                details="Constant SQL query without user interpolation",
            )

        # Check for f-string or % formatting or .format() or + concatenation
        if isinstance(first_arg, ast.JoinedStr):  # f-string
            return TaintCheckResult(
                is_vulnerable=True,
                sink_type="sql",
                details="SQL query constructed with unescaped f-string interpolation",
            )
        elif isinstance(first_arg, ast.BinOp):
            if isinstance(first_arg.op, (ast.Mod, ast.Add)):  # % or +
                return TaintCheckResult(
                    is_vulnerable=True,
                    sink_type="sql",
                    details="SQL query constructed with % format or string concatenation (+)",
                )
        elif isinstance(first_arg, ast.Call):
            if isinstance(first_arg.func, ast.Attribute) and first_arg.func.attr == "format":
                return TaintCheckResult(
                    is_vulnerable=True,
                    sink_type="sql",
                    details="SQL query constructed with str.format()",
                )

        return TaintCheckResult(is_vulnerable=True, sink_type="sql", details="Unparameterized dynamic SQL query")

    # 2. Command Sinks: os.system(cmd), subprocess.run(cmd)
    if func_name in CMD_SINKS:
        args = call_node.args
        keywords = {kw.arg: kw.value for kw in call_node.keywords if kw.arg}

        shell_val = keywords.get("shell")
        shell_is_true = False
        if isinstance(shell_val, ast.Constant) and shell_val.value is True:
            shell_is_true = True

        if func_name == "system":
            shell_is_true = True

        if not args:
            return TaintCheckResult(is_vulnerable=False, sink_type="command", details="empty args")

        first_arg = args[0]
        if isinstance(first_arg, ast.Constant):
            return TaintCheckResult(
                is_vulnerable=False, sink_type="command", is_constant=True, details="Constant command string"
            )

        if shell_is_true:
            if isinstance(first_arg, (ast.JoinedStr, ast.BinOp)) or (
                isinstance(first_arg, ast.Call) and getattr(first_arg.func, "attr", "") == "format"
            ):
                return TaintCheckResult(
                    is_vulnerable=True,
                    sink_type="command",
                    details="Command constructed via formatted string executed in shell mode",
                )
        else:
            if isinstance(first_arg, (ast.List, ast.Tuple)):
                return TaintCheckResult(
                    is_vulnerable=False,
                    sink_type="command",
                    details="Command invoked with argument list without shell",
                )

        return TaintCheckResult(is_vulnerable=shell_is_true, sink_type="command", details="Command execution")

    return TaintCheckResult(is_vulnerable=False, sink_type="unknown", details="Non-sink call")


class CodebaseGraph:
    def __init__(self):
        self.tables: dict[str, FileSymbolTable] = {}
        self.graph: nx.DiGraph = nx.DiGraph()
        self.symbol_lookup: dict[str, QualifiedSymbol] = {}

    def build_from_files(self, files: list[dict[str, Any]]) -> None:
        """Parse all Python files and populate graph nodes and call edges."""
        self.tables.clear()
        self.graph.clear()
        self.symbol_lookup.clear()

        # Phase 1: parse symbols
        for f in files:
            rel_path = f["relative_path"]
            if not rel_path.endswith(".py"):
                continue
            table = analyze_file_symbols(rel_path, f["content"])
            self.tables[rel_path] = table
            for sym_id, sym in table.symbols.items():
                self.symbol_lookup[sym_id] = sym
                self.graph.add_node(
                    sym_id,
                    kind=sym.kind,
                    module=sym.module,
                    name=sym.name,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    file=rel_path,
                )

        # Phase 2: resolve calls and add edges
        for rel_path, table in self.tables.items():
            for sym_id, sym in table.symbols.items():
                for call_name in sym.calls:
                    target_id = self._resolve_target(call_name, table, sym)
                    if target_id and target_id in self.symbol_lookup:
                        self.graph.add_edge(sym_id, target_id, kind="calls")

    def _resolve_target(self, call_name: str, current_table: FileSymbolTable, current_symbol=None) -> str | None:
        """Resolve explicit imports and lexical symbols; leave dynamic calls unresolved."""
        parts = call_name.split(".")
        prefix = parts[0]
        if prefix in {"self", "cls"} and current_symbol and current_symbol.scope_path:
            candidate = "::".join([current_table.module_path, *current_symbol.scope_path, *parts[1:]])
            return candidate if candidate in self.symbol_lookup else None
        for imp in current_table.imports:
            if imp.alias != prefix:
                continue
            suffix = ([imp.imported_name] if imp.imported_name else []) + parts[1:]
            for module in [imp.module.replace(".", "/") + ".py", imp.module.replace(".", "/") + "/__init__.py"]:
                candidate = "::".join([module, *suffix])
                if candidate in self.symbol_lookup:
                    return candidate
        if len(parts) == 1:
            scope = current_symbol.scope_path if current_symbol else []
            for length in range(len(scope), -1, -1):
                candidate = "::".join([current_table.module_path, *scope[:length], call_name])
                if candidate in self.symbol_lookup:
                    return candidate
        return None

    def get_context_for_location(
        self,
        rel_path: str,
        start_line: int,
        files: list[dict[str, Any]],
        hops: int = 1,
    ) -> dict[str, Any]:
        """Gather primary symbol, callers, callees, and configuration context."""
        # Find symbol containing start_line
        eligible = [sym for sym in self.symbol_lookup.values() if sym.module == rel_path and sym.start_line <= start_line <= sym.end_line]
        primary_sym = min(eligible,key=lambda sym:sym.end_line-sym.start_line) if eligible else None

        file_content_map = {f["relative_path"]: f["content"] for f in files}
        related_symbols: list[QualifiedSymbol] = []
        callers: list[str] = []
        callees: list[str] = []

        if primary_sym and primary_sym.id in self.graph:
            # Predecessors (callers)
            for pred in self.graph.predecessors(primary_sym.id):
                callers.append(pred)
                if pred in self.symbol_lookup:
                    related_symbols.append(self.symbol_lookup[pred])

            # Successors (callees)
            for succ in self.graph.successors(primary_sym.id):
                callees.append(succ)
                if succ in self.symbol_lookup:
                    related_symbols.append(self.symbol_lookup[succ])

        # Gather relevant snippets
        context_snippets = []
        # Add primary file snippet
        if rel_path in file_content_map:
            lines = file_content_map[rel_path].splitlines()
            ctx_start = max(0, start_line - 15)
            ctx_end = min(len(lines), start_line + 25)
            snippet = "\n".join(f"{i + 1:4d} | {lines[i]}" for i in range(ctx_start, ctx_end))
            context_snippets.append(
                f"### Primary File: {rel_path} (lines {ctx_start + 1}-{ctx_end}):\n```python\n{snippet}\n```"
            )

        # Add related symbols snippets
        for r_sym in related_symbols[:3]:
            r_mod = r_sym.module
            if r_mod in file_content_map:
                r_lines = file_content_map[r_mod].splitlines()
                s_start = max(0, r_sym.start_line - 5)
                s_end = min(len(r_lines), r_sym.end_line + 5)
                r_snippet = "\n".join(f"{i + 1:4d} | {r_lines[i]}" for i in range(s_start, s_end))
                context_snippets.append(f"### Related Function ({r_sym.id}):\n```python\n{r_snippet}\n```")

        return {
            "primary_symbol": primary_sym.id if primary_sym else f"{rel_path}:L{start_line}",
            "callers": callers,
            "callees": callees,
            "context_text": "\n\n".join(context_snippets),
        }
