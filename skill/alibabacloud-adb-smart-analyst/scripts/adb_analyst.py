#!/usr/bin/env python3
"""ADB MySQL 智能分析助手 - 面向 AI 智能体的语义层交互工具。

用法:
    python3 adb_analyst.py <command> [options]

命令:
    search_semantic_views   向量相似度搜索语义视图
    get_semantic_view       查询语义视图定义
    execute_sql             执行 SQL（语义模式或直连模式）
    create_semantic_view    创建或替换语义视图
    alter_semantic_view     重命名或设置语义视图注释
    drop_semantic_view      删除语义视图
    list_databases          列出可访问的数据库
    explore_table_metadata  探索表结构、统计信息和样本数据

环境变量:
    ADB_MYSQL_HOST       ADB MySQL Proxy 主机地址（必填）
    ADB_MYSQL_PORT       ADB MySQL Proxy 端口（默认: 3306）
    ADB_MYSQL_DATABASE   默认数据库（选填）
    ADB_MYSQL_USER       数据库用户名（必填）
    ADB_MYSQL_PASSWORD   数据库密码（必填）
"""

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from decimal import Decimal
from datetime import date, datetime

SEMANTIC_HINT = "/*+ enable_semantic=true */"
SEMANTIC_REWRITE_HINT = "/*+ enable_semantic=true, rewrite=true */"

SYSTEM_DATABASES = frozenset([
    "information_schema", "mysql", "performance_schema", "sys",
    "__recyclebin__", "INFORMATION_SCHEMA", "MYSQL",
    "PERFORMANCE_SCHEMA", "SYS",
])

DDL_DML_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
    re.IGNORECASE,
)

SELECT_PATTERN = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

EXPLORE_MAX_ROWS = 100

# ── Retry Configuration ──────────────────────────────────

NETWORK_RETRY_MAX = 5
NETWORK_RETRY_DELAYS = [1, 2, 4, 4, 4]

NON_NETWORK_RETRY_MAX = 3
NON_NETWORK_RETRY_DELAYS = [1, 1, 1]

NETWORK_ERROR_CODES = frozenset([2003, 2006, 2013, 2002, 2005])
NETWORK_ERROR_KEYWORDS = frozenset([
    "connect", "timeout", "timed out", "connection",
    "lost", "gone away", "broken pipe",
])


def is_network_error(exc):
    try:
        import pymysql
    except ImportError:
        return False
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return True
    if isinstance(exc, pymysql.err.OperationalError):
        if exc.args and isinstance(exc.args[0], int):
            if exc.args[0] in NETWORK_ERROR_CODES:
                return True
        err_msg = str(exc).lower()
        return any(kw in err_msg for kw in NETWORK_ERROR_KEYWORDS)
    return False


def retry_with_backoff(fn,
                       network_max=NETWORK_RETRY_MAX,
                       network_delays=NETWORK_RETRY_DELAYS,
                       non_network_max=NON_NETWORK_RETRY_MAX,
                       non_network_delays=NON_NETWORK_RETRY_DELAYS):
    network_attempts = 0
    non_network_attempts = 0
    while True:
        try:
            return fn()
        except SystemExit:
            raise
        except Exception as e:
            if is_network_error(e):
                network_attempts += 1
                if network_attempts >= network_max:
                    raise
                delay = network_delays[min(network_attempts - 1, len(network_delays) - 1)]
                time.sleep(delay)
            else:
                non_network_attempts += 1
                if non_network_attempts >= non_network_max:
                    raise
                delay = non_network_delays[min(non_network_attempts - 1, len(non_network_delays) - 1)]
                time.sleep(delay)


def json_serial(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


def output_success(**kwargs):
    result = {"success": True, "error_message": ""}
    result.update(kwargs)
    print(json.dumps(result, ensure_ascii=False, default=json_serial))
    sys.exit(0)


def output_error(msg):
    # Strip control characters (e.g. \x00 from ADB engine error messages)
    cleaned = ''.join(c for c in str(msg) if c >= ' ' or c in '\n\r\t')
    print(json.dumps({
        "success": False,
        "error_message": cleaned,
    }, ensure_ascii=False))
    sys.exit(1)


def get_connection_params():
    host = os.environ.get("ADB_MYSQL_HOST")
    if not host:
        output_error("环境变量 ADB_MYSQL_HOST 未设置")
    return {
        "host": host,
        "port": int(os.environ.get("ADB_MYSQL_PORT", "3306")),
        "database": os.environ.get("ADB_MYSQL_DATABASE", ""),
        "user": os.environ.get("ADB_MYSQL_USER", ""),
        "password": os.environ.get("ADB_MYSQL_PASSWORD", ""),
        "connect_timeout": 5,
        "read_timeout": 30,
        "charset": "utf8mb4",
    }


@contextmanager
def get_connection(database=None):
    try:
        import pymysql
    except ImportError:
        output_error("pymysql 未安装，请执行: uv pip install pymysql")

    params = get_connection_params()
    if database:
        params["database"] = database
    elif not params["database"]:
        params.pop("database", None)

    conn = pymysql.connect(**params)
    try:
        yield conn
    finally:
        conn.close()


def execute_query(conn, sql, params=None):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        if cursor.description:
            columns = [
                {"name": col[0], "type": col[1].__name__ if hasattr(col[1], '__name__') else str(col[1])}
                for col in cursor.description
            ]
            rows = cursor.fetchall()
            return columns, [list(row) for row in rows]
        return [], []


def execute_update(conn, sql, params=None):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount


def run_query(sql, params=None, database=None):
    def _do():
        with get_connection(database) as conn:
            return execute_query(conn, sql, params)
    return retry_with_backoff(_do)


def run_update(sql, params=None, database=None):
    with get_connection(database) as conn:
        return execute_update(conn, sql, params)


def validate_identifier(name, label="identifier"):
    if not name or not IDENTIFIER_PATTERN.match(name):
        output_error("{} '{}' 包含非法字符，仅允许字母、数字和下划线".format(label, name))


def validate_select_only(sql):
    if not SELECT_PATTERN.match(sql):
        output_error("仅允许执行 SELECT 语句")
    if DDL_DML_PATTERN.search(sql):
        output_error("当前模式不允许执行 DDL/DML 语句")


# ── Commands ──────────────────────────────────────────────


def cmd_search_semantic_views(args):
    sql = "{hint} SELECT view_schema, view_name, definition, comment, score FROM information_schema.semantic_views WHERE sv_similar_search(definition, %s, %s)".format(
        hint=SEMANTIC_HINT,
    )
    columns, rows = run_query(sql, (args.keywords, args.top_k))

    col_names = [c["name"] for c in columns]
    views = []
    for row in rows:
        col_map = dict(zip(col_names, row))
        views.append({
            "view_schema": col_map.get("view_schema"),
            "view_name": col_map.get("view_name"),
            "definition": col_map.get("definition"),
            "comment": col_map.get("comment"),
            "score": col_map.get("score"),
        })
    output_success(views=views)


def cmd_get_semantic_view(args):
    conditions = []
    params = []

    if args.schema:
        conditions.append("view_schema = %s")
        params.append(args.schema)
    if args.view_name:
        if not args.schema:
            output_error("使用 --view-name 时必须同时指定 --schema")
        conditions.append("view_name = %s")
        params.append(args.view_name)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = "{hint} SELECT view_schema, view_name, definition, comment FROM information_schema.semantic_views{where}".format(
        hint=SEMANTIC_HINT,
        where=where,
    )

    columns, rows = run_query(sql, params if params else None)

    col_names = [c["name"] for c in columns]
    views = []
    for row in rows:
        col_map = dict(zip(col_names, row))
        views.append({
            "view_schema": col_map.get("view_schema"),
            "view_name": col_map.get("view_name"),
            "definition": col_map.get("definition"),
            "comment": col_map.get("comment"),
        })
    output_success(views=views)


def cmd_execute_sql(args):
    sql = args.sql.strip()
    max_rows = args.max_rows
    semantic_rewrite = not args.no_semantic_rewrite

    if not semantic_rewrite:
        validate_select_only(sql)
        if max_rows > EXPLORE_MAX_ROWS:
            max_rows = EXPLORE_MAX_ROWS

    if semantic_rewrite:
        full_sql = "{hint} {sql}".format(hint=SEMANTIC_REWRITE_HINT, sql=sql)
    else:
        full_sql = sql

    if semantic_rewrite:
        def _do():
            with get_connection() as conn:
                columns, rows = execute_query(conn, full_sql)
                _, rewrite_rows = execute_query(
                    conn, "SELECT last_semantic_rewrite_sql()"
                )
                return columns, rows, rewrite_rows

        columns, rows, rewrite_rows = retry_with_backoff(_do)

        rewrite_info = {}
        if rewrite_rows and rewrite_rows[0]:
            if len(rewrite_rows[0]) >= 2:
                rewrite_info["request_id"] = rewrite_rows[0][0]
                rewrite_info["rewritten_sql"] = rewrite_rows[0][1]
            else:
                rewrite_info["rewritten_sql"] = rewrite_rows[0][0]
    else:
        columns, rows = run_query(full_sql)
        rewrite_info = {}

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    result = dict(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        executed_sql=full_sql,
    )
    if rewrite_info:
        result["rewrite_info"] = rewrite_info

    output_success(**result)


def cmd_create_semantic_view(args):
    validate_identifier(args.schema, "schema")
    validate_identifier(args.view_name, "view_name")

    if args.yaml_file == "-":
        yaml_content = sys.stdin.read()
    else:
        try:
            with open(args.yaml_file, "r", encoding="utf-8") as f:
                yaml_content = f.read()
        except IOError as e:
            output_error("无法读取 YAML 文件: {}".format(e))

    if "$$" in yaml_content:
        output_error("YAML 内容中不能包含 '$$' 序列")

    or_replace = "OR REPLACE " if args.or_replace else ""
    if_not_exists = "IF NOT EXISTS " if args.if_not_exists else ""

    sql = "{hint} CREATE {or_replace}SEMANTIC VIEW {if_not_exists}`{schema}`.`{name}` LANGUAGE YAML AS $$\n{yaml}\n $$".format(
        hint=SEMANTIC_HINT,
        or_replace=or_replace,
        if_not_exists=if_not_exists,
        schema=args.schema,
        name=args.view_name,
        yaml=yaml_content,
    )

    run_update(sql)

    output_success(message="语义视图 {}.{} 创建成功".format(args.schema, args.view_name))


def cmd_alter_semantic_view(args):
    validate_identifier(args.schema, "schema")
    validate_identifier(args.view_name, "view_name")
    if_exists = "" if args.no_if_exists else "IF EXISTS "

    if args.operation == "rename":
        if not args.new_name:
            output_error("rename 操作必须指定 --new-name")
        validate_identifier(args.new_name, "new_name")
        sql = "{hint} ALTER SEMANTIC VIEW {if_exists}`{schema}`.`{name}` RENAME TO `{new_name}`".format(
            hint=SEMANTIC_HINT,
            if_exists=if_exists,
            schema=args.schema,
            name=args.view_name,
            new_name=args.new_name,
        )
    elif args.operation == "set_comment":
        if not args.comment:
            output_error("set_comment 操作必须指定 --comment")
        sql = "{hint} ALTER SEMANTIC VIEW {if_exists}`{schema}`.`{name}` SET COMMENT = %s".format(
            hint=SEMANTIC_HINT,
            if_exists=if_exists,
            schema=args.schema,
            name=args.view_name,
        )
        run_update(sql, (args.comment,))
        output_success(message="已更新 {}.{} 的注释".format(args.schema, args.view_name))
        return
    else:
        output_error("未知操作: {}，请使用 'rename' 或 'set_comment'".format(args.operation))

    run_update(sql)

    output_success(message="语义视图 {}.{} 修改成功".format(args.schema, args.view_name))


def cmd_drop_semantic_view(args):
    validate_identifier(args.schema, "schema")
    validate_identifier(args.view_name, "view_name")
    if_exists = "" if args.no_if_exists else "IF EXISTS "
    sql = "{hint} DROP SEMANTIC VIEW {if_exists}`{schema}`.`{name}`".format(
        hint=SEMANTIC_HINT,
        if_exists=if_exists,
        schema=args.schema,
        name=args.view_name,
    )
    run_update(sql)

    output_success(message="语义视图 {}.{} 已删除".format(args.schema, args.view_name))


def cmd_list_databases(args):
    _, rows = run_query("SHOW DATABASES")

    databases = [row[0] for row in rows if row[0] not in SYSTEM_DATABASES]
    output_success(databases=databases)


def cmd_explore_table_metadata(args):
    op = args.operation
    db = args.database
    table = args.table
    limit = min(args.limit, EXPLORE_MAX_ROWS)

    ops_requiring_table = {
        "describe_table", "sample_data", "table_statistics",
        "partition_info", "index_info", "safe_sample",
        "explain", "show_create_table",
    }
    if op in ops_requiring_table and not table:
        output_error("'{}' 操作必须指定 --table".format(op))

    if op == "explain" and not args.sql:
        output_error("'explain' 操作必须指定 --sql")

    if op == "list_tables":
        _explore_list_tables(db, limit)
    elif op == "describe_table":
        _explore_describe_table(db, table)
    elif op == "sample_data":
        _explore_sample_data(db, table, limit)
    elif op == "table_statistics":
        _explore_table_statistics(db, table)
    elif op == "partition_info":
        _explore_partition_info(db, table)
    elif op == "index_info":
        _explore_index_info(db, table)
    elif op == "safe_sample":
        _explore_safe_sample(db, table, args.columns, limit)
    elif op == "explain":
        _explore_explain(args.sql)
    elif op == "show_create_table":
        _explore_show_create_table(db, table)
    else:
        output_error("未知操作: {}".format(op))


def _explore_list_tables(db, limit):
    sql = (
        "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s LIMIT %s"
    )
    columns, rows = run_query(sql, (db, limit), database=db)
    output_success(columns=columns, rows=rows, row_count=len(rows))


def _explore_describe_table(db, table):
    sql = (
        "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, COLUMN_COMMENT, "
        "IS_NULLABLE, COLUMN_KEY, EXTRA, ORDINAL_POSITION "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION"
    )
    columns, rows = run_query(sql, (db, table), database=db)
    output_success(columns=columns, rows=rows, row_count=len(rows))


def _explore_sample_data(db, table, limit):
    sql = "SELECT * FROM `{db}`.`{table}` LIMIT %s".format(
        db=db.replace("`", "``"),
        table=table.replace("`", "``"),
    )
    columns, rows = run_query(sql, (limit,), database=db)
    output_success(columns=columns, rows=rows, row_count=len(rows))


def _explore_table_statistics(db, table):
    sql = (
        "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, "
        "CREATE_TIME, UPDATE_TIME, TABLE_COMMENT "
        "FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
    )
    columns, rows = run_query(sql, (db, table), database=db)
    output_success(columns=columns, rows=rows, row_count=len(rows))


def _explore_partition_info(db, table):
    meta_sql = (
        "SELECT PARTITION_COLUMN, PARTITION_TYPE, DISTRIBUTE_COLUMN, "
        "DISTRIBUTE_TYPE, PRIMARYKEY_COLUMNS, PARTITION_COUNT, "
        "HOT_PARTITION_COUNT, BUCKET_COUNT "
        "FROM information_schema.kepler_meta_tables "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
    )
    try:
        _, meta_rows = run_query(meta_sql, (db, table), database=db)
    except Exception:
        meta_rows = []

    extra = {}
    if meta_rows:
        row = meta_rows[0]
        extra = {
            "partition_column": row[0],
            "partition_type": row[1],
            "distribute_column": row[2],
            "distribute_type": row[3],
            "primary_key_columns": row[4],
            "partition_count": row[5],
            "hot_partition_count": row[6],
            "bucket_count": row[7],
        }

    part_sql = (
        "SELECT partition_id, row_count, data_size "
        "FROM information_schema.kepler_partitions "
        "WHERE schema_name = %s AND table_name = %s "
        "ORDER BY partition_id DESC LIMIT 10"
    )
    try:
        part_cols, part_rows = run_query(part_sql, (db, table), database=db)
    except Exception:
        part_cols, part_rows = [], []

    output_success(
        columns=part_cols,
        rows=part_rows,
        row_count=len(part_rows),
        **extra
    )


def _explore_index_info(db, table):
    sql = "SHOW INDEXES FROM `{db}`.`{table}`".format(
        db=db.replace("`", "``"),
        table=table.replace("`", "``"),
    )
    columns, rows = run_query(sql, database=db)
    output_success(columns=columns, rows=rows, row_count=len(rows))


def _explore_safe_sample(db, table, columns_arg, limit):
    partition_column = None
    try:
        meta_sql = (
            "SELECT PARTITION_COLUMN, PARTITION_TYPE "
            "FROM information_schema.kepler_meta_tables "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
        )
        _, meta_rows = run_query(meta_sql, (db, table), database=db)
        if meta_rows and meta_rows[0][0]:
            partition_column = meta_rows[0][0]
    except Exception:
        pass

    if columns_arg:
        select_cols = ", ".join(
            "`{}`".format(c.strip().replace("`", "``")) for c in columns_arg.split(",")
        )
    else:
        pk_sql = (
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_KEY = 'PRI' "
            "ORDER BY ORDINAL_POSITION"
        )
        _, pk_rows = run_query(pk_sql, (db, table), database=db)
        pk_cols = [r[0] for r in pk_rows]

        all_sql = (
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION LIMIT 10"
        )
        _, all_rows = run_query(all_sql, (db, table), database=db)
        all_cols = [r[0] for r in all_rows]

        col_set = []
        if partition_column and partition_column not in col_set:
            col_set.append(partition_column)
        for c in pk_cols:
            if c not in col_set:
                col_set.append(c)
        for c in all_cols:
            if c not in col_set:
                col_set.append(c)
        col_set = col_set[:10]
        select_cols = ", ".join("`{}`".format(c.replace("`", "``")) for c in col_set)

    escaped_db = db.replace("`", "``")
    escaped_table = table.replace("`", "``")

    if partition_column:
        part_sql = (
            "SELECT partition_id FROM information_schema.kepler_partitions "
            "WHERE schema_name = %s AND table_name = %s "
            "ORDER BY partition_id DESC LIMIT 1"
        )
        try:
            _, part_rows = run_query(part_sql, (db, table), database=db)
            if part_rows:
                recent_partition = part_rows[0][0]
                escaped_pk = partition_column.replace("`", "``")
                sample_sql = (
                    "SELECT {cols} FROM `{db}`.`{table}` "
                    "WHERE `{pk}` >= %s LIMIT %s"
                ).format(
                    cols=select_cols,
                    db=escaped_db,
                    table=escaped_table,
                    pk=escaped_pk,
                )
                columns, rows = run_query(sample_sql, (recent_partition, limit), database=db)
                output_success(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    partition_key=partition_column,
                )
                return
        except Exception:
            pass

    sample_sql = "SELECT {cols} FROM `{db}`.`{table}` LIMIT %s".format(
        cols=select_cols,
        db=escaped_db,
        table=escaped_table,
    )
    columns, rows = run_query(sample_sql, (limit,), database=db)
    output_success(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        partition_key=None,
    )


def _explore_explain(sql):
    validate_select_only(sql)
    explain_sql = "EXPLAIN {}".format(sql)
    columns, rows = run_query(explain_sql)
    plan_text = "\n".join("\t".join(str(cell) for cell in row) for row in rows)
    output_success(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        explain_plan=plan_text,
    )


def _explore_show_create_table(db, table):
    sql = "SHOW CREATE TABLE `{db}`.`{table}`".format(
        db=db.replace("`", "``"),
        table=table.replace("`", "``"),
    )
    columns, rows = run_query(sql, database=db)
    ddl = rows[0][1] if rows else ""
    output_success(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        create_table_ddl=ddl,
    )


# ── CLI ───────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(
        description="ADB MySQL 智能分析助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # search_semantic_views
    p = sub.add_parser("search_semantic_views", help="向量搜索语义视图")
    p.add_argument("--keywords", required=True, help="以空格分隔的搜索关键词")
    p.add_argument("--top-k", type=int, default=3, help="返回结果数量（默认: 3）")

    # get_semantic_view
    p = sub.add_parser("get_semantic_view", help="查询语义视图定义")
    p.add_argument("--schema", help="按 schema 过滤")
    p.add_argument("--view-name", help="按视图名称过滤（需配合 --schema 使用）")

    # execute_sql
    p = sub.add_parser("execute_sql", help="执行 SQL 查询")
    p.add_argument("--sql", required=True, help="待执行的 SQL")
    p.add_argument("--no-semantic-rewrite", action="store_true",
                   help="直连模式：跳过语义改写 hint，用于数据探索")
    p.add_argument("--max-rows", type=int, default=500,
                   help="最大返回行数（默认: 500，直连模式下上限为 100）")

    # create_semantic_view
    p = sub.add_parser("create_semantic_view", help="创建语义视图")
    p.add_argument("--schema", required=True, help="目标 schema")
    p.add_argument("--view-name", required=True, help="视图名称")
    p.add_argument("--yaml-file", required=True,
                   help="YAML 定义文件路径（使用 '-' 表示从标准输入读取）")
    p.add_argument("--or-replace", action="store_true", help="附加 OR REPLACE 子句")
    p.add_argument("--if-not-exists", action="store_true", help="附加 IF NOT EXISTS 子句")

    # alter_semantic_view
    p = sub.add_parser("alter_semantic_view", help="修改语义视图")
    p.add_argument("--schema", required=True, help="视图所在的 schema")
    p.add_argument("--view-name", required=True, help="当前视图名称")
    p.add_argument("--operation", required=True, choices=["rename", "set_comment"],
                   help="修改操作类型")
    p.add_argument("--new-name", help="新名称（用于 rename 操作）")
    p.add_argument("--comment", help="新注释（用于 set_comment 操作）")
    p.add_argument("--no-if-exists", action="store_true",
                   help="去除 IF EXISTS 子句")

    # drop_semantic_view
    p = sub.add_parser("drop_semantic_view", help="删除语义视图")
    p.add_argument("--schema", required=True, help="视图所在的 schema")
    p.add_argument("--view-name", required=True, help="待删除的视图名称")
    p.add_argument("--no-if-exists", action="store_true",
                   help="去除 IF EXISTS 子句")

    # list_databases
    sub.add_parser("list_databases", help="列出可访问的数据库")

    # explore_table_metadata
    p = sub.add_parser("explore_table_metadata", help="探索表元数据")
    p.add_argument("--operation", required=True,
                   choices=["list_tables", "describe_table", "sample_data",
                            "table_statistics", "partition_info", "index_info",
                            "safe_sample", "explain", "show_create_table"],
                   help="探索操作类型")
    p.add_argument("--database", required=True, help="目标数据库")
    p.add_argument("--table", help="目标表（大多数操作必填）")
    p.add_argument("--columns", help="safe_sample 操作的列名，以逗号分隔")
    p.add_argument("--sql", help="explain 操作的 SELECT SQL")
    p.add_argument("--limit", type=int, default=10,
                   help="最大返回行数（默认: 10，上限: 100）")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "search_semantic_views": cmd_search_semantic_views,
        "get_semantic_view": cmd_get_semantic_view,
        "execute_sql": cmd_execute_sql,
        "create_semantic_view": cmd_create_semantic_view,
        "alter_semantic_view": cmd_alter_semantic_view,
        "drop_semantic_view": cmd_drop_semantic_view,
        "list_databases": cmd_list_databases,
        "explore_table_metadata": cmd_explore_table_metadata,
    }

    try:
        dispatch[args.command](args)
    except SystemExit:
        raise
    except Exception as e:
        output_error("意外错误: {}".format(e))


if __name__ == "__main__":
    main()
