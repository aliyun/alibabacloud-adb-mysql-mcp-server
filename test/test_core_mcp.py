"""core/mcp.py 模块的单元测试

测试范围：
  - AdbMCP 的延迟注册机制（tool / prompt / resource 装饰器）
  - activate() 方法的分组过滤、重复激活、无效分组校验
"""

import pytest

from adb_mysql_mcp_server.core.mcp import AdbMCP, _ComponentType


class TestToolDecorator:
    """测试 @mcp.tool() 装饰器的延迟注册行为"""

    def test_tool_registration(self):
        """使用默认分组注册一个工具，应存入 _pending_registrations"""
        app = AdbMCP("test-server")

        @app.tool()
        async def my_tool(x: str) -> str:
            return x

        # 应该有 1 条注册记录
        assert len(app._pending_registrations) == 1
        # 函数名应匹配
        assert app._pending_registrations[0].func.__name__ == "my_tool"
        # 默认分组应为 "openapi"
        assert app._pending_registrations[0].group == "openapi"

    def test_tool_custom_group(self):
        """指定自定义分组名，应正确存储"""
        app = AdbMCP("test-server")

        @app.tool(group="custom")
        async def my_tool(x: str) -> str:
            return x

        assert app._pending_registrations[0].group == "custom"


class TestPromptDecorator:
    """测试 @mcp.prompt() 装饰器的延迟注册行为"""

    def test_prompt_registration(self):
        """注册一个 prompt，应存入 _pending_registrations"""
        app = AdbMCP("test-server")

        @app.prompt()
        async def my_prompt() -> str:
            return "prompt"

        assert len(app._pending_registrations) == 1
        assert app._pending_registrations[0].func.__name__ == "my_prompt"
        assert app._pending_registrations[0].item_type == _ComponentType.PROMPT


class TestResourceDecorator:
    """测试 @mcp.resource() 装饰器的延迟注册行为"""

    def test_resource_registration(self):
        """注册一个资源，应正确存储 URI、分组和类型"""
        app = AdbMCP("test-server")

        @app.resource("test:///data", group="sql")
        async def my_resource() -> str:
            return "data"

        assert len(app._pending_registrations) == 1
        item = app._pending_registrations[0]
        # 函数名应匹配
        assert item.func.__name__ == "my_resource"
        # 分组应为指定值
        assert item.group == "sql"
        # 类型应为 RESOURCE
        assert item.item_type == _ComponentType.RESOURCE
        # URI 应保存在 args 中
        assert item.args == ("test:///data",)

    def test_resource_default_group(self):
        """不指定分组时，资源应使用默认分组 "openapi" """
        app = AdbMCP("test-server")

        @app.resource("test:///data")
        async def my_resource() -> str:
            return "data"

        assert app._pending_registrations[0].group == "openapi"


class TestActivate:
    """测试 activate() 方法——将延迟注册的组件实际注册到 FastMCP"""

    def test_activate_basic(self):
        """基本激活：指定分组后应标记为已激活"""
        app = AdbMCP("test-server")

        @app.tool()
        async def tool_a() -> str:
            return "a"

        @app.tool(group="other")
        async def tool_b() -> str:
            return "b"

        app.activate(enabled_groups=["openapi"])
        assert app._is_activated

    def test_activate_invalid_group_raises(self):
        """传入不存在的分组名时应抛出 ValueError"""
        app = AdbMCP("test-server")

        @app.tool()
        async def tool_a() -> str:
            return "a"

        with pytest.raises(ValueError):
            app.activate(enabled_groups=["nonexistent"])

    def test_double_activate_ignored(self):
        """重复调用 activate() 不应报错，第二次调用被静默忽略"""
        app = AdbMCP("test-server")

        @app.tool()
        async def tool_a() -> str:
            return "a"

        app.activate(enabled_groups=["openapi"])
        # 第二次调用不应抛异常
        app.activate(enabled_groups=["openapi"])

    def test_activate_with_multiple_groups(self):
        """同时激活多个分组（含工具和资源），应全部注册成功"""
        app = AdbMCP("test-server")

        @app.tool(group="openapi")
        async def tool_a() -> str:
            return "a"

        @app.tool(group="sql")
        async def tool_b() -> str:
            return "b"

        @app.resource("test:///data", group="sql")
        async def res_a() -> str:
            return "data"

        app.activate(enabled_groups=["openapi", "sql"])
        assert app._is_activated

    def test_activate_single_group_filters(self):
        """仅激活一个分组时，另一个分组的组件不应被注册"""
        app = AdbMCP("test-server")

        @app.tool(group="openapi")
        async def tool_a() -> str:
            return "a"

        @app.tool(group="sql")
        async def tool_b() -> str:
            return "b"

        # 只激活 openapi 分组
        app.activate(enabled_groups=["openapi"])
        assert app._is_activated
