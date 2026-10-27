from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict
import networkx as nx
from langgraph.graph import StateGraph, END
from indexer import CodebaseIndex, CodeFetcher

from pathlib import Path
import nova as _nova

nova_call = getattr(_nova, "nova_call")
nova_call_reasoning = getattr(_nova, "nova_call_reasoning")
NOVA_LITE_4B = getattr(_nova, "NOVA_LITE_4B", "nova-2-lite-v1")

NOVA_LITE = "nova-2-lite-v1"

# Max concurrent LLM workers for parallel calls
_MAX_LLM_WORKERS = 4


class AgentState(TypedDict):
    repo_url: str

    files: list
    python_files: list
    repo_path: str

    codebase_index: CodebaseIndex | None
    codebase_summary: str
    code_fetcher: CodeFetcher | None

    graph: nx.DiGraph | None
    vulnerable_paths: list[dict]

    findings: list[dict]
    findings_full: list[dict]
    all_findings: list[dict]

    after_validation: list[dict]


def load_prompt(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(__file__).parent / path
    with open(candidate, "r", encoding="utf-8") as f:
        return f.read()


def ingest_node(state: AgentState) -> dict:
    from ingestor import CodeIngestor

    ingestor = CodeIngestor()

    repo_url = state.get("repo_url", "")
    if not repo_url:
        raise ValueError("No repository URL provided. Please provide a GitHub repository URL to scan.")

    repo_path = ingestor.from_git(repo_url)
    all_files = ingestor.get_files(repo_path)

    python_files = [f for f in all_files if f["relative_path"].endswith(".py")]

    print(f"  Ingested {len(all_files)} total files ({len(python_files)} Python)")

    return {
        "files": all_files,
        "python_files": python_files,
        "repo_path": repo_path,
    }


def build_index_node(state: AgentState) -> dict:
    from indexer import build_codebase_index, format_index_for_llm, print_index_summary

    repo_name = state.get("repo_url", "").rstrip("/").split("/")[-1]
    index, fetcher = build_codebase_index(state["files"], repo_name=repo_name)

    summary = format_index_for_llm(index)

    print("\n" + "=" * 60)
    print("  CODEBASE INDEX BUILT")
    print("=" * 60)
    print_index_summary(index)

    return {
        "codebase_index": index,
        "codebase_summary": summary,
        "code_fetcher": fetcher,
    }


def build_graph_node(state: AgentState) -> dict:
    from graph import GraphBuilder

    graph_builder = GraphBuilder()
    G = graph_builder.build_from_files(state["python_files"])

    vulnerable_paths = graph_builder.find_vulnerable_paths()

    print(f"\n  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"  Vulnerable paths found: {len(vulnerable_paths)}")
    unsanitized = [p for p in vulnerable_paths if not p["sanitized"]]
    print(f"  Unsanitized paths: {len(unsanitized)}")

    return {"vulnerable_paths": vulnerable_paths, "graph": G}


_HIGH_RISK_SINKS = {
    "execute",
    "raw",
    "executemany",
    "system",
    "popen",
    "Popen",
    "check_output",
    "eval",
    "exec",
    "open",
    "send_file",
    "send_from_directory",
    "render_template_string",
    "mark_safe",
}


def targeted_scan_node(state: AgentState) -> dict:
    from graph import extract_code_for_path

    findings = []

    if not state["graph"]:
        return {"findings": findings}

    seen_sigs: set[tuple] = set()
    unique_paths = []
    for path_info in state["vulnerable_paths"]:
        if path_info["sanitized"]:
            continue
        sig = tuple(path_info["path"])
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        unique_paths.append(path_info)

    dupes = sum(1 for p in state["vulnerable_paths"] if not p["sanitized"]) - len(
        unique_paths
    )
    if dupes:
        print(f"  Deduped {dupes} exact-duplicate path(s)")

    by_sink_file: dict[str, list] = defaultdict(list)
    for path_info in unique_paths:
        by_sink_file[path_info["sink_file"]].append(path_info)

    single_template = load_prompt("prompts/targeted_scan.txt")
    batch_template = load_prompt("prompts/targeted_scan_batch.txt")
    total = len(unique_paths)
    scanned = 0

    # Collect all scan tasks for parallel execution
    scan_tasks = []

    for sink_file, paths in by_sink_file.items():
        for batch_start in range(0, len(paths), 5):  # Batch size 5 (up from 3)
            batch = paths[batch_start : batch_start + 5]
            is_high_risk = any(p["sink_type"] in _HIGH_RISK_SINKS for p in batch)
            # High-risk → Lite with reasoning:high; normal → Lite with reasoning:low
            reasoning = "high" if is_high_risk else "low"

            if len(batch) == 1:
                path_info = batch[0]
                relevant_code = extract_code_for_path(
                    path_info["path"], state["graph"], state["python_files"]
                )
                prompt = single_template.format(
                    source_type=path_info["source_type"],
                    source_file=path_info["source_file"],
                    source_line=path_info["source_line"],
                    sink_type=path_info["sink_type"],
                    sink_file=path_info["sink_file"],
                    sink_line=path_info["sink_line"],
                    data_flow_path=" → ".join(path_info["path"]),
                    sanitized=path_info["sanitized"],
                    relevant_code=relevant_code,
                )
                scan_tasks.append(("single", prompt, batch, reasoning, sink_file))
            else:
                parts = []
                for idx, p in enumerate(batch, 1):
                    code = extract_code_for_path(
                        p["path"], state["graph"], state["python_files"]
                    )
                    parts.append(
                        f"PATH {idx}: {p['source_type']} → {p['sink_type']}\n"
                        f"- Source: {p['source_file']} line {p['source_line']}\n"
                        f"- Sink:   {p['sink_file']} line {p['sink_line']}\n"
                        f"- Data flow: {' → '.join(p['path'])}\n"
                        f"- Sanitized: {p['sanitized']}\n"
                        f"- Code:\n{code}"
                    )
                prompt = batch_template.format(
                    num_paths=len(batch),
                    paths_detail="\n\n---\n\n".join(parts),
                )
                scan_tasks.append(("batch", prompt, batch, reasoning, sink_file))

    # Execute all scan tasks in parallel
    def run_scan_task(task):
        kind, prompt, batch, reasoning, sink_file = task
        response = nova_call_reasoning(
            prompt, nova_model=NOVA_LITE, reasoning_effort=reasoning
        )
        return kind, response, batch, sink_file

    print(f"  Running {len(scan_tasks)} scan tasks in parallel (max {_MAX_LLM_WORKERS} workers) [Lite only]")

    with ThreadPoolExecutor(max_workers=_MAX_LLM_WORKERS) as executor:
        futures = [executor.submit(run_scan_task, t) for t in scan_tasks]
        for future in as_completed(futures):
            kind, response, batch, sink_file = future.result()
            scanned += len(batch)

            if kind == "single":
                path_info = batch[0]
                print(
                    f"  [{scanned}/{total}] {path_info['source_type']} → {path_info['sink_type']}"
                )
                if response and response.get("is_vulnerable"):
                    findings.append(
                        {
                            **response,
                            "source": "targeted_scan",
                            "file": path_info["sink_file"],
                            "line": path_info["sink_line"],
                            "path": path_info["path"],
                        }
                    )
            else:
                print(f"  [{scanned}/{total}] batch of {len(batch)} → {sink_file}")
                if response and response.get("findings"):
                    for item in response["findings"]:
                        raw_idx = item.get("path_index", 1) - 1
                        path_info = (
                            batch[raw_idx] if 0 <= raw_idx < len(batch) else batch[0]
                        )
                        if item.get("is_vulnerable"):
                            findings.append(
                                {
                                    **item,
                                    "source": "targeted_scan",
                                    "file": path_info["sink_file"],
                                    "line": path_info["sink_line"],
                                    "path": path_info["path"],
                                }
                            )

    print(f"  Targeted scan found {len(findings)} vulnerabilities")
    return {"findings": findings}


def indexed_sweep_node(state: AgentState) -> dict:
    from indexer import format_file_detail_for_llm, Priority

    findings_full = []
    index = state["codebase_index"]
    fetcher = state["code_fetcher"]
    summary = state["codebase_summary"]

    if not index or not fetcher:
        return {"findings_full": findings_full}

    scan_files = index.get_scan_order()
    to_scan = [
        f for f in scan_files if f.priority in (Priority.CRITICAL, Priority.HIGH)
    ]

    if len(to_scan) < 5:
        to_scan.extend(f for f in scan_files if f.priority == Priority.MEDIUM)

    print(
        f"\n  Sweep scanning {len(to_scan)} files (CRITICAL/HIGH priority) [Nova Lite 4B + reasoning:medium]"
    )

    template = load_prompt("prompts/indexed_scan.txt")

    path_evidence_by_file = {}
    for path_info in state.get("vulnerable_paths", []):
        for key in ("source_file", "sink_file"):
            fpath = path_info.get(key, "")
            if fpath not in path_evidence_by_file:
                path_evidence_by_file[fpath] = []
            path_evidence_by_file[fpath].append(
                f"  {path_info['source_type']} (L{path_info['source_line']}) "
                f"→ {path_info['sink_type']} (L{path_info['sink_line']}) "
                f"[{'sanitized' if path_info['sanitized'] else 'UNSANITIZED'}]"
            )

    for file_idx in to_scan:
        file_detail = format_file_detail_for_llm(file_idx, fetcher)

        graph_evidence = path_evidence_by_file.get(file_idx.path, [])
        graph_str = (
            "\n".join(graph_evidence)
            if graph_evidence
            else "No graph paths through this file."
        )

        prompt = template.format(
            codebase_index=summary,
            file_detail=file_detail,
            graph_evidence=graph_str,
            file_path=file_idx.path,
        )

        print(
            f"  Sweeping: {file_idx.path} ({file_idx.priority}) [4B reasoning:medium]"
        )

        response = nova_call_reasoning(
            prompt,
            nova_model=NOVA_LITE_4B,
            reasoning_effort="medium",
        )

        if response and response.get("findings"):
            for finding in response["findings"]:
                if finding.get("is_vulnerable"):
                    finding["source"] = "indexed_sweep"
                    finding["file"] = finding.get("file", file_idx.path)
                    findings_full.append(finding)

    print(f"  Sweep scan found {len(findings_full)} vulnerabilities")
    return {"findings_full": findings_full}


def merge_findings_node(state: AgentState) -> dict:
    targeted = state.get("findings", [])
    sweep = state.get("findings_full", [])

    seen = {}

    for f in targeted:
        key = (f.get("file", ""), f.get("line", 0), f.get("vulnerability_type", ""))
        f["sources"] = ["targeted_scan"]
        seen[key] = f

    for f in sweep:
        key = (f.get("file", ""), f.get("line", 0), f.get("vulnerability_type", ""))
        if key in seen:
            existing = seen[key]
            existing["sources"].append("indexed_sweep")
            old_conf = existing.get("confidence", 0.5)
            new_conf = f.get("confidence", 0.5)
            existing["confidence"] = min(1.0, (old_conf + new_conf) / 2 + 0.15)
            existing["corroborated"] = True
        else:
            f["sources"] = ["indexed_sweep"]
            f["corroborated"] = False
            seen[key] = f

    all_findings = sorted(
        seen.values(),
        key=lambda x: (
            {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(
                x.get("severity", "Low"), 4
            ),
            -x.get("confidence", 0),
        ),
    )

    print(f"\n  Merged: {len(all_findings)} unique findings")
    print(f"    From targeted scan: {len(targeted)}")
    print(f"    From sweep scan: {len(sweep)}")
    corroborated = sum(1 for f in all_findings if f.get("corroborated"))
    if corroborated:
        print(f"    Corroborated by both: {corroborated} (confidence boosted)")

    return {"all_findings": all_findings}


def red_team_node(state: AgentState) -> dict:
    from graph import extract_code_for_path, extract_code_for_finding

    findings = state.get("all_findings", [])
    template = load_prompt("prompts/red_team.txt")

    critical_high = [f for f in findings if f.get("severity") in ("Critical", "High")]
    skip = [f for f in findings if f.get("severity") not in ("Critical", "High")]
    for f in skip:
        f["red_team_poc"] = None
        f["red_team_success"] = False

    print(f"\n  Red Team: testing {len(critical_high)} Critical/High findings in parallel")

    def attack_finding(finding):
        graph = state["graph"]
        if finding.get("path") and graph:
            relevant_code = extract_code_for_path(
                finding["path"], graph, state["python_files"]
            )
        else:
            relevant_code = extract_code_for_finding(finding, state["python_files"])

        prompt = template.format(
            vulnerability_type=finding.get("vulnerability_type", "Unknown"),
            severity=finding.get("severity", "Unknown"),
            file=finding.get("file", ""),
            line=finding.get("line", 0),
            description=finding.get("description", ""),
            relevant_code=relevant_code,
        )

        print(f"    Attacking: {finding.get('vulnerability_type')} @ {finding.get('file')}:{finding.get('line')}")
        response = nova_call_reasoning(prompt, nova_model=NOVA_LITE, reasoning_effort="medium")

        if response:
            finding["red_team_poc"] = response.get("poc", "")
            finding["red_team_success"] = bool(response.get("exploit_feasible", False))
            finding["red_team_attack_vector"] = response.get("attack_vector", "")
        else:
            finding["red_team_poc"] = None
            finding["red_team_success"] = False
        return finding

    with ThreadPoolExecutor(max_workers=_MAX_LLM_WORKERS) as executor:
        list(executor.map(attack_finding, critical_high))

    confirmed = sum(1 for f in findings if f.get("red_team_success"))
    print(f"  Red Team done: {confirmed} exploitable findings")

    return {"all_findings": findings}


def blue_team_node(state: AgentState) -> dict:
    from graph import extract_code_for_path, extract_code_for_finding

    findings = state.get("all_findings", [])
    template = load_prompt("prompts/blue_team.txt")

    # Separate findings that need blue team analysis vs skip
    to_defend = []
    for finding in findings:
        if finding.get("severity") not in ("Critical", "High"):
            finding["blue_team_disputed"] = False
            finding["blue_team_defense"] = None
        elif not finding.get("red_team_success"):
            finding["blue_team_disputed"] = False
            finding["blue_team_defense"] = "Skipped: red team could not construct a working exploit."
        else:
            to_defend.append(finding)

    print(f"\n  Blue Team: challenging {len(to_defend)} red-team-confirmed findings in parallel")

    def defend_finding(finding):
        graph = state["graph"]
        if finding.get("path") and graph:
            relevant_code = extract_code_for_path(
                finding["path"], graph, state["python_files"]
            )
        else:
            relevant_code = extract_code_for_finding(finding, state["python_files"])

        poc = finding.get("red_team_poc") or "No proof-of-concept was constructed."

        prompt = template.format(
            vulnerability_type=finding.get("vulnerability_type", "Unknown"),
            severity=finding.get("severity", "Unknown"),
            file=finding.get("file", ""),
            line=finding.get("line", 0),
            description=finding.get("description", ""),
            poc=poc,
            relevant_code=relevant_code,
        )

        print(f"    Defending: {finding.get('vulnerability_type')} @ {finding.get('file')}:{finding.get('line')}")
        response = nova_call_reasoning(prompt, nova_model=NOVA_LITE, reasoning_effort="low")

        if response:
            finding["blue_team_disputed"] = bool(response.get("disputed", False))
            finding["blue_team_defense"] = response.get("defense_evidence", "")
        else:
            finding["blue_team_disputed"] = False
            finding["blue_team_defense"] = None
        return finding

    with ThreadPoolExecutor(max_workers=_MAX_LLM_WORKERS) as executor:
        list(executor.map(defend_finding, to_defend))

    for finding in findings:
        llm_conf = float(finding.get("confidence", 0.5))
        graph_confirmed = 1.0 if "targeted_scan" in finding.get("sources", []) else 0.0
        red_success = 1.0 if finding.get("red_team_success") else 0.0
        blue_disputed = 1.0 if finding.get("blue_team_disputed") else 0.0

        final_confidence = (
            0.30 * llm_conf
            + 0.25 * graph_confirmed
            + 0.25 * red_success
            + 0.20 * (1.0 - blue_disputed)
        )
        finding["final_confidence"] = round(final_confidence, 3)

        if final_confidence >= 0.6:
            finding["validation_status"] = "Confirmed"
        elif final_confidence >= 0.3:
            finding["validation_status"] = "Needs Review"
        else:
            finding["validation_status"] = "Likely False Positive"

    disputed = sum(1 for f in findings if f.get("blue_team_disputed"))
    confirmed = sum(1 for f in findings if f.get("validation_status") == "Confirmed")
    print(f"  Blue Team done: {disputed} disputed, {confirmed} confirmed")
    after_validation = [
        f for f in findings if f.get("validation_status") != "Likely False Positive"
    ]
    return {"all_findings": findings, "after_validation": after_validation}


workflow = StateGraph(AgentState)

workflow.add_node("ingest", ingest_node)
workflow.add_node("build_index", build_index_node)
workflow.add_node("build_graph", build_graph_node)
workflow.add_node("targeted_scan", targeted_scan_node)
workflow.add_node("indexed_sweep", indexed_sweep_node)
workflow.add_node("merge_findings", merge_findings_node)
workflow.add_node("red_team", red_team_node)
workflow.add_node("blue_team", blue_team_node)

workflow.set_entry_point("ingest")

workflow.add_edge("ingest", "build_index")
workflow.add_edge("build_index", "build_graph")
workflow.add_edge("build_graph", "targeted_scan")
workflow.add_edge("targeted_scan", "indexed_sweep")
workflow.add_edge("indexed_sweep", "merge_findings")
workflow.add_edge("merge_findings", "red_team")
workflow.add_edge("red_team", "blue_team")
workflow.add_edge("blue_team", END)

app = workflow.compile()

if __name__ == "__main__":
    initial_state: AgentState = {
        "repo_url": "",
        "files": [],
        "python_files": [],
        "repo_path": "",
        "codebase_index": None,
        "codebase_summary": "",
        "code_fetcher": None,
        "graph": None,
        "vulnerable_paths": [],
        "findings": [],
        "findings_full": [],
        "all_findings": [],
        "after_validation": [],
    }

    print("=" * 60)
    print("  NOVAGUARD — AI-Powered Security Scanner")
    print("=" * 60)

    result = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("  SCAN COMPLETE")
    print("=" * 60)
