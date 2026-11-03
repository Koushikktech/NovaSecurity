"""Content and implementation addressed parser artifacts; source is never executed."""

import hashlib
import json

from config import settings
from storage import atomic_json


class AnalysisCache:
    def __init__(self, namespace, implementation, payload):
        digest = hashlib.sha256(implementation + json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.path = settings.artifact_dir / "analysis-cache" / namespace / (digest + ".json")

    def read(self):
        try:
            if self.path.stat().st_size > 10 * 1024 * 1024:
                return None
            data = json.loads(self.path.read_text())
            encoded = json.dumps(data["payload"], sort_keys=True)
            if hashlib.sha256(encoded.encode()).hexdigest() == data["digest"]:
                return data["payload"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, sort_keys=True)
        atomic_json(self.path, {"payload": payload, "digest": hashlib.sha256(encoded.encode()).hexdigest()})
