"""ADB MySQL MCP Server.

This module contains:
  - OpenAPI tools (group: "openapi") for cluster management, diagnostics,
    monitoring, and administration.
  - SQL tools (group: "sql") for executing queries and viewing execution plans.
  - MCP resources (group: "sql") for browsing databases, tables, DDL, and config.
  - Server entry point main() supporting stdio / SSE / streamable_http transports.

All tools and resources are registered via deferred decorators on AdbMCP.
They become active only after mcp.activate() is called in main().

API reference:
  https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/api-adb-2021-12-01-overview
"""

import argparse
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

import anyio
import uvicorn
from mcp.types import ToolAnnotations

from alibabacloud_adb20211201 import models as adb_models

from .core.mcp import AdbMCP
from .db_service import DBService
from .openapi_client import get_adb_client
from .utils import (
    extract_first_column_from_json_rows,
    extract_second_column_from_first_row,
    json_array_to_csv,
    resolve_time_range,
    transform_to_iso8601,
    validate_sql_identifier,
)

logger = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(readOnlyHint=True)

# Default groups enabled when MCP_TOOLSETS is not specified.
DEFAULT_GROUPS = ["openapi", "sql"]

# Shortcut expansions for MCP_TOOLSETS values.
GROUP_EXPANSIONS: dict[str, list[str]] = {
    "all": ["openapi", "sql"],
}

mcp = AdbMCP(
    "Alibaba Cloud ADB MySQL MCP Server",
    port=int(os.getenv("SERVER_PORT", 8000)),
    stateless_http=True,
)


def _set_optional_fields(obj: object, *, skip_empty: bool = True, **kwargs: Any) -> None:
    """Set attributes on obj for each non-None kwargs value.

    When skip_empty is True, empty strings are not set (treats them as "unset").
    """
    for key, value in kwargs.items():
        if value is None:
            continue
        if skip_empty and value == "":
            continue
        setattr(obj, key, value)


# =============================================================================
# Core cluster tools (group: openapi)
# =============================================================================

@mcp.tool(annotations=READ_ONLY)
async def describe_db_clusters(region_id: str) -> str:
    """List ADB MySQL clusters in a region.

    OpenAPI: DescribeDBClusters
    Returns a CSV-formatted cluster list for easy consumption by LLMs.

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeDBClustersRequest(region_id=region_id, page_number=1, page_size=100)
    response = client.describe_dbclusters(request)
    items = response.body.items.dbcluster if response.body.items and response.body.items.dbcluster else []
    res = json_array_to_csv(items)
    return res if res else "No ADB MySQL clusters found."


@mcp.tool(annotations=READ_ONLY)
async def describe_db_cluster_attribute(region_id: str, db_cluster_id: str) -> dict[str, Any]:
    """Get detailed attributes of a cluster (spec, status, VPC info, etc.).

    OpenAPI: DescribeDBClusterAttribute

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeDBClusterAttributeRequest(dbcluster_id=db_cluster_id)
    response = client.describe_dbcluster_attribute(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_cluster_access_whitelist(region_id: str, db_cluster_id: str) -> dict[str, Any]:
    """Get the IP whitelist configuration of a cluster.

    OpenAPI: DescribeClusterAccessWhiteList

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeClusterAccessWhiteListRequest(dbcluster_id=db_cluster_id)
    response = client.describe_cluster_access_white_list(request)
    return response.body.to_map()


@mcp.tool()
async def modify_cluster_access_whitelist(
        region_id: str,
        db_cluster_id: str,
        security_ips: str,
        db_cluster_ip_array_name: str = "default",
        modify_mode: str = "Cover",
) -> dict[str, Any]:
    """Modify the IP whitelist of a cluster.

    OpenAPI: ModifyClusterAccessWhiteList

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        security_ips: Comma-separated IP addresses or CIDR blocks.
        db_cluster_ip_array_name: Whitelist group name, default "default".
        modify_mode: Cover (overwrite), Append (add), or Delete (remove).
    """
    client = get_adb_client(region_id)
    request = adb_models.ModifyClusterAccessWhiteListRequest(
        dbcluster_id=db_cluster_id,
        security_ips=security_ips,
        dbcluster_iparray_name=db_cluster_ip_array_name,
        modify_mode=modify_mode,
    )
    try:
        response = client.modify_cluster_access_white_list(request)
        return response.body.to_map()
    except Exception:
        logger.error("Failed to modify whitelist for cluster %s", db_cluster_id, exc_info=True)
        raise


@mcp.tool(annotations=READ_ONLY)
async def describe_accounts(region_id: str, db_cluster_id: str) -> dict[str, Any]:
    """List database accounts in a cluster.

    OpenAPI: DescribeAccounts

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeAccountsRequest(dbcluster_id=db_cluster_id)
    response = client.describe_accounts(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_cluster_net_info(region_id: str, db_cluster_id: str) -> dict[str, Any]:
    """Get network connection info of a cluster (VPC/public endpoints, ports).

    OpenAPI: DescribeClusterNetInfo

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeClusterNetInfoRequest(dbcluster_id=db_cluster_id)
    response = client.describe_cluster_net_info(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def get_current_time() -> dict[str, str]:
    """Get the current time of the MCP Server (provides time context for LLMs)."""
    return {"current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


# =============================================================================
# Diagnostics & monitoring tools (group: openapi)
# =============================================================================

@mcp.tool(annotations=READ_ONLY)
async def describe_db_cluster_performance(
        region_id: str,
        db_cluster_id: str,
        key: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        resource_pools: Optional[str] = None,
) -> dict[str, Any]:
    """Query cluster performance metrics.

    OpenAPI: DescribeDBClusterPerformance

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        key: Metric key (e.g.AnalyticDB_CPU,AnalyticDB_QPS,AnalyticDB_QueryFailedRatio,AnalyticDB_QueryRT,AnalyticDB_QueryWaitTime,AnalyticDB_Connections,
        AnalyticDB_InsertBytes,AnalyticDB_InsertRT,AnalyticDB_InsertTPS,AnalyticDB_LoadTPS,AnalyticDB_UpdateRT,AnalyticDB_UpdateTPS,AnalyticDB_DeleteRT,
        AnalyticDB_DeleteTPS,AnalyticDB_DiskUsedRatio,AnalyticDB_DiskUsedSize,AnalyticDB_BuildTaskCount,AnalyticDB_Table_Read_Result_Size,
        AnalyticDB_UnavailableNodeCount,AnalyticDB_IO,AnalyticDB_IOPS,AnalyticDB_IO_UTIL,AnalyticDB_IO_WAIT,AnalyticDB_RC_CPU,AnalyticDB_RC_IO,
        AnalyticDB_RC_IOPS,AnalyticDB_RC_MemoryUsedRatio,AnalyticDB_RP_ActualNode,AnalyticDB_RP_CPU,AnalyticDB_RP_OriginalNode,AnalyticDB_RP_PlanNode,
        AnalyticDB_RP_QPS,AnalyticDB_RP_QueuedQueries_Count,AnalyticDB_RP_RT,AnalyticDB_RP_RunningQueries_Count,AnalyticDB_RP_TotalNode,
        AnalyticDB_RP_WaitTime,AnalyticDB_WLM_SQA_AvgRt_MS,AnalyticDB_WLM_SQA_Queries_Count,AnalyticDB_WLM_TotalQueries_Count).
        resource_pools: Optional resource pool name filter.
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeDBClusterPerformanceRequest(
        dbcluster_id=db_cluster_id,
        key=key,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
    )
    _set_optional_fields(request, resource_pools=resource_pools)

    response = client.describe_dbcluster_performance(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_db_cluster_health_status(region_id: str, db_cluster_id: str) -> dict[str, Any]:
    """Query the health status of a cluster (connections, disk, nodes, etc.).

    OpenAPI: DescribeDBClusterHealthStatus

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeDBClusterHealthStatusRequest(dbcluster_id=db_cluster_id)
    response = client.describe_dbcluster_health_status(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_diagnosis_records(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        query_condition: Optional[str] = None,
        resource_group: Optional[str] = None,
        database: Optional[str] = None,
        user_name: Optional[str] = None,
        keyword: Optional[str] = None,
        min_peak_memory: Optional[int] = None,
        min_scan_size: Optional[int] = None,
        max_peak_memory: Optional[int] = None,
        max_scan_size: Optional[int] = None,
        page_number: int = 1,
        page_size: int = 30,
        order: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Query SQL diagnosis summary records within a time range.

    OpenAPI: DescribeDiagnosisRecords

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        query_condition: Optional SQL filter condition.
        resource_group: Optional resource group name filter.
        database: Optional database name filter.
        user_name: Optional user name filter.
        keyword: Optional SQL keyword filter.
        min_peak_memory: Optional minimum peak memory in bytes.
        min_scan_size: Optional minimum scan size in bytes.
        max_peak_memory: Optional maximum peak memory in bytes.
        max_scan_size: Optional maximum scan size in bytes.
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        order: Sort the SQL statement according to the specified fields, in JSON format(e.g. [{"Field":"StartTime", "Type": "desc"}]).
        lang: Language: zh (Chinese) or en (English).
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)

    start_ts = str(int(start_dt.timestamp() * 1000))
    end_ts = str(int(end_dt.timestamp() * 1000))

    request = adb_models.DescribeDiagnosisRecordsRequest(
        dbcluster_id=db_cluster_id,
        start_time=start_ts,
        end_time=end_ts,
        page_number=page_number,
        page_size=page_size,
        lang=lang,
    )
    _set_optional_fields(
        request,
        order=order,
        query_condition=query_condition,
        resource_group=resource_group,
        database=database,
        user_name=user_name,
        keyword=keyword,
        min_peak_memory=min_peak_memory,
        min_scan_size=min_scan_size,
        max_peak_memory=max_peak_memory,
        max_scan_size=max_scan_size,
    )

    response = client.describe_diagnosis_records(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_diagnosis_sql_info(
        region_id: str,
        db_cluster_id: str,
        process_id: str,
        lang: str = "zh",
) -> dict[str, Any]:
    """Get execution details of a single SQL (plan, runtime info, diagnosis).

    OpenAPI: DescribeDiagnosisSQLInfo
    The process_id can be obtained from describe_diagnosis_records results.

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        process_id: SQL process ID (query ID).
        lang: Language: zh (Chinese) or en (English).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeDiagnosisSQLInfoRequest(
        dbcluster_id=db_cluster_id,
        process_id=process_id,
        lang=lang,
    )
    response = client.describe_diagnosis_sqlinfo(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_bad_sql_detection(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Detect bad SQL queries that may impact cluster stability.

    OpenAPI: DescribeBadSqlDetection

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        lang: Language: zh (Chinese) or en (English).
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeBadSqlDetectionRequest(
        dbcluster_id=db_cluster_id,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
        lang=lang,
    )
    response = client.describe_bad_sql_detection(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_sql_patterns(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        keyword: Optional[str] = None,
        order: Optional[str] = None,
        page_number: int = 1,
        page_size: int = 30,
        lang: str = "zh",
) -> dict[str, Any]:
    """Query SQL pattern (template) list sorted by aggregated statistics.

    OpenAPI: DescribeSQLPatterns
    SQL patterns are parameter-normalized SQL templates for identifying
    high-frequency or high-cost queries.

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        keyword: Optional SQL keyword filter.
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        lang: Language: zh (Chinese) or en (English).
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeSQLPatternsRequest(
        dbcluster_id=db_cluster_id,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
        page_number=page_number,
        page_size=page_size,
        lang=lang,
    )
    _set_optional_fields(request, keyword=keyword, order=order)

    response = client.describe_sqlpatterns(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_table_statistics(
        region_id: str,
        db_cluster_id: str,
        keyword: Optional[str] = None,
        order: Optional[str] = None,
        page_number: int = 1,
        page_size: int = 30,
) -> dict[str, Any]:
    """Query table-level statistics (row count, data size, index size, etc.).

    OpenAPI: DescribeTableStatistics

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        keyword: Optional table name filter (supports fuzzy match).
        order: Sort by specified fields in JSON format (e.g. [{"Field":"TotalSize","Type":"desc"}]).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeTableStatisticsRequest(
        dbcluster_id=db_cluster_id,
        page_number=page_number,
        page_size=page_size,
    )
    _set_optional_fields(request, keyword=keyword, order=order)

    response = client.describe_table_statistics(request)
    return response.body.to_map()


# =============================================================================
# Administration & audit tools (group: openapi)
# =============================================================================

@mcp.tool()
async def create_account(
        region_id: str,
        db_cluster_id: str,
        account_name: str,
        account_password: str,
        account_description: Optional[str] = None,
        account_type: str = "Normal",
) -> dict[str, Any]:
    """Create a database account for a cluster.

    OpenAPI: CreateAccount

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        account_name: Account name.
        account_password: Account password (must comply with the password policy).
        account_description: Optional account description.
        account_type: Account type — Normal or Super, default Normal.
    """
    client = get_adb_client(region_id)
    request = adb_models.CreateAccountRequest(
        dbcluster_id=db_cluster_id,
        account_name=account_name,
        account_password=account_password,
        account_type=account_type,
    )
    _set_optional_fields(request, account_description=account_description)

    try:
        response = client.create_account(request)
        return response.body.to_map()
    except Exception:
        logger.error("Failed to create account '%s' on cluster %s", account_name, db_cluster_id, exc_info=True)
        raise


@mcp.tool()
async def modify_db_cluster_description(
        region_id: str,
        db_cluster_id: str,
        description: str,
) -> dict[str, Any]:
    """Modify the description of a cluster.

    OpenAPI: ModifyDBClusterDescription

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        description: New description text.
    """
    client = get_adb_client(region_id)
    request = adb_models.ModifyDBClusterDescriptionRequest(
        dbcluster_id=db_cluster_id,
        dbcluster_description=description,
    )
    try:
        response = client.modify_dbcluster_description(request)
        return response.body.to_map()
    except Exception:
        logger.error("Failed to modify description for cluster %s", db_cluster_id, exc_info=True)
        raise


@mcp.tool(annotations=READ_ONLY)
async def describe_db_cluster_space_summary(region_id: str, db_cluster_id: str) -> dict[str, Any]:
    """Get the storage space summary of a cluster (data, index, log sizes).

    OpenAPI: DescribeDBClusterSpaceSummary

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeDBClusterSpaceSummaryRequest(dbcluster_id=db_cluster_id)
    response = client.describe_dbcluster_space_summary(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_audit_log_records(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        db_name: Optional[str] = None,
        query_keyword: Optional[str] = None,
        sql_type: Optional[str] = None,
        user: Optional[str] = None,
        host_address: Optional[str] = None,
        order: Optional[str] = None,
        page_number: int = 1,
        page_size: int = 30,
) -> dict[str, Any]:
    """Query SQL audit log records. Requires SQL audit to be enabled on the cluster.

    OpenAPI: DescribeAuditLogRecords

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        db_name: Optional database name filter.
        query_keyword: Optional SQL keyword filter.
        sql_type: Optional SQL type filter (e.g. SELECT, INSERT, UPDATE, DELETE).
        user: Optional user name filter.
        host_address: Optional source IP filter.
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeAuditLogRecordsRequest(
        dbcluster_id=db_cluster_id,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
        page_number=page_number,
        page_size=page_size,
    )
    _set_optional_fields(
        request,
        order=order,
        db_name=db_name,
        query_keyword=query_keyword,
        sql_type=sql_type,
        user=user,
        host_address=host_address,
    )

    response = client.describe_audit_log_records(request)
    return response.body.to_map()


# =============================================================================
# Advanced diagnostics tools (group: openapi)
# =============================================================================

@mcp.tool(annotations=READ_ONLY)
async def describe_executor_detection(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Run diagnostics on compute nodes (Executors).

    OpenAPI: DescribeExecutorDetection

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        lang: Language: zh (Chinese) or en (English).
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeExecutorDetectionRequest(
        dbcluster_id=db_cluster_id,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
        lang=lang,
    )
    response = client.describe_executor_detection(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_worker_detection(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Run diagnostics on storage nodes (Workers).

    OpenAPI: DescribeWorkerDetection

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        lang: Language: zh (Chinese) or en (English).
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeWorkerDetectionRequest(
        dbcluster_id=db_cluster_id,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
        lang=lang,
    )
    response = client.describe_worker_detection(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_controller_detection(
        region_id: str,
        db_cluster_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Run diagnostics on access nodes (Controllers).

    OpenAPI: DescribeControllerDetection

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        start_time: Start time in ISO 8601 UTC (e.g. 2025-01-01T00:00Z). Defaults to 1 hour ago.
        end_time: End time in ISO 8601 UTC (e.g. 2025-01-01T01:00Z). Defaults to now.
        lang: Language: zh (Chinese) or en (English).
    """
    start_dt, end_dt = resolve_time_range(start_time, end_time)
    client = get_adb_client(region_id)
    request = adb_models.DescribeControllerDetectionRequest(
        dbcluster_id=db_cluster_id,
        start_time=transform_to_iso8601(start_dt, timespec="minutes"),
        end_time=transform_to_iso8601(end_dt, timespec="minutes"),
        lang=lang,
    )
    response = client.describe_controller_detection(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_available_advices(
        region_id: str,
        db_cluster_id: str,
        advice_date: Optional[str] = None,
        advice_type: Optional[str] = None,
        keyword: Optional[str] = None,
        schema_table_name: Optional[str] = None,
        order: Optional[str] = None,
        page_number: int = 1,
        page_size: int = 30,
        lang: str = "zh",
) -> dict[str, Any]:
    """Get available optimization advices (index, partition, etc.) for a cluster.

    OpenAPI: DescribeAvailableAdvices

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        advice_date: Advice generation date in yyyyMMdd format (e.g. 20250101). Defaults to T-2 days.
        advice_type: Advice type filter — INDEX (index optimization) or TIERING (hot/cold data optimization).
        keyword: Table name keyword for fuzzy search.
        schema_table_name: Full qualified table name in "database.table" format (e.g. tpch.lineitem).
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        lang: Language: zh (Chinese) or en (English).
    """
    client = get_adb_client(region_id)
    if not advice_date:
        advice_date = (datetime.now() - timedelta(days=2)).strftime("%Y%m%d")
    request = adb_models.DescribeAvailableAdvicesRequest(
        dbcluster_id=db_cluster_id,
        advice_date=int(advice_date),
        page_number=page_number,
        page_size=page_size,
        lang=lang,
        region_id=region_id,
    )
    _set_optional_fields(
        request,
        advice_type=advice_type,
        keyword=keyword,
        schema_table_name=schema_table_name,
        order=order,
    )
    response = client.describe_available_advices(request)
    return response.body.to_map()


@mcp.tool()
async def kill_process(region_id: str, db_cluster_id: str, process_id: str) -> dict[str, Any]:
    """Kill a running query process in the cluster.

    OpenAPI: KillProcess
    WARNING: This forcefully terminates the specified query.

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        process_id: Process ID to terminate.
    """
    client = get_adb_client(region_id)
    request = adb_models.KillProcessRequest(
        dbcluster_id=db_cluster_id,
        process_id=process_id,
    )
    try:
        response = client.kill_process(request)
        return response.body.to_map()
    except Exception:
        logger.error("Failed to kill process %s on cluster %s", process_id, db_cluster_id, exc_info=True)
        raise


@mcp.tool(annotations=READ_ONLY)
async def describe_db_resource_group(
        region_id: str,
        db_cluster_id: str,
        group_name: Optional[str] = None,
) -> dict[str, Any]:
    """Get resource group configuration of a cluster.

    OpenAPI: DescribeDBResourceGroup

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        group_name: Optional resource group name filter (returns all if omitted).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeDBResourceGroupRequest(dbcluster_id=db_cluster_id)
    _set_optional_fields(request, group_name=group_name)

    response = client.describe_dbresource_group(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_excessive_primary_keys(
        region_id: str,
        db_cluster_id: str,
        page_number: int = 1,
        page_size: int = 30,
        order: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Detect tables with excessive primary key usage that may impact performance.

    OpenAPI: DescribeExcessivePrimaryKeys

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        lang: Language: zh (Chinese) or en (English).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeExcessivePrimaryKeysRequest(
        dbcluster_id=db_cluster_id,
        page_number=page_number,
        page_size=page_size,
        lang=lang,
        region_id=region_id,
    )
    _set_optional_fields(request, order=order)
    response = client.describe_excessive_primary_keys(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_oversize_non_partition_table_infos(
        region_id: str,
        db_cluster_id: str,
        page_number: int = 1,
        page_size: int = 30,
        order: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Detect oversized non-partition tables that should consider partitioning.

    OpenAPI: DescribeOversizeNonPartitionTableInfos

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        lang: Language: zh (Chinese) or en (English).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeOversizeNonPartitionTableInfosRequest(
        dbcluster_id=db_cluster_id,
        page_number=page_number,
        page_size=page_size,
        lang=lang,
        region_id=region_id,
    )
    _set_optional_fields(request, order=order)
    response = client.describe_oversize_non_partition_table_infos(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_table_partition_diagnose(
        region_id: str,
        db_cluster_id: str,
        page_number: int = 1,
        page_size: int = 30,
        order: Optional[str] = None,
        lang: str = "zh",
) -> dict[str, Any]:
    """Diagnose table partitioning issues (skew, too many/few partitions, etc.).

    OpenAPI: DescribeTablePartitionDiagnose

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        lang: Language: zh (Chinese) or en (English).
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeTablePartitionDiagnoseRequest(
        dbcluster_id=db_cluster_id,
        page_number=page_number,
        page_size=page_size,
        lang=lang,
        region_id=region_id,
    )
    _set_optional_fields(request, order=order)
    response = client.describe_table_partition_diagnose(request)
    return response.body.to_map()


@mcp.tool(annotations=READ_ONLY)
async def describe_inclined_tables(
        region_id: str,
        db_cluster_id: str,
        page_number: int = 1,
        page_size: int = 30,
        order: Optional[str] = None,
        lang: str = "zh",
        table_type: Optional[str] = None,
) -> dict[str, Any]:
    """Detect data-skewed tables where data distribution is uneven across nodes.

    OpenAPI: DescribeInclinedTables

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou).
        db_cluster_id: Cluster ID (e.g. amv-xxx).
        page_number: Page number, default 1.
        page_size: Page size, default 30.
        order: Sort by specified fields in JSON format (e.g. [{"Field":"StartTime","Type":"desc"}]).
        lang: Language: zh (Chinese) or en (English).
        table_type: Optional table type filter, FactTable or DimensionTable, default FactTable.
    """
    client = get_adb_client(region_id)
    request = adb_models.DescribeInclinedTablesRequest(
        dbcluster_id=db_cluster_id,
        page_number=page_number,
        page_size=page_size,
        lang=lang,
        region_id=region_id,
    )
    _set_optional_fields(request, order=order, table_type=table_type)
    response = client.describe_inclined_tables(request)
    return response.body.to_map()


# =============================================================================
# SQL tools (group: sql)
# =============================================================================

@mcp.tool(group="sql", annotations=READ_ONLY)
async def execute_sql(
        query: str,
        region_id: Optional[str] = None,
        db_cluster_id: Optional[str] = None,
        database: Optional[str] = None,
) -> str:
    """Execute a SQL query on an ADB MySQL cluster.

    Connection modes:
      - Direct mode (ADB_MYSQL_USER/PASSWORD configured): region_id/db_cluster_id optional.
      - Temporary account mode (AK/SK only): region_id/db_cluster_id required.

    Args:
        query: The SQL statement to execute.
        region_id: Alibaba Cloud region ID, optional in direct mode.
        db_cluster_id: Cluster ID, optional in direct mode.
        database: Target database name (optional).
    """
    async with DBService(region_id, db_cluster_id, database) as svc:
        return await svc.execute_sql(query)


@mcp.tool(group="sql", annotations=READ_ONLY)
async def get_query_plan(
        query: str,
        region_id: Optional[str] = None,
        db_cluster_id: Optional[str] = None,
        database: Optional[str] = None,
) -> str:
    """Get the EXPLAIN logical execution plan of a SQL query.

    Connection modes are the same as execute_sql.

    Args:
        query: The SQL statement to analyze.
        region_id: Alibaba Cloud region ID, optional in direct mode.
        db_cluster_id: Cluster ID, optional in direct mode.
        database: Target database name (optional).
    """
    async with DBService(region_id, db_cluster_id, database) as svc:
        return await svc.execute_sql(f"EXPLAIN {query}")


@mcp.tool(group="sql", annotations=READ_ONLY)
async def get_execution_plan(
        query: str,
        region_id: Optional[str] = None,
        db_cluster_id: Optional[str] = None,
        database: Optional[str] = None,
) -> str:
    """Get the EXPLAIN ANALYZE actual execution plan with runtime statistics.

    Connection modes are the same as execute_sql.

    Args:
        query: The SQL statement to analyze.
        region_id: Alibaba Cloud region ID, optional in direct mode.
        db_cluster_id: Cluster ID, optional in direct mode.
        database: Target database name (optional).
    """
    async with DBService(region_id, db_cluster_id, database) as svc:
        return await svc.execute_sql(f"EXPLAIN ANALYZE {query}")


# =============================================================================
# MCP Resources (group: sql)
# =============================================================================

@mcp.resource("adbmysql:///databases", group="sql", name="All Databases",
              description="List all databases in the ADB MySQL cluster")
async def resource_list_databases() -> str:
    """List all databases, one per line."""
    async with DBService() as svc:
        result = await svc.execute_sql("SHOW DATABASES")
    return extract_first_column_from_json_rows(result)


@mcp.resource("adbmysql:///{database}/tables", group="sql", name="Database Tables",
              description="List all tables in a specific database")
async def resource_list_tables(database: str) -> str:
    """List all tables in the given database, one per line."""
    validate_sql_identifier(database, "database")
    async with DBService() as svc:
        result = await svc.execute_sql(f"SHOW TABLES FROM `{database}`")
    return extract_first_column_from_json_rows(result)


@mcp.resource("adbmysql:///{database}/{table}/ddl", group="sql", name="Table DDL",
              description="Get the DDL of a table in a specific database")
async def resource_table_ddl(database: str, table: str) -> str:
    """Return the CREATE TABLE DDL of the specified table."""
    validate_sql_identifier(database, "database")
    validate_sql_identifier(table, "table")
    async with DBService() as svc:
        result = await svc.execute_sql(f"SHOW CREATE TABLE `{database}`.`{table}`")
    ddl = extract_second_column_from_first_row(result, default="")
    return ddl if ddl else f"No DDL found for {database}.{table}"


@mcp.resource("adbmysql:///config/{key}/value", group="sql", name="Database Config",
              description="Get the value of a config key in the ADB MySQL cluster")
async def resource_config_value(key: str) -> str:
    """Return the value of the specified ADB MySQL config key."""
    validate_sql_identifier(key, "config key")
    async with DBService() as svc:
        result = await svc.execute_sql(f"SHOW adb_config key={key}")
    value = extract_second_column_from_first_row(result, default="")
    return value if value else f"No config value found for {key}"


# =============================================================================
# Server entry point
# =============================================================================

def _parse_groups(source: str | None) -> list[str]:
    """Parse a toolset group string into a deduplicated list of group names.

    Supports GROUP_EXPANSIONS shortcuts (e.g. "all" -> ["openapi", "sql"]).
    Returns DEFAULT_GROUPS when source is None or empty.
    """
    if not source:
        return list(DEFAULT_GROUPS)
    raw = [g.strip() for g in source.split(",") if g.strip()]
    expanded: list[str] = []
    for g in raw:
        if g in GROUP_EXPANSIONS:
            expanded.extend(GROUP_EXPANSIONS[g])
        else:
            expanded.append(g)
    return list(dict.fromkeys(expanded)) or list(DEFAULT_GROUPS)


def main(toolsets: Optional[str] = None) -> None:
    """MCP Server main entry point.

    Flow:
      1. Parse enabled toolset groups (from argument or MCP_TOOLSETS env var).
      2. Call mcp.activate() to register deferred tools/resources into FastMCP.
      3. Start the server using the transport specified by SERVER_TRANSPORT.
    """
    source_string = toolsets or os.getenv("MCP_TOOLSETS")
    enabled_groups = _parse_groups(source_string)
    mcp.activate(enabled_groups=enabled_groups)

    transport = os.getenv("SERVER_TRANSPORT", "stdio")
    if transport in ("sse", "streamable_http"):
        app = mcp.sse_app() if transport == "sse" else mcp.streamable_http_app()
        config = uvicorn.Config(
            app, host="0.0.0.0",
            port=int(os.getenv("SERVER_PORT", 8000)),
            log_level="info",
        )
        server = uvicorn.Server(config)
        anyio.run(server.serve)
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolsets", help="Comma-separated list of toolset groups to enable")
    args = parser.parse_args()
    main(toolsets=args.toolsets)
