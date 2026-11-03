import json

import pytest

from review.snapshots import load_snapshot, materialize, save_snapshot


def test_snapshot_integrity_and_restore(tmp_path):
    files = [{"relative_path": "app.py", "content": "value = 42", "lines": 1}]
    digest = save_snapshot(tmp_path, {"mode": "project"}, files, [], "")
    payload, actual = load_snapshot(tmp_path)
    assert actual == digest
    destination = tmp_path / "restored"
    destination.mkdir()
    materialize(payload["head"], destination)
    assert (destination / "app.py").read_text() == "value = 42"
    path = tmp_path / "snapshot.json"
    data = json.loads(path.read_text())
    data["payload"]["head"][0]["content"] = "tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity"):
        load_snapshot(tmp_path)


def test_restore_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        materialize([{"relative_path": "../escape", "content": "bad"}], tmp_path)


@pytest.mark.parametrize("document", [[], None, {"version": 1}])
def test_malformed_checkpoint_has_controlled_integrity_error(tmp_path, document):
    (tmp_path / "snapshot.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="integrity"):
        load_snapshot(tmp_path)
