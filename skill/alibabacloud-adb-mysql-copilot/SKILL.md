---
name: alibabacloud-adb-mysql-copilot
description: 阿里云 AnalyticDB for MySQL 运维诊断助手。支持集群信息查询、性能监控、慢查询诊断、运行中SQL分析、表级优化建议等。当用户提到 ADB MySQL、AnalyticDB、慢查询、SQL 诊断、集群性能、查询RT、BadSQL、数据库优化、表分析、分区诊断、数据倾斜等话题时，应该使用该 Skill。即使用户没有明确说"使用 Skill"，只要涉及 ADB MySQL 相关的运维、诊断或监控问题，也应主动使用。
metadata: {"clawdbot":{"emoji":"📊","homepage":"https://www.aliyun.com/product/ApsaraDB/ads","requires":{"bins":["uv"],"env":["ALIBABA_CLOUD_ACCESS_KEY_ID","ALIBABA_CLOUD_ACCESS_KEY_SECRET"]},"os":["darwin","linux"]},"moltbot":{"emoji":"📊","homepage":"https://www.aliyun.com/product/ApsaraDB/ads","requires":{"bins":["uv"],"env":["ALIBABA_CLOUD_ACCESS_KEY_ID","ALIBABA_CLOUD_ACCESS_KEY_SECRET"]},"os":["darwin","linux"]}}
---

## 一、Skill 概述

本 Skill 是 **阿里云 AnalyticDB for MySQL (ADB MySQL) 运维诊断助手**，通过调用内置脚本 `scripts/call_adb_api.py` 与 ADB MySQL OpenAPI 交互，获取实时数据并给出诊断建议。

核心能力：
- **集群管理**：查看集群列表、集群详情、存储空间、账号、网络信息
- **性能监控**：查询 CPU、QPS、RT、内存、连接数等性能指标
- **慢查询诊断**：检测 BadSQL、分析 SQL Pattern、定位慢查询根因
- **运行中 SQL 分析**：查看当前正在执行的 SQL，定位长时间未完成的查询
- **空间诊断**：实例空间巡检，涵盖分区合理性诊断、过大非分区表诊断、表数据倾斜诊断、复制表合理性诊断、主键合理性诊断、空闲索引与冷热表优化建议
- **SQL 执行**：直连数据库执行诊断 SQL（需配置数据库连接信息）

## 二、场景路由

根据用户意图，阅读对应的 `references/` 文件获取详细操作指南。

| 用户意图 | 参考文件 | 何时使用 |
|----------|----------|----------|
| 查看实例列表、实例详情、集群配置、存储空间 | `references/cluster-info.md` | 用户想了解有哪些实例、实例规格或磁盘用量时 |
| 查询变慢、RT 升高、集群卡顿、BadSQL、运行中查询、SQL Pattern 分析 | `references/slow-query-diagnosis.md` | 用户反馈性能下降、查询异常、或需要从整体视角分析 SQL 执行分布时 |
| 执行诊断 SQL、查看系统表、Build 状态、冷热分层、查看配置项 | `references/sql-inspection.md` | OpenAPI 工具无法覆盖、需要直接执行 SQL 或查看实例配置时 |
| 执行实例空间诊断、表建模诊断 | `references/table-modeling-diagnosis.md` | 用户想执行指定实例的空间诊断、表建模诊断 |
| 执行过大非分区表诊断 | `references/oversize-non-partition-table-diagnosis.md` | 用户想了解指定实例下有哪些过大的非分区表 |
| 执行表分区合理性诊断 | `references/table-partition-diagnosis.md` | 用户想了解指定实例下有哪些分区字段设计不合理的表 |
| 执行表主键字段合理性诊断 | `references/excessive-primary-key-diagnosis.md` | 用户想了解指定实例下有哪些主键设计不合理的表 |
| 执行表数据倾斜诊断 | `references/table-skew-diagnosis.md` | 用户想了解指定实例下有哪些数据倾斜的表 |
| 执行复制表合理性诊断 | `references/dimension-table-diagnosis.md` | 用户想了解指定实例下有哪些不合理的复制表 |
| 查看空闲索引优化建议 | `references/index-advice.md` | 用户想了解指定实例下有哪些空闲索引优化建议 |
| 查看冷热表优化建议 | `references/tiering-advice.md` | 用户想了解指定实例下有哪些冷热表优化建议 |

**路由规则**：
1. 识别用户意图，从上表中找到匹配的场景
2. 读取对应的 `references/*.md` 文件，按其中的步骤执行
3. 如果用户意图不属于以上场景，直接使用下方"命令参考"中的子命令即可
4. 多个场景可以组合使用——例如先通过集群信息确认目标实例，再通过慢查询诊断定位问题 SQL

## 三、时间参数处理

很多 OpenAPI 接口需要 `--start-time` 和 `--end-time` 参数，格式为 ISO 8601 UTC（如 `2026-03-09T00:00Z`）。

当用户描述相对时间（如"最近 3 小时"、"过去 24 小时"）时，需要先获取当前 UTC 时间，再计算出具体的起止时间：

```bash
# 获取当前 UTC 时间
uv run ./scripts/call_adb_api.py get_current_utc_time
```

返回示例：
```json
{
  "utc_now": "2026-03-09T08:30:00Z",
  "utc_now_short": "2026-03-09T08:30Z"
}
```

拿到 `utc_now_short` 后，根据用户描述的时间范围计算 `--start-time`。例如用户说"最近 3 小时"，当前 UTC 时间是 `2026-03-09T08:30Z`，则：
- `--end-time 2026-03-09T08:30Z`
- `--start-time 2026-03-09T05:30Z`

如果用户没有指定时间范围，各接口默认使用最近 1 小时。

## 四、命令参考

所有命令通过 `scripts/call_adb_api.py` 调用，格式为：

```bash
uv run ./scripts/call_adb_api.py <子命令> [参数]
```

### 4.1 可用子命令

| 命令 | 说明 | 是否需要 `--cluster-id` |
|------|------|:-----------------------:|
| `describe_db_clusters` | 查询地域内 ADB MySQL 集群列表 | 否 |
| `describe_db_cluster_attribute` | 查询集群详细属性 | 是 |
| `describe_db_cluster_performance` | 查询性能指标（CPU、内存、QPS 等） | 是 |
| `describe_db_cluster_space_summary` | 查询存储空间概览 | 是 |
| `describe_diagnosis_records` | 查询 SQL 诊断记录 | 是 |
| `describe_bad_sql_detection` | 检测影响稳定性的 BadSQL | 是 |
| `describe_sql_patterns` | 查询 SQL Pattern 统计 | 是 |
| `describe_table_statistics` | 查询表级统计信息 | 是 |
| `describe_available_advices` | 获取优化建议 | 是 |
| `describe_excessive_primary_keys` | 检测主键过多的表 | 是 |
| `describe_oversize_non_partition_table_infos` | 检测超大未分区表 | 是 |
| `describe_table_partition_diagnose` | 分区表问题诊断 | 是 |
| `describe_inclined_tables` | 检测数据倾斜表 | 是 |
| `execute_sql` | 直连数据库执行 SQL | 否 |
| `get_current_utc_time` | 获取当前 UTC 时间（用于计算时间范围） | 否 |

### 4.2 通用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--region` | 阿里云地域 ID | `cn-hangzhou` |
| `--cluster-id` | ADB MySQL 集群 ID（如 `amv-xxx`） | 必填 |
| `--start-time` | 起始时间，ISO 8601 UTC 格式（如 `2026-03-09T00:00Z`） | 1 小时前 |
| `--end-time` | 结束时间，ISO 8601 UTC 格式（如 `2026-03-09T01:00Z`） | 当前时间 |
| `--query-condition` | SQL 过滤条件（JSON），如 `{"Type":"status","Value":"running"}` | — |
| `--lang` | 语言：`zh` 或 `en` | `zh` |
| `--order` | 排序字段（JSON），如 `[{"Field":"StartTime","Type":"desc"}]` | — |
| `--page-number` | 页码 | `1` |
| `--page-size` | 每页条数 | `30` |

### 4.3 性能指标 Key 参考

使用 `describe_db_cluster_performance` 时通过 `--key` 指定：

| Key | 含义 |
|-----|------|
| `AnalyticDB_CPU` | CPU 使用率 |
| `AnalyticDB_QPS` | 每秒查询数 |
| `AnalyticDB_QueryRT` | 查询响应时间 |
| `AnalyticDB_QueryWaitTime` | 查询排队等待时间 |
| `AnalyticDB_Connections` | 连接数 |
| `AnalyticDB_DiskUsedRatio` | 磁盘使用率 |
| `AnalyticDB_DiskUsedSize` | 磁盘使用量 |
| `AnalyticDB_UnavailableNodeCount` | 不可用节点数 |
| `AnalyticDB_Table_Read_Result_Size` | 数据扫描量 |
| `AnalyticDB_BuildTaskCount` | Build 任务数 |
| `AnalyticDB_InsertRT` | 写入响应时间 |
| `AnalyticDB_InsertTPS` | 写入 TPS |

### 4.4 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ALIBABA_CLOUD_ACCESS_KEY_ID` | 阿里云 AccessKey ID | 必填（OpenAPI） |
| `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret | 必填（OpenAPI） |
| `ALIBABA_CLOUD_SECURITY_TOKEN` | STS 临时安全令牌 | — |
| `ADB_API_CONNECT_TIMEOUT` | API 连接超时（毫秒） | `10000` |
| `ADB_API_READ_TIMEOUT` | API 读取超时（毫秒） | `300000` |
| `ADB_MYSQL_HOST` | 数据库地址（用于 `execute_sql`） | `localhost` |
| `ADB_MYSQL_PORT` | 数据库端口（用于 `execute_sql`） | `3306` |
| `ADB_MYSQL_USER` | 数据库用户名（用于 `execute_sql`） | — |
| `ADB_MYSQL_PASSWORD` | 数据库密码（用于 `execute_sql`） | — |
| `ADB_MYSQL_DATABASE` | 默认数据库名（用于 `execute_sql`） | — |
| `ADB_MYSQL_CONNECT_TIMEOUT` | 数据库连接超时（秒） | `2` |

### 4.5 输出格式

- OpenAPI 命令结果以格式化 JSON 输出到 **stdout**
- 元数据（地域、集群 ID）输出到 **stderr**
- `execute_sql` 查询结果以 JSON 数组格式输出

```
[Region] cn-hangzhou | [Cluster] amv-xxx
{
  "RequestId": "...",
  "Items": [...]
}
```
### 4.6 重要提醒

**ADB MySQL ≠ MySQL**

AnalyticDB for MySQL（ADB MySQL）是阿里云自研的**云原生分析型数据库**，虽然名称中包含 "MySQL" 且兼容 MySQL 协议，但与 MySQL 有本质区别：

| 维度 | ADB MySQL | MySQL |
|------|-----------|-------|
| 定位 | OLAP 分析型数据仓库 | OLTP 事务型数据库 |
| 存储引擎 | 列存（XUANWU / XUANWU_V2） | 行存（InnoDB） |
| 架构 | 分布式 MPP，存算分离 | 单机或主从复制 |
| 扩展方式 | 计算/存储独立弹性扩缩容 | 纵向扩容或分库分表 |
| 数据写入 | 实时写入 + 异步 BUILD 构建索引 | 事务提交即可见 |
| 特有功能 | 资源组、SET ADB_CONFIG、BUILD、冷热分层、全文检索、向量检索、物化视图、Spark 引擎 | — |

回答 ADB MySQL 相关问题时，**切勿用 MySQL 知识替代**，务必参考 ADB MySQL [官方文档](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/)。
