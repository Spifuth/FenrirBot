"""Read a YAML spec file and return a validated `Spec`."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from .models import Spec


def load_spec(path: str | Path) -> Spec:
    """Parse YAML at `path` and return a validated `Spec`."""
    yaml = YAML(typ="safe")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    return Spec.model_validate(data)
