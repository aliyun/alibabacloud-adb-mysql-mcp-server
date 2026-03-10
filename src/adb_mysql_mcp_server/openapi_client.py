"""Alibaba Cloud ADB MySQL OpenAPI client factory.

Reads AK/SK/STS from environment variables and creates an ADB MySQL
2021-12-01 SDK client. The SDK automatically routes to the correct
regional endpoint based on region_id.

SDK reference:
  https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/developer-reference/api-adb-2021-12-01-overview
"""

import os

from alibabacloud_adb20211201.client import Client as AdbClient
from alibabacloud_tea_openapi.models import Config

# Configurable timeouts via environment variables (in milliseconds)
API_CONNECT_TIMEOUT = int(os.getenv("ADB_API_CONNECT_TIMEOUT", "10000"))  # 10s default
API_READ_TIMEOUT = int(os.getenv("ADB_API_READ_TIMEOUT", "300000"))  # 5min default


def get_aksk() -> tuple[str | None, str | None, str | None]:
    """Read Alibaba Cloud credentials from environment variables.

    Returns:
        (access_key_id, access_key_secret, security_token) tuple.
        Unconfigured fields are None.
    """
    ak = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    sk = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    sts = os.getenv("ALIBABA_CLOUD_SECURITY_TOKEN")
    return ak, sk, sts


def get_adb_client(region_id: str) -> AdbClient:
    """Create an ADB MySQL SDK client for the given region.

    The SDK resolves the endpoint automatically
    (e.g. cn-hangzhou -> adb.cn-hangzhou.aliyuncs.com).

    Args:
        region_id: Alibaba Cloud region ID (e.g. cn-hangzhou, cn-shanghai).

    Returns:
        An AdbClient instance ready to make API calls.
    """
    ak, sk, sts = get_aksk()
    config = Config(
        access_key_id=ak,
        access_key_secret=sk,
        security_token=sts,
        region_id=region_id,
        protocol="https",
        connect_timeout=API_CONNECT_TIMEOUT,
        read_timeout=API_READ_TIMEOUT,
    )
    return AdbClient(config)
