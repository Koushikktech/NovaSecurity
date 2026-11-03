from providers.fake import FakeLLMProvider
from review.harness import InvestigationStep, RepositoryMap, ReviewHarness, RunConfig, ToolCall
from schemas.provider import StructuredGenerationRequest


def test_tools_pin_snapshot_and_cannot_read_host():
    repo = RepositoryMap([{"relative_path": "app.py", "content": "def total(items):\n    return sum(items)\n"}])
    assert repo.execute(ToolCall(name="read_file", path="../../.env"))["error"]
    assert repo.execute(ToolCall(name="get_symbol", query="total"))["symbols"][0]["start"] == 1
    assert repo.execute(ToolCall(name="find_references", query="total"))["matches"][0]["relationship"] == "lexical_hint"


def test_checkpoint_and_budget(tmp_path):
    provider = FakeLLMProvider()
    provider.register_response("test", {"ready": True, "tools": []})
    repo = RepositoryMap([])
    harness = ReviewHarness(provider, RunConfig(max_model_calls=1), repo, "run", tmp_path)
    req = StructuredGenerationRequest(
        run_id="run", stage="test", model_role="review", context="code", system_instruction="review"
    )
    assert harness.generate_structured(req, InvestigationStep).success
    # Checkpoint reuse on a fresh harness avoids another provider call.
    second = ReviewHarness(provider, RunConfig(max_model_calls=1), repo, "run2", tmp_path)
    assert second.generate_structured(req, InvestigationStep).success
    assert second.calls == 0
    assert not harness.generate_structured(req.model_copy(update={"context": "different"}), InvestigationStep).success


def test_investigation_observations_and_limit(tmp_path):
    class Investigator:
        default_model = "test"

        def generate_structured(self, request, schema):
            from schemas.provider import ProviderResponse

            return ProviderResponse(
                success=True, model_id="test", data=InvestigationStep(tools=[ToolCall(name="read_file", path="app.py")])
            )

    repo = RepositoryMap([{"relative_path": "app.py", "content": "value = 3"}])
    harness = ReviewHarness(Investigator(), RunConfig(max_tool_calls=1), repo, "test", tmp_path)
    context = harness.investigate("Inspect value")
    assert "value = 3" in context
    assert harness.tools == 1
    assert any(e["event_type"] == "budget_exhausted" for e in harness.trace)


def test_repository_tools_use_resolved_python_call_graph():
    from analysis.graph_context import CodebaseGraph

    files = [
        {"relative_path": "service.py", "content": "def load(value):\n    return value\n"},
        {"relative_path": "caller.py", "content": "from service import load\ndef handler():\n    return load(1)\n"},
    ]
    graph = CodebaseGraph()
    graph.build_from_files(files)
    repo = RepositoryMap(files, python_graph=graph)
    result = repo.execute(ToolCall(name="find_references", query="load", path="service.py"))
    assert result["references"][0]["relationship"] == "resolved_python_call"
    assert result["references"][0]["path"] == "caller.py"


def test_symbol_change_map_includes_added_and_deleted_python_functions():
    base = [{"relative_path": "app.py", "content": "def old():\n    return 1\n"}]
    head = [{"relative_path": "app.py", "content": "def new():\n    return 2\n"}]
    repo = RepositoryMap(head, base_files=base)
    assert any(s["name"] == "new" for s in repo.changed_symbols)
    assert any(s["name"] == "old" for s in repo.deleted_symbols)


def test_change_impact_connects_changed_symbol_callers_and_test_hints():
    from analysis.graph_context import CodebaseGraph

    base = [{"relative_path": "service.py", "content": "def load(value):\n    return value\n"}]
    head = [
        {"relative_path": "service.py", "content": "def load(value, size):\n    return value\n"},
        {"relative_path": "caller.py", "content": "from service import load\ndef handler():\n    return load(1)\n"},
        {
            "relative_path": "test_service.py",
            "content": "from service import load\ndef test_load():\n    assert load(1, 2)==1\n",
        },
    ]
    graph = CodebaseGraph()
    graph.build_from_files(head)
    repo = RepositoryMap(head, base_files=base, python_graph=graph)
    impact = next(item for item in repo.impact()["changes"] if item["symbol"]["name"] == "load")
    assert any(c["path"] == "caller.py" for c in impact["callers"])
    assert "test_service.py" in impact["test_hints"]


def test_model_request_events_preserve_matching_cache_identity(tmp_path):
    provider = FakeLLMProvider()
    provider.register_response("test", {"ready": True, "tools": []})
    harness = ReviewHarness(provider, RunConfig(), RepositoryMap([]), "run", tmp_path)
    req = StructuredGenerationRequest(
        run_id="run", stage="test", model_role="review", context="code", system_instruction="review"
    )
    assert harness.generate_structured(req, InvestigationStep).success
    events = {event["event_type"]: event for event in harness.trace}
    identifier = events["model_request_started"]["request_id"]
    assert len(identifier) == 64
    assert events["model_request_completed"]["request_id"] == identifier
    assert events["checkpoint_saved"]["key"] == identifier


def test_exact_tool_queries_reject_questions_and_offer_snapshot_symbols():
    repo = RepositoryMap([{"relative_path": "app.py", "content": "def total(items):\n    return sum(items)\n"}])
    invalid = repo.execute(ToolCall(name="find_references", query="Where is total called?"))
    assert invalid["error"] and invalid["suggestions"] == ["app.py:1:total"]
    assert repo.execute(ToolCall(name="get_symbol", query="app.py::total"))["symbols"][0]["name"] == "total"
    assert repo.execute(ToolCall(name="search_code", query="sum(items)"))["matches"][0]["line"] == 2
