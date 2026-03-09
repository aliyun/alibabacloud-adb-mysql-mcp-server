"""pytest 全局配置 —— 自定义命令行参数和共享 fixtures"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    """在 pytest 启动时加载环境变量"""
    env_file = Path(__file__).parent / "test.env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"[pytest] Loaded environment variables from {env_file}")


def pytest_addoption(parser):
    """注册集成测试使用的命令行参数"""
    parser.addoption("--region-id", default="cn-zhangjiakou", help="Alibaba Cloud region ID")
    parser.addoption("--db-cluster-id", default="amv-8vb3w49888dw5v5m", help="ADB MySQL cluster ID")
