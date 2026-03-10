#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "alibabacloud-adb20211201>=3.7.0",
#     "alibabacloud-tea-openapi>=0.3.0",
#     "alibabacloud-tea-util>=0.3.0",
#     "pymysql>=1.1.1",
# ]
# ///
# -*- coding: utf-8 -*-
"""Alibaba Cloud ADB MySQL API command-line tool.

A self-contained script that calls ADB MySQL OpenAPI endpoints and
executes SQL directly. Designed for use with Claude Code skills — can
be run via `uv run` with zero installation.

Supports two connection modes for SQL:
  - Direct mode: set ADB_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE env vars.
  - OpenAPI mode: set ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET for API calls.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import pymysql
    from alibabacloud_adb20211201.client import Client as AdbClient
    from alibabacloud_adb20211201 import models as adb_models
    from alibabacloud_tea_openapi import models as open_api_models
except ImportError as e:
    print(
        "Error: missing required packages. "
        "Install with: pip install alibabacloud-adb20211201 alibabacloud-tea-openapi pymysql",
        file=sys.stderr,
    )
    print(f"Details: {e}", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Time helpers (inlined from utils.py for portability)
# ---------------------------------------------------------------------------

_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo

# (format, timezone): formats without Z -> local timezone; with Z -> UTC
_TIME_FORMATS = (
    ("%Y-%m-%d %H:%M:%S", _LOCAL_TZ),
    ("%Y-%m-%d %H:%M", _LOCAL_TZ),
    ("%Y-%m-%dT%H:%M:%SZ", timezone.utc),
    ("%Y-%m-%dT%H:%MZ", timezone.utc),
)


def _parse_time(s: str) -> datetime:
    """Parse a datetime string into a timezone-aware datetime object."""
    for fmt, tz in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {s}")


def _resolve_time_range(
        start: Optional[str], end: Optional[str], delta: timedelta = timedelta(hours=1)
) -> tuple[datetime, datetime]:
    """Fill missing start/end with sensible defaults (last 1 hour)."""
    has_s, has_e = bool(start), bool(end)
    if has_s and has_e:
        return _parse_time(start), _parse_time(end)
    if has_s:
        s = _parse_time(start)
        return s, s + delta
    if has_e:
        e = _parse_time(end)
        return e - delta, e
    now = datetime.now(_LOCAL_TZ)
    return now - delta, now


def _to_iso8601(dt: datetime, timespec: str = "minutes") -> str:
    """Convert datetime to ISO 8601 UTC string (e.g. 2025-01-01T00:00Z)."""
    return dt.astimezone(timezone.utc).isoformat(timespec=timespec).replace("+00:00", "Z")


def _set_optional(obj: object, **kwargs: object) -> None:
    """Set non-None attributes on a request object."""
    for k, v in kwargs.items():
        if v is not None:
            setattr(obj, k, v)


# ---------------------------------------------------------------------------
# ADB MySQL API client
# ---------------------------------------------------------------------------

API_CONNECT_TIMEOUT = int(os.getenv("ADB_API_CONNECT_TIMEOUT", "10000"))
API_READ_TIMEOUT = int(os.getenv("ADB_API_READ_TIMEOUT", "300000"))


class AdbApiClient:
    """Thin wrapper around the ADB MySQL 2021-12-01 SDK."""

    def __init__(self, region_id: str = "cn-hangzhou"):
        self.region_id = region_id
        self.client = self._create_client()

    def _create_client(self) -> AdbClient:
        ak = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
        sk = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        sts = os.getenv("ALIBABA_CLOUD_SECURITY_TOKEN")

        if not ak or not sk:
            raise ValueError(
                "Alibaba Cloud credentials not found. Set environment variables:\n"
                "  ALIBABA_CLOUD_ACCESS_KEY_ID\n"
                "  ALIBABA_CLOUD_ACCESS_KEY_SECRET"
            )

        config = open_api_models.Config(
            access_key_id=ak,
            access_key_secret=sk,
            security_token=sts,
            region_id=self.region_id,
            protocol="https",
            connect_timeout=API_CONNECT_TIMEOUT,
            read_timeout=API_READ_TIMEOUT,
        )
        return AdbClient(config)

    # -- DescribeDBClusters --------------------------------------------------
    def describe_db_clusters(self) -> dict:
        """List all ADB MySQL clusters in the configured region."""
        request = adb_models.DescribeDBClustersRequest(
            region_id=self.region_id, page_number=1, page_size=100,
            dbcluster_version="All",
        )
        response = self.client.describe_dbclusters(request)
        return response.body.to_map()

    # -- DescribeDBClusterAttribute ------------------------------------------
    def describe_db_cluster_attribute(self, cluster_id: str) -> dict:
        """Get detailed attributes of a specific cluster."""
        request = adb_models.DescribeDBClusterAttributeRequest(dbcluster_id=cluster_id)
        response = self.client.describe_dbcluster_attribute(request)
        return response.body.to_map()

    # -- DescribeDBClusterPerformance ----------------------------------------
    def describe_db_cluster_performance(
            self, cluster_id: str, key: str,
            start_time: Optional[str] = None, end_time: Optional[str] = None,
    ) -> dict:
        """Query cluster performance metrics (CPU, memory, QPS, etc.)."""
        start_dt, end_dt = _resolve_time_range(start_time, end_time)
        request = adb_models.DescribeDBClusterPerformanceRequest(
            dbcluster_id=cluster_id,
            key=key,
            start_time=_to_iso8601(start_dt, timespec="minutes"),
            end_time=_to_iso8601(end_dt, timespec="minutes"),
        )
        response = self.client.describe_dbcluster_performance(request)
        return response.body.to_map()

    # -- DescribeDBClusterSpaceSummary ---------------------------------------
    def describe_db_cluster_space_summary(self, cluster_id: str) -> dict:
        """Get the storage space summary of a cluster."""
        request = adb_models.DescribeDBClusterSpaceSummaryRequest(dbcluster_id=cluster_id)
        response = self.client.describe_dbcluster_space_summary(request)
        return response.body.to_map()

    # -- DescribeDiagnosisRecords --------------------------------------------
    def describe_diagnosis_records(
            self, cluster_id: str,
            start_time: Optional[str] = None, end_time: Optional[str] = None,
            query_condition: Optional[str] = None,
            database: Optional[str] = None, keyword: Optional[str] = None,
            order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Query SQL diagnosis summary records within a time range.

        query_condition supports JSON filters such as:
          - {"Type":"status","Value":"running"}  — running queries
          - {"Type":"status","Value":"finished"} — finished queries
          - {"Type":"maxCost","Value":"100"}      — top 100 by cost
          - {"Type":"cost","Min":"10","Max":"200"} — cost range (ms)
        """
        start_dt, end_dt = _resolve_time_range(start_time, end_time)
        request = adb_models.DescribeDiagnosisRecordsRequest(
            dbcluster_id=cluster_id,
            start_time=str(int(start_dt.timestamp() * 1000)),
            end_time=str(int(end_dt.timestamp() * 1000)),
            page_number=page_number,
            page_size=page_size,
            lang=lang,
        )
        _set_optional(request, query_condition=query_condition,
                      database=database, keyword=keyword, order=order)
        response = self.client.describe_diagnosis_records(request)
        return response.body.to_map()

    # -- DescribeBadSqlDetection ---------------------------------------------
    def describe_bad_sql_detection(
            self, cluster_id: str,
            start_time: Optional[str] = None, end_time: Optional[str] = None,
            lang: str = "zh",
    ) -> dict:
        """Detect bad SQL queries that may impact cluster stability."""
        start_dt, end_dt = _resolve_time_range(start_time, end_time)
        request = adb_models.DescribeBadSqlDetectionRequest(
            dbcluster_id=cluster_id,
            start_time=_to_iso8601(start_dt),
            end_time=_to_iso8601(end_dt),
            lang=lang,
        )
        response = self.client.describe_bad_sql_detection(request)
        return response.body.to_map()

    # -- DescribeSQLPatterns -------------------------------------------------
    def describe_sql_patterns(
            self, cluster_id: str,
            start_time: Optional[str] = None, end_time: Optional[str] = None,
            keyword: Optional[str] = None, order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Query SQL pattern (template) list sorted by aggregated statistics."""
        start_dt, end_dt = _resolve_time_range(start_time, end_time)
        request = adb_models.DescribeSQLPatternsRequest(
            dbcluster_id=cluster_id,
            start_time=_to_iso8601(start_dt),
            end_time=_to_iso8601(end_dt),
            page_number=page_number,
            page_size=page_size,
            lang=lang,
        )
        _set_optional(request, keyword=keyword, order=order)
        response = self.client.describe_sqlpatterns(request)
        return response.body.to_map()

    # -- DescribeTableStatistics ---------------------------------------------
    def describe_table_statistics(
            self, cluster_id: str,
            keyword: Optional[str] = None, order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30,
    ) -> dict:
        """Query table-level statistics (row count, data size, index size, etc.)."""
        request = adb_models.DescribeTableStatisticsRequest(
            dbcluster_id=cluster_id,
            page_number=page_number,
            page_size=page_size,
        )
        _set_optional(request, keyword=keyword, order=order)
        response = self.client.describe_table_statistics(request)
        return response.body.to_map()

    # -- DescribeAvailableAdvices --------------------------------------------
    def describe_available_advices(
            self, cluster_id: str,
            advice_date: Optional[str] = None, advice_type: Optional[str] = None,
            keyword: Optional[str] = None, schema_table_name: Optional[str] = None,
            order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Get available optimization advices (index, partition, etc.)."""
        if not advice_date:
            advice_date = (datetime.now() - timedelta(days=2)).strftime("%Y%m%d")
        request = adb_models.DescribeAvailableAdvicesRequest(
            dbcluster_id=cluster_id,
            advice_date=int(advice_date),
            page_number=page_number,
            page_size=page_size,
            lang=lang,
            region_id=self.region_id,
        )
        _set_optional(request, advice_type=advice_type, keyword=keyword,
                      schema_table_name=schema_table_name, order=order)
        response = self.client.describe_available_advices(request)
        return response.body.to_map()

    # -- DescribeExcessivePrimaryKeys ----------------------------------------
    def describe_excessive_primary_keys(
            self, cluster_id: str,
            order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Detect tables with excessive primary key usage."""
        request = adb_models.DescribeExcessivePrimaryKeysRequest(
            dbcluster_id=cluster_id,
            page_number=page_number,
            page_size=page_size,
            lang=lang,
            region_id=self.region_id,
        )
        _set_optional(request, order=order)
        response = self.client.describe_excessive_primary_keys(request)
        return response.body.to_map()

    # -- DescribeOversizeNonPartitionTableInfos ------------------------------
    def describe_oversize_non_partition_table_infos(
            self, cluster_id: str,
            order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Detect oversized non-partition tables that should consider partitioning."""
        request = adb_models.DescribeOversizeNonPartitionTableInfosRequest(
            dbcluster_id=cluster_id,
            page_number=page_number,
            page_size=page_size,
            lang=lang,
            region_id=self.region_id,
        )
        _set_optional(request, order=order)
        response = self.client.describe_oversize_non_partition_table_infos(request)
        return response.body.to_map()

    # -- DescribeTablePartitionDiagnose --------------------------------------
    def describe_table_partition_diagnose(
            self, cluster_id: str,
            order: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Diagnose table partitioning issues (skew, too many/few partitions, etc.)."""
        request = adb_models.DescribeTablePartitionDiagnoseRequest(
            dbcluster_id=cluster_id,
            page_number=page_number,
            page_size=page_size,
            lang=lang,
            region_id=self.region_id,
        )
        _set_optional(request, order=order)
        response = self.client.describe_table_partition_diagnose(request)
        return response.body.to_map()

    # -- DescribeInclinedTables ----------------------------------------------
    def describe_inclined_tables(
            self, cluster_id: str,
            order: Optional[str] = None, table_type: Optional[str] = None,
            page_number: int = 1, page_size: int = 30, lang: str = "zh",
    ) -> dict:
        """Detect data-skewed tables where data distribution is uneven across nodes."""
        request = adb_models.DescribeInclinedTablesRequest(
            dbcluster_id=cluster_id,
            page_number=page_number,
            page_size=page_size,
            lang=lang,
            region_id=self.region_id,
        )
        _set_optional(request, order=order, table_type=table_type)
        response = self.client.describe_inclined_tables(request)
        return response.body.to_map()


# ---------------------------------------------------------------------------
# SQL execution (direct connection via pymysql)
# ---------------------------------------------------------------------------

DB_CONNECT_TIMEOUT = int(os.getenv("ADB_MYSQL_CONNECT_TIMEOUT", "2"))


def _get_db_config() -> dict:
    """Read database connection config from environment variables.

    Returns a dict with host/port/user/password/database, or empty dict
    if user/password are not configured.
    """
    user = os.getenv("ADB_MYSQL_USER")
    password = os.getenv("ADB_MYSQL_PASSWORD")
    if not user or not password:
        return {}
    return {
        "host": os.getenv("ADB_MYSQL_HOST", "localhost"),
        "port": int(os.getenv("ADB_MYSQL_PORT", "3306")),
        "user": user,
        "password": password,
        "database": os.getenv("ADB_MYSQL_DATABASE"),
    }


def execute_sql(query: str, database: Optional[str] = None) -> str:
    """Execute a SQL query via direct pymysql connection.

    Requires ADB_MYSQL_HOST/PORT/USER/PASSWORD env vars to be set.
    Returns JSON array of row dicts for queries, or {"affected_rows": N}
    for non-query statements.
    """
    cfg = _get_db_config()
    if not cfg:
        raise ValueError(
            "Database credentials not configured. Set environment variables:\n"
            "  ADB_MYSQL_HOST, ADB_MYSQL_PORT, ADB_MYSQL_USER, ADB_MYSQL_PASSWORD"
        )
    if database:
        cfg["database"] = database

    conn = pymysql.connect(
        **cfg,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=DB_CONNECT_TIMEOUT,
    )
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            if not columns:
                return json.dumps({"affected_rows": cursor.rowcount}, ensure_ascii=False)
            return json.dumps(rows, ensure_ascii=False, default=str)
        finally:
            cursor.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add --region to a subcommand parser."""
    parser.add_argument(
        "--region", default="cn-hangzhou",
        help="Alibaba Cloud region ID (default: cn-hangzhou)",
    )


def _add_cluster_args(parser: argparse.ArgumentParser) -> None:
    """Add --region and --cluster-id to a subcommand parser."""
    _add_common_args(parser)
    parser.add_argument(
        "--cluster-id", required=True,
        help="ADB MySQL cluster ID (e.g. amv-xxx)",
    )


def _add_time_args(parser: argparse.ArgumentParser) -> None:
    """Add --start-time and --end-time to a subcommand parser."""
    parser.add_argument(
        "--start-time",
        help="Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.",
    )
    parser.add_argument(
        "--end-time",
        help="End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.",
    )


def _add_page_args(parser: argparse.ArgumentParser) -> None:
    """Add --page-number and --page-size to a subcommand parser."""
    parser.add_argument("--page-number", type=int, default=1, help="Page number (default: 1)")
    parser.add_argument("--page-size", type=int, default=30, help="Page size (default: 30)")


def _add_lang_arg(parser: argparse.ArgumentParser) -> None:
    """Add --lang to a subcommand parser."""
    parser.add_argument("--lang", default="zh", choices=["zh", "en"], help="Language (default: zh)")


def _add_order_arg(parser: argparse.ArgumentParser) -> None:
    """Add --order to a subcommand parser."""
    parser.add_argument(
        "--order",
        help='Sort by specified fields in JSON format (e.g. \'[{"Field":"StartTime","Type":"desc"}]\')',
    )


def _output(data: dict) -> None:
    """Print result as formatted JSON to stdout."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _log(msg: str) -> None:
    """Print metadata to stderr."""
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_describe_db_clusters(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region}")
    _output(client.describe_db_clusters())


def cmd_describe_db_cluster_attribute(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_db_cluster_attribute(args.cluster_id))


def cmd_describe_db_cluster_performance(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id} | [Key] {args.key}")
    _output(client.describe_db_cluster_performance(
        args.cluster_id, args.key, args.start_time, args.end_time,
    ))


def cmd_describe_db_cluster_space_summary(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_db_cluster_space_summary(args.cluster_id))


def cmd_describe_diagnosis_records(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_diagnosis_records(
        args.cluster_id,
        start_time=args.start_time, end_time=args.end_time,
        query_condition=args.query_condition,
        database=args.database, keyword=args.keyword,
        order=args.order,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_describe_bad_sql_detection(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_bad_sql_detection(
        args.cluster_id,
        start_time=args.start_time, end_time=args.end_time,
        lang=args.lang,
    ))


def cmd_describe_sql_patterns(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_sql_patterns(
        args.cluster_id,
        start_time=args.start_time, end_time=args.end_time,
        keyword=args.keyword, order=args.order,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_describe_table_statistics(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_table_statistics(
        args.cluster_id,
        keyword=args.keyword, order=args.order,
        page_number=args.page_number, page_size=args.page_size,
    ))


def cmd_describe_available_advices(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_available_advices(
        args.cluster_id,
        advice_date=args.advice_date, advice_type=args.advice_type,
        keyword=args.keyword, schema_table_name=args.schema_table_name,
        order=args.order,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_describe_excessive_primary_keys(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_excessive_primary_keys(
        args.cluster_id,
        order=args.order,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_describe_oversize_non_partition_table_infos(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_oversize_non_partition_table_infos(
        args.cluster_id,
        order=args.order,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_describe_table_partition_diagnose(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_table_partition_diagnose(
        args.cluster_id,
        order=args.order,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_describe_inclined_tables(args: argparse.Namespace) -> None:
    client = AdbApiClient(args.region)
    _log(f"[Region] {args.region} | [Cluster] {args.cluster_id}")
    _output(client.describe_inclined_tables(
        args.cluster_id,
        order=args.order, table_type=args.table_type,
        page_number=args.page_number, page_size=args.page_size,
        lang=args.lang,
    ))


def cmd_execute_sql(args: argparse.Namespace) -> None:
    _log(f"[SQL] {args.query[:80]}{'...' if len(args.query) > 80 else ''}")
    result = execute_sql(args.query, database=args.database)
    print(result)


def cmd_get_current_utc_time(args: argparse.Namespace) -> None:
    now = datetime.now(timezone.utc)
    _output({
        "utc_now": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "utc_now_short": now.strftime("%Y-%m-%dT%H:%MZ"),
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alibaba Cloud ADB MySQL API CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run ./scripts/call_adb_api.py describe_db_clusters
  uv run ./scripts/call_adb_api.py describe_db_cluster_attribute --cluster-id amv-xxx
  uv run ./scripts/call_adb_api.py describe_db_cluster_performance --cluster-id amv-xxx --key AnalyticDB_CPU
  uv run ./scripts/call_adb_api.py describe_diagnosis_records --cluster-id amv-xxx \\
      --start-time 2025-01-01T00:00Z --end-time 2025-01-01T01:00Z
  uv run ./scripts/call_adb_api.py describe_bad_sql_detection --cluster-id amv-xxx
  uv run ./scripts/call_adb_api.py describe_sql_patterns --cluster-id amv-xxx
  uv run ./scripts/call_adb_api.py describe_table_statistics --cluster-id amv-xxx
  uv run ./scripts/call_adb_api.py describe_available_advices --cluster-id amv-xxx --advice-type INDEX
  uv run ./scripts/call_adb_api.py describe_inclined_tables --cluster-id amv-xxx
  uv run ./scripts/call_adb_api.py execute_sql --query "SELECT 1"
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="API command to execute")

    # describe_db_clusters
    p = subparsers.add_parser("describe_db_clusters", help="List ADB MySQL clusters")
    _add_common_args(p)
    p.set_defaults(func=cmd_describe_db_clusters)

    # describe_db_cluster_attribute
    p = subparsers.add_parser("describe_db_cluster_attribute", help="Get cluster attributes")
    _add_cluster_args(p)
    p.set_defaults(func=cmd_describe_db_cluster_attribute)

    # describe_db_cluster_performance
    p = subparsers.add_parser("describe_db_cluster_performance", help="Query performance metrics")
    _add_cluster_args(p)
    _add_time_args(p)
    p.add_argument(
        "--key", required=True,
        help="Metric key (e.g. AnalyticDB_CPU, AnalyticDB_Memory_Avg, "
             "AnalyticDB_QPS, AnalyticDB_TPS, AnalyticDB_Connections, AnalyticDB_DiskUsage)",
    )
    p.set_defaults(func=cmd_describe_db_cluster_performance)

    # describe_db_cluster_space_summary
    p = subparsers.add_parser("describe_db_cluster_space_summary", help="Get storage space summary")
    _add_cluster_args(p)
    p.set_defaults(func=cmd_describe_db_cluster_space_summary)

    # describe_diagnosis_records
    p = subparsers.add_parser("describe_diagnosis_records", help="Query SQL diagnosis records")
    _add_cluster_args(p)
    _add_time_args(p)
    p.add_argument(
        "--query-condition",
        help='JSON filter, e.g. \'{"Type":"status","Value":"running"}\' '
             'or \'{"Type":"maxCost","Value":"100"}\'',
    )
    p.add_argument("--database", help="Database name filter")
    p.add_argument("--keyword", help="SQL keyword filter")
    _add_order_arg(p)
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_diagnosis_records)

    # describe_bad_sql_detection
    p = subparsers.add_parser("describe_bad_sql_detection", help="Detect bad SQL queries")
    _add_cluster_args(p)
    _add_time_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_bad_sql_detection)

    # describe_sql_patterns
    p = subparsers.add_parser("describe_sql_patterns", help="Query SQL pattern statistics")
    _add_cluster_args(p)
    _add_time_args(p)
    p.add_argument("--keyword", help="SQL keyword filter")
    _add_order_arg(p)
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_sql_patterns)

    # describe_table_statistics
    p = subparsers.add_parser("describe_table_statistics", help="Query table-level statistics")
    _add_cluster_args(p)
    p.add_argument("--keyword", help="Table name filter (fuzzy match)")
    _add_order_arg(p)
    _add_page_args(p)
    p.set_defaults(func=cmd_describe_table_statistics)

    # describe_available_advices
    p = subparsers.add_parser("describe_available_advices", help="Get optimization advices")
    _add_cluster_args(p)
    p.add_argument("--advice-date", help="Advice date in yyyyMMdd format (default: T-2 days)")
    p.add_argument("--advice-type", choices=["INDEX", "TIERING"], help="Advice type filter")
    p.add_argument("--keyword", help="Table name keyword for fuzzy search")
    p.add_argument("--schema-table-name", help='Full qualified table name (e.g. "tpch.lineitem")')
    _add_order_arg(p)
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_available_advices)

    # describe_excessive_primary_keys
    p = subparsers.add_parser("describe_excessive_primary_keys", help="Detect excessive primary keys")
    _add_cluster_args(p)
    _add_order_arg(p)
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_excessive_primary_keys)

    # describe_oversize_non_partition_table_infos
    p = subparsers.add_parser("describe_oversize_non_partition_table_infos", help="Detect oversized non-partition tables")
    _add_cluster_args(p)
    _add_order_arg(p)
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_oversize_non_partition_table_infos)

    # describe_table_partition_diagnose
    p = subparsers.add_parser("describe_table_partition_diagnose", help="Diagnose table partitioning issues")
    _add_cluster_args(p)
    _add_order_arg(p)
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_table_partition_diagnose)

    # describe_inclined_tables
    p = subparsers.add_parser("describe_inclined_tables", help="Detect data-skewed tables")
    _add_cluster_args(p)
    _add_order_arg(p)
    p.add_argument("--table-type", choices=["FactTable", "DimensionTable"], help="Table type filter")
    _add_page_args(p)
    _add_lang_arg(p)
    p.set_defaults(func=cmd_describe_inclined_tables)

    # execute_sql (direct DB connection, requires ADB_MYSQL_* env vars)
    p = subparsers.add_parser("execute_sql", help="Execute SQL via direct database connection")
    p.add_argument("--query", required=True, help="SQL statement to execute")
    p.add_argument("--database", help="Target database name (overrides ADB_MYSQL_DATABASE)")
    p.set_defaults(func=cmd_execute_sql)

    # get_current_utc_time (no credentials required)
    p = subparsers.add_parser("get_current_utc_time", help="Print current UTC time for time range calculations")
    p.set_defaults(func=cmd_get_current_utc_time)

    # Parse and dispatch
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
