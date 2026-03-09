"""openapi_client.py 模块的单元测试

测试范围：
  - get_aksk 函数从环境变量读取 AK/SK/STS
  - get_adb_client 函数创建 ADB MySQL SDK 客户端实例
"""

import os
from unittest.mock import patch

from adb_mysql_mcp_server.openapi_client import get_aksk, get_adb_client


class TestGetAksk:
    """测试 get_aksk——从环境变量读取阿里云访问密钥"""

    def test_reads_from_env(self):
        """环境变量全部设置时，应正确返回 AK、SK 和 STS Token"""
        env = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "test_ak",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test_sk",
            "ALIBABA_CLOUD_SECURITY_TOKEN": "test_sts",
        }
        with patch.dict(os.environ, env, clear=False):
            ak, sk, sts = get_aksk()
            assert ak == "test_ak"
            assert sk == "test_sk"
            assert sts == "test_sts"

    def test_returns_none_when_missing(self):
        """环境变量为空字符串时，返回值也是空字符串（由调用方判断是否有效）"""
        env = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "",
        }
        with patch.dict(os.environ, env, clear=False):
            ak, sk, sts = get_aksk()
            assert ak == ""

    def test_sts_optional(self):
        """STS Token 是可选的，未设置时应返回 None"""
        env = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ALIBABA_CLOUD_SECURITY_TOKEN", None)
            ak, sk, sts = get_aksk()
            assert ak == "ak"
            assert sts is None


class TestGetAdbClient:
    """测试 get_adb_client——创建 ADB MySQL SDK 客户端"""

    def test_returns_client_instance(self):
        """传入 region_id 后，应返回一个非空的客户端实例"""
        env = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "test_ak",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test_sk",
        }
        with patch.dict(os.environ, env, clear=False):
            client = get_adb_client("cn-hangzhou")
            assert client is not None
