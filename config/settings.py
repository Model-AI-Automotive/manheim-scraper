import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv()


def load_site_config(site: str = "copart") -> Dict[str, Any]:
    """Load site-specific configuration from YAML file"""
    config_path = Path(__file__).parent / f"{site}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


def get_settings() -> Dict[str, str]:
    """Get application settings from environment variables"""
    required_vars = [
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "COPART_USERNAME",
        "COPART_PASSWORD",
    ]

    settings = {}
    missing = []

    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            missing.append(var)
        settings[var.lower()] = value

    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    return settings


def get_optional_setting(key: str, default: str = None) -> str:
    """Get optional setting with default"""
    return os.environ.get(key, default)
