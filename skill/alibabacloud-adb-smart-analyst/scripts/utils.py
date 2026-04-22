#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared utilities: JSON encoder, serialization, logging, pymysql import guard.

This module provides common utilities used across all mixins:
- _DBJsonEncoder: Custom JSON encoder for MySQL types (Decimal, datetime, bytes)
- _dumps: Unified JSON serialization entry point
- logger: Global logger instance
"""

import sys
import json
import logging
from decimal import Decimal
from datetime import date, datetime

try:
    import pymysql
except ImportError as e:
    print(f"Error: missing dependency - {e}")
    print("Please run: pip install pymysql")
    sys.exit(1)

# Global logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ADBSmartAnalystSkill")


class _DBJsonEncoder(json.JSONEncoder):
    """Custom JSON encoder for MySQL types that are not natively serializable.

    Handles:
        - Decimal: converted to string to preserve precision
        - datetime: formatted as 'YYYY-MM-DD HH:MM:SS'
        - date: formatted as 'YYYY-MM-DD'
        - bytes: decoded as UTF-8 with error replacement
    """

    def default(self, obj):
        if isinstance(obj, Decimal):
            # Preserve precision, let the model decide whether to convert to float
            return str(obj)
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)


def _dumps(obj) -> str:
    """Unified JSON serialization entry point.

    Automatically handles Decimal, datetime, date, and bytes types.

    Args:
        obj: Any Python object to serialize.

    Returns:
        JSON string representation.
    """
    return json.dumps(obj, ensure_ascii=False, cls=_DBJsonEncoder)
