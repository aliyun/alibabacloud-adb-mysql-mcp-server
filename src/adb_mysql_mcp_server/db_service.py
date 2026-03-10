"""Database connection service.

Provides the DBService async context manager supporting two connection modes:
  1. Direct mode: user configures ADB_MYSQL_USER + ADB_MYSQL_PASSWORD env vars;
     connects to the database directly via PyMySQL.
  2. Temporary account mode: no DB credentials configured; creates a temporary
     database account via OpenAPI, executes SQL, then deletes the account.

Usage:
    async with DBService(region_id, db_cluster_id, database) as svc:
        result = await svc.execute_sql("SELECT 1")
"""

import asyncio
import json
import logging
import os
import secrets
import socket
import string

import pymysql
from alibabacloud_adb20211201 import models as adb_models

from .openapi_client import get_adb_client

logger = logging.getLogger(__name__)

# Configurable timeouts via environment variables
CONNECT_TIMEOUT = int(os.getenv("ADB_MYSQL_CONNECT_TIMEOUT", "2"))


def _random_str(length: int = 8) -> str:
    """Generate a random lowercase alphanumeric string for temp account names.

    Uses secrets module for cryptographically secure random generation.
    """
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_password(length: int = 32) -> str:
    """Generate a random password that satisfies ADB MySQL password policy.

    Policy requires at least one uppercase, one lowercase, one digit,
    and one special character. Uses secrets module for cryptographically
    secure random generation.
    """
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    special = "_!@#$%^&*()-+="
    pool = upper + lower + digits + special
    chosen = [secrets.choice(upper), secrets.choice(lower), secrets.choice(digits), secrets.choice(special)]
    rest = [secrets.choice(pool) for _ in range(length - len(chosen))]
    # Shuffle using secrets
    chars = chosen + rest
    shuffled = []
    while chars:
        idx = secrets.randbelow(len(chars))
        shuffled.append(chars.pop(idx))
    return "".join(shuffled)


def _test_connect(host: str, port: int, timeout: int | None = None) -> bool:
    """Test TCP reachability of a host:port, used to probe VPC/public endpoints.

    Args:
        host: The hostname to connect to.
        port: The port number.
        timeout: Connection timeout in seconds. Defaults to CONNECT_TIMEOUT env var (2s).

    Returns:
        True if connection succeeded, False otherwise.
    """
    if timeout is None:
        timeout = CONNECT_TIMEOUT
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except Exception:
        return False


def _get_env_db_config() -> tuple[str | None, str | None, str | None, int | None, str | None]:
    """Read direct-connection DB config from environment variables.

    Returns:
        (user, password, host, port, database) tuple.
        All fields are None when user or password is not configured.
    """
    user = os.getenv("ADB_MYSQL_USER")
    password = os.getenv("ADB_MYSQL_PASSWORD")
    host = os.getenv("ADB_MYSQL_HOST")
    port = int(os.getenv("ADB_MYSQL_PORT", 3306))
    database = os.getenv("ADB_MYSQL_DATABASE")
    if user and password:
        return user, password, host or "localhost", port, database
    return None, None, None, None, None


class DBService:
    """Async context manager for ADB MySQL database connections and SQL execution.

    Direct mode (ADB_MYSQL_USER + ADB_MYSQL_PASSWORD configured):
      - region_id / db_cluster_id are optional.
      - Uses credentials from environment variables directly.

    Temporary account mode (only AK/SK configured):
      - region_id / db_cluster_id are required.
      - Auto-discovers connection address, creates/deletes temp accounts via OpenAPI.
    """

    def __init__(self, region_id: str | None = None, db_cluster_id: str | None = None, database: str | None = None):
        self.region_id = region_id
        self.db_cluster_id = db_cluster_id
        self.database = database

        self._env_user, self._env_password, self._env_host, self._env_port, env_db = _get_env_db_config()
        if self.database is None and env_db:
            self.database = env_db

        self._use_env = self._env_user is not None

        if not self._use_env and (not region_id or not db_cluster_id):
            raise ValueError(
                "region_id and db_cluster_id are required when ADB_MYSQL_USER/ADB_MYSQL_PASSWORD "
                "are not configured (temporary account mode requires OpenAPI access)."
            )

        self._temp_account_name: str | None = None
        self._temp_account_password: str | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._conn: pymysql.Connection | None = None

    async def __aenter__(self):
        if self._use_env:
            self._host = self._env_host
            self._port = self._env_port
        else:
            await asyncio.to_thread(self._discover_connection_address)
            await asyncio.to_thread(self._create_temp_account)

        await asyncio.to_thread(self._connect)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await asyncio.to_thread(self._close)
        if not self._use_env and self._temp_account_name:
            await asyncio.to_thread(self._delete_temp_account)

    # -- Public API ------------------------------------------------------------

    async def execute_sql(self, sql: str) -> str:
        """Execute SQL and return results as a JSON string.

        Queries return a JSON array of row dicts; non-queries return
        {"affected_rows": N}.
        """
        return await asyncio.to_thread(self._execute_sql_sync, sql)

    # -- Internal helpers ------------------------------------------------------

    def _discover_connection_address(self):
        """Discover the cluster connection address via DescribeClusterNetInfo.

        Prefers VPC (private) endpoints for lower latency; falls back to
        public endpoints if the VPC address is unreachable.
        """
        client = get_adb_client(self.region_id)
        req = adb_models.DescribeClusterNetInfoRequest(dbcluster_id=self.db_cluster_id)
        resp = client.describe_cluster_net_info(req)
        items = resp.body.items.address if resp.body.items and resp.body.items.address else []

        vpc_host, vpc_port, pub_host, pub_port = None, None, None, None
        for item in items:
            net_type = (item.net_type or "").lower()
            if net_type == "private" or "vpc" in net_type:
                vpc_host = item.connection_string
                vpc_port = int(item.port) if item.port else 3306
            elif net_type == "public":
                pub_host = item.connection_string
                pub_port = int(item.port) if item.port else 3306

        if vpc_host and _test_connect(vpc_host, vpc_port):
            self._host, self._port = vpc_host, vpc_port
        elif pub_host and _test_connect(pub_host, pub_port):
            self._host, self._port = pub_host, pub_port
        else:
            raise ConnectionError(
                f"Cannot connect to cluster {self.db_cluster_id}. "
                "Ensure the MCP Server can reach the cluster network (VPC or public)."
            )

    def _create_temp_account(self):
        """Create a temporary database account via CreateAccount API.

        Account name format: mcp_ + 10 random chars (e.g. mcp_a3b5x7k9m2).
        Account type: Normal (read/write, non-privileged).
        """
        self._temp_account_name = "mcp_" + _random_str(10)
        self._temp_account_password = _random_password(32)
        client = get_adb_client(self.region_id)
        req = adb_models.CreateAccountRequest(
            dbcluster_id=self.db_cluster_id,
            account_name=self._temp_account_name,
            account_password=self._temp_account_password,
            account_description="Temporary account created by MCP Server",
            account_type="Normal",
        )
        client.create_account(req)

    def _delete_temp_account(self):
        """Delete the temporary account via DeleteAccount API (best-effort).

        Logs a warning if deletion fails to help with troubleshooting
        orphaned accounts.
        """
        if not self._temp_account_name:
            return
        try:
            client = get_adb_client(self.region_id)
            req = adb_models.DeleteAccountRequest(
                dbcluster_id=self.db_cluster_id,
                account_name=self._temp_account_name,
            )
            client.delete_account(req)
            logger.debug(f"Successfully deleted temp account: {self._temp_account_name}")
        except Exception as e:
            logger.warning(
                f"Failed to delete temp account '{self._temp_account_name}': {e}. "
                "The account may need manual cleanup."
            )

    def _connect(self):
        """Establish a PyMySQL connection using the appropriate credentials."""
        user = self._env_user if self._use_env else self._temp_account_name
        password = self._env_password if self._use_env else self._temp_account_password
        self._conn = pymysql.connect(
            host=self._host,
            port=self._port,
            user=user,
            password=password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def _close(self):
        """Close the DB connection, silently ignoring errors."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _execute_sql_sync(self, sql: str) -> str:
        """Execute SQL synchronously, returning results as a JSON string.

        Queries with columns return a JSON array of row dicts.
        Statements without result columns return {"affected_rows": N}.
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            if not columns:
                return json.dumps({"affected_rows": cursor.rowcount}, ensure_ascii=False)
            return json.dumps(rows, ensure_ascii=False, default=str)
        finally:
            cursor.close()
