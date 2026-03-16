"""
Configuration loading and validation for the OpenClaw Insight Analysis system.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdbConfig:
    jdbc_url: str
    username: str
    password: str
    host: str
    port: int
    database: str
    session_table: str
    logs_table: str
    connection_pool_size: int


@dataclass
class CollectionConfig:
    interval_minutes: int
    batch_size: int
    retention_days: int
    enable_log_collection: bool
    enable_token_collection: bool


@dataclass
class FiltersConfig:
    min_level: str
    include_subsystems: list[str]
    exclude_subsystems: list[str]


@dataclass
class LlmConfig:
    endpoint: str
    api_key: str
    model: str
    api_type: str  # "openai" or "anthropic"
    max_concurrency: int
    temperature: float
    max_tokens: Optional[int] = None


@dataclass
class AnalysisConfig:
    enable_l1: bool = True
    enable_l2: bool = True
    enable_l3: bool = True
    analysis_window_days: int = 7
    max_sessions_for_llm: int = 500


@dataclass
class AppConfig:
    adb: AdbConfig
    collection: CollectionConfig
    filters: FiltersConfig
    llm: Optional[LlmConfig] = None
    analysis: Optional[AnalysisConfig] = None


CONFIG_FILE_NAME = "config.json"


def load_config() -> AppConfig:
    config_path = os.path.join(os.path.dirname(__file__), "..", CONFIG_FILE_NAME)
    config_path = os.path.abspath(config_path)

    if not os.path.exists(config_path):
        print(
            f"Configuration file not found: {config_path}\n"
            "Please copy config.example.json to config.json and fill in the actual configuration."
        )
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as config_file:
        raw = json.load(config_file)

    config = _parse_config(raw)
    _validate_config(config)
    return config


def _parse_config(raw: dict) -> AppConfig:
    adb_raw = raw.get("adb", {})
    adb = AdbConfig(
        jdbc_url=adb_raw.get("jdbcUrl", ""),
        username=adb_raw.get("username", ""),
        password=adb_raw.get("password", ""),
        host=adb_raw.get("host", ""),
        port=int(adb_raw.get("port", 3306)),
        database=adb_raw.get("database", ""),
        session_table=adb_raw.get("sessionTable", ""),
        logs_table=adb_raw.get("logsTable", "openclaw_logs"),
        connection_pool_size=int(adb_raw.get("connectionPoolSize", 5)),
    )

    col_raw = raw.get("collection", {})
    collection = CollectionConfig(
        interval_minutes=int(col_raw.get("intervalMinutes", 5)),
        batch_size=int(col_raw.get("batchSize", 100)),
        retention_days=int(col_raw.get("retentionDays", 7)),
        enable_log_collection=bool(col_raw.get("enableLogCollection", True)),
        enable_token_collection=bool(col_raw.get("enableTokenCollection", True)),
    )

    fil_raw = raw.get("filters", {})
    filters = FiltersConfig(
        min_level=fil_raw.get("minLevel", "info"),
        include_subsystems=fil_raw.get("includeSubsystems", []),
        exclude_subsystems=fil_raw.get("excludeSubsystems", []),
    )

    llm: Optional[LlmConfig] = None
    if "llm" in raw and raw["llm"]:
        llm_raw = raw["llm"]
        llm = LlmConfig(
            endpoint=llm_raw.get("endpoint", ""),
            api_key=llm_raw.get("apiKey", ""),
            model=llm_raw.get("model", ""),
            api_type=llm_raw.get("apiType", "openai"),
            max_concurrency=int(llm_raw.get("maxConcurrency", 5)),
            temperature=float(llm_raw.get("temperature", 0.1)),
            max_tokens=llm_raw.get("maxTokens"),
        )

    analysis: Optional[AnalysisConfig] = None
    if "analysis" in raw and raw["analysis"]:
        ana_raw = raw["analysis"]
        analysis = AnalysisConfig(
            enable_l1=bool(ana_raw.get("enableL1", True)),
            enable_l2=bool(ana_raw.get("enableL2", True)),
            enable_l3=bool(ana_raw.get("enableL3", True)),
            analysis_window_days=int(ana_raw.get("analysisWindowDays", 7)),
            max_sessions_for_llm=int(ana_raw.get("maxSessionsForLlm", 500)),
        )

    return AppConfig(adb=adb, collection=collection, filters=filters, llm=llm, analysis=analysis)


def _validate_config(config: AppConfig) -> None:
    if not config.adb.host or not config.adb.port or not config.adb.database:
        raise ValueError("ADB configuration missing host, port, or database")
    if not config.adb.username or not config.adb.password:
        raise ValueError("ADB configuration missing username or password")
    if not config.adb.session_table:
        raise ValueError("ADB configuration missing sessionTable")
    if config.collection.interval_minutes <= 0:
        raise ValueError("collection.intervalMinutes must be greater than 0")
    if config.collection.batch_size <= 0:
        raise ValueError("collection.batchSize must be greater than 0")

    if config.llm:
        if not config.llm.endpoint:
            raise ValueError("llm.endpoint is required when llm config is provided")
        if not config.llm.api_key:
            raise ValueError("llm.apiKey is required when llm config is provided")
        if not config.llm.model:
            raise ValueError("llm.model is required when llm config is provided")

    if config.analysis is None:
        config.analysis = AnalysisConfig()

    if (config.analysis.enable_l2 or config.analysis.enable_l3) and not config.llm:
        print("[Config] ⚠️ L2/L3 analysis requires LLM config. Only L1 analysis will run.")
        config.analysis.enable_l2 = False
        config.analysis.enable_l3 = False
