"""Serialize the control-tower schema to YAML/JSON and self-check it.

The pipeline authors the schema in YAML (human-readable, the SSOT the CEO can
read and diff); the GUI's Rust gateway normalizes it to JSON at the boundary.
This module is the emit path for both forms plus a structural self-check.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from .definition import build_schema
from .model import Schema


def schema_dict() -> dict[str, Any]:
    return build_schema().to_dict()


def to_yaml(data: dict[str, Any] | None = None) -> str:
    if data is None:
        data = schema_dict()
    # Mapping (not a scalar) -> safe_dump won't emit doc-end markers; preserve
    # authored key order for readability/diff stability.
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)


def to_json(data: dict[str, Any] | None = None, *, indent: int = 2) -> str:
    if data is None:
        data = schema_dict()
    return json.dumps(data, indent=indent, ensure_ascii=False)


def check(schema: Schema | None = None) -> list[str]:
    """Return structural problems (empty == conformant)."""
    if schema is None:
        schema = build_schema()
    return schema.validate()
