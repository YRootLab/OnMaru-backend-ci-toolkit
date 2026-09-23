from __future__ import annotations
import re
from pathlib import Path
from pipeline_toolkit.contracts import Evidence, Quality

def collect_time(path: str | Path) -> list[Evidence]:
    try: text = Path(path).read_text()
    except FileNotFoundError: return [Evidence("system", None, "seconds", Quality.MISSING, "/usr/bin/time", warnings=("artifact missing",))]
    elapsed = re.search(r"Elapsed \(wall clock\) time .*: ([\d:.]+)", text)
    user = re.search(r"User time \(seconds\): ([\d.]+)", text)
    system = re.search(r"System time \(seconds\): ([\d.]+)", text)
    memory = re.search(r"Maximum resident set size .*: (\d+)", text)
    if not elapsed and not memory: return [Evidence("system", None, "unknown", Quality.INVALID, "/usr/bin/time")]
    warnings = tuple(item for item in (f"cpu_user_seconds={user.group(1)}" if user else None, f"cpu_system_seconds={system.group(1)}" if system else None, f"peak_memory_kb={memory.group(1)}" if memory else None) if item)
    return [Evidence("system.wall", _duration(elapsed.group(1)) if elapsed else None, "seconds", Quality.SUCCESS, "/usr/bin/time", warnings=warnings)]

def _duration(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 2: return float(parts[0]) * 60 + float(parts[1])
    return float(value)
