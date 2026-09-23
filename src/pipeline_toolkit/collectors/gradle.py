from __future__ import annotations
import csv
import hashlib
from pathlib import Path
from pipeline_toolkit.contracts import Artifact, Evidence, Quality

def collect_gradle_profiler(path: str | Path, benchmark_id: str = "gradle.profiler") -> list[Evidence]:
    source = Path(path)
    if not source.is_file(): return [Evidence(benchmark_id, None, "milliseconds", Quality.MISSING, "gradle-profiler", warnings=("artifact missing",))]
    raw = source.read_bytes()
    artifact = Artifact(str(source), hashlib.sha256(raw).hexdigest(), "gradle-profiler")
    try:
        rows = list(csv.DictReader(raw.decode().splitlines()))
        required = {"elapsed time (ms)", "cpu time (ms)", "max memory (MB)"}
        if not rows or not required.issubset(rows[0]): raise ValueError("missing Gradle Profiler columns")
        row = rows[0]
        elapsed = float(row["elapsed time (ms)"])
        warnings = (f"scenario={row.get('scenario', 'unknown')}", f"cpu_ms={row['cpu time (ms)']}", f"peak_memory_mb={row['max memory (MB)']}")
    except (UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
        return [Evidence(benchmark_id, None, "milliseconds", Quality.INVALID, "gradle-profiler", raw_artifact=artifact, warnings=(str(exc),))]
    return [Evidence(benchmark_id, elapsed, "milliseconds", Quality.SUCCESS, "gradle-profiler", raw_artifact=artifact, warnings=warnings)]
