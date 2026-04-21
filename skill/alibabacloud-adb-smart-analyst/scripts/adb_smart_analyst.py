#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADB Smart Analyst Skill - Entry Point Module

A progressive architecture based on "semantic discovery -> logical extraction ->
physical alignment -> execution feedback". The 3x3 self-healing mechanism is
controlled by the Agent following the SKILL.md workflow. Each script execution
performs a single operation, with the current attempt number passed via --attempt.

Core Functions:
    1. search_metrics_rag:       [Step 1] Semantic metric search (vector-first)
    2. get_batch_table_metadata: [Step 2] Batch table metadata query
    3. execute_adb_sql:          [Step 3] SQL executor (returns raw errors)
    4. create_semantic_view:     Create semantic view from YAML

Environment Variables:
    ADB_MYSQL_HOST:     ADB MySQL host address
    ADB_MYSQL_USER:     Database username
    ADB_MYSQL_PASSWORD: Database password
    ADB_MYSQL_PORT:     Port number (optional, default 3306)
"""

import sys
import json
from typing import Optional

# Submodule imports (relative import when scripts is used as a package)
# Falls back to absolute import for direct script execution
try:
    from .utils import _dumps, logger
    from .db_connection import DBConnectionMixin
    from .semantic import SemanticMixin
    from .table_metadata import TableMetadataMixin
    from .sql_executor import SqlExecutorMixin
except ImportError:
    # fallback for direct script execution: python adb_smart_analyst.py
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from utils import _dumps, logger
    from db_connection import DBConnectionMixin
    from semantic import SemanticMixin
    from table_metadata import TableMetadataMixin
    from sql_executor import SqlExecutorMixin


class ADBSmartAnalystSkill(DBConnectionMixin, SemanticMixin, TableMetadataMixin, SqlExecutorMixin):
    """ADB Smart Analyst Skill - combines Step 1/2/3 and semantic view management.

    This class combines all mixin capabilities:
    - DBConnectionMixin: Database connection management
    - SemanticMixin: Step 1 semantic metric search + semantic view creation
    - TableMetadataMixin: Step 2 physical table metadata query
    - SqlExecutorMixin: Step 3 SQL execution

    The 3x3 retry loop is controlled by the Agent following the SKILL.md workflow.

    Attributes:
        MAX_ATTEMPTS (int): Maximum attempts per phase (default: 3)
    """

    MAX_ATTEMPTS = 3  # Maximum attempts per phase

    def __init__(self,
                 host: Optional[str] = None,
                 user: Optional[str] = None,
                 password: Optional[str] = None,
                 port: int = 3306):
        """Initialize the ADB Smart Analyst Skill.

        Args:
            host:     ADB host address (reads from ADB_HOST env var if not provided)
            user:     Database username (reads from ADB_USER env var if not provided)
            password: Database password (reads from ADB_PASSWORD env var if not provided)
            port:     Port number, default 3306
        """
        self._init_db_config(host=host, user=user, password=password, port=port)


# ==================== CLI Entry Point ====================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ADB Smart Analyst Skill")
    subparsers = parser.add_subparsers(dest="command", help="available commands")

    # search_metrics_rag command
    search_parser = subparsers.add_parser("search_metrics_rag", help="[L1] search metric definitions")
    search_parser.add_argument("query", type=str, help="search keyword")
    search_parser.add_argument("--top-k", type=int, default=5, help="number of results to return")
    search_parser.add_argument("--attempt", type=int, default=1,
                               help="current call attempt (1-3), used for logging and attempt-3 full fallback")

    # get_batch_table_metadata command
    metadata_parser = subparsers.add_parser("get_batch_table_metadata", help="[L2] query table metadata")
    metadata_parser.add_argument(
        "tables", type=str,
        help="JSON array, each element supports catalog(optional)/schema(required)/table(required): "
             "'[{\"catalog\":\"c\",\"schema\":\"db\",\"table\":\"t\"}]'"
    )
    metadata_parser.add_argument("--attempt", type=int, default=1,
                                 help="current call attempt (1-3)")

    # execute_adb_sql command
    exec_parser = subparsers.add_parser("execute_adb_sql", help="[L3] execute SQL")
    exec_parser.add_argument("sql", type=str, help="SQL statement")
    exec_parser.add_argument("--attempt", type=int, default=1,
                             help="current call attempt (1-3)")

    # create_semantic_view command
    create_sv_parser = subparsers.add_parser("create_semantic_view", help="create a semantic view from YAML")
    create_sv_parser.add_argument("name", type=str, help="semantic view name")
    create_sv_parser.add_argument("yaml_content", type=str, help="YAML definition content")
    create_sv_parser.add_argument("--or-replace", action="store_true", help="use OR REPLACE")
    create_sv_parser.add_argument("--if-not-exists", action="store_true", help="use IF NOT EXISTS")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize Skill
    try:
        skill = ADBSmartAnalystSkill()
    except ValueError as e:
        print(f"Initialization failed: {e}")
        sys.exit(1)

    # Dispatch command
    if args.command == "search_metrics_rag":
        result = skill.search_metrics_rag(args.query, args.top_k, args.attempt)

    elif args.command == "get_batch_table_metadata":
        try:
            tables = json.loads(args.tables.strip())
            if not isinstance(tables, list):
                raise ValueError("must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            print(_dumps({"status": "error", "message": f"Failed to parse tables argument: {e}, please pass a JSON array"}))
            sys.exit(1)
        result = skill.get_batch_table_metadata(tables, args.attempt)

    elif args.command == "execute_adb_sql":
        result = skill.execute_adb_sql(args.sql, args.attempt)

    elif args.command == "create_semantic_view":
        result = skill.create_semantic_view(
            name=args.name,
            yaml_content=args.yaml_content,
            or_replace=args.or_replace,
            if_not_exists=args.if_not_exists
        )

    else:
        parser.print_help()
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()