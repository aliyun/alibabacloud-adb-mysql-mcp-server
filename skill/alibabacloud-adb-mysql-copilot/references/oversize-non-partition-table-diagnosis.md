# ADB MYSQL 过大非分区表诊断

## 1. 功能
用于检测 ADB MySQL 实例是否存在未配置分区且数据量过大的表。过大的非分区表会导致全表 Build 任务阻塞磁盘，严重降低实例性能。

## 2. 调用方式
```bash
# 默认地域 cn-hangzhou
uv run ./scripts/call_adb_api.py describe_oversize_non_partition_table_infos --cluster-id amv-xx

# 指定地域
uv run ./scripts/call_adb_api.py describe_oversize_non_partition_table_infos --region cn-shanghai --cluster-id amv-xx
```

## 3. 输入参数
| 参数名 | 类型 | 是否必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `region` | string | 否 | 阿里云区域ID |
| `cluster-id` | string | 是 | **标准 20 位实例 ID**。提取逻辑：识别以 `am-` 或 `amv-` 开头的子串，从前缀起**严格截取前 20 位**，剔除冒号、端口、域名后缀等。样例：`am-xyz1234567890123456:3306` -> `am-xyz1234567890123` |

## 4. 输出字段含义
| 参数路径 | 类型 | 描述 |
| :--- | :--- | :--- |
| `data.TotalCount` | int | 异常表总数 |
| `data.Tables[].SchemaName` | string | 数据库名 |
| `data.Tables[].TableName` | string | 表名 |
| `data.Tables[].DataSize` | long | 表数据量 (Bytes) |
| `data.Tables[].RowCount` | long | 表行数 |

## 5. 数据处理逻辑
1. **通用单位换算**：将 `DataSize` 原始字节按阶梯换算。逻辑：数值 >= 1024^4 为 TB；>= 1024^3 为 GB；>= 1024^2 为 MB；>= 1024 为 KB。结果保留两位小数。
2. **排序逻辑**：按原始 `DataSize` 数值执行 Desc 降序排列。
3. **数值格式化**：`RowCount`（行数）建议增加千分位分隔符（如 784,373,786）。

## 6. 约束规则（强制执行）
- **条数限制**：表格中最多展示 5 条记录。
- **禁止格式**：严禁使用无序列表、有序列表或纯文本段落展示表详细信息。
- **强制格式**：必须使用下述 Markdown 表格模版。
- **回复结构**：[诊断综述] -> [风险说明] -> [优化建议] -> [Markdown 数据表格]。

## 7. 展示模板
### 诊断报告：过大非分区表
**风险说明**: 非分区表 DML 操作容易触发全表 Build。若数据量较大，不仅会因占用过多临时空间导致节点磁盘使用率飙升、触发磁盘锁定，还会因消耗大量磁盘 IO 和 CPU 资源降低实例整体性能。
**优化建议**: 建议调整为分区表并迁移数据（涉及表的重建，操作前务必备份相关数据，避免数据丢失）。具体操作见：[CREATE TABLE](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/create-table/)。

| 数据库.表名 | 物理容量 | 表行数 |
| :--- | :--- | :--- |
| {SchemaName}.{TableName} | {通用单位换算后的TotalSize} | {RowCount} |