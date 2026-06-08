# ADB Smart Analyst Skill 使用示例

本文档提供实际调用场景的完整示例，展示两阶段问数流程（意图锚定 → 确定性执行）以及降级探索模式。

所有命令均通过统一入口 `scripts/adb_analyst.py` 执行，需先设置环境变量：

```bash
export ADB_MYSQL_HOST=<ADB MySQL地址>
export ADB_MYSQL_PORT=3306
export ADB_MYSQL_DATABASE=<默认数据库>
export ADB_MYSQL_USER=<用户名>
export ADB_MYSQL_PASSWORD=<密码>
```

---

## 示例 1：正常路径 — 单视图自决

**场景**：查询去年北京的销售情况

### 第一阶段 — 意图锚定

**Step 1**：提取关键词并搜索语义视图

```bash
uv run scripts/adb_analyst.py search_semantic_views --keywords "北京 销售" --top-k 3
```

**返回结果**：
```json
{
  "success": true,
  "error_message": "",
  "views": [
    {
      "view_schema": "sales_db",
      "view_name": "SALES_ANALYSIS",
      "definition": "name: SALES_ANALYSIS\ndescription: ...\ntables:\n  ...",
      "comment": "销售分析视图",
      "score": 0.91
    },
    {
      "view_schema": "sales_db",
      "view_name": "USER_PURCHASE",
      "definition": "...",
      "comment": "用户购买分析",
      "score": 0.68
    }
  ]
}
```

**Step 2**：问题拆解与语义对象映射

- 目标指标词：「销售情况」
- 过滤条件词：「北京」「去年」

SALES_ANALYSIS 视图映射验证：
- 「销售」→ metrics 中 `total_revenue`（description: "总销售收入"）、`order_count`（description: "订单数量"）✓
- 「北京」→ dimension `city`（description: "订单城市"）✓
- 「去年」→ dimension `order_year`（expr: `YEAR(order_date)`）✓

**决策**：SALES_ANALYSIS 完全覆盖所有关键词，且为唯一高分候选，自决。

> 已选择视图 sales_db.SALES_ANALYSIS（score 0.91）：
>   「北京」→ 维度 city
>   「销售」→ 指标 total_revenue, order_count
>   「去年」→ 维度 order_year = 2025

### 第二阶段 — 确定性执行

**Step 3**：生成并执行语义 SQL

```bash
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, order_year, AGG(total_revenue), AGG(order_count) FROM sales_db.SALES_ANALYSIS WHERE city = '北京' AND order_year = 2025 GROUP BY city, order_year LIMIT 100"
```

**返回结果**：
```json
{
  "success": true,
  "error_message": "",
  "columns": [
    {"name": "city", "type": "VARCHAR"},
    {"name": "order_year", "type": "INT"},
    {"name": "total_revenue", "type": "DECIMAL"},
    {"name": "order_count", "type": "BIGINT"}
  ],
  "rows": [["北京", 2025, 12580000.00, 3842]],
  "row_count": 1,
  "truncated": false,
  "executed_sql": "/*+ enable_semantic=true, rewrite=true */ SELECT city, order_year, AGG(total_revenue), AGG(order_count) FROM sales_db.SALES_ANALYSIS WHERE city = '北京' AND order_year = 2025 GROUP BY city, order_year LIMIT 100",
  "rewrite_info": {
    "rewritten_sql": "SELECT o_city AS city, YEAR(o_orderdate) AS order_year, SUM(o_revenue) AS total_revenue, COUNT(*) AS order_count FROM sales_db.orders WHERE o_city = '北京' AND YEAR(o_orderdate) = 2025 GROUP BY o_city, YEAR(o_orderdate) LIMIT 100"
  }
}
```

**展示结果**：

| 城市 | 年份 | 总收入 | 订单数 |
|------|------|--------|--------|
| 北京 | 2025 | 12,580,000.00 | 3,842 |

---

## 示例 2：歧义路径 — 多视图候选需澄清

**场景**：查询北京的发货情况

### 第一阶段 — 意图锚定

```bash
uv run scripts/adb_analyst.py search_semantic_views --keywords "北京 发货" --top-k 3
```

返回两个覆盖度接近的候选：SALES_ANALYSIS（score=0.85）、LOGISTICS_ANALYSIS（score=0.83）。

两个视图均能完整映射「发货」和「北京」，但口径不同（销售口径 vs 物流口径）。此时展示候选及映射关系让用户选择。

用户选择后触发**澄清-重检循环**：将用户回复融入关键词重新搜索 → 重新映射 → 重新决策 → 确定视图后进入第二阶段。

---

## 示例 3：降级路径 — 数据探索模式

**场景**：语义视图无法满足需求，降级探索物理表

### 第一阶段 — Schema 发现

```bash
uv run scripts/adb_analyst.py list_databases
```

**返回结果**：
```json
{
  "success": true,
  "error_message": "",
  "databases": ["sales_db", "logistics", "analytics"]
}
```

### 第二阶段 — 表发现与规模评估

```bash
# 列出数据库中的所有表
uv run scripts/adb_analyst.py explore_table_metadata --operation list_tables --database logistics

# 查看表统计信息（行数、数据量）
uv run scripts/adb_analyst.py explore_table_metadata --operation table_statistics --database logistics --table shipments
```

### 第三阶段 — 结构分析

```bash
# 查看表的列结构
uv run scripts/adb_analyst.py explore_table_metadata --operation describe_table --database logistics --table shipments

# 查看分区信息
uv run scripts/adb_analyst.py explore_table_metadata --operation partition_info --database logistics --table shipments

# 查看建表 DDL
uv run scripts/adb_analyst.py explore_table_metadata --operation show_create_table --database logistics --table shipments

# 查看索引信息
uv run scripts/adb_analyst.py explore_table_metadata --operation index_info --database logistics --table shipments
```

### 第四阶段 — 安全采样与查询

```bash
# 安全采样（自动检测分区键）
uv run scripts/adb_analyst.py explore_table_metadata --operation safe_sample --database logistics --table shipments --columns shipment_id,ship_date,status --limit 5

# 查看查询执行计划
uv run scripts/adb_analyst.py explore_table_metadata --operation explain --database logistics --table shipments --sql "SELECT COUNT(*) FROM logistics.shipments WHERE ship_date >= '2026-05-01'"

# 执行查询（直连模式，跳过语义改写）
uv run scripts/adb_analyst.py execute_sql --sql "SELECT destination_city, COUNT(*) AS cnt FROM \`logistics\`.\`shipments\` WHERE ship_date >= '2026-05-10' GROUP BY destination_city LIMIT 20" --no-semantic-rewrite
```

---

## 示例 4：语义视图管理

### 获取语义视图定义

```bash
# 获取指定视图的完整定义
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db --view-name SALES_ANALYSIS

# 列出某个 schema 下所有语义视图
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db
```

### 创建语义视图

```bash
# 从 YAML 文件创建语义视图
uv run scripts/adb_analyst.py create_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --yaml-file /tmp/view.yaml

# 使用 OR REPLACE 创建或替换
uv run scripts/adb_analyst.py create_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --yaml-file /tmp/view.yaml --or-replace
```

### 修改语义视图

```bash
# 重命名语义视图
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --operation rename --new-name SHIPPING_ANALYSIS

# 设置注释
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --operation set_comment --comment "Updated logistics view"
```

### 删除语义视图

```bash
uv run scripts/adb_analyst.py drop_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS
```

---

## 示例 5：语义 SQL 语法说明

语义 SQL 使用 `AGG()` 包裹指标字段，由语义引擎映射到实际聚合函数：

```sql
-- 基础语义查询
SELECT city, AGG(total_revenue)
FROM sales_db.SALES_ANALYSIS
WHERE order_year = 2025
GROUP BY city
LIMIT 100

-- 带 HAVING 过滤
SELECT city, AGG(total_revenue), AGG(order_count)
FROM sales_db.SALES_ANALYSIS
GROUP BY city
HAVING AGG(order_count) > 100
ORDER BY AGG(total_revenue) DESC
LIMIT 20

-- 临时指标（对维度或事实使用聚合函数）
SELECT city, COUNT(DISTINCT customer_name), AGG(total_revenue)
FROM sales_db.SALES_ANALYSIS
GROUP BY city
LIMIT 50
```

---

## 示例 6：OpenAPI 方式（SQL 语义功能不可用时）

当 SQL 方式的语义功能不可用时，语义操作通过 aliyun CLI 完成，数据执行仍通过 SQL 连接。

### 搜索语义视图

```bash
aliyun adb search-semantic-views --api-version 2021-12-01 \
  --db-cluster-id am-bp1xxxxxxxx \
  --query-text "北京 销售" \
  --topk 3
```

### 语义 SQL 改写

```bash
aliyun adb generate-sql-by-semantic-sql --api-version 2021-12-01 \
  --db-cluster-id am-bp1xxxxxxxx \
  --sql "SELECT city, AGG(revenue) FROM sales_db.SALES_ANALYSIS GROUP BY city LIMIT 100"
```

### 执行改写后的物理 SQL

```bash
uv run scripts/adb_analyst.py execute_sql --sql "<改写后的物理 SQL>" --no-semantic-rewrite
```

---

## 常见问题

**Q: 搜索语义视图返回空结果或所有 score < 0.5？**
- 尝试换用不同关键词重新搜索
- 经过 3 轮澄清仍无法确定语义视图时，降级到数据探索模式

**Q: 语义 SQL 执行报语法错误？**
- 检查指标是否用 `AGG()` 包裹
- 检查 WHERE 中是否误用了指标字段（WHERE 只能使用维度或事实字段）
- 检查字段名是否与 YAML 定义中的 `name` 一致
- 自动修正重试最多 2 次

**Q: 直连模式查询超时？**
- 先用 `table_statistics` 确认表规模
- 超大表（>1 亿行）添加时间过滤条件（最近 7 天）
- 使用 `explain` 检查执行计划
- 减少维度数量，添加 LIMIT

**Q: 连接报错 `RuntimeError: 'cryptography' package is required`？**
- 执行 `uv pip install cryptography` 安装加密库
- 通常在 MySQL 8.0 默认的 `caching_sha2_password` 认证插件时需要
