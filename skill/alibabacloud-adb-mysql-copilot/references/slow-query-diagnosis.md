# 慢查询诊断

当用户反馈"查询变慢"、"RT 升高"、"集群卡顿"时，按以下步骤排查。

## 一、查看性能指标趋势

首先确认问题时间段内的关键指标变化：

```bash
# 查询 RT（响应时间）趋势
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_QueryRT

# 查询 QPS 趋势
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_QPS

# 查询排队等待时间
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_QueryWaitTime

# 查询不可用节点数
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_UnavailableNodeCount

# 查询数据扫描量
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_Table_Read_Result_Size
```

**分析要点**：
- RT 升高是否伴随 QPS 突增？→ 可能是并发过高
- RT 升高是否伴随 QueryWaitTime 升高？→ 可能是资源排队导致
- RT 升高是否伴随 UnavailableNodeCount > 0？→ 可能是节点故障
- RT 升高是否伴随 Table_Read_Result_Size 突增？→ 可能是某些查询扫描了过多数据

## 二、检测 BadSQL

排查是否有影响集群稳定性的异常 SQL：

```bash
uv run ./scripts/call_adb_api.py describe_bad_sql_detection --cluster-id amv-xxx
```

**返回值关键字段**：

| 字段                 | 含义                                   |
|--------------------|--------------------------------------|
| `Cost`             | 总耗时（毫秒），包含排队+计划+执行时间                 |
| `PeakMemory`       | 峰值内存（Byte）                           |
| `OperatorCost`     | 算子总 CPU 时间（毫秒）                       |
| `ScanSize`         | 扫描数据量（Byte）                          |
| `OutputDataSize`   | 返回数据量（Byte）                          |
| `ProcessId`        | 查询 ID，可用于进一步诊断                       |
| `PatternId`        | SQLPattern ID，可用于和下面的SQL Pattern分析结合 |
| `SQL`              | SQL 语句（最长 5120 字符）                   |
| `DiagnosisResults` | 自诊断结果，包含具体诊断码和建议                     |

**诊断逻辑**：
- `PeakMemory` 过大 → 建议优化 SQL，减少 JOIN 或限制返回行数
- `OperatorCost` 过高 → 存在计算密集型算子，检查是否有不必要的全表扫描
- `ScanSize` 过大 → 缺少有效过滤条件或索引
- `OutputDataSize` 过大 -> 查询结果数据量过大，建议增加过滤条件或者limit限制返回行数
- 拿到 `ProcessId` 后可以调用 `describe_diagnosis_sql_info`（MCP 工具）查看详细执行计划和诊断建议

## 三、分析运行中的查询

对于仍在执行中、尚未完成的 SQL，需要用 `describe_diagnosis_records` 加 `--query-condition` 过滤：

```bash
# 查看当前运行中的 SQL
uv run ./scripts/call_adb_api.py describe_diagnosis_records \
    --cluster-id amv-xxx \
    --query-condition '{"Type":"status","Value":"running"}'
```

**返回值关键字段**：

| 字段                  | 含义                             |
|---------------------|--------------------------------|
| `ProcessId`         | 查询 ID                          |
| `PatternId`         | SQLPattern ID，可用于和下面的SQL Pattern分析结合 |
| `SQL`               | SQL 语句                         |
| `Cost`              | 总耗时（毫秒）                        |
| `QueueTime`         | 排队等待时间（毫秒）                     |
| `TotalPlanningTime` | 生成执行计划的时间（毫秒）                  |
| `ExecutionTime`     | 执行时间（毫秒）                       |
| `PeakMemory`        | 峰值内存（Byte）                     |
| `ScanSize`          | 扫描数据量（Byte）                    |
| `OutputDataSize`    | 返回数据量（Byte）                    |
| `OutputRows`        | 返回行数                           |
| `EtlWriteRows`      | ETL 任务写入的行数                    |
| `Status`            | 状态：running / finished / failed |
| `ResourceCostRank`  | 算子耗时排名（仅 running 状态有效）         |
| `ResourceGroup`     | 资源组                            |
| `Database`          | 数据库名                           |

**处理建议**：
- 运行中的 SQL 如果 Cost 已经很高且 ResourceCostRank 排名靠前，考虑是否需要 Kill
- 如果需要终止查询，可以使用 MCP 工具 `kill_process` 或 SQL `KILL QUERY <ProcessId>`，但最好是得到用户允许以后，再终止查询

## 四、SQL Pattern 分析

SQL Pattern 是参数归一化后的 SQL 模板（例如 `SELECT * FROM t WHERE id = 1` 和 `SELECT * FROM t WHERE id = 2` 属于同一个 Pattern）。通过 Pattern 汇总，可以从整体视角识别高频或高消耗的查询类型。

```bash
uv run ./scripts/call_adb_api.py describe_sql_patterns --cluster-id amv-xxx
```

**返回值关键字段**：

基础统计：

| 字段 | 含义 |
|------|------|
| `PatternId` | SQL Pattern ID |
| `SQLPattern` | 参数归一化后的 SQL 模板 |
| `Tables` | 涉及的表名 |
| `QueryCount` | 执行次数 |
| `FailedCount` | 失败次数 |
| `AverageQueryTime` | 平均总耗时（毫秒） |
| `MaxQueryTime` | 最大总耗时（毫秒） |
| `AveragePeakMemory` | 平均峰值内存（Byte） |
| `AverageScanSize` | 平均数据扫描量（Byte） |

资源占比（重点关注）——反映单个 Pattern 在集群中的资源消耗占比：

| 字段 | 含义 |
|------|------|
| `QueryTimeSum` / `QueryTimePercentage` | 耗时总量（毫秒） / 占比（%） |
| `PeakMemorySum` / `PeakMemoryPercentage` | 峰值内存总量（Byte） / 占比（%） |
| `ScanSizeSum` / `ScanSizePercentage` | 数据扫描总量（Byte） / 占比（%） |
| `OperatorCostSum` / `OperatorCostPercentage` | CPU Cost 总量（毫秒） / 占比（%） |
| `ScanCostSum` / `ScanCostPercentage` | 表扫描 Cost 总量（Byte） / 占比（%） |

**诊断逻辑**：

重点关注 Percentage 字段超过 **30%** 的 Pattern——说明单个 Pattern 消耗了集群近三分之一的对应资源：

- **`QueryTimePercentage` > 30%**：该 Pattern 占据了大量查询时间，是集群"最耗时的SQL类型"
- **`PeakMemoryPercentage` > 30%**：该 Pattern 消耗了大量内存，高并发时容易引发 OOM
- **`ScanSizePercentage` > 30%**：该 Pattern 扫描了大量数据，可能缺少索引或过滤条件
- **`OperatorCostPercentage` > 30%**：该 Pattern 的 CPU 消耗最大，存在计算密集型算子
- **`ScanCostPercentage` > 30%**：该 Pattern 的表扫描开销最大

综合判断：
- 某个 Pattern 同时在多个 Percentage 上排名靠前 → 集群性能的主要瓶颈
- `QueryCount` 很高 + `QueryTimePercentage` 很高 → 高频且耗时的查询，优化收益最大
- `QueryCount` 低 + `MaxQueryTime` 很高 → 偶发的重查询，可能是特定业务场景导致
- `FailedCount` 较高 → 需要排查失败原因（语法错误、超时、资源不足等）

拿到目标 Pattern 后，可从 `describe_diagnosis_records` 中找到该 Pattern 下的具体慢 SQL 的 `ProcessId`。

---

> **⚠️ 重要提示：ProcessId 和 PatternId 的输出规范**
>
> `ProcessId` 和 `PatternId` 是排查问题的核心标识符，在输出给用户时必须遵循以下规范：
> - **必须完整输出**：不得截断、简写或省略任何部分
> - **必须精确**：不得杜撰或修改，必须与 API 返回值完全一致
> - **原因说明**：用户需要使用这些 ID 进行后续排查（如 `describe_diagnosis_sql_info`、`kill_process` 等），错误的 ID 会导致排查失败