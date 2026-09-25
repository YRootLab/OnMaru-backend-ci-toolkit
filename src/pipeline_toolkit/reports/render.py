from __future__ import annotations
import html, json
import base64, struct, zlib
from typing import Any

def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"

def render_markdown(report: dict[str, Any]) -> str:
    status = report.get("status", "unknown")
    lines = ["# Benchmark report", "", f"- Status: `{status}`"]
    for key in ("wall_clock_seconds", "work_seconds", "critical_path_seconds", "sample_count"):
        if key in report: lines.append(f"- {key}: `{report[key]}`")
    for key in sorted(k for k in report if k not in {"status", "wall_clock_seconds", "work_seconds", "critical_path_seconds", "sample_count"}):
        lines.append(f"- {key}: `{report[key]}`")
    return "\n".join(lines) + "\n"

def render_html(report: dict[str, Any]) -> str:
    body = html.escape(render_markdown(report)).replace("\n", "<br>\n")
    return "<!doctype html><meta charset='utf-8'><title>Benchmark report</title><main>" + body + "</main>\n"

def render_job_summary(report: dict[str, Any]) -> str:
    return render_markdown(report)

def render_png(report: dict[str, Any]) -> str:
    width, height = 240, 80
    pixels = bytearray(width * height * 3)
    for index in range(0, len(pixels), 3): pixels[index:index + 3] = b"\xff\xff\xff"
    metrics = report.get("metrics", {})
    values = [float(value) for value in metrics.values() if isinstance(value, (int, float))]
    maximum = max(values, default=1.0)
    for row, value in enumerate(values[:6]):
        bar_width = min(width - 20, max(1, int((value / maximum) * (width - 20))))
        for y in range(8 + row * 11, min(height, 16 + row * 11)):
            for x in range(10, 10 + bar_width):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = b"\x2f\x6f\xb3"
    raw = b"".join(b"\x00" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")
