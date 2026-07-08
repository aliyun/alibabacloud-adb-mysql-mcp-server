"""SQL 安全校验与 SQL 工具入口的回归测试。"""

import asyncio

import pytest

from adb_mysql_mcp_server import server
from adb_mysql_mcp_server.sql_safety import SqlSafetyValidator


class FakeDBService:
    calls = []

    def __init__(self, *args):
        self.args = args

    async def __aenter__(self):
        FakeDBService.calls.append(("enter", self.args))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute_sql(self, sql):
        FakeDBService.calls.append(("execute", sql))
        return sql


@pytest.fixture(autouse=True)
def fake_db_service(monkeypatch):
    FakeDBService.calls = []
    monkeypatch.setattr(server, "DBService", FakeDBService)
    monkeypatch.delenv("ENABLE_SQL_WRITE_TOOLS", raising=False)


def test_validate_read_only_sql_rejects_multi_statement():
    with pytest.raises(ValueError, match="single statement"):
        SqlSafetyValidator.validate_read_only_sql("select 1; drop table users")


def test_validate_read_only_sql_rejects_write_sql():
    with pytest.raises(ValueError, match="Only read-only SQL"):
        SqlSafetyValidator.validate_read_only_sql("delete from users")


def test_validate_read_only_sql_allows_show_create_table():
    assert SqlSafetyValidator.validate_read_only_sql("show create table orders") == "show create table orders"


def test_execute_sql_validates_before_connecting():
    with pytest.raises(ValueError, match="ENABLE_SQL_WRITE_TOOLS=true"):
        asyncio.run(server.execute_sql("drop table users"))

    assert FakeDBService.calls == []


def test_execute_sql_rejects_too_long_sql_before_connecting():
    too_long_sql = "select " + "a" * (SqlSafetyValidator.MAX_SQL_LENGTH + 1)

    with pytest.raises(ValueError, match="SQL is too long"):
        asyncio.run(server.execute_sql(too_long_sql))

    assert FakeDBService.calls == []


def test_execute_sql_uses_configured_max_sql_length(monkeypatch):
    monkeypatch.setenv("ADB_MYSQL_MAX_SQL_LENGTH", "12")

    with pytest.raises(ValueError, match="SQL is too long"):
        asyncio.run(server.execute_sql("select " + "a" * 20))

    assert FakeDBService.calls == []


def test_execute_sql_allows_larger_configured_max_sql_length(monkeypatch):
    monkeypatch.setenv("ADB_MYSQL_MAX_SQL_LENGTH", str(SqlSafetyValidator.MAX_SQL_LENGTH + 100))
    sql = "select " + "a" * (SqlSafetyValidator.MAX_SQL_LENGTH + 1)

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_rejects_invalid_configured_max_sql_length(monkeypatch):
    monkeypatch.setenv("ADB_MYSQL_MAX_SQL_LENGTH", "invalid")

    with pytest.raises(ValueError, match="ADB_MYSQL_MAX_SQL_LENGTH must be a positive integer"):
        asyncio.run(server.execute_sql("select 1"))

    assert FakeDBService.calls == []


def test_execute_sql_allows_single_select():
    result = asyncio.run(server.execute_sql(" select * from users "))

    assert result == "select * from users"
    assert ("execute", "select * from users") in FakeDBService.calls


def test_execute_sql_allows_terminal_semicolon():
    result = asyncio.run(server.execute_sql(" select * from users; "))

    assert result == "select * from users"
    assert ("execute", "select * from users") in FakeDBService.calls


def test_execute_sql_allows_terminal_semicolon_with_string_semicolon():
    result = asyncio.run(server.execute_sql("select ';' as marker;"))

    assert result == "select ';' as marker"
    assert ("execute", "select ';' as marker") in FakeDBService.calls


def test_execute_sql_allows_parenthesized_select():
    result = asyncio.run(server.execute_sql("(select * from users);"))

    assert result == "(select * from users)"
    assert ("execute", "(select * from users)") in FakeDBService.calls


def test_execute_sql_allows_dangerous_keyword_inside_string():
    sql = "select 'delete drop update' as word"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_dangerous_keyword_inside_like_pattern():
    sql = "select * from users where note like '%drop table%'"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_rejects_select_into_outfile():
    with pytest.raises(ValueError, match="Only read-only SQL"):
        asyncio.run(server.execute_sql("select * into outfile '/tmp/users.csv' from users"))

    assert FakeDBService.calls == []


def test_execute_sql_rejects_comment_outside_string_but_allows_comment_text_inside_string():
    string_comment_sql = "select '-- delete is just text' as comment_text"

    result = asyncio.run(server.execute_sql(string_comment_sql))

    assert result == string_comment_sql
    assert ("execute", string_comment_sql) in FakeDBService.calls

    with pytest.raises(ValueError, match="single statement without comments"):
        asyncio.run(server.execute_sql("select * from users -- real comment"))


def test_execute_sql_allows_read_only_with_cte():
    result = asyncio.run(server.execute_sql("with cte as (select 1) select * from cte"))

    assert result == "with cte as (select 1) select * from cte"
    assert ("execute", "with cte as (select 1) select * from cte") in FakeDBService.calls


def test_execute_sql_allows_parenthesized_read_only_with_cte():
    sql = "(with cte as (select 1) select * from cte)"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_rejects_parenthesized_write_sql():
    with pytest.raises(ValueError, match="ENABLE_SQL_WRITE_TOOLS=true"):
        asyncio.run(server.execute_sql("(delete from users)"))

    assert FakeDBService.calls == []


def test_execute_sql_rejects_write_inside_with_cte():
    with pytest.raises(ValueError, match="Only read-only SQL"):
        asyncio.run(server.execute_sql("with cte as (delete from users) select * from cte"))

    assert FakeDBService.calls == []


def test_execute_sql_allows_write_inside_with_cte_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "with cte as (delete from users) select * from cte"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_write_keyword_inside_select_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "select update_status(id) from users"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_select_into_outfile_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "select * into outfile '/tmp/users.csv' from users"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_write_requires_explicit_enable():
    with pytest.raises(ValueError, match="ENABLE_SQL_WRITE_TOOLS=true"):
        asyncio.run(server.execute_sql("delete from users where id = 1"))

    assert FakeDBService.calls == []


def test_execute_sql_allows_delete_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")

    result = asyncio.run(server.execute_sql("delete from users where id = 1;"))

    assert result == "delete from users where id = 1;"
    assert ("execute", "delete from users where id = 1;") in FakeDBService.calls


def test_execute_sql_allows_drop_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")

    result = asyncio.run(server.execute_sql("drop table old_orders"))

    assert result == "drop table old_orders"
    assert ("execute", "drop table old_orders") in FakeDBService.calls


def test_execute_sql_still_allows_read_only_sql_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")

    result = asyncio.run(server.execute_sql("select * from users"))

    assert result == "select * from users"
    assert ("execute", "select * from users") in FakeDBService.calls


def test_execute_sql_allows_unknown_keyword_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "vacuum table users"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_multi_statement_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "select 1; update users set role = 'admin' where id = 1;"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_comment_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "select * from users -- real comment"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_unclosed_string_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "select 'unterminated"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_execute_sql_allows_transaction_block_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")
    sql = "begin; update users set role = 'admin' where id = 1; commit;"

    result = asyncio.run(server.execute_sql(sql))

    assert result == sql
    assert ("execute", sql) in FakeDBService.calls


def test_get_query_plan_rejects_non_select_sql():
    with pytest.raises(ValueError, match="EXPLAIN only supports SELECT or read-only WITH"):
        asyncio.run(server.get_query_plan("update users set role = 'admin'"))

    assert FakeDBService.calls == []


def test_get_query_plan_rejects_stacked_sql():
    with pytest.raises(ValueError, match="single statement"):
        asyncio.run(server.get_query_plan("select 1; drop table users"))

    assert FakeDBService.calls == []


def test_get_query_plan_allows_terminal_semicolon():
    result = asyncio.run(server.get_query_plan("select * from users;"))

    assert result == "EXPLAIN select * from users"


def test_get_query_plan_allows_read_only_with_cte():
    result = asyncio.run(server.get_query_plan("with cte as (select 1) select * from cte"))

    assert result == "EXPLAIN with cte as (select 1) select * from cte"


def test_get_query_plan_allows_parenthesized_select():
    result = asyncio.run(server.get_query_plan("(select * from users);"))

    assert result == "EXPLAIN (select * from users)"


def test_get_query_plan_rejects_write_inside_with_cte():
    with pytest.raises(ValueError, match="EXPLAIN only supports SELECT or read-only WITH"):
        asyncio.run(server.get_query_plan("with cte as (delete from users) select * from cte"))

    assert FakeDBService.calls == []


def test_get_query_plan_rejects_write_even_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")

    with pytest.raises(ValueError, match="EXPLAIN only supports SELECT or read-only WITH"):
        asyncio.run(server.get_query_plan("update users set role = 'admin'"))

    assert FakeDBService.calls == []


def test_get_execution_plan_allows_single_select():
    result = asyncio.run(server.get_execution_plan("select * from users"))

    assert result == "EXPLAIN ANALYZE select * from users"


def test_get_execution_plan_allows_read_only_with_cte():
    result = asyncio.run(server.get_execution_plan("with cte as (select 1) select * from cte"))

    assert result == "EXPLAIN ANALYZE with cte as (select 1) select * from cte"


def test_get_execution_plan_rejects_write_even_when_write_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SQL_WRITE_TOOLS", "true")

    with pytest.raises(ValueError, match="EXPLAIN only supports SELECT or read-only WITH"):
        asyncio.run(server.get_execution_plan("update users set role = 'admin'"))

    assert FakeDBService.calls == []
