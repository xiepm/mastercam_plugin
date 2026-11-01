from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .errors import PlannerError


ROOT = Path(__file__).resolve().parents[4]
SCHEMA_DIR = ROOT / "schemas"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    schema = _load_json(SCHEMA_DIR / schema_name)
    registry = Registry()
    for dependency in ("feature_taxonomy.schema.json",):
        dependency_schema = _load_json(SCHEMA_DIR / dependency)
        registry = registry.with_resource(
            dependency_schema["$id"], Resource.from_contents(dependency_schema)
        )
    return Draft202012Validator(schema, registry=registry)


def validate_document(document: dict[str, Any], schema_name: str, label: str) -> None:
    errors = sorted(_validator(schema_name).iter_errors(document), key=lambda item: list(item.path))
    if not errors:
        return
    first = errors[0]
    location = "/".join(str(part) for part in first.absolute_path) or "<root>"
    raise PlannerError(f"{label} does not match {schema_name} at {location}: {first.message}")


def validate_features(document: dict[str, Any]) -> None:
    validate_document(document, "features.schema.json", "features input")
    if document.get("schema_version") != "2.2.0":
        raise PlannerError("P07 G8 requires features.json schema_version 2.2.0")


def validate_context(document: dict[str, Any]) -> None:
    validate_document(document, "manufacturing_context.schema.json", "manufacturing context")


def validate_plan(document: dict[str, Any]) -> None:
    validate_document(document, "cam_plan.schema.json", "cam plan")
