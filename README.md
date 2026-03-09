# AnalyticDB for MySQL MCP Server

English | [中文](README_zh.md)

AnalyticDB for MySQL MCP Server is a universal interface between AI Agents and [AnalyticDB MySQL](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql). It provides two categories of capabilities:

- **OpenAPI Tools** (`openapi` group): Manage clusters, whitelists, accounts, networking, monitoring, diagnostics, and audit logs via Alibaba Cloud OpenAPI.
- **SQL Tools & Resources** (`sql` group): Connect directly to ADB MySQL clusters to execute SQL, view execution plans, and browse database metadata.

Read-only tools are annotated with `ToolAnnotations(readOnlyHint=True)` per the MCP protocol, allowing clients to distinguish them from mutating operations.

## Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended package manager and runner)
- Alibaba Cloud AccessKey (required for OpenAPI tools)
- Optional: ADB MySQL connection credentials (for SQL tools in direct-connection mode)

## Quick Start

### Option 1: Local Source + stdio

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server
uv sync
```

Add the following to your MCP client configuration:

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/alibabacloud-adb-mysql-mcp-server",
        "run",
        "adb-mysql-mcp-server"
      ],
      "env": {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "your_access_key_id",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret"
      }
    }
  }
}
```

### Option 2: pip Install + stdio

```bash
pip install adb-mysql-mcp-server
```

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "adb-mysql-mcp-server",
        "adb-mysql-mcp-server"
      ],
      "env": {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "your_access_key_id",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret"
      }
    }
  }
}
```

### Option 3: SSE Transport

Start the HTTP SSE server by setting `SERVER_TRANSPORT=sse`:

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
export SERVER_TRANSPORT=sse
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

Client SSE configuration:

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### Option 4: Streamable HTTP Transport

Start the Streamable HTTP server by setting `SERVER_TRANSPORT=streamable_http`:

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
export SERVER_TRANSPORT=streamable_http
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

Client Streamable HTTP configuration:

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Option 5: SQL-Only Mode (No AK/SK Required)

If you only need SQL tools (execute queries, view execution plans, browse database metadata) without OpenAPI management tools, you can configure the server with database credentials only — no Alibaba Cloud AccessKey is needed.

The following example uses SSE transport:

```bash
export ADB_MYSQL_HOST="your_adb_mysql_host"
export ADB_MYSQL_PORT="3306"
export ADB_MYSQL_USER="your_username"
export ADB_MYSQL_PASSWORD="your_password"
export ADB_MYSQL_DATABASE="your_database"
export MCP_TOOLSETS=sql
export SERVER_TRANSPORT=sse
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

Client configuration:

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

> Set `MCP_TOOLSETS=sql` to activate only the SQL tools and MCP resources. OpenAPI tools that require AK/SK will not be loaded. For other transport modes (stdio, streamable_http), refer to the corresponding options above.

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` | Yes (OpenAPI tools) | Alibaba Cloud AccessKey ID |
| `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | Yes (OpenAPI tools) | Alibaba Cloud AccessKey Secret |
| `ALIBABA_CLOUD_SECURITY_TOKEN` | No | STS temporary security token |
| `ADB_MYSQL_HOST` | No | Database host (direct-connection mode) |
| `ADB_MYSQL_PORT` | No | Database port, default 3306 (direct-connection mode) |
| `ADB_MYSQL_USER` | No | Database username (direct-connection mode) |
| `ADB_MYSQL_PASSWORD` | No | Database password (direct-connection mode) |
| `ADB_MYSQL_DATABASE` | No | Default database name (direct-connection mode) |
| `ADB_MYSQL_CONNECT_TIMEOUT` | No | Database connection timeout in seconds, default 2 |
| `ADB_API_CONNECT_TIMEOUT` | No | OpenAPI connection timeout in milliseconds, default 10000 (10s) |
| `ADB_API_READ_TIMEOUT` | No | OpenAPI read timeout in milliseconds, default 300000 (5min) |
| `SERVER_TRANSPORT` | No | Transport protocol: `stdio` (default), `sse`, `streamable_http` |
| `SERVER_PORT` | No | SSE/HTTP server port, default 8000 |
| `MCP_TOOLSETS` | No | Enabled toolset groups, comma-separated, default `openapi,sql` (all) |

> **SQL tool connection modes**: When `ADB_MYSQL_USER` and `ADB_MYSQL_PASSWORD` are configured, SQL tools connect directly using the provided credentials. When not configured, a temporary database account is automatically created via OpenAPI, used for SQL execution, and cleaned up afterward.

## Toolset Grouping

Tools and resources are organized into groups, controlled via the `MCP_TOOLSETS` environment variable:

| Group | Description |
| --- | --- |
| `openapi` | Cluster management & diagnostics (OpenAPI) |
| `sql` | SQL execution & metadata browsing |
| `all` | Shortcut, equivalent to `openapi,sql` |

**Example**: Enable only OpenAPI tools:

```bash
export MCP_TOOLSETS=openapi
```

Enable only SQL tools and resources:

```bash
export MCP_TOOLSETS=sql
```

## Tool List

### Cluster Management (group: `openapi`)

| Tool | Description |
| --- | --- |
| `describe_db_clusters` | List ADB MySQL clusters in a region |
| `describe_db_cluster_attribute` | Get detailed cluster attributes |
| `describe_cluster_access_whitelist` | Get cluster IP whitelist |
| `modify_cluster_access_whitelist` | Modify cluster IP whitelist |
| `describe_accounts` | List database accounts in a cluster |
| `describe_cluster_net_info` | Get cluster network connection info |
| `get_current_time` | Get current server time |

### Diagnostics & Monitoring (group: `openapi`)

| Tool | Description |
| --- | --- |
| `describe_db_cluster_performance` | Query cluster performance metrics (CPU, memory, QPS, etc.) |
| `describe_db_cluster_health_status` | Query cluster health status |
| `describe_diagnosis_records` | Query SQL diagnosis summary records |
| `describe_diagnosis_sql_info` | Get SQL execution details (plan, runtime info) |
| `describe_bad_sql_detection` | Detect bad SQL impacting cluster stability |
| `describe_sql_patterns` | Query SQL pattern list |
| `describe_table_statistics` | Query table-level statistics |

### Administration & Audit (group: `openapi`)

| Tool | Description |
| --- | --- |
| `create_account` | Create a database account |
| `modify_db_cluster_description` | Modify cluster description |
| `describe_db_cluster_space_summary` | Get cluster storage space summary |
| `describe_audit_log_records` | Query SQL audit log records |

### Advanced Diagnostics (group: `openapi`)

| Tool | Description |
| --- | --- |
| `describe_executor_detection` | Compute node diagnostics |
| `describe_worker_detection` | Storage node diagnostics |
| `describe_controller_detection` | Access node diagnostics |
| `describe_available_advices` | Get optimization advices |
| `kill_process` | Kill a running query process |
| `describe_db_resource_group` | Get resource group configuration |
| `describe_excessive_primary_keys` | Detect tables with excessive primary keys |
| `describe_oversize_non_partition_table_infos` | Detect oversized non-partition tables |
| `describe_table_partition_diagnose` | Diagnose table partitioning issues |
| `describe_inclined_tables` | Detect data-skewed tables |

### SQL Tools (group: `sql`)

| Tool | Description |
| --- | --- |
| `execute_sql` | Execute SQL on an ADB MySQL cluster |
| `get_query_plan` | Get EXPLAIN execution plan |
| `get_execution_plan` | Get EXPLAIN ANALYZE actual execution plan |

### MCP Resources (group: `sql`)

| Resource URI | Description |
| --- | --- |
| `adbmysql:///databases` | List all databases |
| `adbmysql:///{database}/tables` | List all tables in a database |
| `adbmysql:///{database}/{table}/ddl` | Get table DDL |
| `adbmysql:///config/{key}/value` | Get a config key value |

## Local Development

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server
uv sync
```

Run tests:

```shell
uv run python -m pytest test/ -v
```

Debug with MCP Inspector:

```shell
npx @modelcontextprotocol/inspector \
  -e ALIBABA_CLOUD_ACCESS_KEY_ID=your_ak \
  -e ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_sk \
  uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

## License

Apache License 2.0
