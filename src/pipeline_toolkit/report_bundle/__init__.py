"""Canonical inputs for generating report bundles."""

from .model import (
    ALLOWED_STATUSES,
    ReportBundleInput,
    ReportBundleValidationError,
    ReportFact,
    is_performance_eligible,
    load_report_bundle,
)

__all__ = [
    "ALLOWED_STATUSES",
    "ReportBundleInput",
    "ReportBundleValidationError",
    "ReportFact",
    "is_performance_eligible",
    "load_report_bundle",
]
