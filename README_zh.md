# AnalyticDB for MySQL MCP Server

[English](README.md) | 中文

AnalyticDB for MySQL MCP Server 是 AI Agent 与 [AnalyticDB MySQL](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql) 之间的通用接口。它支持两大类能力：

- **OpenAPI 工具**（`openapi` 组）：通过阿里云 OpenAPI 管理集群、白名单、账号、网络、监控、诊断、审计等
- **SQL 工具 & 资源**（`sql` 组）：直接连接 ADB MySQL 集群执行 SQL、查看执行计划、浏览数据库元数据

只读工具标注了 `ToolAnnotations(readOnlyHint=True)`（MCP 协议标准能力），便于客户端区分只读操作和变更操作。

## 一、前置条件

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)（推荐的包管理和运行工具）
- 阿里云 AccessKey（用于 OpenAPI 类工具）
- 可选：ADB MySQL 连接信息（用于 SQL 类工具的直连模式）

## 二、快速开始

### 2.1 使用 [cherry-studio](https://github.com/CherryHQ/cherry-studio)（推荐）

1. 下载并安装 [cherry-studio](https://github.com/CherryHQ/cherry-studio)
2. 参考[文档](https://docs.cherry-ai.com/cherry-studio/download)安装 `uv`，这是 MCP 运行环境所必需的
3. 参考 [MCP 配置文档](https://docs.cherry-ai.com/advanced-basic/mcp/install)进行配置。你可以直接导入以下 JSON 配置。

![cherry-studio 配置示例](assets/cherry-config.png)

**配置 A — 仅 SQL 工具（执行查询、查看执行计划、浏览元数据）：**

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "name": "adb-mysql-mcp-server",
      "type": "stdio",
      "isActive": true,
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/alibabacloud-adb-mysql-mcp-server",
        "run",
        "adb-mysql-mcp-server"
      ],
      "env": {
        "ADB_MYSQL_HOST": "your_adb_mysql_host",
        "ADB_MYSQL_PORT": "3306",
        "ADB_MYSQL_USER": "your_username",
        "ADB_MYSQL_PASSWORD": "your_password",
        "ADB_MYSQL_DATABASE": "your_database"
      }
    }
  }
}
```

**配置 B — OpenAPI 工具（集群管理、诊断、监控）：

> **注意**： 请将`ALIBABA_CLOUD_ACCESS_KEY_ID`和`ALIBABA_CLOUD_ACCESS_KEY_SECRET`配置成阿里云AKSK。

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "name": "adb-mysql-mcp-server",
      "type": "stdio",
      "isActive": true,
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

> 你也可以同时设置所有环境变量来启用 OpenAPI 工具和 SQL 工具。如果未配置 AK/SK，OpenAPI 工具会自动禁用，仅保留 SQL 工具。

### 2.2 使用 Claude Code

从 GitHub 下载并同步依赖：

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server
uv sync
```

将以下配置添加到 Claude Code MCP 配置文件中（项目级：项目根目录下的 `.mcp.json`，或用户级：`~/.claude/settings.json`）：

**stdio 传输模式：**

```json5
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
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "ALIBABA_CLOUD_SECURITY_TOKEN": "",
        // 如需连接具体实例执行 SQL，取消以下注释：
        // "ADB_MYSQL_HOST": "your_adb_mysql_host",
        // "ADB_MYSQL_PORT": "3306",
        // "ADB_MYSQL_USER": "your_username",
        // "ADB_MYSQL_PASSWORD": "your_password",
        // "ADB_MYSQL_DATABASE": "your_database"
      }
    }
  }
}
```

**SSE 传输模式** — 先启动服务端，再配置客户端：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
# 如需连接具体实例执行 SQL，取消以下注释：
# export ADB_MYSQL_HOST="your_adb_mysql_host"
# export ADB_MYSQL_PORT="3306"
# export ADB_MYSQL_USER="your_username"
# export ADB_MYSQL_PASSWORD="your_password"
# export ADB_MYSQL_DATABASE="your_database"
export SERVER_TRANSPORT=sse
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

**Streamable HTTP 传输模式** — 先启动服务端，再配置客户端：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
# 如需连接具体实例执行 SQL，取消以下注释：
# export ADB_MYSQL_HOST="your_adb_mysql_host"
# export ADB_MYSQL_PORT="3306"
# export ADB_MYSQL_USER="your_username"
# export ADB_MYSQL_PASSWORD="your_password"
# export ADB_MYSQL_DATABASE="your_database"
export SERVER_TRANSPORT=streamable_http
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

> **说明**：如果未配置 `ADB_MYSQL_USER` / `ADB_MYSQL_PASSWORD` 但配置了 AK/SK，系统会通过 OpenAPI 自动创建临时数据库账号执行 SQL，执行完毕后自动清理。

### 2.3 使用 Cline

设置环境变量并启动 MCP 服务：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
export SERVER_TRANSPORT=sse
export SERVER_PORT=8000

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

然后配置 Cline 远程服务地址：

```
remote_server = "http://127.0.0.1:8000/sse"
```

## 三、环境变量

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

## 四、工具列表

### 4.1 集群管理（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `describe_db_clusters` | 查询指定地域的 ADB MySQL 集群列表 |
| `describe_db_cluster_attribute` | 查询集群详细属性信息 |
| `describe_cluster_access_whitelist` | 查询集群 IP 白名单 |
| `modify_cluster_access_whitelist` | 修改集群 IP 白名单 |
| `describe_accounts` | 查询集群数据库账号列表 |
| `describe_cluster_net_info` | 查询集群网络信息 |
| `get_current_time` | 获取当前服务器时间 |

### 4.2 诊断与监控（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `describe_db_cluster_performance` | 查询集群性能数据（CPU、内存、QPS 等） |
| `describe_db_cluster_health_status` | 查询集群健康状态 |
| `describe_diagnosis_records` | 查询 SQL 诊断汇总记录 |
| `describe_diagnosis_sql_info` | 查询 SQL 执行详情（执行计划、运行时信息） |
| `describe_bad_sql_detection` | 检测影响集群稳定性的 Bad SQL |
| `describe_sql_patterns` | 查询 SQL Pattern 列表 |
| `describe_table_statistics` | 查询表统计信息 |

### 4.3 管控与审计（组: `openapi`）

| 工具名 | 说明 |
| --- | --- |
| `create_account` | 创建数据库账号 |
| `modify_db_cluster_description` | 修改集群描述 |
| `describe_db_cluster_space_summary` | 查询集群空间概览 |
| `describe_audit_log_records` | 查询 SQL 审计日志 |

### 4.4 高级诊断（组: `openapi`）

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

### 4.5 SQL 工具（组: `sql`）

| 工具名 | 说明 |
| --- | --- |
| `execute_sql` | 在 ADB MySQL 集群中执行 SQL |
| `get_query_plan` | 获取 SQL 的 EXPLAIN 执行计划 |
| `get_execution_plan` | 获取 SQL 的 EXPLAIN ANALYZE 实际执行计划 |

### 4.6 MCP 资源（组: `sql`）

| 资源 URI | 说明 |
| --- | --- |
| `adbmysql:///databases` | 列出所有数据库 |
| `adbmysql:///{database}/tables` | 列出指定数据库的所有表 |
| `adbmysql:///{database}/{table}/ddl` | 获取指定表的 DDL |
| `adbmysql:///config/{key}/value` | 获取指定配置项的值 |

## 五、本地开发

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
## 六、SKILL

除了上述 MCP Server，本项目还在 `skill/` 目录下提供了一个**独立的** SKILL。该技能可以直接部署到 Claude Code，无需依赖本 MCP Server（是通过该SKILL目录下的`call_adb_api.py`实现对ADBMySQL OpenApi的调用）。

技能覆盖集群信息查询、性能监控、慢查询诊断、SQL Pattern 分析、SQL 执行等场景，并内置了常见诊断场景的引导式工作流。

详细的安装和使用说明请参见 [skill/skill_readme_cn.md](skill/skill_readme_cn.md)。

> **说明**：后续 Skill 的演进将对接我们新版的 Agent，敬请期待。


## License

Apache License 2.0
