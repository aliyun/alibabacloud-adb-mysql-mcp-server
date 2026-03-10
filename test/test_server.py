"""server.py 模块的单元测试

测试范围：
  - _parse_groups 函数的各种输入场景
  - _has_openapi_credentials 函数在不同环境变量下的行为
  - 工具/资源的注册数量和分组
  - GROUP_EXPANSIONS 和 DEFAULT_GROUPS 常量
"""

from unittest import mock

from adb_mysql_mcp_server.server import mcp, _parse_groups, _has_openapi_credentials, GROUP_EXPANSIONS, DEFAULT_GROUPS
from adb_mysql_mcp_server.core.mcp import _ComponentType


class TestParseGroups:
    """测试 _parse_groups 函数——负责将 MCP_TOOLSETS 环境变量解析成分组列表"""

    def test_default(self):
        """传入 None 时，应返回默认分组"""
        assert _parse_groups(None) == ["openapi", "sql"]

    def test_empty_string(self):
        """传入空字符串时，应返回默认分组"""
        assert _parse_groups("") == ["openapi", "sql"]

    def test_single_group(self):
        """传入单个分组名，应返回仅包含该分组的列表"""
        assert _parse_groups("openapi") == ["openapi"]

    def test_sql_only(self):
        """仅传入 sql 分组"""
        assert _parse_groups("sql") == ["sql"]

    def test_multiple_groups(self):
        """传入多个分组名（逗号分隔），应按序返回"""
        assert _parse_groups("openapi,sql") == ["openapi", "sql"]

    def test_strips_whitespace(self):
        """分组名前后的空格应被自动去除"""
        assert _parse_groups(" openapi , sql ") == ["openapi", "sql"]

    def test_expansion_all(self):
        """传入 'all' 应展开为所有已定义的分组"""
        assert _parse_groups("all") == ["openapi", "sql"]

    def test_expansion_deduplicates(self):
        """传入 'openapi,all' 时，展开后应自动去重"""
        result = _parse_groups("openapi,all")
        assert result == ["openapi", "sql"]

    def test_custom_group_passthrough(self):
        """未在 GROUP_EXPANSIONS 中定义的自定义分组名应原样返回"""
        assert _parse_groups("custom") == ["custom"]


class TestHasOpenApiCredentials:
    """测试 _has_openapi_credentials 函数——判断 AK/SK 是否已配置"""

    def test_returns_true_when_both_set(self):
        """AK 和 SK 都配置时，应返回 True"""
        with mock.patch.dict("os.environ", {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak123",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk456",
        }):
            assert _has_openapi_credentials() is True

    def test_returns_false_when_ak_missing(self):
        """只配置了 SK 而没有 AK 时，应返回 False"""
        env = {"ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk456"}
        with mock.patch.dict("os.environ", env, clear=True):
            assert _has_openapi_credentials() is False

    def test_returns_false_when_sk_missing(self):
        """只配置了 AK 而没有 SK 时，应返回 False"""
        env = {"ALIBABA_CLOUD_ACCESS_KEY_ID": "ak123"}
        with mock.patch.dict("os.environ", env, clear=True):
            assert _has_openapi_credentials() is False

    def test_returns_false_when_both_missing(self):
        """AK 和 SK 都未配置时，应返回 False"""
        with mock.patch.dict("os.environ", {}, clear=True):
            assert _has_openapi_credentials() is False

    def test_returns_false_when_empty_strings(self):
        """AK 或 SK 为空字符串时，应返回 False"""
        with mock.patch.dict("os.environ", {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "",
        }):
            assert _has_openapi_credentials() is False


class TestToolRegistration:
    """测试 mcp 实例上的延迟注册——验证工具和资源是否正确收集"""

    def test_total_registrations(self):
        """总注册数 = 工具数 + 资源数"""
        tool_count = len([t for t in mcp._pending_registrations if t.item_type == _ComponentType.TOOL])
        res_count = len([t for t in mcp._pending_registrations if t.item_type == _ComponentType.RESOURCE])
        assert len(mcp._pending_registrations) == tool_count + res_count

    def test_has_tools(self):
        """至少应该注册了一些工具"""
        tools = [t for t in mcp._pending_registrations if t.item_type == _ComponentType.TOOL]
        assert len(tools) > 0

    def test_has_resources(self):
        """至少应该注册了一些资源"""
        resources = [t for t in mcp._pending_registrations if t.item_type == _ComponentType.RESOURCE]
        assert len(resources) > 0

    def test_tool_names(self):
        """验证所有已注册工具的名称列表（按注册顺序）"""
        tools = [t for t in mcp._pending_registrations if t.item_type == _ComponentType.TOOL]
        names = [t.func.__name__ for t in tools]
        # 集群管理工具
        assert "describe_db_clusters" in names
        assert "describe_db_cluster_attribute" in names
        assert "get_current_time" in names
        # 诊断与监控工具
        assert "describe_db_cluster_performance" in names
        assert "describe_diagnosis_records" in names
        # 管控与审计工具
        assert "create_account" in names
        assert "describe_audit_log_records" in names
        # 高级诊断工具
        assert "kill_process" in names
        assert "describe_db_resource_group" in names
        # SQL 工具
        assert "execute_sql" in names
        assert "get_query_plan" in names
        assert "get_execution_plan" in names

    def test_openapi_group_has_tools(self):
        """'openapi' 分组应包含 OpenAPI 工具"""
        openapi_tools = [t for t in mcp._pending_registrations
                         if t.item_type == _ComponentType.TOOL and t.group == "openapi"]
        assert len(openapi_tools) > 0

    def test_sql_group_tools(self):
        """'sql' 分组应包含 execute_sql、get_query_plan、get_execution_plan"""
        sql_tools = [t for t in mcp._pending_registrations
                     if t.item_type == _ComponentType.TOOL and t.group == "sql"]
        names = {t.func.__name__ for t in sql_tools}
        assert "execute_sql" in names
        assert "get_query_plan" in names
        assert "get_execution_plan" in names

    def test_sql_group_resources(self):
        """'sql' 分组应包含 databases、tables、ddl、config 四个 MCP 资源"""
        resources = [t for t in mcp._pending_registrations
                     if t.item_type == _ComponentType.RESOURCE and t.group == "sql"]
        names = {t.func.__name__ for t in resources}
        assert "resource_list_databases" in names
        assert "resource_list_tables" in names
        assert "resource_table_ddl" in names
        assert "resource_config_value" in names

    def test_resource_uris(self):
        """验证所有资源的 URI 格式正确"""
        resources = [t for t in mcp._pending_registrations
                     if t.item_type == _ComponentType.RESOURCE]
        uris = [t.args[0] for t in resources]
        assert "adbmysql:///databases" in uris
        assert "adbmysql:///{database}/tables" in uris
        assert "adbmysql:///{database}/{table}/ddl" in uris
        assert "adbmysql:///config/{key}/value" in uris


class TestGroupExpansions:
    """测试分组展开常量是否正确定义"""

    def test_all_expansion_defined(self):
        """'all' 快捷方式应展开为 openapi + sql"""
        assert "all" in GROUP_EXPANSIONS
        assert GROUP_EXPANSIONS["all"] == ["openapi", "sql"]

    def test_default_groups(self):
        """默认分组应为 openapi + sql"""
        assert DEFAULT_GROUPS == ["openapi", "sql"]
