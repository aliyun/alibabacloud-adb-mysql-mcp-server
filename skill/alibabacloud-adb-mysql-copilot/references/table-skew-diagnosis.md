# ADB MYSQL 表数据倾斜诊断

## 1. 功能
用于检测 ADB MySQL 实例是否存在数据倾斜的事实表。数据倾斜会导致资源使用不均衡，影响查询性能，存储节点磁盘使用率倾斜，极易引发集群锁定并产生查询性能毛刺（长尾）

## 2. 调用方式
```bash
# 默认地域 cn-hangzhou
uv run ./scripts/call_adb_api.py describe_inclined_tables --cluster-id amv-xx --table-type FactTable

# 指定地域
uv run ./scripts/call_adb_api.py describe_inclined_tables --region cn-shanghai --cluster-id amv-xx --table-type FactTable
```

## 3. 输入参数
| 参数名 | 类型 | 是否必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `region` | string | 否 | 阿里云区域ID |
| `cluster-id` | string | 是 | **标准 20 位实例 ID**。提取逻辑：识别以 `am-` 或 `amv-` 开头的子串，从前缀起**严格截取前 20 位**，剔除冒号、端口、域名后缀等。样例：`am-xyz1234567890123456:3306` -> `am-xyz1234567890123` |
| `table-type` | string | 是 | 固定传入 "FactTable" |

## 4. 输出字段含义
| 参数路径 | 类型 | 描述 |
| :--- | :--- | :--- |
| `data.TotalCount` | int | 异常表总数 |
| `data.Items.Table[].Schema` | string | 数据库名 |
| `data.Items.Table[].Name` | string | 表名 |
| `data.Items.Table[].Size` | int | 倾斜的Shard数 |
| `data.Items.Table[].TotalSize` | long | 表数据量 (Bytes) |

## 5. 数据处理逻辑
1. **通用单位换算**：将 `TotalSize` 原始字节按阶梯换算。逻辑：数值 >= 1024^4 为 TB；>= 1024^3 为 GB；>= 1024^2 为 MB；>= 1024 为 KB。结果保留两位小数。
2. **排序逻辑**：按原始 `TotalSize` 数值执行 Desc 降序排列。

## 6. 约束规则（强制执行）
- **条数限制**：表格中最多展示 5 条记录。
- **禁止格式**：严禁使用无序列表、有序列表或纯文本段落展示表详细信息。
- **强制格式**：必须使用下述 Markdown 表格模版。
- **回复结构**：[诊断综述] -> [风险说明] -> [优化建议] -> [Markdown 数据表格]。

## 7. 展示模板
### 诊断报告：表数据倾斜诊断
- **风险说明**：数据倾斜会导致资源使用不均衡，影响查询性能，存储节点磁盘使用率倾斜，极易引发集群锁定并产生查询性能毛刺（长尾）。
- **优化建议**：建议调整倾斜表的分布键（涉及表的重建，操作前务必备份相关数据）。参考文档：[选择分布键](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/use-cases/schema-design#section-vqv-1bq-tkb)

| 数据库.表名 | 表数据量 | 倾斜情况 |
| :--- | :--- | :--- |
| {Schema}.{Name} | {通用单位换算后的TotalSize} | 检测有{Size}个Shard存在数据倾斜 |