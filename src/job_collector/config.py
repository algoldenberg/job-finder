"""Load the YAML config. The path can be overridden with JOB_COLLECTOR_CONFIG."""

import os
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path or os.environ.get("JOB_COLLECTOR_CONFIG", DEFAULT_CONFIG))
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
