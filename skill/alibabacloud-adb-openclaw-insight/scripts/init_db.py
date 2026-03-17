"""
Initialize AnalyticDB MySQL database tables.
"""

from __future__ import annotations

import asyncio
import sys

from scripts.config import load_config
from scripts.db import close_connection_pool, execute_query


async def init_database() -> None:
    config = load_config()

    print("[Init] Starting database initialization...")
    print(f"[Init] Target database: {config.adb.host}:{config.adb.port}/{config.adb.database}")
    print(f"[Init] Session table: {config.adb.session_table}")

    create_session_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{config.adb.session_table}` (
            row_id BIGINT NOT NULL AUTO_INCREMENT,
            session_id VARCHAR(255) NOT NULL,
            `type` VARCHAR(100) NOT NULL,
            id VARCHAR(255),
            parent_id VARCHAR(255),
            timestamp DATETIME(3) NOT NULL,
            hostname VARCHAR(255),
            complete_session LONGTEXT NOT NULL,
            role VARCHAR(50) COMMENT 'Message role: user/assistant/tool',
            model VARCHAR(255) COMMENT 'Model name',
            api VARCHAR(255) COMMENT 'API identifier',
            provider VARCHAR(255) COMMENT 'Provider name',
            stop_reason VARCHAR(100) COMMENT 'Stop reason',
            input_tokens INT DEFAULT 0 COMMENT 'Input token count',
            output_tokens INT DEFAULT 0 COMMENT 'Output token count',
            cache_read_tokens INT DEFAULT 0 COMMENT 'Cache read token count',
            cache_write_tokens INT DEFAULT 0 COMMENT 'Cache write token count',
            total_tokens INT DEFAULT 0 COMMENT 'Total token count',
            total_cost DECIMAL(12, 6) DEFAULT 0 COMMENT 'Call cost',
            tool_name VARCHAR(255) COMMENT 'Tool name',
            tool_input LONGTEXT COMMENT 'Tool input parameters JSON',
            tool_use_id VARCHAR(255) COMMENT 'Tool call ID',
            is_error TINYINT DEFAULT 0 COMMENT 'Whether the tool call errored',
            content_text LONGTEXT COMMENT 'Plain text content',
            content_length INT DEFAULT 0 COMMENT 'Character length of content_text',
            thinking_text LONGTEXT COMMENT 'Model thinking process text',
            sender_id VARCHAR(255) COMMENT 'Sender user ID',
            PRIMARY KEY (row_id, timestamp),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_session_id (session_id),
            INDEX idx_type (`type`),
            INDEX idx_id (id),
            INDEX idx_parent_id (parent_id),
            INDEX idx_timestamp (timestamp),
            INDEX idx_hostname (hostname),
            INDEX idx_sender_id (sender_id),
            INDEX idx_role (role),
            INDEX idx_model (model),
            INDEX idx_tool_name (tool_name),
            INDEX idx_api (api),
            INDEX idx_provider (provider)
        )
        DISTRIBUTED BY HASH(row_id)
        PARTITION BY VALUE(DATE_FORMAT(timestamp, '%Y%m%d'))
    """

    try:
        execute_query(config.adb, create_session_table_sql)
        print(f"[Init] ✅ Session table {config.adb.session_table} created successfully (or already exists)")
    except Exception as error:
        print(f"[Init] ❌ Failed to create session table: {error}")
        raise

    logs_table = config.adb.logs_table or "openclaw_logs"
    print(f"[Init] Logs table: {logs_table}")

    create_logs_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{logs_table}` (
            id BIGINT NOT NULL AUTO_INCREMENT,
            timestamp DATETIME(3) NOT NULL,
            level VARCHAR(20) NOT NULL,
            subsystem VARCHAR(255),
            raw_field_0 TEXT,
            raw_field_1 TEXT,
            raw_field_2 TEXT,
            meta_runtime VARCHAR(64),
            meta_runtime_version VARCHAR(64),
            hostname VARCHAR(255),
            meta_name TEXT,
            meta_parent_names TEXT,
            meta_date DATETIME(3),
            meta_log_level_id INT,
            meta_log_level_name VARCHAR(20),
            meta_path TEXT,
            complete_log LONGTEXT NOT NULL,
            PRIMARY KEY (id, timestamp),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_timestamp (timestamp),
            INDEX idx_level (level),
            INDEX idx_subsystem (subsystem),
            INDEX idx_hostname (hostname),
            INDEX idx_meta_date (meta_date),
            INDEX idx_meta_log_level_id (meta_log_level_id),
            INDEX idx_meta_log_level_name (meta_log_level_name)
        )
        DISTRIBUTED BY HASH(id)
        PARTITION BY VALUE(DATE_FORMAT(timestamp, '%Y%m%d'))
    """

    try:
        execute_query(config.adb, create_logs_table_sql)
        print(f"[Init] ✅ Logs table {logs_table} created successfully (or already exists)")
    except Exception as error:
        print(f"[Init] ❌ Failed to create logs table: {error}")
        raise

    create_analysis_result_table_sql = """
        CREATE TABLE IF NOT EXISTS `openclaw_analysis_results` (
            row_id BIGINT NOT NULL AUTO_INCREMENT,
            run_id VARCHAR(36) NOT NULL COMMENT 'Unique ID for each analysis run (UUID)',
            case_name VARCHAR(100) NOT NULL COMMENT 'Analysis case name, e.g. L2-1, L2-2, ...',
            analysis_type VARCHAR(50) NOT NULL COMMENT 'L1_OPERATIONAL / L2_BEHAVIOR / L3_ORGANIZATIONAL',
            status VARCHAR(20) NOT NULL DEFAULT 'success' COMMENT 'success / failure / skipped',
            elapsed_seconds DOUBLE DEFAULT NULL COMMENT 'Execution time in seconds',
            time_range_start VARCHAR(30) DEFAULT NULL COMMENT 'Analysis window start timestamp',
            time_range_end VARCHAR(30) DEFAULT NULL COMMENT 'Analysis window end timestamp',
            summary TEXT DEFAULT NULL COMMENT 'Human-readable summary of the result',
            details LONGTEXT NOT NULL COMMENT 'Full analysis result JSON',
            error_message TEXT DEFAULT NULL COMMENT 'Error message if status is failure',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (row_id),
            INDEX idx_run_id (run_id),
            INDEX idx_case_name (case_name),
            INDEX idx_analysis_type (analysis_type)
        )
    """

    try:
        execute_query(config.adb, create_analysis_result_table_sql)
        print("[Init] ✅ Analysis results table openclaw_analysis_results created successfully (or already exists)")
    except Exception as error:
        print(f"[Init] ❌ Failed to create analysis results table: {error}")
        raise

    print("[Init] ✅ Database initialization completed")
    close_connection_pool()


if __name__ == "__main__":
    try:
        asyncio.run(init_database())
    except Exception as error:
        print(f"[Init] Execution failed: {error}")
        sys.exit(1)
