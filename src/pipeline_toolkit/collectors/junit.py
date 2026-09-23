from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from pipeline_toolkit.contracts import Evidence, Quality

def collect_junit(path: str | Path, benchmark_id: str = "tests") -> list[Evidence]:
    source = str(path)
    try: root = ET.parse(path).getroot()
    except FileNotFoundError: return [Evidence(benchmark_id, None, "seconds", Quality.MISSING, "junit", warnings=("artifact missing",))]
    except ET.ParseError as exc: return [Evidence(benchmark_id, None, "seconds", Quality.INVALID, "junit", warnings=(str(exc),))]
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites: return [Evidence(benchmark_id, None, "seconds", Quality.INVALID, "junit", warnings=("no testsuite",))]
    total = sum(float(s.attrib.get("time", 0)) for s in suites)
    failed = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
    skipped = sum(int(s.attrib.get("skipped", 0)) for s in suites)
    quality = Quality.FAILED if failed else Quality.SUCCESS
    return [Evidence(benchmark_id, total, "seconds", quality, "junit", warnings=(f"failed={failed}", f"skipped={skipped}"))]
