#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Connection Mixin: configuration validation and connection management
"""

import os
from typing import Optional

try:
    from .utils import logger
except ImportError:
    from utils import logger

import pymysql


class DBConnectionMixin:
    """Provides database connection capability via environment variables or constructor args"""

    def _init_db_config(self,
                        host: Optional[str] = None,
                        user: Optional[str] = None,
                        password: Optional[str] = None,
                        port: int = 3306):
        """Initialize database configuration from args or environment variables"""
        self.db_config = {
            "host":        host or os.getenv("ADB_MYSQL_HOST"),
            "user":        user or os.getenv("ADB_MYSQL_USER"),
            "password":    password or os.getenv("ADB_MYSQL_PASSWORD"),
            "port":        int(os.getenv("ADB_MYSQL_PORT", port)),
            "charset":     "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
        }
        self._validate_config()

    def _validate_config(self):
        """Validate database configuration completeness"""
        missing = []
        for key in ["host", "user", "password"]:
            if not self.db_config.get(key):
                missing.append(f"ADB_{key.upper()}")
        if missing:
            raise ValueError(
                f"Incomplete database config, missing env vars: {', '.join(missing)}\n"
                f"Run the following in your current shell session (not written to disk):\n"
                + "\n".join(f"  export {v}=<your_value>" for v in missing)
            )

    def _get_connection(self):
        """Get a database connection"""
        try:
            return pymysql.connect(**self.db_config)
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise ConnectionError(f"Cannot connect to ADB database: {e}")
