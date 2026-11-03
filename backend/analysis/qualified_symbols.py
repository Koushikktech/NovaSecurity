from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field


class QualifiedSymbol(BaseModel):
    id: str  # "path/module.py::ClassName::method_name"
    name: str  # "method_name"
    module: str  # "path/module.py"
    scope_path: list[str] = Field(default_factory=list)  # ["ClassName"]
    kind: str  # "function", "class", "method"
    start_line: int
    end_line: int
    parameters: list[str] = Field(default_factory=list)
    docstring: str | None = None
    calls: list[str] = Field(default_factory=list)  # raw call names observed in body


class ImportAlias(BaseModel):
    module: str
    imported_name: str
    alias: str


class FileSymbolTable(BaseModel):
    module_path: str
    imports: list[ImportAlias] = Field(default_factory=list)
    symbols: dict[str, QualifiedSymbol] = Field(default_factory=dict)
    parse_error: str | None = None


def analyze_file_symbols(relative_path: str, source_code: str) -> FileSymbolTable:
    import sys
    from pathlib import Path

    from analysis.cache import AnalysisCache

    cache = AnalysisCache("python-symbols-v2", Path(__file__).read_bytes(), [sys.version, relative_path, source_code])
    data = cache.read()
    if data is not None:
        try:
            return FileSymbolTable.model_validate(data)
        except ValueError:
            pass
    result = _cached_symbols(relative_path, source_code).model_copy(deep=True)
    cache.write(result.model_dump())
    return result


@lru_cache(maxsize=256)
def _cached_symbols(relative_path: str, source_code: str) -> FileSymbolTable:
    """Extract Python symbols using the runtime's non-executing standard AST parser."""
    import ast
    from pathlib import PurePosixPath

    table = FileSymbolTable(module_path=relative_path)
    try:
        root = ast.parse(source_code)
    except (SyntaxError, ValueError, RecursionError) as exc:
        table.parse_error = str(exc)
        return table
    for node in root.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                table.imports.append(
                    ImportAlias(
                        module=alias.name if alias.asname else alias.name.split(".")[0],
                        imported_name="",
                        alias=alias.asname or alias.name.split(".")[0],
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                parents = list(PurePosixPath(relative_path).parent.parts)
                module = ".".join(parents[: len(parents) - node.level + 1] + ([module] if module else []))
            for alias in node.names:
                if alias.name != "*":
                    table.imports.append(
                        ImportAlias(module=module, imported_name=alias.name, alias=alias.asname or alias.name)
                    )

    class Calls(ast.NodeVisitor):
        def __init__(self):
            self.names = []

        def visit_Call(self, node):
            try:
                self.names.append(ast.unparse(node.func))
            except (ValueError, RecursionError):
                pass
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            pass

        def visit_AsyncFunctionDef(self, node):
            pass

        def visit_ClassDef(self, node):
            pass

    def walk(nodes, scope):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                identifier = "::".join([relative_path, *scope, node.name])
                calls = Calls()
                if not isinstance(node, ast.ClassDef):
                    for child in node.body:
                        calls.visit(child)
                parameters = []
                if not isinstance(node, ast.ClassDef):
                    parameters = [p.arg for p in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
                table.symbols[identifier] = QualifiedSymbol(
                    id=identifier,
                    name=node.name,
                    module=relative_path,
                    scope_path=list(scope),
                    kind="class" if isinstance(node, ast.ClassDef) else "method" if scope else "function",
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    parameters=parameters,
                    docstring=ast.get_docstring(node),
                    calls=calls.names,
                )
                walk(node.body, [*scope, node.name])
            else:
                # Definitions nested under conditionals retain their lexical scope.
                for field in ("body", "orelse", "finalbody"):
                    children = getattr(node, field, None)
                    if isinstance(children, list):
                        walk(children, scope)

    walk(root.body, [])
    return table
