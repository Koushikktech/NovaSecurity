from analysis.stage_cache import cached_static_analysis
from config import settings


def test_static_stage_replay_preserves_provenance_and_reissues_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    source = tmp_path / "source"
    source.mkdir()
    code = "def collect(item, items=[]):\n    items.append(item)\n    return items\n"
    (source / "app.py").write_text(code)
    files = [{"relative_path": "app.py", "content": code}]
    initial, coverage = cached_static_analysis(str(source), files, "first")
    assert initial

    def unexpected(*args, **kwargs):
        raise AssertionError("Analyzer should not rerun for matching source and tools")

    monkeypatch.setattr("analysis.stage_cache.run_all_static_analyzers", unexpected)
    replay, report = cached_static_analysis(str(source), files, "second")
    assert replay[0].run_id == "second" and replay[0].id != initial[0].id
    assert replay[0].evidence_items[0].kind == "cached_static_analysis"
    assert report["ruff"]["original_run_id"] == "first"
    assert report["ruff"]["cache_reused"]
