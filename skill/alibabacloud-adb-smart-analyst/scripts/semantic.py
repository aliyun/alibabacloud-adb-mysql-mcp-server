#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Layer Mixin: read and write operations for semantic views.

This mixin provides:
- Step 1: Semantic metric search (search_metrics_rag)
- Semantic view lifecycle management (create_semantic_view)
"""

try:
    from .utils import _dumps, logger
except ImportError:
    from utils import _dumps, logger


class SemanticMixin:
    """Semantic layer operations: read (Step 1 search) and write (CREATE).

    This mixin combines:
    - Step 1 semantic metric search: query semantic views from information_schema
    - Semantic view creation: CREATE SEMANTIC VIEW DDL operations
    """

    # =========================================================================
    # Step 1: Semantic Discovery (Read)
    # =========================================================================

    def search_metrics_rag(self, query: str, top_k: int = 5, attempt: int = 1) -> str:
        """[Step 1] Semantic metric search - find metric definitions by business keyword.

        Behavior: vector search first; falls back to keyword fuzzy match if unavailable.

        Args:
            query (str, required, ALWAYS use English, NOT Chinese): business keyword
                - metric name: revenue, profit, margin, roi, arpu, dau
                - business term: gmv, growth rate, conversion rate
                - combined: "channel revenue", "region profit"
            top_k (int, default 5): number of results, range 1-10
            attempt (int, default 1): current call attempt passed by the Agent.
                Attempt 1: original keyword; Attempt 2: split keywords;
                Attempt 3: synonyms or broader terms

        Returns:
            success: {status:success, count:N, data:[{view_name, definition}], mode:vector|keyword}
            failure: {status:error, error_type:STEP1_..., message:...}

        Examples:
            search_metrics_rag(query="revenue")
            search_metrics_rag(query="channel revenue")
            search_metrics_rag(query="profit rate", top_k=3, attempt=2)
        """
        logger.info(f"[Step 1 Attempt {attempt}/{self.MAX_ATTEMPTS}] Searching metrics: query='{query}'")

        if attempt > self.MAX_ATTEMPTS:
            return _dumps({
                "status":     "error",
                "error_type": "STEP1_MAX_ATTEMPTS_EXCEEDED",
                "message":    f"Step 1 (semantic discovery) reached max attempts ({self.MAX_ATTEMPTS}). Metric not found in the catalog, please verify the metric name or contact the admin."
            })

        conn = None
        try:
            conn = self._get_connection()

            logger.info("[Step 1] Using vector search")
            mode = "vector"
            with conn.cursor() as cursor:
                sql = """
                    /*+ semantic_view_similar_search_query='%s', semantic_view_similar_search_top_k=%s */
                        SELECT
                            view_schema,
                            view_name,
                            definition
                        FROM information_schema.semantic_views
                        LIMIT %s
                """
                cursor.execute(sql, (query, top_k, top_k))
                rows = cursor.fetchall()
            result_data = [
                {
                    "view_schema": r['view_schema'],
                    "view_name":   r['view_name'],
                    "definition":  r['definition'] or ""
                }
                for r in rows
            ]

            # ---- not found handling ----
            if not result_data:
                logger.warning(f"[Step 1 Attempt {attempt}] No matching metrics found")

                if attempt == 3:
                    # Third attempt failed: full fallback
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT view_schema, view_name, definition "
                            "FROM information_schema.semantic_views LIMIT 10"
                        )
                        all_rows = cursor.fetchall()

                    if not all_rows:
                        return _dumps({
                            "status":     "error",
                            "error_type": "EMPTY_SEMANTIC_VIEWS",
                            "message":    "No semantic view records found in the database."
                        })

                    all_data = [
                        {
                            "view_schema": r['view_schema'],
                            "view_name":   r['view_name'],
                            "definition":  r['definition'] or ""
                        }
                        for r in all_rows
                    ]
                    logger.info(f"[Step 1 Attempt {attempt}] Full fallback: returning {len(all_data)} records")
                    return _dumps({
                        "status":  "success",
                        "count":   len(all_data),
                        "data":    all_data,
                        "mode":    "full_return",
                        "message": f"No match found for '{query}'. Returning all {len(all_data)} records from the database."
                    })
                else:
                    return _dumps({
                        "status":  "success",
                        "count":   0,
                        "data":    [],
                        "message": f"No semantic metrics found for '{query}'. Try splitting the keyword or using synonyms."
                    })

            logger.info(f"[Step 1 Attempt {attempt}] [{mode}] Found {len(result_data)} metric definition(s)")
            return _dumps({
                "status": "success",
                "count":  len(result_data),
                "data":   result_data,
                "mode":   mode
            })

        except Exception as e:
            logger.error(f"[Step 1 Attempt {attempt}] Search failed: {e}")
            return _dumps({
                "status":     "error",
                "error_type": "STEP1_SEARCH_ERROR",
                "message":    f"Metric search failed: {str(e)}"
            })
        finally:
            if conn:
                conn.close()

    # =========================================================================
    # Semantic View Lifecycle Management (Write)
    # =========================================================================

    def create_semantic_view(self, name: str, yaml_content: str,
                             or_replace: bool = True,
                             if_not_exists: bool = True) -> str:
        """Create a semantic view from YAML content.

        Args:
            name (str, required): semantic view name, format: [schema.]view_name
            yaml_content (str, required): YAML definition of the semantic view
            or_replace (bool, default True): whether to use OR REPLACE
            if_not_exists (bool, default True): whether to use IF NOT EXISTS

        Returns:
            success: {status:success, message:..., name:...}
            failure: {status:error, message:...}

        Examples:
            create_semantic_view(
                name="tpch.tpch_sales",
                yaml_content="name: tpch_sales\\ntables:\\n  ..."
            )
        """
        # Build DDL keywords
        replace_clause = "OR REPLACE " if or_replace else ""
        exists_clause = "IF NOT EXISTS " if if_not_exists else ""

        # Escape dollar signs in YAML content for dollar-quoting
        escaped_yaml = yaml_content.replace("$$", "\\$\\$")

        # Use dollar-quoting for YAML content to avoid escaping issues
        sql = (
            f"CREATE {replace_clause}SEMANTIC VIEW {exists_clause}{name}\n"
            f"LANGUAGE YAML\n"
            f"AS\n"
            f"$${escaped_yaml}$$"
        )

        logger.info(f"[SemanticView] Creating semantic view: {name}")

        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()

            logger.info(f"[SemanticView] Semantic view '{name}' created successfully")
            return _dumps({
                "status":  "success",
                "message": f"Semantic view '{name}' created successfully.",
                "name":    name
            })

        except Exception as e:
            error_message = str(e)
            logger.error(f"[SemanticView] Failed to create semantic view '{name}': {error_message}")
            return _dumps({
                "status":  "error",
                "message": f"Failed to create semantic view '{name}': {error_message}"
            })
        finally:
            if conn:
                conn.close()
