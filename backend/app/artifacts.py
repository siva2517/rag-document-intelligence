"""Per-document artifact store: every pipeline stage writes its output here so runs can be restored.

Layout:  {root}/{doc_id}/manifest.json, original.pdf, insights.json, requirements.json, ...
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _dir(self, doc_id: str) -> Path:
        path = self.root / doc_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, doc_id: str, name: str) -> Path:
        return self.root / doc_id / name

    def save_bytes(self, doc_id: str, name: str, data: bytes) -> None:
        (self._dir(doc_id) / name).write_bytes(data)
        self._record(doc_id, name)

    def save_json(self, doc_id: str, name: str, data: Any) -> None:
        (self._dir(doc_id) / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._record(doc_id, name)

    def load_json(self, doc_id: str, name: str) -> Any | None:
        path = self.path(doc_id, name)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def manifest(self, doc_id: str) -> dict:
        return self.load_json(doc_id, "manifest.json") or {}

    def _record(self, doc_id: str, name: str) -> None:
        manifest = self.manifest(doc_id)
        manifest[name] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (self._dir(doc_id) / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def delete(self, doc_id: str) -> None:
        shutil.rmtree(self.root / doc_id, ignore_errors=True)
