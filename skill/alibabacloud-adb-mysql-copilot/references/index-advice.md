# ADB MYSQL 空闲索引优化建议

## 1. 功能
用于检测 ADB MySQL 实例是否存在空闲索引优化建议。

## 2. 调用方式
```bash
# 默认地域 cn-hangzhou
uv run ./scripts/call_adb_api.py describe_available_advices --cluster-id amv-xx --advice-type INDEX --page-size 5

# 指定地域
uv run ./scripts/call_adb_api.py describe_available_advices --region cn-shanghai --cluster-id amv-xx --advice-type INDEX --page-size 5
```

## 3. 输入参数
| 参数名 | 类型 | 是否必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `region` | string | 否 | 阿里云区域ID |
| `cluster-id` | string | 是 | **标准 20 位实例 ID**。提取逻辑：识别以 `am-` 或 `amv-` 开头的子串，从前缀起**严格截取前 20 位**，剔除冒号、端口、域名后缀等。样例：`am-xyz1234567890123456:3306` -> `am-xyz1234567890123` |
| `advice-type` | string | 是 | 固定传 "INDEX" |
| `page-size` | int | 否 | 每页条数，固定传 5 |

## 4. 输出字段含义
| 参数路径 | 类型 | 描述 |
| :--- | :--- | :--- |
| `data.TotalCount` | int | 异常表总数 |
| `data.Items[].SchemaName` | string | 数据库名 |
| `data.Items[].TableName` | string | 表名 |
| `data.Items[].SQL` | string | SQL |
| `data.Items[].IndexFields` | string | 索引字段 |
| `data.Items[].Reason` | string | 具体优化建议 |
| `data.Items[].Benefit` | string | 预期优化收益 |

## 5. 数据处理逻辑
暂无

## 6. 约束规则（强制执行）
- **条数限制**：表格中最多展示 5 条记录。
- **禁止格式**：严禁使用无序列表、有序列表或纯文本段落展示表详细信息。
- **强制格式**：必须使用下述 Markdown 表格模版。
- **回复结构**：[诊断综述] -> [风险说明] -> [优化建议] -> [Markdown 数据表格]。

## 7. 展示模板
### 诊断报告：空闲索引优化建议
- **风险说明**：冗余索引占用磁盘空间，增加存储成本，并拖慢数据写入速度。
- **优化建议**：建议前往控制台【空间诊断 > 索引诊断】执行清理建议。参考：[ALTER TABLE](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/alter-table)。

| 数据库.表名 | 索引字段 | SQL | 具体优化建议 | 预期优化收益 |
| :--- | :--- | :--- | :--- | :--- |
| {SchemaName}.{TableName} | {IndexFields} | {SQL} | {Reason} | {Benefit} |