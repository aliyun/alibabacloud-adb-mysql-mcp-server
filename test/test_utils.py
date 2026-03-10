"""utils.py 模块的单元测试

测试范围：
  - 日期时间转换函数（transform_to_datetime, transform_to_iso8601, convert_datetime_to_timestamp_ms）
  - 数据格式化函数（json_array_to_csv, json_array_to_markdown）
  - JSON 提取辅助函数（extract_first_column_from_json_rows, extract_second_column_from_first_row）
  - SQL 标识符校验函数（validate_sql_identifier）
"""

from datetime import datetime, timedelta, timezone

import pytest

from adb_mysql_mcp_server.utils import (
    convert_datetime_to_timestamp_ms,
    extract_first_column_from_json_rows,
    extract_second_column_from_first_row,
    json_array_to_csv,
    json_array_to_markdown,
    resolve_time_range,
    transform_to_datetime,
    transform_to_iso8601,
    validate_sql_identifier,
)


LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo


class TestTransformToDatetime:
    """测试 transform_to_datetime——将常见日期字符串解析为带时区的 datetime 对象"""

    def test_with_seconds(self):
        """'YYYY-MM-DD HH:MM:SS' 格式应解析为本地时区"""
        result = transform_to_datetime("2025-06-01 12:30:45")
        assert result == datetime(2025, 6, 1, 12, 30, 45, tzinfo=LOCAL_TZ)

    def test_with_minutes(self):
        """'YYYY-MM-DD HH:MM' 格式（不含秒）应解析为本地时区"""
        result = transform_to_datetime("2025-06-01 12:30")
        assert result == datetime(2025, 6, 1, 12, 30, tzinfo=LOCAL_TZ)

    def test_iso8601_utc_with_seconds(self):
        """'YYYY-MM-DDTHH:MM:SSZ' 格式应解析为 UTC"""
        result = transform_to_datetime("2025-06-01T12:30:45Z")
        assert result == datetime(2025, 6, 1, 12, 30, 45, tzinfo=timezone.utc)

    def test_iso8601_utc_without_seconds(self):
        """'YYYY-MM-DDTHH:MMZ' 格式（不含秒）应解析为 UTC"""
        result = transform_to_datetime("2025-06-01T12:30Z")
        assert result == datetime(2025, 6, 1, 12, 30, tzinfo=timezone.utc)

    def test_local_and_utc_offset_correct(self):
        """本地时间和 UTC 时间之间的偏移应等于本地时区的 UTC 偏移"""
        local_dt = transform_to_datetime("2025-06-01 12:30:00")
        utc_dt = transform_to_datetime("2025-06-01T12:30:00Z")
        diff = local_dt.utcoffset() - utc_dt.utcoffset()
        assert diff == LOCAL_TZ.utcoffset(local_dt)

    def test_result_is_timezone_aware(self):
        """所有解析结果都应带时区信息"""
        for s in ("2025-06-01 12:30:00", "2025-06-01T12:30:00Z"):
            result = transform_to_datetime(s)
            assert result.tzinfo is not None

    def test_invalid_format(self):
        """不支持的格式应抛出 ValueError"""
        with pytest.raises(ValueError):
            transform_to_datetime("not-a-date")


class TestResolveTimeRange:
    """测试 resolve_time_range——自动补全缺失的 start_time/end_time"""

    def test_both_provided(self):
        """start_time 和 end_time 都提供时，直接解析返回（本地时区）"""
        start_dt, end_dt = resolve_time_range("2025-01-01 08:00:00", "2025-01-01 10:00:00")
        assert start_dt == datetime(2025, 1, 1, 8, 0, 0, tzinfo=LOCAL_TZ)
        assert end_dt == datetime(2025, 1, 1, 10, 0, 0, tzinfo=LOCAL_TZ)

    def test_only_start_provided(self):
        """仅提供 start_time 时，end_time = start_time + 1 小时"""
        start_dt, end_dt = resolve_time_range("2025-01-01 08:00:00", None)
        assert start_dt == datetime(2025, 1, 1, 8, 0, 0, tzinfo=LOCAL_TZ)
        assert end_dt == datetime(2025, 1, 1, 9, 0, 0, tzinfo=LOCAL_TZ)

    def test_only_end_provided(self):
        """仅提供 end_time 时，start_time = end_time - 1 小时"""
        start_dt, end_dt = resolve_time_range(None, "2025-01-01 10:00:00")
        assert start_dt == datetime(2025, 1, 1, 9, 0, 0, tzinfo=LOCAL_TZ)
        assert end_dt == datetime(2025, 1, 1, 10, 0, 0, tzinfo=LOCAL_TZ)

    def test_neither_provided(self):
        """都不提供时，默认返回最近 1 小时范围（本地时区）"""
        start_dt, end_dt = resolve_time_range(None, None)
        assert (end_dt - start_dt) == timedelta(hours=1)
        assert start_dt.tzinfo is not None
        assert abs((datetime.now(LOCAL_TZ) - end_dt).total_seconds()) < 5

    def test_custom_delta(self):
        """自定义 delta 参数（如 2 小时）"""
        start_dt, end_dt = resolve_time_range(
            "2025-01-01 08:00:00", None, delta=timedelta(hours=2)
        )
        assert end_dt == datetime(2025, 1, 1, 10, 0, 0, tzinfo=LOCAL_TZ)

    def test_empty_string_treated_as_none(self):
        """空字符串应被视为未提供"""
        start_dt, end_dt = resolve_time_range("", "")
        assert (end_dt - start_dt) == timedelta(hours=1)


class TestTransformToIso8601:
    """测试 transform_to_iso8601——将 datetime 转为 ISO 8601 UTC 字符串"""

    def test_utc(self):
        """UTC 时区的 datetime 应正确转换，末尾为 'Z'"""
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = transform_to_iso8601(dt)
        assert result == "2025-06-01T12:00:00Z"


class TestConvertDatetimeToTimestampMs:
    """测试 convert_datetime_to_timestamp_ms——日期字符串转毫秒时间戳"""

    def test_basic(self):
        """正常输入应返回一个正整数毫秒时间戳"""
        result = convert_datetime_to_timestamp_ms("2025-01-01 00:00:00")
        assert isinstance(result, int)
        assert result > 0


class TestJsonArrayToCsv:
    """测试 json_array_to_csv——将字典列表转为 CSV 字符串"""

    def test_empty(self):
        """空列表或 None 应返回空字符串"""
        assert json_array_to_csv([]) == ""
        assert json_array_to_csv(None) == ""

    def test_dict_list(self):
        """正常字典列表应包含表头和数据"""
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = json_array_to_csv(data)
        # 应包含列名
        assert "a" in result
        assert "b" in result
        # 应包含数据值
        assert "1" in result

    def test_none_values(self):
        """字典中值为 None 时，CSV 中应输出为空字符串"""
        data = [{"a": None, "b": "x"}]
        result = json_array_to_csv(data)
        assert "x" in result


class TestJsonArrayToMarkdown:
    """测试 json_array_to_markdown——将数据转为 Markdown 表格"""

    def test_empty(self):
        """空输入应返回空字符串"""
        assert json_array_to_markdown([], []) == ""

    def test_basic(self):
        """正常输入应生成包含表头和数据行的 Markdown 表格"""
        headers = ["name", "value"]
        rows = [{"name": "cpu", "value": "80%"}]
        result = json_array_to_markdown(headers, rows)
        # 验证表头行
        assert "| name | value |" in result
        # 验证数据行
        assert "| cpu | 80% |" in result


class TestExtractFirstColumnFromJsonRows:
    """测试 extract_first_column_from_json_rows——从 JSON 行数组中提取第一列"""

    def test_empty_string(self):
        """空字符串输入应返回空字符串"""
        assert extract_first_column_from_json_rows("") == ""

    def test_empty_array(self):
        """空 JSON 数组应返回空字符串"""
        assert extract_first_column_from_json_rows("[]") == ""

    def test_invalid_json(self):
        """非法 JSON 应返回空字符串"""
        assert extract_first_column_from_json_rows("not json") == ""

    def test_single_row(self):
        """单行数据应返回第一列的值"""
        result = extract_first_column_from_json_rows('[{"Database": "mydb"}]')
        assert result == "mydb"

    def test_multiple_rows(self):
        """多行数据应返回换行分隔的第一列值"""
        result = extract_first_column_from_json_rows(
            '[{"Database": "a"}, {"Database": "b"}, {"Database": "c"}]'
        )
        assert result == "a\nb\nc"


class TestExtractSecondColumnFromFirstRow:
    """测试 extract_second_column_from_first_row——从第一行提取第二列值（用于获取 DDL 等）"""

    def test_empty_string(self):
        """空字符串输入应返回默认值"""
        assert extract_second_column_from_first_row("", default="x") == "x"

    def test_empty_array(self):
        """空数组应返回默认值"""
        assert extract_second_column_from_first_row("[]", default="y") == "y"

    def test_invalid_json(self):
        """非法 JSON 应返回默认值"""
        assert extract_second_column_from_first_row("bad", default="z") == "z"

    def test_two_columns(self):
        """有两列时应返回第二列的值（如 SHOW CREATE TABLE 的结果）"""
        result = extract_second_column_from_first_row(
            '[{"Table": "t1", "Create Table": "CREATE TABLE t1 (...)"}]',
            default="",
        )
        assert "CREATE TABLE" in result

    def test_single_column_fallback(self):
        """只有一列时应退化为返回第一列的值"""
        result = extract_second_column_from_first_row('[{"col": "val"}]', default="d")
        assert result == "val"


class TestValidateSqlIdentifier:
    """测试 validate_sql_identifier——SQL 标识符合法性校验（防注入）"""

    def test_valid_identifier(self):
        """合法标识符（字母、数字、下划线）应通过校验"""
        validate_sql_identifier("my_db")
        validate_sql_identifier("table123")
        validate_sql_identifier("_private")

    def test_empty_raises(self):
        """空字符串应抛出 ValueError"""
        with pytest.raises(ValueError, match="Invalid identifier"):
            validate_sql_identifier("")

    def test_special_chars_raise(self):
        """包含特殊字符（如连字符、分号）的标识符应被拒绝"""
        with pytest.raises(ValueError, match="Invalid"):
            validate_sql_identifier("db-name")
        with pytest.raises(ValueError, match="Invalid"):
            validate_sql_identifier("table;drop")

    def test_custom_kind_in_message(self):
        """通过 kind 参数可自定义错误消息中的标识符类型描述"""
        with pytest.raises(ValueError, match="Invalid database"):
            validate_sql_identifier("bad-name", kind="database")
