"""db_service.py 模块的单元测试

测试范围：
  - _random_str / _random_password 随机字符串生成
  - _get_env_db_config 环境变量读取
  - DBService 初始化逻辑（直连模式 vs 临时账号模式）
"""

import os
import asyncio
from unittest.mock import patch

import pytest

from adb_mysql_mcp_server.db_service import _random_str, _random_password, _get_env_db_config, DBService


class TestRandomStr:
    """测试 _random_str——生成临时账号名的随机字符串"""

    def test_length(self):
        """生成的字符串长度应与参数一致"""
        s = _random_str(12)
        assert len(s) == 12

    def test_default_length(self):
        """不传参时默认长度应为 8"""
        s = _random_str()
        assert len(s) == 8

    def test_all_lowercase_or_digit(self):
        """生成的字符串应仅包含小写字母和数字"""
        s = _random_str(100)
        assert s == s.lower()
        assert all(c.isalnum() for c in s)


class TestRandomPassword:
    """测试 _random_password——生成满足 ADB MySQL 密码策略的随机密码"""

    def test_length(self):
        """生成的密码长度应与参数一致"""
        pw = _random_password(32)
        assert len(pw) == 32

    def test_contains_required_classes(self):
        """密码应至少包含大写字母、小写字母和数字（满足密码复杂度要求）"""
        pw = _random_password(32)
        assert any(c.isupper() for c in pw), "应包含大写字母"
        assert any(c.islower() for c in pw), "应包含小写字母"
        assert any(c.isdigit() for c in pw), "应包含数字"


class TestGetEnvDbConfig:
    """测试 _get_env_db_config——从环境变量读取数据库直连配置"""

    def test_returns_config_when_set(self):
        """所有环境变量都设置时，应完整返回配置"""
        env = {
            "ADB_MYSQL_USER": "user1",
            "ADB_MYSQL_PASSWORD": "pass1",
            "ADB_MYSQL_HOST": "10.0.0.1",
            "ADB_MYSQL_PORT": "3307",
            "ADB_MYSQL_DATABASE": "testdb",
        }
        with patch.dict(os.environ, env, clear=False):
            user, password, host, port, db = _get_env_db_config()
            assert user == "user1"
            assert password == "pass1"
            assert host == "10.0.0.1"
            assert port == 3307
            assert db == "testdb"

    def test_returns_nones_when_missing(self):
        """未设置用户名/密码时，所有字段应为 None"""
        with patch.dict(os.environ, {}, clear=True):
            user, password, host, port, db = _get_env_db_config()
            assert user is None
            assert password is None

    def test_defaults_host_to_localhost_when_missing(self):
        """设置了用户名/密码但未设置 HOST 时，HOST 应默认为 localhost"""
        env = {
            "ADB_MYSQL_USER": "u",
            "ADB_MYSQL_PASSWORD": "p",
        }
        with patch.dict(os.environ, env, clear=False):
            user, password, host, port, db = _get_env_db_config()
            assert host == "localhost"
            assert port == 3306


class TestDBServiceInit:
    """测试 DBService 的初始化逻辑——根据环境变量选择连接模式"""

    def test_uses_env_when_available(self):
        """配置了 ADB_MYSQL_USER/PASSWORD 时，应使用直连模式"""
        env = {
            "ADB_MYSQL_USER": "u",
            "ADB_MYSQL_PASSWORD": "p",
            "ADB_MYSQL_HOST": "h",
            "ADB_MYSQL_PORT": "3306",
        }
        with patch.dict(os.environ, env, clear=False):
            svc = DBService("cn-hangzhou", "amv-test")
            assert svc._use_env is True

    def test_env_mode_without_region_id(self):
        """直连模式下，不传 region_id 也不应报错"""
        env = {
            "ADB_MYSQL_USER": "u",
            "ADB_MYSQL_PASSWORD": "p",
            "ADB_MYSQL_HOST": "h",
            "ADB_MYSQL_PORT": "3306",
        }
        with patch.dict(os.environ, env, clear=False):
            svc = DBService()
            assert svc._use_env is True
            assert svc.region_id is None

    def test_falls_back_when_no_env(self):
        """未配置 USER/PASSWORD 时，应使用临时账号模式（需要 region_id 和 cluster_id）"""
        with patch.dict(os.environ, {}, clear=True):
            svc = DBService("cn-hangzhou", "amv-test")
            assert svc._use_env is False

    def test_no_env_no_region_raises(self):
        """临时账号模式下，不传 region_id 应抛出 ValueError"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="region_id and db_cluster_id are required"):
                DBService()

    def test_temp_account_is_deleted_when_connect_fails(self, monkeypatch):
        """临时账号创建后若连接失败，应主动清理账号。"""
        events = []

        def fake_discover(self):
            events.append("discover")
            self._host = "127.0.0.1"
            self._port = 3306

        def fake_create(self):
            events.append("create")
            self._temp_account_name = "mcp_test"
            self._temp_account_password = "password"

        def fake_connect(self):
            events.append("connect")
            raise RuntimeError("connect failed")

        def fake_delete(self):
            events.append("delete")

        monkeypatch.setattr(DBService, "_discover_connection_address", fake_discover)
        monkeypatch.setattr(DBService, "_create_temp_account", fake_create)
        monkeypatch.setattr(DBService, "_connect", fake_connect)
        monkeypatch.setattr(DBService, "_delete_temp_account", fake_delete)

        with patch.dict(os.environ, {}, clear=True):
            svc = DBService("cn-hangzhou", "amv-test")
            with pytest.raises(RuntimeError, match="connect failed"):
                asyncio.run(svc.__aenter__())

        assert events == ["discover", "create", "connect", "delete"]
