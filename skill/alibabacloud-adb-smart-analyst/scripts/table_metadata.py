#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 2 - Physical Alignment Mixin: batch table metadata query
"""

from typing import List, Dict

try:
    from .utils import _dumps, logger
except ImportError:
    from utils import _dumps, logger


class TableMetadataMixin:
    """Step 2 physical table metadata query, supports internal / external catalog dual paths"""

    def get_batch_table_metadata(self, tables: List[Dict[str, str]], attempt: int = 1) -> str:
        """
        [Step 2] Physical table metadata query - verify column existence

        Args:
            tables (list, required): list of table descriptors, each a dict with:
                - catalog (str, optional): data catalog name. Omitted or "adb" queries information_schema;
                             others are external catalogs, queried via DESC
                - schema  (str, required): database name
                - table   (str, required): table name
            attempt (int, default 1): current call attempt passed by the Agent

        Returns:
            success: {status:success, data:{"[catalog.]schema.table": [{column_name, column_type, column_comment, column_key}]}}
            failure: {status:error, message:...}

        Examples:
            get_batch_table_metadata([{"schema":"db","table":"t"}])
            get_batch_table_metadata([{"catalog":"adb","schema":"db","table":"t"}])
            # external catalog: queried via DESC catalog.schema.table
            get_batch_table_metadata([{"catalog":"hive_catalog","schema":"sales","table":"orders"}])
        """
        logger.info(f"[Step 2 Attempt {attempt}/{self.MAX_ATTEMPTS}] Querying table metadata: tables={tables}")

        if attempt > self.MAX_ATTEMPTS:
            return _dumps({
                "status":     "error",
                "error_type": "STEP2_MAX_ATTEMPTS_EXCEEDED",
                "message":    f"Step 2 (physical alignment) reached max attempts ({self.MAX_ATTEMPTS}). Metadata inconsistency detected, consider retrying Step 1 to re-fetch semantic definitions."
            })

        if not tables:
            return _dumps({
                "status":  "error",
                "message": "No tables provided."
            })

        conn = None
        try:
            conn = self._get_connection()
            result = {}

            for table_info in tables:
                table_name   = table_info.get('table')
                schema_name  = table_info.get('schema')
                catalog_name = table_info.get('catalog')   # None / "" / "adb" / external

                if not table_name:
                    continue

                # schema is required
                if not schema_name:
                    result_key = f"{catalog_name + '.' if catalog_name else ''}{table_name}"
                    result[result_key] = {"error": f"Table '{table_name}' missing required parameter: schema"}
                    logger.warning(f"[Step 2] Table '{table_name}' missing schema, skipped")
                    continue

                # determine whether this is an external catalog
                is_external = (
                    catalog_name is not None
                    and catalog_name.strip().lower() not in {"", "adb"}
                )

                if is_external:
                    # ---- external catalog: DESC catalog.schema.table ----
                    full_name = f"`{catalog_name}`.`{schema_name}`.`{table_name}`"
                    with conn.cursor() as cursor:
                        cursor.execute(f"DESC {full_name}")
                        rows = cursor.fetchall()

                    # DESC returns: Field, Type, Null, Key, Default, Extra
                    columns = []
                    for row in rows:
                        field    = row.get('Field') or row.get('field', '')
                        col_type = row.get('Type')  or row.get('type', '')
                        key      = row.get('Key')   or row.get('key', '')
                        columns.append({
                            "column_name":    field,
                            "column_type":    col_type,
                            "column_comment": "",   # DESC does not return comment
                            "column_key":     key or ""
                        })
                    result_key = f"{catalog_name}.{schema_name}.{table_name}"

                else:
                    # ---- internal (adb / default): query information_schema.columns ----
                    effective_schema = schema_name or self.db_config.get('database')
                    with conn.cursor() as cursor:
                        cursor.execute(f"DESC `{effective_schema}`.`{table_name}`")
                        rows = cursor.fetchall()

                    columns = []
                    for row in rows:
                        field    = row.get('Field') or row.get('field', '')
                        col_type = row.get('Type')  or row.get('type', '')
                        key      = row.get('Key')   or row.get('key', '')
                        columns.append({
                            "column_name":    field,
                            "column_type":    col_type,
                            "column_comment": "",   # DESC does not return comment
                            "column_key":     key or ""
                        })

                    if catalog_name and catalog_name.strip().lower() not in {"", "adb"}:
                        result_key = f"{catalog_name}.{effective_schema}.{table_name}"
                    elif effective_schema:
                        result_key = f"{effective_schema}.{table_name}"
                    else:
                        result_key = table_name

                result[result_key] = columns

            logger.info(f"[Step 2 Attempt {attempt}] Query complete: {len(result)} table(s)")
            return _dumps({"status": "success", "data": result})

        except Exception as e:
            logger.error(f"[Step 2 Attempt {attempt}] Metadata query failed: {e}")
            return _dumps({
                "status":     "error",
                "error_type": "STEP2_METADATA_ERROR",
                "message":    f"Table metadata query failed: {str(e)}"
            })
        finally:
            if conn:
                conn.close()
