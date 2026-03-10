# ADB MYSQL 表主键字段过大诊断

## 1. 功能
检测表主键设计是否合理，识别字段过多或容量过大的合规风险

## 2. 调用方式
```bash
# 默认地域 cn-hangzhou
uv run ./scripts/call_adb_api.py describe_excessive_primary_keys --cluster-id amv-xx

# 指定地域
uv run ./scripts/call_adb_api.py describe_excessive_primary_keys --region cn-shanghai --cluster-id amv-xx
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
| `data.Tables[].TotalSize` | int | 表物理空间大小 (Bytes) |
| `data.Tables[].ColumnCount` | int | 全表总字段数 |
| `data.Tables[].PrimaryKeyCount` | int | 主键包含字段数 |
| `data.Tables[].PrimaryKeyIndexSize` | long | 主键物理空间大小 (Bytes) |

## 5. 数据处理逻辑
1. **通用单位换算**：将 `TotalSize` 和 `PrimaryKeyIndexSize` 原始字节按阶梯换算。逻辑：数值 >= 1024^4 为 TB；>= 1024^3 为 GB；>= 1024^2 为 MB；>= 1024 为 KB。结果保留两位小数。
2. **排序逻辑**：按原始 `PrimaryKeyIndexSize` 数值执行 Desc 降序排列。

## 6. 约束规则（强制执行）
- **条数限制**：表格中最多展示 5 条记录。
- **禁止格式**：严禁使用无序列表、有序列表或纯文本段落展示表详细信息。
- **强制格式**：必须使用下述 Markdown 表格模版。
- **回复结构**：[诊断综述] -> [风险说明] -> [优化建议] -> [Markdown 数据表格]。

## 7. 展示模板
### 诊断报告：表主键字段过大合理性诊断
- **风险说明**：主键过多会增加主键索引存储开销和磁盘锁定风险，还会导致表写入性能下降。
- **优化建议**：建议重新设计并精简主键字段（涉及表重建，需备份）。参考：[CREATE TABLE](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/create-table/)。

| 数据库.表名 | 主键/总字段数 | 表容量 | 主键容量 |
| :--- | :--- | :--- | :--- |
| {SchemaName}.{TableName} | {PrimaryKeyCount} / {ColumnCount} | {通用单位换算后的TotalSize} | {通用单位换算后的PrimaryKeyIndexSize} |