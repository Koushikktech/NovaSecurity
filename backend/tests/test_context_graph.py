from __future__ import annotations

import ast

from analysis.graph_context import CodebaseGraph, inspect_call_safety
from analysis.qualified_symbols import analyze_file_symbols


def _get_call_node(code_snippet: str) -> ast.Call:
    tree = ast.parse(code_snippet)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            return node
    raise ValueError("No call node found in snippet")


def test_four_graph_probes_counterexamples():
    """Verify that the 4 graph counterexamples from Section 2 are accurately classified."""

    # Probe 1: Constant SQL query unrelated to input
    code1 = "cursor.execute('SELECT id, name FROM users WHERE active = 1')"
    res1 = inspect_call_safety(_get_call_node(code1), code1)
    assert res1.is_vulnerable is False
    assert res1.is_constant is True
    assert res1.sink_type == "sql"

    # Probe 2: Parameterized SQL query
    code2 = "cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"
    res2 = inspect_call_safety(_get_call_node(code2), code2)
    assert res2.is_vulnerable is False
    assert res2.is_parameterized is True
    assert res2.sink_type == "sql"

    # Probe 3: Safe subprocess command execution with argument list (shell=False)
    code3 = "subprocess.run(['ls', '-la', user_path])"
    res3 = inspect_call_safety(_get_call_node(code3), code3)
    assert res3.is_vulnerable is False
    assert res3.sink_type == "command"

    # Probe 4: Genuinely concatenated SQL query
    code4 = "cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')"
    res4 = inspect_call_safety(_get_call_node(code4), code4)
    assert res4.is_vulnerable is True
    assert res4.sink_type == "sql"


def test_qualified_symbols_name_collisions():
    """Verify that same-name functions in different classes or scopes receive distinct qualified IDs."""
    source_a = """
class UserHandler:
    def process(self, request):
        return "user"

class OrderHandler:
    def process(self, request):
        return "order"

def process(request):
    return "global"
"""
    table = analyze_file_symbols("handlers.py", source_a)
    symbols = table.symbols

    assert "handlers.py::UserHandler::process" in symbols
    assert "handlers.py::OrderHandler::process" in symbols
    assert "handlers.py::process" in symbols

    user_proc = symbols["handlers.py::UserHandler::process"]
    order_proc = symbols["handlers.py::OrderHandler::process"]
    global_proc = symbols["handlers.py::process"]

    assert user_proc.id != order_proc.id
    assert user_proc.scope_path == ["UserHandler"]
    assert order_proc.scope_path == ["OrderHandler"]
    assert global_proc.scope_path == []


def test_codebase_graph_cross_file_traversal():
    """Verify that call graph traverses callers and callees with qualified IDs."""
    files = [
        {
            "relative_path": "routes/user.py",
            "content": """
from services.auth import authenticate_user

def login_route(request):
    return authenticate_user(request.username, request.password)
""",
        },
        {
            "relative_path": "services/auth.py",
            "content": """
from repositories.user import find_by_credentials

def authenticate_user(u, p):
    return find_by_credentials(u, p)
""",
        },
        {
            "relative_path": "repositories/user.py",
            "content": """
def find_by_credentials(u, p):
    return None
""",
        },
    ]

    graph = CodebaseGraph()
    graph.build_from_files(files)

    # routes/user.py::login_route calls services/auth.py::authenticate_user
    ctx = graph.get_context_for_location("services/auth.py", 4, files)
    assert ctx["primary_symbol"] == "services/auth.py::authenticate_user"
    assert any("routes/user.py" in c for c in ctx["callers"])
