"""Language-aware parse checks and bounded, deterministic context retrieval."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

from runtime_budget import remaining_time
from schemas.contracts import AnalysisStatus, EvidenceItem, Finding, FindingCategory, Location, Severity

SUPPORTED = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript"}


def finding(run_id, path, line, rule, message, category="bug", related=None):
    return Finding(
        run_id=run_id,
        stable_fingerprint=hashlib.sha256(f"{path}:{rule}:{message}".encode()).hexdigest()[:24],
        category=FindingCategory(category),
        rule_id=rule,
        title=message.split(". ")[0],
        explanation=message,
        user_impact=(
            "The async function can finish before the operations complete, so failures and completion are not propagated."
            if rule == "js:async-foreach"
            else "Existing callers may raise an argument error when the changed interface is used."
            if "signature" in rule
            else "The parser or static rule identifies a concrete syntax or style problem."
        ),
        proposed_remedy=(
            "Use await Promise.all(items.map(async ...)) or an awaited for…of loop, depending on ordering requirements."
            if rule == "js:async-foreach"
            else "Update the caller to supply the new arguments, or preserve compatibility with a default in the callee."
            if "signature" in rule
            else "Inspect the cited syntax or style rule."
        ),
        severity=Severity.LOW if category == "style" else Severity.MEDIUM,
        primary_location=Location(path=path, start_line=line, end_line=line),
        analysis_status=AnalysisStatus.STATIC_MATCH,
        analysis_sources=["proofline-language"],
        evidence_items=[EvidenceItem(kind="static_analysis", tool_or_profile=rule, output_snippet=message)],
        related_locations=related or [],
    )


def javascript_analysis(files, run_id):
    selected = [
        {"path": f["relative_path"], "content": f["content"]}
        for f in files
        if Path(f["relative_path"]).suffix in {".js", ".jsx", ".ts", ".tsx"} or f["relative_path"] == "tsconfig.json"
    ]
    if not selected:
        return [], {}, {"status": "skipped", "reason": "No JavaScript/TypeScript files"}
    try:
        from analysis.cache import AnalysisCache

        script = Path(__file__).resolve().parents[2] / "scripts/analyze-javascript.cjs"
        compiler_version = json.loads(
            (script.parent.parent / "frontend/node_modules/typescript/package.json").read_text()
        )["version"]
        cache = AnalysisCache("typescript-v2", script.read_bytes(), {"files": selected, "compiler": compiler_version})
        rows = cache.read()
        if rows is None:
            proc = subprocess.run(
                ["node", "--max-old-space-size=512", str(script)],
                input=json.dumps(selected),
                text=True,
                capture_output=True,
                timeout=remaining_time(30),
                check=True,
            )
            rows = json.loads(proc.stdout)
            cache.write(rows)
        results = [
            finding(run_id, row["path"], item["line"], item["rule"], item["message"], item["category"])
            for row in rows
            for item in row["findings"]
        ]
        return (
            results,
            {r["path"]: r for r in rows},
            {
                "status": "executed",
                "tool": "typescript-parser",
                "files": len(rows),
                "capabilities": ["syntax", "selected_semantic_diagnostics", "compiler_references", "tsconfig_paths"],
                "limitations": [
                    "Snapshot-local module resolution; external dependency declarations absent unless included; selected diagnostic codes only"
                ],
            },
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return (
            [],
            {},
            {
                "status": "failed",
                "error": type(exc).__name__,
                "reason": "Install Node and frontend dependencies for JS/TS parsing",
            },
        )


def select_context(files, changed, budget=60000):
    """Include changed modules, imports, and reverse dependencies. Never execute code."""
    inventory = {f["relative_path"]: f for f in files if Path(f["relative_path"]).suffix in SUPPORTED}
    names = {p: Path(p).stem for p in inventory}
    selected = set(changed) & inventory.keys()
    if not selected:
        # Favor application entrypoints and substantive modules over alphabetical order.
        ranked = sorted(
            inventory,
            key=lambda p: (
                -(
                    3 * any(x in p.lower() for x in ("route", "service", "api", "main", "index"))
                    + min(inventory[p]["content"].count("def ") + inventory[p]["content"].count("function "), 10)
                    - 4 * ("test" in p.lower())
                ),
                p,
            ),
        )
        selected = set(ranked[:8])
    for _ in range(2):
        expanded = set(selected)
        for path, f in inventory.items():
            # Conservative lexical dependencies are retrieval hints, not resolved calls.
            if any(
                names[other] in f["content"] or names[path] in inventory[other]["content"]
                for other in selected
                if other != path
            ):
                expanded.add(path)
        selected = expanded

    def rank(path):
        references = sum(
            names[other] in inventory[path]["content"] for other in changed if other in names and other != path
        )
        return (path not in changed, -references, "test" not in path, path)

    ordered = sorted(selected, key=rank)
    parts = []
    omitted = []
    used = 0
    for path in ordered:
        text = inventory[path]["content"]
        block = f"File: {path}\n" + "\n".join(f"{i + 1}: {line}" for i, line in enumerate(text.splitlines()))
        if used + len(block) > budget:
            omitted.append(path)
            continue
        used += len(block)
        parts.append(block)
    return "\n\n".join(parts), {
        "selected": ordered,
        "omitted": omitted,
        "selection": "bounded lexical imports/callers; unresolved relationships are hints",
    }


def python_contracts(base_files, head_files, changed, run_id):
    """Check explicit imported calls against changed top-level required signatures."""
    from schemas.contracts import RelatedLocation

    def parsed(files):
        result = {}
        for f in files:
            if f["relative_path"].endswith(".py"):
                try:
                    result[f["relative_path"]] = ast.parse(f["content"])
                except SyntaxError:
                    pass
        return result

    base, head = parsed(base_files), parsed(head_files)
    results = []
    for path in changed:
        if path not in base or path not in head:
            continue
        old = {n.name: n for n in base[path].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in head[path].body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name not in old:
                continue
            if ast.dump(old[fn.name].args) == ast.dump(fn.args):
                continue
            module = path.removesuffix(".py").replace("/", ".")
            required = [a.arg for a in fn.args.posonlyargs + fn.args.args][
                : len(fn.args.posonlyargs + fn.args.args) - len(fn.args.defaults)
            ]
            for caller, tree in head.items():
                aliases = {
                    a.asname or a.name
                    for n in tree.body
                    if isinstance(n, ast.ImportFrom) and n.module == module
                    for a in n.names
                    if a.name == fn.name
                }
                for call in ast.walk(tree):
                    if (
                        not isinstance(call, ast.Call)
                        or not isinstance(call.func, ast.Name)
                        or call.func.id not in aliases
                    ):
                        continue
                    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
                        continue
                    bound = set(required[: len(call.args)]) | {k.arg for k in call.keywords}
                    missing = set(required) - bound
                    if missing:
                        results.append(
                            finding(
                                run_id,
                                caller,
                                call.lineno,
                                "python:changed-signature",
                                f"Call to {module}.{fn.name} is missing required arguments {sorted(missing)} after this PR changes its signature.",
                                related=[
                                    RelatedLocation(
                                        path=path,
                                        lines=[fn.lineno],
                                        qualified_symbol=f"{module}.{fn.name}",
                                        relationship="callee",
                                    )
                                ],
                            )
                        )
    return results


def test_gaps(base_files, head_files, changed):
    tests = [f for f in head_files if "test" in f["relative_path"]]
    gaps = []
    for path in changed:
        if "test" in path or Path(path).suffix not in SUPPORTED:
            continue
        if not any(Path(path).stem in t["content"] or Path(path).stem in t["relative_path"] for t in tests):
            gaps.append(
                {
                    "path": path,
                    "status": "no_matching_test_found",
                    "suggestion": f"Exercise changed behavior in {path}, including empty input, error propagation and an ordinary successful call. This is a retrieval gap, not proof of missing coverage.",
                }
            )
    return gaps


def javascript_contracts(base_index, head_index, changed, run_id):
    from schemas.contracts import RelatedLocation

    results = []
    for caller, row in head_index.items():
        for binding in row.get("bindings", []):
            if not binding["module"].startswith("."):
                continue
            module = str((Path(caller).parent / binding["module"]))
            import posixpath

            module = posixpath.normpath(module)
            candidates = [module + suffix for suffix in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js")]
            path = next((p for p in candidates if p in changed and p in base_index and p in head_index), None)
            if not path:
                continue
            before = next(
                (n for n in base_index[path]["symbols"] if n["name"] == binding["name"] and n["exported"]), None
            )
            after = next(
                (n for n in head_index[path]["symbols"] if n["name"] == binding["name"] and n["exported"]), None
            )
            if not before or not after or before["parameters"] == after["parameters"]:
                continue
            required = sum(p["required"] for p in after["parameters"])
            for call in row.get("calls", []):
                if call["name"] == binding["local"] and not call["spread"] and call["arguments"] < required:
                    results.append(
                        finding(
                            run_id,
                            caller,
                            call["line"],
                            "js:changed-signature",
                            f"Call to {binding['name']} supplies {call['arguments']} arguments after {path} changes to require {required}.",
                            related=[
                                RelatedLocation(
                                    path=path,
                                    lines=[after["line"]],
                                    qualified_symbol=binding["name"],
                                    relationship="callee",
                                )
                            ],
                        )
                    )
    return results
