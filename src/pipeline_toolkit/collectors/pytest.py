from __future__ import annotations
import re
from pathlib import Path
from pipeline_toolkit.contracts import Evidence, Quality

def collect_pytest(path: str | Path, benchmark_id: str = "pytest") -> list[Evidence]:
    try: text = Path(path).read_text()
    except FileNotFoundError: return [Evidence(benchmark_id, None, "seconds", Quality.MISSING, "pytest", warnings=("artifact missing",))]
    match = re.search(r"(?P<passed>\d+) passed", text)
    failed = re.search(r"(?P<n>\d+) failed", text)
    duration = re.search(r"in (?P<seconds>[\d.]+)s", text)
    if not match and not failed: return [Evidence(benchmark_id, None, "seconds", Quality.INVALID, "pytest", warnings=("unrecognized output",))]
    quality = Quality.FAILED if failed else Quality.SUCCESS
    return [Evidence(benchmark_id, float(duration.group("seconds")) if duration else None, "seconds", quality, "pytest", warnings=(f"passed={match.group('passed') if match else 0}", f"failed={failed.group('n') if failed else 0}"))]
