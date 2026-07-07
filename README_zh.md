# AnalyticDB for MySQL MCP Server

[English](README.md) | 中文

AnalyticDB for MySQL MCP Server 是 AI Agent 与 [AnalyticDB MySQL](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql) 之间的通用接口。它支持两类工具组：

- **SQL 工具 & 资源**（`sql` 组）：直接连接 ADB MySQL 集群执行 SQL、查看执行计划、浏览数据库元数据。`sql` 组只是工具组开关；其中 `execute_sql` 默认运行在只读模式，完整 SQL 执行模式需要额外显式配置 `ENABLE_SQL_WRITE_TOOLS=true`
- **OpenAPI 工具**（`openapi` 组）：通过阿里云 OpenAPI 管理集群、白名单、账号、网络、监控、诊断、审计等

只读工具标注了 `ToolAnnotations(readOnlyHint=True)`（MCP 协议标准能力），便于客户端区分只读操作和变更操作。

## 一、前置条件

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)（推荐的包管理和运行工具）
- 阿里云 AccessKey（用于 OpenAPI 类工具）
- 可选：ADB MySQL 连接信息（用于 SQL 类工具的直连模式）

## 二、快速开始

### 2.0 配置选择速查

先按使用场景选择工具组和额外开关，再复制对应客户端配置：

| 使用场景 | 工具组 | 额外开关 | 适合场景 |
| --- | --- | --- | --- |
| 只读 SQL 查询、EXPLAIN、元数据浏览 | `sql` | 不需要 | 默认推荐，适合查询、排查和只读分析 |
| 通过 `execute_sql` 开启完整 SQL 执行 | `sql` | `ENABLE_SQL_WRITE_TOOLS=true` | 需要执行 INSERT/UPDATE/DELETE/DDL/多语句等完整 SQL，且信任当前 MCP 客户端 |
| OpenAPI 集群管理工具 + SQL 只读工具 | `openapi,sql` | 阿里云 AK/SK + `ADB_MYSQL_*` 直连配置 | 需要管理集群、账号、白名单、诊断、监控，同时保留 SQL 只读能力 |
| OpenAPI + 完整 SQL 执行 | `openapi,sql` | 阿里云 AK/SK + `ADB_MYSQL_*` 直连配置 + `ENABLE_SQL_WRITE_TOOLS=true` | 同时需要管控能力和完整 SQL 执行能力 |

> `MCP_TOOLSETS=sql` 只是启用 SQL 工具组；完整 SQL 执行不是独立工具组，也没有 `sql_write` 工具组，必须通过 `ENABLE_SQL_WRITE_TOOLS=true` 单独开启。

配置前请确认：

- 直连数据库模式：配置 `ADB_MYSQL_HOST`、`ADB_MYSQL_PORT`、`ADB_MYSQL_USER`、`ADB_MYSQL_PASSWORD`，可选配置 `ADB_MYSQL_DATABASE`。
- 临时账号模式：如果未配置 `ADB_MYSQL_USER` / `ADB_MYSQL_PASSWORD`，但配置了 AK/SK，系统会通过 OpenAPI 创建临时数据库账号；调用 SQL 工具时需要传入 `region_id` 和 `db_cluster_id`。
- 远程 SSE / Streamable HTTP：如果 `SERVER_HOST` 不是本地回环地址，服务端必须配置 `API_KEY`，客户端必须配置 `Authorization: Bearer <API_KEY>`。
- 完整 SQL 执行：只对可信用户和可信 MCP 客户端开启，并建议使用最小权限数据库账号。

### 2.1 使用 [cherry-studio](https://github.com/CherryHQ/cherry-studio)（推荐）

1. 下载并安装 [cherry-studio](https://github.com/CherryHQ/cherry-studio)
2. 参考[文档](https://docs.cherry-ai.com/cherry-studio/download)安装 `uv`，这是 MCP 运行环境所必需的
3. 参考 [MCP 配置文档](https://docs.cherry-ai.com/advanced-basic/mcp/install)进行配置。你可以直接导入以下 JSON 配置。

![cherry-studio 配置示例](assets/cherry-config.png)

**配置 A — 仅 SQL 只读工具（执行只读查询、查看执行计划、浏览元数据）：**

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
        "ADB_MYSQL_DATABASE": "your_database",
        "MCP_TOOLSETS": "sql"
      }
    }
  }
}
```

**配置 B — OpenAPI 工具 + SQL 只读工具：**

> **注意**：OpenAPI 工具包含创建账号、修改白名单、终止查询等变更/管控能力。仅在明确需要管理操作时开启。下面示例同时保留 `sql` 工具组，因此也包含数据库直连配置。

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
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "ADB_MYSQL_HOST": "your_adb_mysql_host",
        "ADB_MYSQL_PORT": "3306",
        "ADB_MYSQL_USER": "your_username",
        "ADB_MYSQL_PASSWORD": "your_password",
        "ADB_MYSQL_DATABASE": "your_database",
        "MCP_TOOLSETS": "openapi,sql"
      }
    }
  }
}
```

如果只希望暴露 OpenAPI 管理工具，不需要 SQL 工具和资源，可将 `MCP_TOOLSETS` 改为 `openapi`，并删除 `ADB_MYSQL_*` 直连数据库配置。

**配置 C — 通过 `execute_sql` 开启完整 SQL 执行：**

> **警告**：设置 `ENABLE_SQL_WRITE_TOOLS=true` 后，`execute_sql` 将暴露完整 SQL 执行能力。服务端只做基础输入校验，不再限制 SQL 类型、注释、分号、多语句、DDL、DML、DCL 或 TCL。仅应对可信用户开启，并建议使用最小权限数据库账号。

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
        "ADB_MYSQL_DATABASE": "your_database",
        "MCP_TOOLSETS": "sql",
        "ENABLE_SQL_WRITE_TOOLS": "true"
      }
    }
  }
}
```

**配置 D — OpenAPI 工具 + 完整 SQL 执行：**

> **警告**：该配置同时开启 OpenAPI 管理能力和 `execute_sql` 完整 SQL 执行能力，仅建议在可信客户端、可信用户和最小权限数据库账号下使用。

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
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "ADB_MYSQL_HOST": "your_adb_mysql_host",
        "ADB_MYSQL_PORT": "3306",
        "ADB_MYSQL_USER": "your_username",
        "ADB_MYSQL_PASSWORD": "your_password",
        "ADB_MYSQL_DATABASE": "your_database",
        "MCP_TOOLSETS": "openapi,sql",
        "ENABLE_SQL_WRITE_TOOLS": "true"
      }
    }
  }
}
```

> 不配置 `MCP_TOOLSETS` 时默认只启用 `sql` 工具组，且 `execute_sql` 默认仍是只读模式。如果未配置 AK/SK，即使显式请求 OpenAPI 工具也会自动禁用。

### 2.2 使用 Claude Code

从 GitHub 下载并同步依赖：

```shell
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server
uv sync
```

将以下配置添加到 Claude Code MCP 配置文件中（项目级：项目根目录下的 `.mcp.json`，或用户级：`~/.claude/settings.json`）：

**stdio 传输模式：**

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
        "MCP_TOOLSETS": "sql",
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

如需 OpenAPI 管理工具，需要增加 `ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`，并在 `MCP_TOOLSETS` 中显式包含 `openapi`。下面示例使用常见配置 `MCP_TOOLSETS=openapi,sql`，因此同时包含数据库直连配置，复制后 SQL 只读工具也可直接使用：

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
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "MCP_TOOLSETS": "openapi,sql",
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

如果只希望暴露 OpenAPI 管理工具，不需要 SQL 工具和资源，可将 `MCP_TOOLSETS` 改为 `openapi`，并删除 `ADB_MYSQL_*` 直连数据库配置。

如需通过 `execute_sql` 开启完整 SQL 执行，保持 `MCP_TOOLSETS=sql` 并设置 `ENABLE_SQL_WRITE_TOOLS=true`。注意，`MCP_TOOLSETS=sql` 或 `MCP_TOOLSETS=all` 本身都不会开启完整 SQL 执行：

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
        "MCP_TOOLSETS": "sql",
        "ENABLE_SQL_WRITE_TOOLS": "true",
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

如果同时需要 OpenAPI 管理和完整 SQL 执行，可以设置 `MCP_TOOLSETS=openapi,sql`，并设置 `ENABLE_SQL_WRITE_TOOLS=true`：

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
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "MCP_TOOLSETS": "openapi,sql",
        "ENABLE_SQL_WRITE_TOOLS": "true",
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

**SSE 传输模式** — 先启动服务端，再配置客户端：

```bash
export MCP_TOOLSETS=sql
export ADB_MYSQL_HOST="your_adb_mysql_host"
export ADB_MYSQL_PORT="3306"
export ADB_MYSQL_USER="your_username"
export ADB_MYSQL_PASSWORD="your_password"
export ADB_MYSQL_DATABASE="your_database"
export SERVER_TRANSPORT=sse
export SERVER_HOST=127.0.0.1
export SERVER_PORT=8000
# 当 SERVER_HOST 不是本地回环地址时必须配置 API_KEY，建议不少于 32 位
# export API_KEY="replace-with-a-random-token-at-least-32-chars"
# 如需启用 OpenAPI 管理工具，增加 AK/SK 并显式包含 openapi：
# export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
# export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
# export MCP_TOOLSETS=openapi,sql
# 如需通过 execute_sql 开启完整 SQL 执行，必须显式设置：
# export ENABLE_SQL_WRITE_TOOLS=true

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

如果服务端监听非本地回环地址，需要在服务端配置 `API_KEY`，并在客户端请求头中携带 `Authorization`。简单说：`API_KEY` 配在服务端环境变量里，`Authorization: Bearer <API_KEY>` 配在客户端请求头里。

```bash
# 服务端配置
export SERVER_TRANSPORT=sse
export SERVER_HOST=0.0.0.0
export API_KEY="replace-with-a-random-token-at-least-32-chars"
uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://your-server-host:8000/sse",
      "headers": {
        "Authorization": "Bearer replace-with-a-random-token-at-least-32-chars"
      }
    }
  }
}
```

**Streamable HTTP 传输模式** — 先启动服务端，再配置客户端：

```bash
export MCP_TOOLSETS=sql
export ADB_MYSQL_HOST="your_adb_mysql_host"
export ADB_MYSQL_PORT="3306"
export ADB_MYSQL_USER="your_username"
export ADB_MYSQL_PASSWORD="your_password"
export ADB_MYSQL_DATABASE="your_database"
export SERVER_TRANSPORT=streamable_http
export SERVER_HOST=127.0.0.1
export SERVER_PORT=8000
# 当 SERVER_HOST 不是本地回环地址时必须配置 API_KEY，建议不少于 32 位
# export API_KEY="replace-with-a-random-token-at-least-32-chars"
# 如需启用 OpenAPI 管理工具，增加 AK/SK 并显式包含 openapi：
# export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
# export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
# export MCP_TOOLSETS=openapi,sql
# 如需通过 execute_sql 开启完整 SQL 执行，必须显式设置：
# export ENABLE_SQL_WRITE_TOOLS=true

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

`streamable_http` 监听非本地回环地址时，也使用同样的服务端 `API_KEY` 和客户端 `Authorization: Bearer <API_KEY>` 请求头配置方式。客户端完整 JSON 配置示例：

```json
{
  "mcpServers": {
    "adb-mysql-mcp-server": {
      "url": "http://your-server-host:8000/mcp",
      "headers": {
        "Authorization": "Bearer replace-with-a-random-token-at-least-32-chars"
      }
    }
  }
}
```

> **说明**：如果未配置 `ADB_MYSQL_USER` / `ADB_MYSQL_PASSWORD` 但配置了 AK/SK，系统会通过 OpenAPI 自动创建临时数据库账号执行 SQL，执行完毕后自动清理。

### 2.3 使用 Cline

设置环境变量并启动 MCP 服务：

```bash
export MCP_TOOLSETS=sql
export ADB_MYSQL_HOST="your_adb_mysql_host"
export ADB_MYSQL_PORT="3306"
export ADB_MYSQL_USER="your_username"
export ADB_MYSQL_PASSWORD="your_password"
export ADB_MYSQL_DATABASE="your_database"
export SERVER_TRANSPORT=sse
export SERVER_HOST=127.0.0.1
export SERVER_PORT=8000
# 如需启用 OpenAPI 管理工具，增加 AK/SK 并显式包含 openapi：
# export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
# export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"
# export MCP_TOOLSETS=openapi,sql

uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

然后配置 Cline 远程服务地址：

```
remote_server = "http://127.0.0.1:8000/sse"
```

### 2.4 启动后验证

服务启动并连接到 MCP 客户端后，可以用下面的只读语句做冒烟验证，不会修改数据库：

```sql
select 1 as ok;
```

```sql
select current_date as today, current_timestamp as now_time;
```

也可以使用 `get_query_plan` 或 `get_execution_plan` 测试查询计划工具：

```sql
select 1 as plan_test;
```

默认只读模式下，下面的多语句应被拒绝，可用于确认单语句保护生效：

```sql
select 1; select 2;
```

如需进一步确认写保护，仅建议在测试库或确认表名后执行下面语句；默认只读模式下它应被拒绝：

```sql
update your_table set id = id where 1 = 0;
```

如果你还没有确定真实表名，不要执行带表名的语句；先使用 `show databases;`、MCP 资源 `adbmysql:///databases` 或 `adbmysql:///{database}/tables` 查看元数据。

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
| `ADB_MYSQL_MAX_SQL_LENGTH` | 否 | 允许的 SQL 语句最大长度，默认 10000，必须是正整数 |
| `ADB_API_CONNECT_TIMEOUT` | 否 | OpenAPI 连接超时（毫秒），默认 10000（10秒） |
| `ADB_API_READ_TIMEOUT` | 否 | OpenAPI 读取超时（毫秒），默认 300000（5分钟） |
| `MCP_TOOLSETS` | 否 | 要启用的工具组，多个用英文逗号分隔。默认：`sql`。支持的工具组：`sql`、`openapi`；快捷值：`all` 等价于 `openapi,sql`。该变量只控制工具组暴露，不控制完整 SQL 执行权限 |
| `SERVER_TRANSPORT` | 否 | 传输协议：`stdio`（默认）、`sse`、`streamable_http` |
| `SERVER_HOST` | 否 | SSE/HTTP 监听地址，默认 `127.0.0.1`；非回环地址必须配置 `API_KEY` |
| `SERVER_PORT` | 否 | SSE/HTTP 服务端口，默认 8000 |
| `API_KEY` | 否 | MCP HTTP 鉴权 token；配置后客户端需发送 `Authorization: Bearer <API_KEY>`；非回环地址必填，建议不少于 32 位 |
| `ENABLE_SQL_WRITE_TOOLS` | 否 | 控制 `execute_sql` 是否开启完整 SQL 执行模式。默认：`false`；必须显式设置为 `true` 才会进入完整 SQL 执行模式；实际可执行范围仍受数据库账号权限、数据库驱动和最大长度限制 |

## 四、工具列表

默认只启用 `sql` 工具组，且 `execute_sql` 只允许只读 SQL。`openapi` 工具组必须在 `MCP_TOOLSETS` 中显式包含 `openapi` 才会开启。`MCP_TOOLSETS` 只决定工具组是否暴露；通过 `execute_sql` 开启完整 SQL 执行必须额外显式配置 `ENABLE_SQL_WRITE_TOOLS=true`。

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
| `execute_sql` | 在 ADB MySQL 集群中执行 SQL。默认只允许只读 SQL；完整 SQL 执行需要 `ENABLE_SQL_WRITE_TOOLS=true` |
| `get_query_plan` | 获取单条 SELECT 或只读 WITH CTE SQL 的 EXPLAIN 执行计划 |
| `get_execution_plan` | 获取单条 SELECT 或只读 WITH CTE SQL 的 EXPLAIN ANALYZE 实际执行计划 |

### 4.6 MCP 资源（组: `sql`）

MCP 资源归属 `sql` 组，是因为这些资源通过数据库 SQL 连接读取元数据，例如 `SHOW DATABASES`、`SHOW TABLES`、`SHOW CREATE TABLE`、`SHOW adb_config`。它们属于只读元数据资源，会跟默认 SQL 只读工具组一起启用。

| 资源 URI | 说明 |
| --- | --- |
| `adbmysql:///databases` | 列出所有数据库 |
| `adbmysql:///{database}/tables` | 列出指定数据库的所有表 |
| `adbmysql:///{database}/{table}/ddl` | 获取指定表的 DDL |
| `adbmysql:///config/{key}/value` | 获取指定配置项的值 |

## 五、安全策略

### 5.1 SQL 只读模式

当 `ENABLE_SQL_WRITE_TOOLS` 未设置为 `true` 时，`execute_sql` 运行在只读模式。服务端会在打开数据库连接前校验 SQL：

- 允许 `SELECT`、`SHOW`、`DESCRIBE`、`DESC`、`EXPLAIN` 和只读 `WITH` CTE 等只读 SQL。
- 允许末尾单个可选分号，并在执行前移除。
- 拒绝多语句 SQL。
- 拒绝字符串或引用标识符外的 SQL 注释。
- 拒绝未闭合字符串或引用标识符。
- 拒绝 `SELECT` 或 `WITH` 语句体中的写关键字，包括嵌套写操作。
- 拒绝 `SELECT ... INTO OUTFILE` 和 `SELECT ... INTO DUMPFILE`。

该模式用于降低 AI 客户端误操作或未授权变更的风险。

### 5.2 完整 SQL 执行模式

> **风险说明**：完整 SQL 执行模式表示 MCP 服务端提供通用 SQL 执行入口。开启后，服务端不再尝试判断 SQL 是否为读或写，也不拦截多语句、注释、DDL、DML、DCL 或 TCL。请仅在可信用户、可信 MCP 客户端和最小权限数据库账号下开启。

当 `ENABLE_SQL_WRITE_TOOLS=true` 时，`execute_sql` 将作为完整 SQL 执行入口。服务端只做基础输入校验：必须是字符串、去除首尾空白后不能为空、不超过 `ADB_MYSQL_MAX_SQL_LENGTH`。

开启后服务端不再限制 SQL 类型、注释、分号、多语句、DDL、DML、DCL 或 TCL，也不做 SQL 语法校验。凡是当前数据库账号权限和数据库驱动允许执行的 SQL，都可能被执行。

`get_query_plan` 和 `get_execution_plan` 不是完整 SQL 执行工具。即使设置了 `ENABLE_SQL_WRITE_TOOLS=true`，它们也始终只允许单条只读 `SELECT` 或只读 `WITH` CTE 语句。

### 5.3 运维建议

- 不要在公网或共享网络上暴露未配置强 `API_KEY` 的 SSE 或 Streamable HTTP 服务。
- 使用高强度随机 API Key，并在可能泄露时及时轮换。
- 只读部署建议使用数据库只读账号。
- 开启完整 SQL 执行时，建议使用最小权限数据库账号。
- OpenAPI 工具仅建议在可信管控场景中开启。

## 六、本地开发

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
  -e ADB_MYSQL_HOST=your_adb_mysql_host \
  -e ADB_MYSQL_PORT=3306 \
  -e ADB_MYSQL_USER=your_username \
  -e ADB_MYSQL_PASSWORD=your_password \
  -e ADB_MYSQL_DATABASE=your_database \
  -e MCP_TOOLSETS=openapi,sql \
  uv --directory /path/to/alibabacloud-adb-mysql-mcp-server run adb-mysql-mcp-server
```

## 七、SKILL

除了上述 MCP Server，本项目还在 `skill/` 目录下提供了一个**独立的** SKILL。该技能可以直接部署到 Claude Code，无需依赖本 MCP Server（是通过该SKILL目录下的`call_adb_api.py`实现对ADBMySQL OpenApi的调用）。

技能覆盖集群信息查询、性能监控、慢查询诊断、SQL Pattern 分析、SQL 执行等场景，并内置了常见诊断场景的引导式工作流。

详细的安装和使用说明请参见 [skill/skill_readme_cn.md](skill/skill_readme_cn.md)。

> **说明**：后续 Skill 的演进将对接我们新版的 Agent，敬请期待。


## License

Apache License 2.0
