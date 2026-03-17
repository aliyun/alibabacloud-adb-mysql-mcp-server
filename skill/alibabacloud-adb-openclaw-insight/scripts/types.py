"""
Shared type definitions and utility functions for the OpenClaw Insight Analysis system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


# ─── Time Range ───

@dataclass
class TimeRange:
    start_date: str  # ISO date: "2026-03-01"
    end_date: str    # ISO date: "2026-03-10"


def time_range_to_sql_params(range_: TimeRange) -> tuple[str, str]:
    """Generates SQL parameter values for a TimeRange.

    start_date always uses 00:00:00.
    end_date: if it contains a time component (space or 'T'), use as-is;
    otherwise append 00:00:00.
    """
    start = range_.start_date if " " in range_.start_date or "T" in range_.start_date else f"{range_.start_date} 00:00:00"
    end = range_.end_date if " " in range_.end_date or "T" in range_.end_date else f"{range_.end_date} 00:00:00"
    return (start, end)


def yesterday_range() -> TimeRange:
    """Returns a TimeRange for 'yesterday' (the most recent full day)."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    return TimeRange(
        start_date=yesterday.isoformat(),
        end_date=today.isoformat(),
    )


def last_n_days_range(days: int) -> TimeRange:
    """Returns a TimeRange for the last N days ending at the current moment."""
    now = datetime.now()
    start = now - timedelta(days=days)
    return TimeRange(
        start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_date=now.strftime("%Y-%m-%d %H:%M:%S"),
    )


# ─── stop_reason classification ───

NORMAL_COMPLETION_REASONS = {"stop", "end_turn"}
INTERMEDIATE_REASONS = {"toolUse"}
TRUNCATION_REASONS = {"max_tokens"}


def is_intermediate_stop_reason(stop_reason: str | None) -> bool:
    return stop_reason is not None and stop_reason in INTERMEDIATE_REASONS


def is_normal_completion(stop_reason: str | None) -> bool:
    return stop_reason is not None and stop_reason in NORMAL_COMPLETION_REASONS


def is_truncation(stop_reason: str | None) -> bool:
    return stop_reason is not None and stop_reason in TRUNCATION_REASONS


def is_abnormal_termination(stop_reason: str | None) -> bool:
    if stop_reason is None:
        return False
    return (
        stop_reason not in NORMAL_COMPLETION_REASONS
        and stop_reason not in INTERMEDIATE_REASONS
        and stop_reason not in TRUNCATION_REASONS
    )
