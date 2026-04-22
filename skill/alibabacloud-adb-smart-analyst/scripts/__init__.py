#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADB Smart Analyst Skill - Scripts Package

This package provides the core functionality for the ADB Smart Analyst Skill:
- Database connection management
- Semantic metric search (Step 1)
- Table metadata query (Step 2)
- SQL execution (Step 3)
- Semantic view lifecycle management
"""

import sys
import os

# Ensure the scripts directory is in the path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Core utilities
from utils import _dumps, logger

# Mixins
from db_connection import DBConnectionMixin
from semantic import SemanticMixin
from table_metadata import TableMetadataMixin
from sql_executor import SqlExecutorMixin

# Main class
from adb_smart_analyst import ADBSmartAnalystSkill

__all__ = [
    # Utilities
    "_dumps",
    "logger",
    # Mixins
    "DBConnectionMixin",
    "SemanticMixin",
    "TableMetadataMixin",
    "SqlExecutorMixin",
    # Main class
    "ADBSmartAnalystSkill",
]
