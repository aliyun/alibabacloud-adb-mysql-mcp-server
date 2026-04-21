# ADB Smart Analyst Skill 使用示例

本文档提供实际调用场景的完整示例，展示 Step 1 → Step 2 → Step 3 三阶段问数流程。

所有命令均通过统一入口 `scripts/adb_smart_analyst.py` 执行，需先设置环境变量：

```bash
export ADB_MYSQL_HOST=<host>
export ADB_MYSQL_USER=<user>
export ADB_MYSQL_PASSWORD=<password>
export ADB_MYSQL_PORT=3306
```

---

## 示例 1：简单指标查询（Step 1 单阶段）

**场景**：查询"毛利率"的语义定义

```bash
uv run scripts/adb_smart_analyst.py search_metrics_rag "毛利率" --attempt 1
```

**返回结果**：
```json
{
  "status": "success",
  "count": 1,
  "data": [
    {
      "view_schema": "schema_name",
      "view_name": "gross_profit_margin",
      "definition": "name: gross_profit_margin\ndescription: 毛利率，毛利额占销售收入的比例\nbase_tables:\n  - schema: sales_db\n    table: finance_fact\nmeasures:\n  - name: gross_profit_rate\n    expression: \"SUM(f_revenue - f_cost) / SUM(f_revenue) * 100\"\ndimensions:\n  - name: channel_id\n    column: channel_id\n    table: finance_fact\n  - name: dt\n    column: dt\n    table: finance_fact\nrelationships:\n  - \"order_status = 'completed'\""
    }
  ]
}
```

> `definition` 字段是原始 YAML 字符串，包含 `base_tables`（物理表）、`measures`（计算公式）、`dimensions`（可用维度）、`relationships`（关联/过滤条件）。

---

## 示例 2：完整三阶段问数流程

**场景**：查询各渠道上月销售额与毛利

### Step 1：语义检索

```bash
uv run scripts/adb_smart_analyst.py search_metrics_rag "销售额 毛利" --attempt 1
```

**从返回的 YAML 中提取关键信息**：
- `base_tables`：`sales_db.finance_fact`、`sales_db.dim_channel`
- `measures`：`SUM(f_revenue)`、`SUM(f_revenue - f_cost)`
- `dimensions`：`channel_id`、`dt`

### Step 2：物理对齐（用 base_tables 中的物理表，非语义视图名）

```bash
uv run scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"schema":"sales_db","table":"finance_fact"},{"schema":"sales_db","table":"dim_channel"}]' \
  --attempt 1
```

**确认字段存在**：`f_revenue`、`f_cost`、`channel_id`、`channel_name` 均存在。

### Step 3：SQL 执行

```bash
uv run scripts/adb_smart_analyst.py execute_adb_sql \
  "SELECT c.channel_name, SUM(f.f_revenue) AS revenue, SUM(f.f_revenue - f.f_cost) AS gross_profit FROM sales_db.finance_fact f JOIN sales_db.dim_channel c ON f.channel_id = c.channel_id WHERE DATE_FORMAT(f.dt, '%Y-%m') = DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 1 MONTH), '%Y-%m') GROUP BY c.channel_name ORDER BY revenue DESC" \
  --attempt 1
```

---

## 示例 3：3x3 自愈机制演示

### Step 1 阶段：关键词重试

```bash
# 第 1 次：原始关键词
uv run scripts/adb_smart_analyst.py search_metrics_rag "利润率" --attempt 1
# 返回空 → 更换关键词

# 第 2 次：拆分关键词
uv run scripts/adb_smart_analyst.py search_metrics_rag "毛利" --attempt 2
# 返回空 → 再次更换

# 第 3 次：同义词，同时触发全量兜底（attempt=3 时自动返回所有语义视图）
uv run scripts/adb_smart_analyst.py search_metrics_rag "收益" --attempt 3
# 不管是否匹配，全量返回所有记录，Agent 从中筛选

# attempt 超出上限时返回错误
uv run scripts/adb_smart_analyst.py search_metrics_rag "xxx" --attempt 4
# 返回：{"status": "error", "error_type": "L1_MAX_ATTEMPTS_EXCEEDED"}
```

### Step 2 阶段：字段不存在，回溯 Step 1

```bash
# Step 1 找到 YAML，expression 中用了 f_profit 字段
uv run scripts/adb_smart_analyst.py search_metrics_rag "利润" --attempt 1

# Step 2 校验：发现 finance_fact 没有 f_profit 列
uv run scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"schema":"sales_db","table":"finance_fact"}]' --attempt 1
# 字段不匹配 → 回溯 Step 1，更换关键词重新搜索

# Step 1 第 2 次：换关键词带字段提示
uv run scripts/adb_smart_analyst.py search_metrics_rag "利润 f_revenue f_cost" --attempt 2
```

### Step 3 阶段：SQL 报错，修正重试

```bash
# 第 1 次：字段名拼写错误
uv run scripts/adb_smart_analyst.py execute_adb_sql \
  "SELECT revenue FROM sales_db.finance_fact" --attempt 1
# 返回：Error 1054 Unknown column 'revenue'

# 第 2 次：参考 YAML measures 中的 expression 修正字段名
uv run scripts/adb_smart_analyst.py execute_adb_sql \
  "SELECT f_revenue FROM sales_db.finance_fact LIMIT 10" --attempt 2
# 成功
```

---

## 示例 4：Python API 直接调用

```python
import json
import sys
sys.path.insert(0, "scripts")
from adb_smart_analyst import ADBSmartAnalystSkill

skill = ADBSmartAnalystSkill()

# [Step 1] 语义检索，attempt 由调用方递增传入
result_l1 = json.loads(skill.search_metrics_rag("毛利率", attempt=1))

# 从 YAML definition 中提取 base_tables
import yaml
definition = yaml.safe_load(result_l1["data"][0]["definition"])
tables = definition.get("base_tables", [])

# [Step 2] 物理对齐，传入从 YAML 提取的物理表
result_l2 = json.loads(skill.get_batch_table_metadata(tables, attempt=1))

# [Step 3] SQL 执行
sql = "SELECT SUM(f_revenue - f_cost) AS gross_profit FROM sales_db.finance_fact WHERE dt >= '2025-01-01'"
result_l3 = json.loads(skill.execute_adb_sql(sql, attempt=1))
print(result_l3)
```

---

## get_batch_table_metadata 两种传参格式

```bash
# 格式 1（推荐）：JSON 数组，支持指定 schema
uv run scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"schema":"sales_db","table":"finance_fact"},{"schema":"sales_db","table":"dim_channel"}]'

---

## 最佳实践

1. **Step 1 检索**：用原子词（"毛利"而非"毛利率增长情况"），最多重试 3 次，第 3 次触发全量兜底
2. **Step 2 对齐**：从 YAML `base_tables` 提取物理表，**不要用语义视图名**
3. **SQL 生成**：用 YAML `measures.expression` 作为 SELECT 子句，用 `dimensions` 作为 GROUP BY 候选
4. **Step 3 修正**：报错后参考 YAML 中已验证的字段名和表结构重新生成 SQL
5. **--attempt 传参**：每次调用时由 Agent 递增传入，脚本本身无状态

---

## 语义视图管理示例

### 创建语义视图

```bash
# 创建新的语义视图
SKILL_DIR="$(find ~ -maxdepth 3 -name 'alibabacloud-adb-smart-analyst' -type d 2>/dev/null | grep -m1 alibabacloud-adb-smart-analyst)"
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py create_semantic_view "tpch.my_sales_view" "name: my_sales_view\ntables:\n  - name: orders\n    base_table:\n      schema: sales_db\n      table: orders\n    metrics:\n      - name: revenue\n        expr: SUM(amount)"
```

### 删除语义视图（通过 execute_adb_sql）

```bash
# 删除语义视图
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql "DROP SEMANTIC VIEW tpch.my_sales_view"

# 使用 IF EXISTS 避免报错
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql "DROP SEMANTIC VIEW IF EXISTS tpch.my_sales_view"
```

### 重命名语义视图（通过 execute_adb_sql）

```bash
# 重命名语义视图
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql "ALTER SEMANTIC VIEW tpch.old_view RENAME TO tpch.new_view"

# 使用 IF EXISTS 避免报错
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql "ALTER SEMANTIC VIEW IF EXISTS old_view RENAME TO new_view"
```

---

## 常见问题

**Q: Step 1 搜索 3 次都失败？**
- 第 3 次会自动全量返回所有语义视图，Agent 从中找最接近的；若仍无匹配，告知用户"指标库未覆盖该指标"

**Q: Step 2 一直发现字段不匹配？**
- 检查语义视图定义是否过时，可直接查询 `information_schema.semantic_views` 核实

**Q: Step 3 报错如何参考语义定义修正？**
- 查看 YAML `measures.expression` 中的字段名，Step 2 返回的实际列名，两者对照确认拼写

**Q: Decimal 类型报 JSON 序列化错误？**
- 已修复：脚本内置 `_DBJsonEncoder`，自动将 `Decimal` 转为字符串，`datetime`/`date` 格式化为标准字符串
