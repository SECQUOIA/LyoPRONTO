# Copyright (C) 2026, SECQUOIA

"""Analysis helpers for benchmark result records."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def record_succeeded(record: dict[str, Any]) -> bool:
    """Return whether a serialized benchmark record represents a valid run."""
    if record.get("failed") is True:
        return False

    scipy = record.get("scipy")
    if not isinstance(scipy, dict) or scipy.get("success") is not True:
        return False

    pyomo = record.get("pyomo")
    if pyomo is None:
        return True

    return isinstance(pyomo, dict) and pyomo.get("success") is True


def success_summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize record-level success using solver and validation flags."""
    record_list = list(records)
    total = len(record_list)
    succeeded = sum(1 for record in record_list if record_succeeded(record))
    failed = total - succeeded
    success_rate = 100.0 * succeeded / total if total else 0.0

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": success_rate,
    }


def record_method(record: dict[str, Any]) -> str:
    """Return the displayed method name for a benchmark record."""
    pyomo = record.get("pyomo")
    if pyomo is None:
        return "scipy"
    if isinstance(pyomo, dict):
        discretization = pyomo.get("discretization") or {}
        if isinstance(discretization, dict) and discretization.get("method"):
            return str(discretization["method"])
    return "pyomo"


def record_params(record: dict[str, Any]) -> str:
    """Return a compact parameter label for a benchmark record."""
    params = record.get("params") or {}
    if isinstance(params, dict) and params:
        return ", ".join(f"{key}={value}" for key, value in params.items())
    return "no swept parameters"


def failure_lines(
    records: Iterable[dict[str, Any]], limit: int | None = None
) -> list[str]:
    """Return compact labels for records that did not pass validation."""
    failed_records = [record for record in records if not record_succeeded(record)]
    if limit is not None:
        failed_records = failed_records[:limit]
    return [
        f"{record_method(record)}: {record_params(record)}" for record in failed_records
    ]
