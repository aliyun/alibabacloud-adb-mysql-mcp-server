# SQL 巡检与配置查看


当 OpenAPI 工具覆盖不到的场景，可以直连数据库执行诊断 SQL 或查看实例配置项。

> **⚠️ 注意事项**
>
> 执行 `execute_sql` 时需要的实例账号密码信息，必须通过环境变量提供：
> - `ADB_MYSQL_HOST` - 实例连接地址
> - `ADB_MYSQL_USER` - 数据库用户名
> - `ADB_MYSQL_PASSWORD` - 数据库密码
> - `ADB_MYSQL_PORT` - 数据库端口
>
> 请勿在命令行中指定 `--host`、`--user`、`--password` 等参数，也不要在执行脚本时自行设置环境变量。环境变量应由用户提供。

## 一、常用诊断 SQL

### 1.1 Build 任务状态

查看后台 Build 任务是否正常，是否有积压：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SELECT * FROM information_schema.KEPLER_META_BUILD_TASK ORDER BY create_time DESC LIMIT 20"
```

### 1.2 冷热数据分层

查询所有表的冷热存储策略：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SELECT * FROM information_schema.table_usage;"
```

查询单个表的冷热存储策略：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SELECT * FROM information_schema.table_usage WHERE table_schema='<schema_name>' AND table_name='<table_name>';"
```

查询所有表的冷热存储策略变更进度：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SELECT * FROM information_schema.storage_policy_modify_progress;"
```

查询单个表的冷热存储策略变更进度：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SELECT * FROM information_schema.storage_policy_modify_progress WHERE table_schema='<schema_name>' AND table_name='<table_name>';"
```

### 1.3 表结构与分布键

查看表的建表语句，了解分布键、分区方式等：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SHOW CREATE TABLE mydb.mytable"
```

### 1.4 当前运行中的查询（数据库侧）

通过数据库的 PROCESSLIST 查看所有正在执行的连接和查询：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SHOW PROCESSLIST"
```

### 1.5 查询实例的配置项

> **注意**：ADB MySQL 的配置项与开源 MySQL 不同，必须使用 `SHOW ADB_CONFIG` 命令查看 ADB MySQL 专属配置项。不要使用 `SHOW VARIABLES` 或 `SHOW GLOBAL VARIABLES`，那些是开源 MySQL 的配置项，对 ADB MySQL 不适用。

查看所有配置项：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "select key,value from information_schema.kepler_meta_configs;"
```

查看某个配置项的值：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SHOW ADB_CONFIG KEY=QUERY_TIMEOUT;"
```

修改某个配置项的值：

```bash
uv run ./scripts/call_adb_api.py execute_sql \
    --query "SET ADB_CONFIG KEY=VALUE"
```

### 1.6 常用 Config 参数

以下参数来自官方文档，通过 `SET ADB_CONFIG KEY=VALUE` 设置，作用于整个集群。

#### 1.6.1 超时与限制

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `QUERY_TIMEOUT` | 查询超时时间（毫秒），超过后查询自动取消 | — |
| `INSERT_SELECT_TIMEOUT` | INSERT/UPDATE/DELETE 语句最大执行时间（毫秒） | 86400000 (24h) |
| `MAX_IN_ITEMS_COUNT` | IN 条件个数限制（3.1.8及以下: 2000, 3.1.9~3.1.10: 4000, 3.2.1+: 20000） | 按版本 |

#### 1.6.2 查询执行模式

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `QUERY_TYPE` | 切换查询执行模式：`interactive` / `batch` | — |

#### 1.6.3 查询队列（Interactive 资源组）

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `XIHE_ENV_QUERY_ETL_MAX_CONCURRENT_SIZE` | LOWEST 队列最大可运行查询数 | 20 |
| `XIHE_ENV_QUERY_ETL_MAX_QUEUED_SIZE` | LOWEST 队列最大可排队查询数 | 200 |
| `XIHE_ENV_QUERY_LOW_PRIORITY_MAX_CONCURRENT_SIZE` | LOW 队列最大可运行查询数 | 20 |
| `XIHE_ENV_QUERY_LOW_PRIORITY_MAX_QUEUED_SIZE` | LOW 队列最大可排队查询数 | 200 |
| `XIHE_ENV_QUERY_NORMAL_MAX_CONCURRENT_SIZE` | NORMAL 队列最大可运行查询数 | 20 |
| `XIHE_ENV_QUERY_NORMAL_MAX_QUEUED_SIZE` | NORMAL 队列最大可排队查询数 | 200 |
| `XIHE_ENV_QUERY_HIGH_MAX_CONCURRENT_SIZE` | HIGH 队列最大可运行查询数 | 40 |
| `XIHE_ENV_QUERY_HIGH_MAX_QUEUED_SIZE` | HIGH 队列最大可排队查询数 | 400 |

#### 1.6.4 XIHE BSP 作业

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `QUERY_PRIORITY` | BSP 作业优先级：HIGH / NORMAL / LOW / LOWEST | NORMAL |
| `ELASTIC_JOB_MAX_ACU` | 单个 BSP 作业最大 ACU 数，范围 [3, Job型资源组最大资源量] | 9 |
| `BATCH_QUERY_TIMEOUT` | BSP 作业超时时间（毫秒） | 7200000 (2h) |

#### 1.6.5 外表导入

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `HIVE_SPLIT_ASYNC_GENERATION_ENABLED` | Hive 生成执行计划时异步提交 Split 任务（3.1.10.1+） | false |
| `SQL_OUTPUT_BATCH_SIZE` | 批量导入数据时的数据条数 | — |
| `ENABLE_ODPS_MULTI_PARTITION_PART_MATCH` | 是否预先遍历 MaxCompute 分区记录数 | — |
| `ASYNC_GET_SPLIT` | MaxCompute 异步 Split 优化（3.1.10.1+） | false |

#### 1.6.6 BUILD 调度

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `RC_CSTORE_BUILD_SCHEDULE_PERIOD` | BUILD 自动调度时间段（0~24 整数，如 `6,8` 表示 6 点到 8 点） | — |
| `RC_BUILD_TASK_PRIORITY_LIST` | 单表/多表 BUILD 调度优先级，`task_priority` 越大越优先 | 0 |
| `RC_ELASTIC_JOB_SCHEDULER_ENABLE` | 弹性导入开关 | — |

#### 1.6.7 REMOTE_CALL 函数

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `XIHE_REMOTE_CALL_SERVER_ENDPOINT` | 函数计算服务内网接入地址 | — |
| `XIHE_REMOTE_CALL_SERVER_AK` | 函数计算服务 AccessKey ID | — |
| `XIHE_REMOTE_CALL_SERVER_SK` | 函数计算服务 AccessKey Secret | — |
| `XIHE_REMOTE_CALL_COMPRESS_ENABLED` | 是否 GZIP 压缩数据传输 | — |
| `XIHE_REMOTE_CALL_MAX_BATCH_SIZE` | 向函数计算服务发送的数据行数 | — |

#### 1.6.8 扫描并发控制

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `SPLIT_FLOW_CONTROL_ENABLED` | 开启扫描并发控制 | true |
| `NODE_LEVEL_SPLIT_FLOW_CONTROL_ENABLED` | 根据节点整体并发额度动态调整 Task 并发 | false |
| `MIN_RUNNING_SPLITS_LIMIT_PER_TASK` | Task 扫描并发额度最小值 | 1 |
| `TARGET_RUNNING_SPLITS_LIMIT_PER_TASK` | Task 扫描并发额度中间值 | 32 |
| `MAX_RUNNING_SPLITS_LIMIT_PER_TASK` | Task 扫描并发额度最大值 | 64 |
| `WORKER_MAX_RUNNING_SOURCE_SPLITS_PER_NODE` | 存储节点扫描并发额度（不建议修改） | 256 |
| `EXECUTOR_MAX_RUNNING_SOURCE_SPLITS_PER_NODE` | 计算节点扫描并发额度（不建议修改） | 256 |

#### 1.6.9 其他

| 参数名 | 含义 | 默认值 |
|--------|------|--------|
| `REPLICATION_SWITCH_TIME_RANGE` | 新旧集群切换时间窗口（如 `23:00, 23:30`） | — |
| `FILTER_NOT_PUSHDOWN_COLUMNS` | 关闭特定字段的过滤条件下推（3.1.4+） | — |
| `VIEW_OUTPUT_NAME_CASE_SENSITIVE` | 逻辑视图大小写敏感 | false |
| `ALLOW_MULTI_QUERIES` | 开启 Multi-Statement（连续执行多个 SQL） | false |
| `BINLOG_ENABLE` | 开启 Binlog（3.2.0.0+ 默认已开启） | — |
| `PAGING_CACHE_SCHEMA` | 分页查询缓存表的数据库 | — |
| `PAGING_CACHE_MAX_TABLE_COUNT` | 缓存表最大个数 | 100 |
| `PAGING_CACHE_EXPIRATION_TIME` | 缓存过期时间（秒） | 600 |
| `PAGING_CACHE_ENABLE` | 全局开关 Paging Cache | true |
| `RC_DDL_ENGINE_REWRITE_XUANWUV2` | 新建表引擎默认使用 XUANWU_V2 | true |

> 完整文档参考：[Config和Hint配置参数](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/user-guide/config-and-hint-configuration-parameters)

## 二、官方文档参考

遇到更复杂的诊断场景时，可以从以下官方文档中查找对应的诊断 SQL：

- **系统内存表**：https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/system-table-parameters
- **Build 相关**：https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/build
- **冷热数据转换**：https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/use-cases/separation-of-hot-and-cold-data-storage
- **Config和Hint配置参数**：https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/user-guide/config-and-hint-configuration-parameters
