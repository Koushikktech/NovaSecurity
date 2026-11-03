import json
import stat
from concurrent.futures import ThreadPoolExecutor

from storage import atomic_json


def test_parallel_checkpoint_writes_remain_atomic_and_owner_only(tmp_path):
    target = tmp_path / "checkpoint.json"
    payloads = [{"writer": i, "content": "x" * 10000} for i in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda payload: atomic_json(target, payload), payloads))
    assert json.loads(target.read_text()) in payloads
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))
