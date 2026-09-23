from __future__ import annotations
import re
import xml.etree.ElementTree as ET
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

def collect_pytest_xml(path: str | Path, benchmark_id: str = "pytest") -> Evidence:
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError:
        return Evidence(benchmark_id, None, "seconds", Quality.MISSING, "pytest.xml", warnings=("artifact missing",))
    except ET.ParseError as exc:
        return Evidence(benchmark_id, None, "seconds", Quality.INVALID, "pytest.xml", warnings=(str(exc),))
    cases = list(root.findall(".//testcase"))
    failed = int(root.attrib.get("failures", 0)) + int(root.attrib.get("errors", 0))
    skipped = int(root.attrib.get("skipped", 0))
    duration = float(root.attrib.get("time", 0))
    slowest = sorted(((float(c.attrib.get("time", 0)), c.attrib.get("name", "unknown")) for c in cases), reverse=True)[:5]
    warnings = (f"tests={len(cases)}", f"failures={failed}", f"skipped={skipped}", *tuple(f"slowest={name}:{seconds}" for seconds, name in slowest))
    return Evidence(benchmark_id, duration, "seconds", Quality.FAILED if failed else Quality.SUCCESS, "pytest.xml", warnings=warnings)
