"""Validation for the A4 Mastercam read-only evidence contract.

The export is evidence about how a real project was programmed.  It is never
treated as a manufacturing-feature label and never authorizes training by
itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


CONTRACT_VERSION = "aicnc.mastercam-readonly-export/0.1"
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")
_FORBIDDEN_KEYS = {
    "source_path",
    "raw_source_path",
    "filename",
    "file_name",
    "customer",
    "customer_name",
    "order",
    "order_id",
    "display_name",
    "operation_name",
    "tool_name",
}


class ReadonlyExportValidationError(ValueError):
    """Raised when an export breaks the read-only, privacy or reference contract."""


def _fail(message: str) -> None:
    raise ReadonlyExportValidationError(message)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[4] / "schemas" / "mastercam_readonly_export.schema.json"


def _load_schema() -> dict[str, Any]:
    return json.loads(_schema_path().read_text(encoding="utf-8"))


def load_factory3_cam_project_hashes(records_path: Path) -> set[str]:
    """Load MCAM hashes, not STEP hashes, from the frozen Factory3 intake ledger."""

    digests: set[str] = set()
    record_count = 0
    for line_number, line in enumerate(
        records_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        record_count += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            _fail(f"Factory3 intake record {line_number} is not valid JSON: {error}")
        projects = record.get("asset_roles", {}).get("cam_project")
        if not isinstance(projects, list) or not projects:
            _fail(f"Factory3 intake record {line_number} has no cam_project asset")
        for project in projects:
            digest = str(project.get("content_sha256", "")).upper()
            if not SHA256_PATTERN.fullmatch(digest):
                _fail(
                    f"Factory3 intake record {line_number} has an invalid cam_project SHA-256"
                )
            digests.add(digest)
    if record_count == 0 or not digests:
        _fail("Factory3 intake ledger did not contain any cam_project hashes")
    return digests


def _walk_keys(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in _FORBIDDEN_KEYS:
                _fail(f"{location}.{key} is forbidden because raw project identity must not be exported")
            _walk_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_keys(child, f"{location}[{index}]")


def _validate_schema(payload: Any) -> None:
    validator = Draft202012Validator(_load_schema(), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "$" + "".join(
            f"[{item}]" if isinstance(item, int) else f".{item}"
            for item in error.absolute_path
        )
        _fail(f"schema violation at {location}: {error.message}")


def validate_readonly_export(
    payload: Any,
    *,
    forbidden_project_sha256: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate an export and return a compact, non-identifying summary."""

    _validate_schema(payload)
    _walk_keys(payload)

    project = payload["project"]
    project_sha256 = project["project_sha256"]
    if not SHA256_PATTERN.fullmatch(project_sha256):
        _fail("project.project_sha256 must be uppercase SHA-256")
    expected_suffix = project_sha256[:16].lower()
    if project["project_id"] != f"mcproj-{expected_suffix}":
        _fail("project.project_id does not match project.project_sha256")
    if payload["export_id"] != f"mce-{expected_suffix}":
        _fail("export_id does not match project.project_sha256")
    if project["copy_sha256_after"] != project_sha256:
        _fail("the isolated project copy changed during export")
    forbidden = {digest.upper() for digest in forbidden_project_sha256}
    if project_sha256 in forbidden:
        _fail("Factory3 is a frozen external-test candidate and cannot enter A4 discovery")

    groups = payload["groups"]
    group_ids = [group["group_id"] for group in groups]
    if len(group_ids) != len(set(group_ids)):
        _fail("groups contains duplicate group_id")
    group_id_set = set(group_ids)
    for group in groups:
        parent = group["parent_group_id"]
        if parent is not None and parent not in group_id_set:
            _fail(f"group {group['group_id']} references an unknown parent group")

    setups = payload["setups"]
    setup_ids = [setup["setup_id"] for setup in setups]
    if len(setup_ids) != len(set(setup_ids)):
        _fail("setups contains duplicate setup_id")
    setup_by_id = {setup["setup_id"]: setup for setup in setups}

    operations = payload["operations"]
    operation_ids = [operation["operation_id"] for operation in operations]
    source_ids = [operation["source_operation_id"] for operation in operations]
    if len(operation_ids) != len(set(operation_ids)):
        _fail("operations contains duplicate operation_id")
    if len(source_ids) != len(set(source_ids)):
        _fail("operations contains duplicate source_operation_id")
    if [operation["sequence"] for operation in operations] != list(range(len(operations))):
        _fail("operation.sequence must be contiguous and preserve exported order")

    operation_id_set = set(operation_ids)
    for setup in setups:
        linked = setup["operation_ids"]
        if any(operation_id not in operation_id_set for operation_id in linked):
            _fail(f"setup {setup['setup_id']} references an unknown operation")
    seen_in_setups: list[str] = []
    for setup in setups:
        seen_in_setups.extend(setup["operation_ids"])
    if sorted(seen_in_setups) != sorted(operation_ids):
        _fail("every operation must occur in exactly one setup")

    for operation in operations:
        if operation["setup_id"] not in setup_by_id:
            _fail(f"operation {operation['operation_id']} references an unknown setup")
        if operation["operation_id"] not in setup_by_id[operation["setup_id"]]["operation_ids"]:
            _fail(f"operation {operation['operation_id']} and setup membership disagree")
        for key in ("machine_group_id", "toolpath_group_id"):
            group_id = operation[key]
            if group_id is not None and group_id not in group_id_set:
                _fail(f"operation {operation['operation_id']} references unknown {key}")

    summary = payload["summary"]
    if summary["group_count"] != len(groups):
        _fail("summary.group_count does not match groups")
    if summary["setup_count"] != len(setups):
        _fail("summary.setup_count does not match setups")
    if summary["operation_count"] != len(operations):
        _fail("summary.operation_count does not match operations")
    selection_total = (
        summary["direct_selection_count"]
        + summary["partial_selection_count"]
        + summary["unavailable_selection_count"]
    )
    if selection_total != len(operations):
        _fail("selection summary counts do not match operations")

    return {
        "contract_version": CONTRACT_VERSION,
        "project_id": project["project_id"],
        "project_sha256": project_sha256,
        "group_count": len(groups),
        "setup_count": len(setups),
        "operation_count": len(operations),
        "training_authorized": False,
        "operation_is_feature_label": False,
    }


def load_and_validate_readonly_export(
    path: Path,
    *,
    forbidden_project_sha256: Iterable[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, validate_readonly_export(
        payload, forbidden_project_sha256=forbidden_project_sha256
    )
