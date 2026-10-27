import string

from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_python as tspy
import networkx as nx

PY_LANGUAGE = Language(tspy.language())
parser = Parser(PY_LANGUAGE)

SOURCES = {
    "request.args",
    "request.form",
    "request.json",
    "request.data",
    "request.files",
    "request.cookies",
    "request.headers",
    "request.values",
    "request.GET",
    "request.POST",
    "request.FILES",
    "request.COOKIES",
    "request.META",
    "request.body",
    "request.post",
    "request.json",
    "request.query",
    "request.match_info",
    "request.headers",
    "request.cookies",
    "request.content",
    "request.rel_url",
    "request.query_params",
    "request.path_params",
    "request.form",
    "input",
    "os.environ",
    "sys.argv",
    "sys.stdin",
}

SOURCE_CALLS = {
    "request.post",
    "request.json",
    "request.text",
    "request.read",
    "request.multipart",
    "request.content.read",
    "get_session",
    "input",
}

SINKS = {
    "execute",
    "raw",
    "executemany",
    "system",
    "popen",
    "run",
    "call",
    "check_output",
    "Popen",
    "eval",
    "exec",
    "render",
    "render_template",
    "render_template_string",
    "mark_safe",
    "open",
    "send_file",
    "send_from_directory",
    "redirect",
}

SANITIZERS = {
    "escape",
    "clean",
    "sanitize",
    "validate",
    "quote",
    "encode",
    "strip_tags",
    "parameterize",
    "bleach",
}

FUNC_QUERY = Query(
    PY_LANGUAGE,
    """
    (function_definition
      name: (identifier) @func_name
      parameters: (parameters) @func_params
      body: (block) @func_body)
    """,
)

CALL_QUERY = Query(
    PY_LANGUAGE,
    """
    (call) @call_node
    """,
)

ATTRIBUTE_QUERY = Query(
    PY_LANGUAGE,
    """
    (attribute
      object: (_) @attr_object
      attribute: (identifier) @attr_name)
    """,
)

ASSIGNMENT_QUERY = Query(
    PY_LANGUAGE,
    """
    (assignment
      left: (_) @assign_target
      right: (_) @assign_value)
    """,
)

SUBSCRIPT_QUERY = Query(
    PY_LANGUAGE,
    """
    (subscript
      value: (_) @sub_value
      subscript: (_) @sub_key)
    """,
)


class GraphBuilder:

    def __init__(self):
        self.graph = nx.DiGraph()
        self._func_name_to_id = {}

    def build_from_files(self, files: list[dict]) -> nx.DiGraph:

        self.graph = nx.DiGraph()
        self._func_name_to_id = {}

        for file_info in files:
            self._process_file(file_info)

        self._link_cross_file_calls()

        return self.graph

    def _process_file(self, file_info: dict):

        filepath = file_info["relative_path"]
        code = file_info["content"]
        code_bytes = code.encode("utf-8")

        tree = parser.parse(code_bytes)
        root = tree.root_node

        cursor = QueryCursor(FUNC_QUERY)
        matches = cursor.matches(root)

        for _pattern_idx, match_captures in matches:
            func_name_node = match_captures["func_name"][0]
            func_params_node = match_captures["func_params"][0]
            func_body_node = match_captures["func_body"][0]

            func_name = (
                func_name_node.text.decode() if func_name_node.text is not None else ""
            )
            func_params = (
                func_params_node.text.decode()
                if func_params_node.text is not None
                else ""
            )
            func_line = func_name_node.start_point[0] + 1

            node_id = f"{filepath}::{func_name}"

            self.graph.add_node(
                node_id,
                type="function",
                file=filepath,
                line=func_line,
                name=func_name,
                params=func_params,
                label=f"{func_name}()",
            )

            self._func_name_to_id[func_name] = node_id
            self._extract_calls_in_scope(func_body_node, filepath, node_id, code_bytes)
            self._extract_sources_in_scope(
                func_body_node, filepath, node_id, code_bytes
            )
            self._extract_source_calls_in_scope(
                func_body_node, filepath, node_id, code_bytes
            )
            self._extract_param_sources(func_name, func_params, filepath, node_id)

    def _extract_calls_in_scope(
        self, body_node, filepath: str, enclosing_func_id: str, code_bytes: bytes
    ):

        cursor = QueryCursor(CALL_QUERY)
        captures = cursor.captures(body_node)

        for call_node in captures.get("call_node", []):
            called_name = self._resolve_call_name(call_node)
            if not called_name:
                continue

            call_line = call_node.start_point[0] + 1
            last_part = called_name.split(".")[-1]

            if last_part in SINKS:
                sink_id = f"{filepath}::SINK::{last_part}::L{call_line}"
                self.graph.add_node(
                    sink_id,
                    type="sink",
                    file=filepath,
                    line=call_line,
                    sink_type=last_part,
                    full_call=called_name,
                    label=f"SINK:{called_name}()",
                )
                self.graph.add_edge(
                    enclosing_func_id,
                    sink_id,
                    type="calls_sink",
                    line=call_line,
                )

            elif last_part in SANITIZERS:
                san_id = f"{filepath}::SANITIZER::{last_part}::L{call_line}"
                self.graph.add_node(
                    san_id,
                    type="sanitizer",
                    file=filepath,
                    line=call_line,
                    sanitizer_type=last_part,
                    full_call=called_name,
                    label=f"SAN:{called_name}()",
                )
                self.graph.add_edge(
                    enclosing_func_id,
                    san_id,
                    type="calls_sanitizer",
                    line=call_line,
                )

            else:
                target_id = self._func_name_to_id.get(last_part)
                if target_id and target_id != enclosing_func_id:
                    self.graph.add_edge(
                        enclosing_func_id,
                        target_id,
                        type="calls",
                        line=call_line,
                    )
                else:
                    if "pending_calls" not in self.graph.nodes[enclosing_func_id]:
                        self.graph.nodes[enclosing_func_id]["pending_calls"] = []
                    self.graph.nodes[enclosing_func_id]["pending_calls"].append(
                        last_part
                    )

    def _resolve_call_name(self, call_node) -> str:
        if not call_node.children:
            return ""

        func_node = call_node.children[0]
        return self._node_to_dotted_name(func_node)

    def _node_to_dotted_name(self, node) -> str:
        if node.type == "identifier":
            return node.text.decode()

        elif node.type == "attribute":
            obj = node.child_by_field_name("object")
            attr = node.child_by_field_name("attribute")
            if obj and attr:
                obj_name = self._node_to_dotted_name(obj)
                attr_name = attr.text.decode()
                return f"{obj_name}.{attr_name}"

        return node.text.decode() if hasattr(node, "text") else ""

    def _extract_sources_in_scope(
        self, body_node, filepath: str, enclosing_func_id: str, code_bytes: bytes
    ):

        cursor = QueryCursor(ATTRIBUTE_QUERY)
        captures = cursor.captures(body_node)

        seen_sources = set()

        objects = captures.get("attr_object", [])
        names = captures.get("attr_name", [])

        for obj_node, name_node in zip(objects, names):
            obj_text = self._node_to_dotted_name(obj_node)
            attr_text = name_node.text.decode() if name_node.text is not None else ""
            full_attr = f"{obj_text}.{attr_text}"
            matched_source = None
            for source in SOURCES:
                if full_attr == source or full_attr.startswith(source + "."):
                    matched_source = source
                    break

            if matched_source and matched_source not in seen_sources:
                seen_sources.add(matched_source)
                source_line = obj_node.start_point[0] + 1
                source_id = f"{filepath}::SOURCE::{matched_source}::L{source_line}"

                self.graph.add_node(
                    source_id,
                    type="source",
                    file=filepath,
                    line=source_line,
                    source_type=matched_source,
                    label=f"SRC:{matched_source}",
                )

                self.graph.add_edge(
                    source_id,
                    enclosing_func_id,
                    type="data_source",
                    line=source_line,
                )

        sub_cursor = QueryCursor(SUBSCRIPT_QUERY)
        sub_captures = sub_cursor.captures(body_node)
        sub_values = sub_captures.get("sub_value", [])
        for sub_val_node in sub_values:
            sub_text = self._node_to_dotted_name(sub_val_node)
            matched_source = None
            for source in SOURCES:
                if (
                    sub_text == source
                    or sub_text.startswith(source + ".")
                    or sub_text.startswith(source + "[")
                ):
                    matched_source = source
                    break
            if matched_source and matched_source not in seen_sources:
                seen_sources.add(matched_source)
                source_line = sub_val_node.start_point[0] + 1
                source_id = f"{filepath}::SOURCE::{matched_source}::L{source_line}"
                if not self.graph.has_node(source_id):
                    self.graph.add_node(
                        source_id,
                        type="source",
                        file=filepath,
                        line=source_line,
                        source_type=matched_source,
                        label=f"SRC:{matched_source}",
                    )
                    self.graph.add_edge(
                        source_id,
                        enclosing_func_id,
                        type="data_source",
                        line=source_line,
                    )

    def _extract_source_calls_in_scope(
        self, body_node, filepath: str, enclosing_func_id: str, code_bytes: bytes
    ):
        """Detect sources that appear as method calls, e.g. await request.post()"""
        cursor = QueryCursor(CALL_QUERY)
        captures = cursor.captures(body_node)

        seen_sources = set()

        for call_node in captures.get("call_node", []):
            called_name = self._resolve_call_name(call_node)
            if not called_name:
                continue

            matched_source = None
            for source_call in SOURCE_CALLS:
                if called_name == source_call or called_name.endswith(
                    "." + source_call
                ):
                    matched_source = source_call
                    break

            if not matched_source:
                for source in SOURCES:
                    if called_name.startswith(source):
                        matched_source = source
                        break

            if matched_source and matched_source not in seen_sources:
                seen_sources.add(matched_source)
                source_line = call_node.start_point[0] + 1
                source_id = f"{filepath}::SOURCE::{matched_source}::L{source_line}"

                if not self.graph.has_node(source_id):
                    self.graph.add_node(
                        source_id,
                        type="source",
                        file=filepath,
                        line=source_line,
                        source_type=matched_source,
                        label=f"SRC:{matched_source}()",
                    )
                    self.graph.add_edge(
                        source_id,
                        enclosing_func_id,
                        type="data_source",
                        line=source_line,
                    )

    def _extract_param_sources(
        self, func_name: str, func_params: str, filepath: str, node_id: str
    ):
        """Mark functions whose parameter names suggest they receive user input
        (e.g., 'request' parameter in view functions) as having an implicit source."""

        REQUEST_PARAMS = {"request", "req"}

        param_text = func_params.strip("()")
        param_names = [
            p.strip().split(":")[0].split("=")[0].strip() for p in param_text.split(",")
        ]
        param_names = [p for p in param_names if p and p != "self" and p != "cls"]

        for param in param_names:
            if param in REQUEST_PARAMS:
                source_id = f"{filepath}::SOURCE::request_param::L{self.graph.nodes[node_id].get('line', 0)}"
                if not self.graph.has_node(source_id):
                    self.graph.add_node(
                        source_id,
                        type="source",
                        file=filepath,
                        line=self.graph.nodes[node_id].get("line", 0),
                        source_type="request (parameter)",
                        label=f"SRC:request_param",
                    )
                    self.graph.add_edge(
                        source_id,
                        node_id,
                        type="data_source",
                        line=self.graph.nodes[node_id].get("line", 0),
                    )

    def _link_cross_file_calls(self):
        for node_id in list(self.graph.nodes):
            node_data = self.graph.nodes[node_id]
            if node_data.get("type") != "function":
                continue

            pending = node_data.pop("pending_calls", [])
            for called_name in pending:
                target_id = self._func_name_to_id.get(called_name)
                if target_id and target_id != node_id:
                    self.graph.add_edge(
                        node_id,
                        target_id,
                        type="calls",
                    )

    def get_sources(self) -> list[str]:
        return [n for n, d in self.graph.nodes(data=True) if d.get("type") == "source"]

    def get_sinks(self) -> list[str]:
        return [n for n, d in self.graph.nodes(data=True) if d.get("type") == "sink"]

    def get_sanitizers(self) -> list[str]:
        return [
            n for n, d in self.graph.nodes(data=True) if d.get("type") == "sanitizer"
        ]

    def get_functions(self) -> list[str]:
        return [
            n for n, d in self.graph.nodes(data=True) if d.get("type") == "function"
        ]

    def find_vulnerable_paths(self) -> list[dict]:
        sources = self.get_sources()
        sinks = self.get_sinks()
        sanitizer_set = set(self.get_sanitizers())
        findings = []

        for source_id in sources:
            for sink_id in sinks:
                try:
                    if nx.has_path(self.graph, source_id, sink_id):
                        path = nx.shortest_path(self.graph, source_id, sink_id)

                        sanitized = bool(sanitizer_set.intersection(set(path)))

                        source_data = self.graph.nodes[source_id]
                        sink_data = self.graph.nodes[sink_id]

                        findings.append(
                            {
                                "source": source_id,
                                "sink": sink_id,
                                "path": path,
                                "sanitized": sanitized,
                                "source_type": source_data.get(
                                    "source_type", "unknown"
                                ),
                                "sink_type": sink_data.get("sink_type", "unknown"),
                                "source_file": source_data.get("file", ""),
                                "sink_file": sink_data.get("file", ""),
                                "source_line": source_data.get("line", 0),
                                "sink_line": sink_data.get("line", 0),
                            }
                        )
                except nx.NetworkXError:
                    continue

        return findings

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"  GRAPH SUMMARY")
        print(f"{'='*60}")
        print(f"  Total nodes: {self.graph.number_of_nodes()}")
        print(f"  Total edges: {self.graph.number_of_edges()}")
        print()

        for ntype in ["function", "source", "sink", "sanitizer"]:
            nodes = [
                (n, d) for n, d in self.graph.nodes(data=True) if d.get("type") == ntype
            ]
            icon = {
                "function": "[FN]",
                "source": "[SRC]",
                "sink": "[SINK]",
                "sanitizer": "[SAN]",
            }.get(ntype, "")
            print(f"  {icon} {ntype.upper()}S ({len(nodes)}):")
            for node_id, data in nodes:
                line_info = f"L{data.get('line', '?')}"
                file_info = data.get("file", "")
                if ntype == "function":
                    print(f"     {data['name']}()  @ {file_info}:{line_info}")
                elif ntype == "source":
                    print(
                        f"     {data.get('source_type', '?')}  @ {file_info}:{line_info}"
                    )
                elif ntype == "sink":
                    print(
                        f"     {data.get('full_call', data.get('sink_type', '?'))}()  @ {file_info}:{line_info}"
                    )
                elif ntype == "sanitizer":
                    print(
                        f"     {data.get('full_call', data.get('sanitizer_type', '?'))}()  @ {file_info}:{line_info}"
                    )
            print()

        print(f"  EDGES ({self.graph.number_of_edges()}):")
        for u, v, data in self.graph.edges(data=True):
            u_short = u.split("::")[-1] if "::" in u else u
            v_short = v.split("::")[-1] if "::" in v else v
            edge_type = data.get("type", "unknown")
            print(f"     {u_short} ──[{edge_type}]──> {v_short}")
        print()


def _match_file(target: str, files: list[dict]) -> str | None:
    import os

    target_norm = os.path.normpath(target)

    for f in files:
        candidate = os.path.normpath(f["relative_path"])
        if candidate == target_norm:
            return f["content"]
    for f in files:
        candidate = os.path.normpath(f["relative_path"])
        if candidate.endswith(target_norm) or target_norm.endswith(candidate):
            return f["content"]

    return None


def extract_function_at_line(lines: list[str], start_line: int) -> list[str]:
    if not lines or start_line < 0:
        return []

    start_line = min(start_line, len(lines) - 1)

    func_start = start_line
    search_from = max(0, start_line - 5)
    for i in range(start_line, search_from - 1, -1):
        stripped = lines[i].lstrip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            func_start = i
            break

    first_stripped = lines[func_start].lstrip()
    if not (
        first_stripped.startswith("def ") or first_stripped.startswith("async def ")
    ):
        end = min(len(lines), start_line + 20)
        return lines[start_line:end]

    base_indent = len(lines[func_start]) - len(lines[func_start].lstrip())
    result = [lines[func_start]]

    for line in lines[func_start + 1 :]:

        if line.strip() == "":
            result.append(line)
            continue
        current_indent = len(line) - len(line.lstrip())

        if current_indent <= base_indent:
            break
        result.append(line)

    while result and result[-1].strip() == "":
        result.pop()

    return result


def extract_code_for_path(
    path_nodes: list[str],
    graph: nx.DiGraph,
    files: list[dict],
    context_lines: int = 5,
) -> str:
    extracted_parts: list[str] = []
    seen: set[str] = set()

    for node_id in path_nodes:
        if node_id in seen:
            continue
        seen.add(node_id)

        if not graph.has_node(node_id):
            extracted_parts.append(f"# [MISSING] {node_id}  (node not in graph)")
            continue

        node_data = graph.nodes[node_id]
        node_file = node_data.get("file", "")
        node_line = node_data.get("line", 0)
        node_type = node_data.get("type", "unknown")

        file_content = _match_file(node_file, files)
        if file_content is None:
            extracted_parts.append(
                f"# [{node_type.upper()}] {node_id}  "
                f"(source file not found: {node_file})"
            )
            continue

        lines = file_content.splitlines()
        if not lines:
            continue

        if node_type == "function" and node_line > 0:
            func_lines = extract_function_at_line(lines, node_line - 1)
            code_snippet = "\n".join(func_lines)
        else:
            start = max(0, node_line - 1 - context_lines)
            end = min(len(lines), node_line + context_lines)
            code_snippet = "\n".join(lines[start:end])

        header = f"# [{node_type.upper()}] {node_id}  " f"({node_file}:{node_line})"
        extracted_parts.append(f"{header}\n{code_snippet}")

    return "\n\n".join(extracted_parts)


def extract_code_for_finding(
    finding: dict,
    files: list[dict],
    context_lines: int = 5,
) -> str:
    target_file = finding.get("file", "")
    target_line = finding.get("line", 0)

    file_content = _match_file(target_file, files)
    if file_content is None:
        return f"# Code not found for {target_file}:{target_line}"

    lines = file_content.splitlines()
    if not lines:
        return "# File is empty"

    zero_based = max(0, target_line - 1)

    func_lines = extract_function_at_line(lines, zero_based)
    if func_lines:
        return "\n".join(func_lines)

    start = max(0, zero_based - context_lines)
    end = min(len(lines), zero_based + context_lines + 1)
    return "\n".join(lines[start:end])
