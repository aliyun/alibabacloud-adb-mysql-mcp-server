# ADB MYSQL 表分区合理性诊断

## 1. 功能
用于检测 ADB MySQL 实例是否存在分区设计不合理的表。创建分区表时若分区字段设置不合理，则会导致以下问题：1. 分区过大时（例如：按年做分区，每一年的数据会存储在一个分区内，此时分区数较少，但每个分区内的数据量较大），若该分区存在Build任务，会导致Build任务耗时长，占用较多的资源（存储节点CPU和磁盘IO资源），进而影响集群的稳定性

## 2. 调用方式
```bash
# 默认地域 cn-hangzhou
uv run ./scripts/call_adb_api.py describe_table_partition_diagnose --cluster-id amv-xx --page-size 5

# 指定地域
uv run ./scripts/call_adb_api.py describe_table_partition_diagnose --region cn-shanghai --cluster-id amv-xx --page-size 5
```

## 3. 输入参数
| 参数名 | 类型 | 是否必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `region` | string | 否 | 阿里云区域ID |
| `cluster-id` | string | 是 | **标准 20 位实例 ID**。提取逻辑：识别以 `am-` 或 `amv-` 开头的子串，从前缀起**严格截取前 20 位**，剔除冒号、端口、域名后缀等。样例：`am-xyz1234567890123456:3306` -> `am-xyz1234567890123` |
| `page-size` | int | 否 | 每页条数，固定传 5 |

## 4. 输出字段含义
| 参数路径 | 类型 | 描述 |
| :--- | :--- | :--- |
| `data.TotalCount` | int | 异常表总数 |
| `data.Items[].SchemaName` | string | 数据库名 |
| `data.Items[].TableName` | string | 表名 |
| `data.Items[].TotalSize` | long | 表数据量 (Bytes) |

## 5. 数据处理逻辑
1. **通用单位换算**：将 `TotalSize` 原始字节按阶梯换算。逻辑：数值 >= 1024^4 为 TB；>= 1024^3 为 GB；>= 1024^2 为 MB；>= 1024 为 KB。结果保留两位小数。
2. **排序逻辑**：按原始 `TotalSize` 数值执行 Desc 降序排列。

## 6. 约束规则（强制执行）
- **条数限制**：表格中最多展示 5 条记录。
- **禁止格式**：严禁使用无序列表、有序列表或纯文本段落展示表详细信息。
- **强制格式**：必须使用下述 Markdown 表格模版。
- **回复结构**：[诊断综述] -> [风险说明] -> [优化建议] -> [Markdown 数据表格]。

## 7. 展示模板
### 诊断报告：表分区合理性诊断
- **风险说明**：分区过大会导致 Build 任务耗时长，占用更多存储节点 CPU/IO 资源；分区过小会导致集群缓存大量分区信息，消耗内存并降低查询扫描性能。
- **优化建议**：建议重新设计分区字段或粒度，确保单分区行数在合理范围内。参考：[CREATE TABLE](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/create-table/)。

| 数据库.表名 | 物理容量 |
| :--- | :--- |
| {SchemaName}.{TableName} | {通用单位换算后的TotalSize} |