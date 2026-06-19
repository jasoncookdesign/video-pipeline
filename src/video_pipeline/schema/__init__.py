"""Control-tower schema contract (INI-087).

The pipeline authors the GUI's single source of truth here. See ``model`` for
the grammar dataclasses, ``definition`` for the JasonOS schema instance, and
``emit`` for serialization + self-check.
"""

from __future__ import annotations

from .assemble import resolve_argv
from .definition import build_schema
from .emit import check, schema_dict, to_json, to_yaml
from .model import (
    Artifact,
    Engine,
    ExportTarget,
    IOBinding,
    Param,
    Schema,
    Step,
    Task,
    UI,
    SCHEMA_VERSION,
)

__all__ = [
    "build_schema",
    "check",
    "resolve_argv",
    "schema_dict",
    "to_json",
    "to_yaml",
    "Artifact",
    "Engine",
    "ExportTarget",
    "IOBinding",
    "Param",
    "Schema",
    "Step",
    "Task",
    "UI",
    "SCHEMA_VERSION",
]
