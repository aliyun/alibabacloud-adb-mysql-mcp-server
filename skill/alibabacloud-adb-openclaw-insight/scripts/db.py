"""
MySQL connection utilities using mysql-connector-python.

Each operation creates a fresh connection and closes it immediately after use,
avoiding connection-pool exhaustion / deadlock issues that arise when pooled
connections are shared across sync and async call paths.
"""

from __future__ import annotations

import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import mysql.connector

from scripts.config import AdbConfig

SqlValue = str | int | float | bool | None

# Dedicated thread pool for async DB wrappers
_db_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db")


def _create_connection(adb_config: AdbConfig):
    """Create a new standalone MySQL connection (not pooled)."""
    return mysql.connector.connect(
        host=adb_config.host,
        port=adb_config.port,
        user=adb_config.username,
        password=adb_config.password,
        database=adb_config.database,
        connection_timeout=30,
        autocommit=True,
    )


def close_connection_pool() -> None:
    """No-op kept for backward compatibility with callers."""
    print("[DB] Connection cleanup (no-op, using per-call connections)")


def execute_query(adb_config: AdbConfig, sql: str, params: Optional[tuple | list] = None) -> list[dict]:
    """Execute a SELECT query and return rows as a list of dicts."""
    start_time = time.time()
    connection = _create_connection(adb_config)
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        cursor.close()
        elapsed = time.time() - start_time
        print(f"[DB] Query returned {len(rows)} rows in {elapsed:.1f}s")
        return rows
    finally:
        connection.close()


async def execute_query_async(adb_config: AdbConfig, sql: str, params: Optional[tuple | list] = None) -> list[dict]:
    """Async wrapper for execute_query using a dedicated DB thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_db_executor, execute_query, adb_config, sql, params)


def execute_batch_insert(
    adb_config: AdbConfig,
    table_name: str,
    columns: list[str],
    rows: list[list[SqlValue]],
) -> int:
    """Batch insert rows into a table. Returns the number of affected rows."""
    if not rows:
        return 0

    connection = _create_connection(adb_config)
    try:
        escaped_columns = ", ".join(f"`{col}`" for col in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO `{table_name}` ({escaped_columns}) VALUES ({placeholders})"

        cursor = connection.cursor()
        cursor.executemany(sql, [tuple(row) for row in rows])
        affected = cursor.rowcount
        cursor.close()
        return affected
    finally:
        connection.close()