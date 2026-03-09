# AnalyticDB for MySQL MCP Server

[English](README.md) | 中文

AnalyticDB for MySQL MCP Server 是 AI Agent 与 [AnalyticDB MySQL](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql) 之间的通用接口。它支持两大类能力：

- **OpenAPI 工具**（`openapi` 组）：通过阿里云 OpenAPI 管理集群、白名单、账号、网络、监控、诊断、审计等
- **SQL 工具 & 资源**（`sql` 组）：直接连接 ADB MySQL 集群执行 SQL、查看执行计划、浏览数据库元数据

只读工具标注了 `ToolAnnotations(readOnlyHint=True)`（MCP 协议标准能力），便于客户端区分只读操作和变更操作。

## 前置条件

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)（推荐的包管理和运行工具）
- 阿里云 AccessKey（用于 OpenAPI 类工具）
- 可选：ADB MySQL 连接信息（用于 SQL 类工具的直连模式）

## 快速开始

### 方式一：本地源码 + stdio

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server
uv sync
```

在 MCP 客户端配置文件中添加：

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

### 方式二：pip 安装 + stdio

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

### 方式三：SSE 传输模式

通过设置 `SERVER_TRANSPORT=sse` 启动 HTTP SSE 服务：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
export SERVER_TRANSPORT=sse
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

客户端配置 SSE 连接：

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### 方式四：Streamable HTTP 传输模式

通过设置 `SERVER_TRANSPORT=streamable_http` 启动 Streamable HTTP 服务：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
export SERVER_TRANSPORT=streamable_http
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

客户端配置 Streamable HTTP 连接：

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### 方式五：仅 SQL 模式（无需 AK/SK）

如果只需要使用 SQL 工具（执行查询、查看执行计划、浏览数据库元数据），无需 OpenAPI 管理类工具，可以仅配置数据库连接信息，不需要阿里云 AccessKey。

以下示例使用 SSE 传输模式：

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

客户端配置：

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

> 设置 `MCP_TOOLSETS=sql` 仅激活 SQL 工具和 MCP 资源，不加载需要 AK/SK 的 OpenAPI 工具。如需使用其他传输协议（stdio、streamable_http），请参考上述对应方式。

## 环境变量

| 变量名 | 必需 | 说明 |
| --- | --- | --- |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` | 是（OpenAPI 工具） | 阿里云 AccessKey ID |
| `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 是（OpenAPI 工具） | 阿里云 AccessKey Secret |
| `ALIBABA_CLOUD_SECURITY_TOKEN` | 否 | STS 临时安全令牌 |
| `ADB_MYSQL_HOST` | 否 | 数据库主机地址（直连模式） |
| `ADB_MYSQL_PORT` | 否 | 数据库端口，默认 3306（直连模式） |
| `ADB_MYSQL_USER` | 否 | 数据库用户名（直连模式） |
| `ADB_MYSQL_PASSWORD` | 否 | 数据库密码（直连模式） |
| `ADB_MYSQL_DATABASE` | 否 | 默认数据库名（直连模式） |
| `ADB_MYSQL_CONNECT_TIMEOUT` | 否 | 数据库连接超时（秒），默认 2 |
| `ADB_API_CONNECT_TIMEOUT` | 否 | OpenAPI 连接超时（毫秒），默认 10000（10秒） |
| `ADB_API_READ_TIMEOUT` | 否 | OpenAPI 读取超时（毫秒），默认 300000（5分钟） |
| `SERVER_TRANSPORT` | 否 | 传输协议：`stdio`（默认）、`sse`、`streamable_http` |
| `SERVER_PORT` | 否 | SSE/HTTP 服务端口，默认 8000 |
| `MCP_TOOLSETS` | 否 | 启用的工具集，逗号分隔，默认 `openapi,sql`（全部） |

> **SQL 工具连接模式说明**：当配置了 `ADB_MYSQL_USER` 和 `ADB_MYSQL_PASSWORD` 时，SQL 工具使用直连模式。未配置时，自动通过 OpenAPI 创建临时账号执行 SQL，执行完毕后自动清理。

## 工具集分组

工具和资源分为两个组，可通过 `MCP_TOOLSETS` 环境变量控制启用：

| 组名 | 说明 |
| --- | --- |
| `openapi` | 集群管理与诊断（OpenAPI） |
| `sql` | SQL 执行与元数据浏览 |
| `all` | 快捷方式，等同于 `openapi,sql` |

**示例**：仅启用 OpenAPI 工具：

```bash
export MCP_TOOLSETS=openapi
```

仅启用 SQL 工具和资源：

```bash
export MCP_TOOLSETS=sql
```

## 工具列表

### 集群管理（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `describe_db_clusters` | 查询指定地域的 ADB MySQL 集群列表 |
| `describe_db_cluster_attribute` | 查询集群详细属性信息 |
| `describe_cluster_access_whitelist` | 查询集群 IP 白名单 |
| `modify_cluster_access_whitelist` | 修改集群 IP 白名单 |
| `describe_accounts` | 查询集群数据库账号列表 |
| `describe_cluster_net_info` | 查询集群网络信息 |
| `get_current_time` | 获取当前服务器时间 |

### 诊断与监控（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `describe_db_cluster_performance` | 查询集群性能数据（CPU、内存、QPS 等） |
| `describe_db_cluster_health_status` | 查询集群健康状态 |
| `describe_diagnosis_records` | 查询 SQL 诊断汇总记录 |
| `describe_diagnosis_sql_info` | 查询 SQL 执行详情（执行计划、运行时信息） |
| `describe_bad_sql_detection` | 检测影响集群稳定性的 Bad SQL |
| `describe_sql_patterns` | 查询 SQL Pattern 列表 |
| `describe_table_statistics` | 查询表统计信息 |

### 管控与审计（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `create_account` | 创建数据库账号 |
| `modify_db_cluster_description` | 修改集群描述 |
| `describe_db_cluster_space_summary` | 查询集群空间概览 |
| `describe_audit_log_records` | 查询 SQL 审计日志 |

### 高级诊断（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `describe_executor_detection` | 计算节点诊断 |
| `describe_worker_detection` | 存储节点诊断 |
| `describe_controller_detection` | 接入节点诊断 |
| `describe_available_advices` | 查询优化建议 |
| `kill_process` | 终止运行中的查询进程 |
| `describe_db_resource_group` | 查询资源组信息 |
| `describe_excessive_primary_keys` | 检测主键过多的表 |
| `describe_oversize_non_partition_table_infos` | 检测超大未分区表 |
| `describe_table_partition_diagnose` | 分区表问题诊断 |
| `describe_inclined_tables` | 检测数据倾斜表 |

### SQL 工具（组: `sql`）

| 工具名 | 说明 |
| --- | --- |
| `execute_sql` | 在 ADB MySQL 集群中执行 SQL |
| `get_query_plan` | 获取 SQL 的 EXPLAIN 执行计划 |
| `get_execution_plan` | 获取 SQL 的 EXPLAIN ANALYZE 实际执行计划 |

### MCP 资源（组: `sql`）

| 资源 URI | 说明 |
| --- | --- |
| `adbmysql:///databases` | 列出所有数据库 |
| `adbmysql:///{database}/tables` | 列出指定数据库的所有表 |
| `adbmysql:///{database}/{table}/ddl` | 获取指定表的 DDL |
| `adbmysql:///config/{key}/value` | 获取指定配置项的值 |

## 本地开发

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server
uv sync
```

运行测试：

```shell
uv run python -m pytest test/ -v
```

使用 MCP Inspector 调试：

```shell
npx @modelcontextprotocol/inspector \
  -e ALIBABA_CLOUD_ACCESS_KEY_ID=your_ak \
  -e ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_sk \
  uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

## License

Apache License 2.0
