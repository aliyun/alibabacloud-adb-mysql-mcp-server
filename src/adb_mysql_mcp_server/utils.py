"""General utility functions.

Provides datetime conversion, data formatting (CSV / Markdown), and other
helpers used by the tool functions in server.py.
"""

import csv
import json
import re
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any


def transform_to_iso8601(dt: datetime, timespec: str = "seconds") -> str:
    """Convert a datetime to an ISO 8601 UTC string.

    Example: datetime(2025,1,1,8,0) -> "2025-01-01T00:00:00Z"

    Args:
        dt: The datetime object to convert.
        timespec: Precision (seconds, milliseconds, etc.).
    """
    return dt.astimezone(timezone.utc).isoformat(timespec=timespec).replace("+00:00", "Z")


_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo

# (format, timezone) pairs: formats without trailing Z are treated as local
# timezone; formats with Z are treated as UTC.
_DATETIME_FORMATS = (
    ("%Y-%m-%d %H:%M:%S", _LOCAL_TZ),
    ("%Y-%m-%d %H:%M",    _LOCAL_TZ),
    ("%Y-%m-%dT%H:%M:%SZ", timezone.utc),
    ("%Y-%m-%dT%H:%MZ",    timezone.utc),
)


def transform_to_datetime(s: str) -> datetime:
    """Parse a common datetime string into a timezone-aware datetime object.

    Supported formats:
      - "2025-01-01 12:30:45"       (Y-m-d H:M:S, local timezone)
      - "2025-01-01 12:30"          (Y-m-d H:M, local timezone)
      - "2025-01-01T04:30:45Z"      (ISO 8601 UTC with seconds)
      - "2025-01-01T04:30Z"         (ISO 8601 UTC without seconds)

    Returns:
        A timezone-aware datetime object.

    Raises:
        ValueError: If no supported format matches.
    """
    for fmt, tz in _DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {s}")


def resolve_time_range(
    start_time: str | None,
    end_time: str | None,
    delta: timedelta = timedelta(hours=1),
) -> tuple[datetime, datetime]:
    """Resolve an optional start/end time pair into concrete datetime objects.

    Rules:
      - Both provided:     parse both as-is.
      - Only start:        end = start + delta.
      - Only end:          start = end - delta.
      - Neither provided:  end = now, start = now - delta.

    Args:
        start_time: Optional datetime string (e.g. "2025-01-01 00:00:00").
        end_time:   Optional datetime string.
        delta:      Time span used to fill the missing boundary. Defaults to 1 hour.

    Returns:
        (start_dt, end_dt) tuple of datetime objects.
    """
    has_start = bool(start_time)
    has_end = bool(end_time)

    if has_start and has_end:
        return transform_to_datetime(start_time), transform_to_datetime(end_time)
    if has_start and not has_end:
        start_dt = transform_to_datetime(start_time)
        return start_dt, start_dt + delta
    if not has_start and has_end:
        end_dt = transform_to_datetime(end_time)
        return end_dt - delta, end_dt
    # Neither provided — default to local timezone
    now = datetime.now(_LOCAL_TZ)
    return now - delta, now


def convert_datetime_to_timestamp_ms(date_str: str) -> int:
    """Convert a datetime string to a millisecond Unix timestamp.

    Args:
        date_str: A string in any format supported by transform_to_datetime.
    """
    dt = transform_to_datetime(date_str)
    return int(time.mktime(dt.timetuple())) * 1000


def convert_iso8601_utc_to_timestamp_ms(iso_str: str) -> int:
    """Convert an ISO 8601 UTC string to a millisecond Unix timestamp.

    Args:
        iso_str: A string in format "2025-01-01T00:00Z" (yyyy-MM-ddTHH:mmZ).
    """
    # Remove trailing Z and parse
    iso_str = iso_str.rstrip("Z")
    dt = datetime.fromisoformat(iso_str)
    # Treat as UTC
    dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def json_array_to_csv(data: list[Any] | None) -> str:
    """Convert a list of dicts (or SDK models) to a CSV string.

    Accepts either list[dict] or list[SdkModel] (with .to_map()).
    Used by tools like describe_db_clusters to return tabular data
    that LLMs can easily consume.

    Args:
        data: Input data list. Returns "" if empty or not a list.
    """
    if not data or not isinstance(data, list):
        return ""

    fieldnames: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            fieldnames.update(item.keys())
        elif hasattr(item, "to_map"):
            fieldnames.update(item.to_map().keys())

    if not fieldnames:
        return ""

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=sorted(fieldnames))
    writer.writeheader()
    for item in data:
        row = item if isinstance(item, dict) else item.to_map()
        writer.writerow({k: v if v is not None else "" for k, v in row.items()})
    return output.getvalue()


def json_array_to_markdown(headers: list[str], rows: list[dict]) -> str:
    """Convert data into a Markdown table string.

    Args:
        headers: Column name list.
        rows: List of row dicts.
    """
    if not headers or not rows:
        return ""
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in rows:
        md += "| " + " | ".join(str(row.get(h, "-")) for h in headers) + " |\n"
    return md


def extract_first_column_from_json_rows(json_str: str) -> str:
    """Parse JSON array of row dicts; return first column value per row, newline-joined.

    Returns empty string if json_str is empty, invalid JSON, or has no rows.
    """
    if not json_str:
        return ""
    try:
        rows = json.loads(json_str)
    except json.JSONDecodeError:
        return ""
    if not rows or not isinstance(rows, list):
        return ""
    return "\n".join(str(list(row.values())[0]) for row in rows)


def extract_second_column_from_first_row(json_str: str, default: str = "") -> str:
    """Parse JSON array of row dicts; return second column from first row.

    Falls back to first column if only one column exists.
    Returns default if no rows or invalid JSON.
    """
    if not json_str:
        return default
    try:
        rows = json.loads(json_str)
    except json.JSONDecodeError:
        return default
    if not rows or not isinstance(rows, list):
        return default
    vals = list(rows[0].values())
    return str(vals[1]) if len(vals) > 1 else str(vals[0])


_SQL_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def validate_sql_identifier(name: str, kind: str = "identifier") -> None:
    """Validate that a string is a safe SQL identifier (alphanumeric + underscore).

    Raises:
        ValueError: If name contains invalid characters.
    """
    if not name or not _SQL_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {kind}: must contain only letters, digits, and underscores")
