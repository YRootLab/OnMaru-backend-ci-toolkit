from __future__ import annotations
import json
from pathlib import Path
from pipeline_toolkit.contracts import Evidence, Quality

def collect_buildkit(path: str | Path) -> list[Evidence]:
    try: data = json.loads(Path(path).read_text())
    except FileNotFoundError: return [Evidence("docker.build", None, "seconds", Quality.MISSING, "buildkit")]
    except (json.JSONDecodeError, OSError) as exc: return [Evidence("docker.build", None, "seconds", Quality.INVALID, "buildkit", warnings=(str(exc),))]
    duration = data.get("duration_seconds")
    quality = Quality.SUCCESS if isinstance(duration, (int, float)) else Quality.PARTIAL
    warnings = tuple(f"{key}={data[key]}" for key in ("cache_hit", "image_digest") if key in data)
    return [Evidence("docker.build", duration, "seconds", quality, "buildkit", warnings=warnings)]
