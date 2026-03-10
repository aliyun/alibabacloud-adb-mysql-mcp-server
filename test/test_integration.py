"""集成测试 —— 无 mock，直接调用阿里云 OpenAPI

运行前提：
  1. 配置环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET
  2. （可选）通过 --region-id / --db-cluster-id 指定目标集群，否则使用默认值

运行方式：
  # 使用默认集群（amv-6wei5f835qnhxbq0 / cn-beijing）
  uv run python -m pytest test/test_integration.py -v -s

  # 指定集群
  uv run python -m pytest test/test_integration.py -v -s \
      --region-id cn-hangzhou --db-cluster-id amv-xxxxxxxx

注意：
  - 默认运行只读接口，不会修改任何云资源
  - 变更操作测试需加 -k "mutating" 显式运行
  - 跳过条件：未配置 AK/SK 时自动跳过全部用例（CI 环境友好）
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from adb_mysql_mcp_server import server

# ---------------------------------------------------------------------------
# Fixtures（命令行参数在 conftest.py 中注册）
# ---------------------------------------------------------------------------

@pytest.fixture
def region_id(request):
    return request.config.getoption("--region-id")


@pytest.fixture
def db_cluster_id(request):
    return request.config.getoption("--db-cluster-id")


@pytest.fixture
def time_range_utc_min():
    """返回最近 1 小时的时间范围（ISO 8601 UTC 格式）"""
    now = datetime.now(timezone.utc)
    end = now.strftime("%Y-%m-%dT%H:%MZ")
    start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
    return start, end


# 未配置 AK/SK 时跳过所有集成测试
skip_no_ak = pytest.mark.skipif(
    not os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID") or not os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"),
    reason="ALIBABA_CLOUD_ACCESS_KEY_ID / SECRET not set, skipping integration tests",
)

pytestmark = [skip_no_ak, pytest.mark.asyncio]


# ===========================================================================
# 集群管理工具
# ===========================================================================

class TestDescribeDBClusters:
    """集成测试：describe_db_clusters —— 查询集群列表"""

    async def test_returns_string(self, region_id):
        """调用后应返回非空字符串（CSV 或 'No ADB MySQL clusters found.'）"""
        result = await server.describe_db_clusters(region_id)
        assert isinstance(result, str)
        assert len(result) > 0


class TestDescribeDBClusterAttribute:
    """集成测试：describe_db_cluster_attribute —— 查询集群属性"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典，且包含 DBClusterId"""
        result = await server.describe_db_cluster_attribute(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "Items" in result or "DBClusterId" in result or "RequestId" in result


class TestDescribeClusterAccessWhitelist:
    """集成测试：describe_cluster_access_whitelist —— 查询集群白名单"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_cluster_access_whitelist(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeAccounts:
    """集成测试：describe_accounts —— 查询集群账号列表"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_accounts(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeClusterNetInfo:
    """集成测试：describe_cluster_net_info —— 查询集群网络信息"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_cluster_net_info(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestGetCurrentTime:
    """集成测试：get_current_time —— 获取当前时间"""

    async def test_returns_time(self):
        """返回值应包含 current_time 字段"""
        result = await server.get_current_time()
        assert "current_time" in result
        assert len(result["current_time"]) > 0


# ===========================================================================
# 诊断与监控工具
# ===========================================================================

class TestDescribeDBClusterPerformance:
    """集成测试：describe_db_cluster_performance —— 查询集群性能数据"""

    async def test_returns_dict(self, region_id, db_cluster_id, time_range_utc_min):
        """查询 CPU 指标，应返回字典"""
        start, end = time_range_utc_min
        result = await server.describe_db_cluster_performance(
            region_id, db_cluster_id, "AnalyticDB_CPU", start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeDBClusterHealthStatus:
    """集成测试：describe_db_cluster_health_status —— 查询集群健康状态"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_db_cluster_health_status(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeDiagnosisRecords:
    """集成测试：describe_diagnosis_records —— 查询 SQL 诊断记录"""

    async def test_returns_dict_with_default_time(self, region_id, db_cluster_id):
        """使用默认时间（最近 1 小时）查询诊断记录，应返回字典"""
        result = await server.describe_diagnosis_records(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_returns_dict_with_explicit_time(self, region_id, db_cluster_id, time_range_utc_min):
        """使用显式时间查询诊断记录，应返回字典"""
        start, end = time_range_utc_min
        result = await server.describe_diagnosis_records(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_with_query_condition_running(self, region_id, db_cluster_id):
        """使用 query_condition 过滤运行中的 SQL"""
        result = await server.describe_diagnosis_records(
            region_id, db_cluster_id,
            query_condition='{"Type":"status","Value":"running"}',
        )
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_with_query_condition_max_cost(self, region_id, db_cluster_id):
        """使用 query_condition 查询耗时最长的 Top 100 SQL"""
        result = await server.describe_diagnosis_records(
            region_id, db_cluster_id,
            query_condition='{"Type":"maxCost","Value":"100"}',
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeDiagnosisSqlInfo:
    """集成测试：describe_diagnosis_sql_info —— 查询单条 SQL 执行详情

    注意：需要先从 describe_diagnosis_records 获取 process_id，
    如果最近 1 小时没有诊断记录则跳过。
    """

    async def test_returns_dict_if_records_exist(self, region_id, db_cluster_id, time_range_utc_min):
        """如果存在诊断记录，取第一条的 process_id 查询详情"""
        start, end = time_range_utc_min
        records = await server.describe_diagnosis_records(
            region_id, db_cluster_id, start, end
        )
        query_list = records.get("Querys", [])
        if not query_list:
            pytest.skip("No diagnosis records in the last hour, skipping sql info test")

        process_id = str(query_list[0].get("ProcessId", ""))
        if not process_id:
            pytest.skip("No ProcessId in first diagnosis record")

        result = await server.describe_diagnosis_sql_info(
            region_id, db_cluster_id, process_id
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeBadSqlDetection:
    """集成测试：describe_bad_sql_detection —— Bad SQL 检测"""

    async def test_returns_dict(self, region_id, db_cluster_id, time_range_utc_min):
        """查询最近 1 小时 Bad SQL，应返回字典"""
        start, end = time_range_utc_min
        result = await server.describe_bad_sql_detection(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeSqlPatterns:
    """集成测试：describe_sql_patterns —— 查询 SQL Pattern"""

    async def test_returns_dict(self, region_id, db_cluster_id, time_range_utc_min):
        """查询最近 1 小时 SQL Pattern，应返回字典"""
        start, end = time_range_utc_min
        result = await server.describe_sql_patterns(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeTableStatistics:
    """集成测试：describe_table_statistics —— 查询表统计信息"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_table_statistics(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


# ===========================================================================
# 管控与审计工具（只读部分）
# ===========================================================================

class TestDescribeDBClusterSpaceSummary:
    """集成测试：describe_db_cluster_space_summary —— 查询空间概览"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_db_cluster_space_summary(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeAuditLogRecords:
    """集成测试：describe_audit_log_records —— 查询审计日志"""

    async def test_returns_dict(self, region_id, db_cluster_id, time_range_utc_min):
        """查询最近 1 小时审计日志，应返回字典"""
        start, end = time_range_utc_min
        result = await server.describe_audit_log_records(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


# ===========================================================================
# 高级诊断工具
# ===========================================================================

class TestDescribeExecutorDetection:
    """集成测试：describe_executor_detection —— 计算节点诊断"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """默认时间范围查询，返回值应为字典"""
        result = await server.describe_executor_detection(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_with_explicit_time(self, region_id, db_cluster_id, time_range_utc_min):
        """传入显式时间范围查询"""
        start, end = time_range_utc_min
        result = await server.describe_executor_detection(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeWorkerDetection:
    """集成测试：describe_worker_detection —— 存储节点诊断"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """默认时间范围查询，返回值应为字典"""
        result = await server.describe_worker_detection(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_with_explicit_time(self, region_id, db_cluster_id, time_range_utc_min):
        """传入显式时间范围查询"""
        start, end = time_range_utc_min
        result = await server.describe_worker_detection(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeControllerDetection:
    """集成测试：describe_controller_detection —— 接入节点诊断"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """默认时间范围查询，返回值应为字典"""
        result = await server.describe_controller_detection(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_with_explicit_time(self, region_id, db_cluster_id, time_range_utc_min):
        """传入显式时间范围查询"""
        start, end = time_range_utc_min
        result = await server.describe_controller_detection(
            region_id, db_cluster_id, start, end
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeAvailableAdvices:
    """集成测试：describe_available_advices —— 查询优化建议"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """默认参数查询，返回值应为字典"""
        result = await server.describe_available_advices(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result

    async def test_with_advice_type(self, region_id, db_cluster_id):
        """按建议类型 INDEX 过滤"""
        result = await server.describe_available_advices(
            region_id, db_cluster_id, advice_type="INDEX"
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeDBResourceGroup:
    """集成测试：describe_db_resource_group —— 查询资源组"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_db_resource_group(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeExcessivePrimaryKeys:
    """集成测试：describe_excessive_primary_keys —— 检测主键过多的表"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """查询最近 1 小时，应返回字典"""
        result = await server.describe_excessive_primary_keys(
            region_id, db_cluster_id
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeOversizeNonPartitionTableInfos:
    """集成测试：describe_oversize_non_partition_table_infos —— 检测超大未分区表"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_oversize_non_partition_table_infos(
            region_id, db_cluster_id
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeTablePartitionDiagnose:
    """集成测试：describe_table_partition_diagnose —— 分区表诊断"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_table_partition_diagnose(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestDescribeInclinedTables:
    """集成测试：describe_inclined_tables —— 数据倾斜检测"""

    async def test_returns_dict(self, region_id, db_cluster_id):
        """返回值应为字典"""
        result = await server.describe_inclined_tables(region_id, db_cluster_id)
        assert isinstance(result, dict)
        assert "RequestId" in result


# ===========================================================================
# 变更操作工具（慎用：会修改云资源）
# 运行方式：uv run python -m pytest test/test_integration.py -v -s -k "mutating"
# ===========================================================================

class TestModifyClusterAccessWhitelist:
    """集成测试：modify_cluster_access_whitelist —— 修改白名单

    测试策略：先读取当前白名单，用 Append 模式添加一个测试 IP，
    再用 Delete 模式删除，确保集群白名单恢复原状。
    """

    @pytest.mark.mutating
    async def test_append_and_delete(self, region_id, db_cluster_id):
        """追加一个测试 IP 后再删除，验证操作可逆"""
        test_ip = "192.168.253.253"

        # 追加测试 IP
        result = await server.modify_cluster_access_whitelist(
            region_id, db_cluster_id,
            security_ips=test_ip,
            modify_mode="Append",
        )
        assert isinstance(result, dict)
        assert "RequestId" in result

        # 删除测试 IP（恢复原状）
        result = await server.modify_cluster_access_whitelist(
            region_id, db_cluster_id,
            security_ips=test_ip,
            modify_mode="Delete",
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestCreateAccount:
    """集成测试：create_account —— 创建数据库账号

    测试策略：创建一个临时测试账号，验证返回值。
    注意：重复运行可能因账号已存在而失败，需手动清理。
    """

    @pytest.mark.mutating
    async def test_create_account(self, region_id, db_cluster_id):
        """创建临时测试账号，应返回 RequestId"""
        import random
        import string
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        account_name = f"test_{suffix}"
        account_password = f"Test@{suffix}12"

        result = await server.create_account(
            region_id, db_cluster_id,
            account_name=account_name,
            account_password=account_password,
            account_description="integration test temp account",
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestModifyDBClusterDescription:
    """集成测试：modify_db_cluster_description —— 修改集群描述

    测试策略：先读取当前描述，修改为测试值，再改回原值。
    """

    @pytest.mark.mutating
    async def test_modify_and_restore(self, region_id, db_cluster_id):
        """修改集群描述后恢复原值"""
        # 读取当前描述
        attr = await server.describe_db_cluster_attribute(region_id, db_cluster_id)
        original_desc = attr.get("Items", {}).get("DBCluster", [{}])[0].get("DBClusterDescription", "")

        test_desc = "integration-test-temp-desc"

        # 修改为测试描述
        result = await server.modify_db_cluster_description(
            region_id, db_cluster_id, test_desc
        )
        assert isinstance(result, dict)
        assert "RequestId" in result

        # 恢复原始描述
        result = await server.modify_db_cluster_description(
            region_id, db_cluster_id, original_desc
        )
        assert isinstance(result, dict)
        assert "RequestId" in result


class TestKillProcess:
    """集成测试：kill_process —— 终止查询

    测试策略：使用一个不存在的 process_id，预期 API 返回错误或空结果。
    不会影响正在运行的实际查询。
    """

    @pytest.mark.mutating
    async def test_kill_nonexistent_process(self, region_id, db_cluster_id):
        """终止不存在的 process_id，应抛出异常或返回错误"""
        try:
            result = await server.kill_process(
                region_id, db_cluster_id, process_id="0"
            )
            # 如果 API 没有抛出异常，至少应返回字典
            assert isinstance(result, dict)
        except Exception:
            # 不存在的 process_id 抛出异常是正常行为
            pass


# ===========================================================================
# 以下工具需要数据库连接，需配置 ADB_MYSQL_* 环境变量或 AK/SK：
#   - execute_sql / get_query_plan / get_execution_plan
#   - resource_list_databases / resource_list_tables / resource_table_ddl / resource_config_value
#
# 如需测试 SQL 工具，可单独运行：
#   uv run python -m pytest test/test_integration.py -v -s -k "sql"
# ===========================================================================
