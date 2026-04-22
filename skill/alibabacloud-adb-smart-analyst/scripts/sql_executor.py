#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 3 - SQL Execution Mixin: execute queries against ADB MySQL and return results
"""

try:
    from .utils import _dumps, logger
except ImportError:
    from utils import _dumps, logger


class SqlExecutorMixin:
    """Step 3 SQL executor, auto-injects ADB high-performance hint"""

    def execute_adb_sql(self, sql: str, attempt: int = 1) -> str:
        """
        [Step 3] SQL executor - execute queries in ADB MySQL

        Behavior: executes SQL and returns results or raw error messages,
                  auto-injects ADB high-performance hint.

        Args:
            sql (str, required): SQL statement to execute
                - supports: SELECT, aggregation, JOIN, window functions
                - example: "SELECT region, SUM(revenue) FROM sales GROUP BY region"
            attempt (int, default 1): current call attempt passed by the Agent

        Returns:
            success: {status:success, row_count:N, columns:[...], data:[...]}
            failure: {status:error, message:"raw MySQL error message"}

        Examples:
            execute_adb_sql(sql="SELECT * FROM dim_product LIMIT 10")
            execute_adb_sql(sql="SELECT region, SUM(amt) FROM fact_order GROUP BY region", attempt=2)
        """
        logger.info(f"[Step 3 Attempt {attempt}/{self.MAX_ATTEMPTS}] Executing SQL: {sql[:100]}...")

        if attempt > self.MAX_ATTEMPTS:
            return _dumps({
                "status":     "error",
                "error_type": "STEP3_MAX_ATTEMPTS_EXCEEDED",
                "message":    f"Step 3 (SQL execution) reached max attempts ({self.MAX_ATTEMPTS}). SQL cannot be executed, consider retrying Step 2 to verify metadata or Step 1 to re-fetch definitions."
            })

        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Auto-inject ADB high-performance query hint
                if "adb_config" not in sql.lower():
                    sql = f"/*+ adb_config(query_type=complex) */ {sql}"

                cursor.execute(sql)

                # Retrieve column names
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                # Fetch rows (capped to prevent large result sets)
                rows = cursor.fetchmany(100)

                # Convert to dict format
                data = []
                for row in rows:
                    if isinstance(row, dict):
                        data.append({col: row.get(col) for col in columns})
                    else:
                        data.append({col: (row[i] if i < len(row) else None)
                                     for i, col in enumerate(columns)})

                logger.info(f"[Step 3 Attempt {attempt}] SQL executed successfully: {len(data)} row(s)")
                return _dumps({
                    "status":    "success",
                    "row_count": len(data),
                    "columns":   columns,
                    "data":      data
                })

        except Exception as e:
            error_message = str(e)
            logger.error(f"[Step 3 Attempt {attempt}] SQL execution failed: {error_message}")
            # Return the raw MySQL error message without any wrapping
            return _dumps({
                "status":  "error",
                "message": error_message
            })
        finally:
            if conn:
                conn.close()
