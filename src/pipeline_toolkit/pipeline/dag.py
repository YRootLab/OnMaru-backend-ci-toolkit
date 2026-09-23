from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Job:
    id: str
    needs: tuple[str, ...] = ()
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "success"
    queued_at: datetime | None = None

@dataclass(frozen=True)
class DagMetrics:
    work_seconds: float
    wall_clock_seconds: float
    critical_path_seconds: float
    critical_path: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    queue_seconds: float = 0
    idle_seconds: float = 0

def critical_path(jobs: list[Job]) -> DagMetrics:
    known = [j for j in jobs if j.started_at and j.completed_at]
    warnings = tuple(f"missing timestamp:{j.id}" for j in jobs if not j.started_at or not j.completed_at)
    if not known: return DagMetrics(0, 0, 0, (), warnings)
    by_id = {j.id: j for j in known}; best: dict[str, tuple[float, tuple[str, ...]]] = {}
    def visit(job: Job) -> tuple[float, tuple[str, ...]]:
        if job.id in best: return best[job.id]
        own = (job.completed_at - job.started_at).total_seconds()
        parents = [visit(by_id[p]) for p in job.needs if p in by_id]
        prev = max(parents, default=(0, ()))
        best[job.id] = (prev[0] + own, (*prev[1], job.id)); return best[job.id]
    paths = [visit(j) for j in known]
    start, end = min(j.started_at for j in known), max(j.completed_at for j in known)
    longest = max(paths, default=(0, ()))
    work = sum((j.completed_at-j.started_at).total_seconds() for j in known)
    wall = (end-start).total_seconds()
    queue = sum((j.started_at-j.queued_at).total_seconds() for j in known if j.queued_at)
    return DagMetrics(work, wall, longest[0], longest[1], warnings, queue, max(0, wall-longest[0]))
