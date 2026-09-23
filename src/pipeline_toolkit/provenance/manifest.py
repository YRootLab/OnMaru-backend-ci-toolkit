from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path
from pipeline_toolkit.contracts import Artifact

@dataclass(frozen=True)
class ArtifactManifest:
    artifacts: tuple[Artifact, ...]

    @classmethod
    def from_files(cls, files: dict[str, str | Path]) -> "ArtifactManifest":
        items = []
        seen: set[str] = set()
        for kind, raw_path in sorted(files.items()):
            path = Path(raw_path)
            if not path.is_file(): raise FileNotFoundError(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen: raise ValueError(f"duplicate artifact checksum: {digest}")
            seen.add(digest)
            items.append(Artifact(str(path), digest, kind, path.stat().st_size))
        return cls(tuple(items))

    def as_dict(self) -> dict:
        return {"artifacts": [a.__dict__ for a in self.artifacts]}
