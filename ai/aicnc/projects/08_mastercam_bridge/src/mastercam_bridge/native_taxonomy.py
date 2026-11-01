"""Validation and aggregation for the Mastercam-native taxonomy contract.

The contract deliberately preserves Mastercam semantics.  Operation types are
historical process evidence; native feature objects are review-only candidates
until STEP/OCCT mapping and human confirmation exist.  This module never
authorizes training and never promotes an Operation into a feature label.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .readonly_export import validate_readonly_export


CONTRACT_VERSION = "aicnc.mastercam-native-taxonomy/0.1"
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")
_FORBIDDEN_KEYS = {
    "source_path", "raw_source_path", "filename", "file_name", "customer",
    "customer_name", "order", "order_id", "display_name", "operation_name", "tool_name",
}


class NativeTaxonomyValidationError(ValueError):
    """Raised when native evidence breaks contract, privacy or reference gates."""


def _fail(message: str) -> None:
    raise NativeTaxonomyValidationError(message)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[4] / "schemas" / "mastercam_native_taxonomy.schema.json"


def _load_schema() -> dict[str, Any]:
    return json.loads(_schema_path().read_text(encoding="utf-8"))


def _walk_keys(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in _FORBIDDEN_KEYS:
                _fail(f"{location}.{key} is forbidden because raw identity must not be exported")
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


def validate_native_taxonomy(
    payload: dict[str, Any],
    *,
    forbidden_project_sha256: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate one native export and return a compact non-identifying summary."""

    _validate_schema(payload)
    _walk_keys(payload)
    project = payload["project"]
    digest = project["project_sha256"]
    if not SHA256_PATTERN.fullmatch(digest):
        _fail("project.project_sha256 must be uppercase SHA-256")
    suffix = digest[:16].lower()
    if project["project_id"] != f"mcproj-{suffix}" or payload["export_id"] != f"mcent-{suffix}":
        _fail("project/export identifiers do not match project.project_sha256")
    if project["copy_sha256_after"] != digest:
        _fail("the isolated project copy changed during export")
    if digest in {str(item).upper() for item in forbidden_project_sha256}:
        _fail("Factory3 is a frozen external-test candidate and cannot enter A4 discovery")

    policy = payload["policy"]
    if any(policy[key] for key in (
        "source_mutations_permitted", "mutation_calls_made", "toolpath_regeneration_permitted",
        "postprocessing_permitted", "gcode_generation_permitted", "customer_fields_exported",
        "operation_is_feature_label", "feature_instances_are_truth", "automatic_face_binding_authorized",
        "source_project_opened",
    )):
        _fail("native taxonomy policy attempts a forbidden mutation, label or authorization")
    if payload["training_authorized"] is not False:
        _fail("training_authorized must remain false")

    operations = payload["operations"]
    operation_ids = [item["operation_id"] for item in operations]
    source_ids = [item["source_operation_id"] for item in operations]
    if len(operation_ids) != len(set(operation_ids)):
        _fail("operations contains duplicate operation_id")
    if len(source_ids) != len(set(source_ids)):
        _fail("operations contains duplicate source_operation_id")
    if [item["sequence"] for item in operations] != list(range(len(operations))):
        _fail("operation sequence must be contiguous and preserve native order")
    operation_id_set = set(operation_ids)

    setups = payload["setups"]
    setup_ids = [item["setup_id"] for item in setups]
    if len(setup_ids) != len(set(setup_ids)):
        _fail("setups contains duplicate setup_id")
    setup_map = {item["setup_id"]: item for item in setups}
    linked_ids: list[str] = []
    for setup in setups:
        linked = setup["operation_ids"]
        if any(item not in operation_id_set for item in linked):
            _fail(f"setup {setup['setup_id']} references an unknown operation")
        linked_ids.extend(linked)
    if sorted(linked_ids) != sorted(operation_ids):
        _fail("every operation must occur in exactly one setup")
    for operation in operations:
        if operation["setup_id"] not in setup_map:
            _fail(f"operation {operation['operation_id']} references an unknown setup")
        if operation["operation_id"] not in setup_map[operation["setup_id"]]["operation_ids"]:
            _fail(f"operation {operation['operation_id']} and setup membership disagree")

    taxonomy = payload["operation_taxonomy"]
    taxonomy_counts = Counter()
    for item in taxonomy:
        key = (item["native_type_key"], item["operation_type"], item["runtime_class"])
        if key in taxonomy_counts:
            _fail("operation_taxonomy contains duplicate native tuple")
        taxonomy_counts[key] = item["occurrence_count"]
    observed_counts = Counter(
        (item["native_type_key"], item["operation_type"], item["runtime_class"])
        for item in operations
    )
    if dict(observed_counts) != dict(taxonomy_counts):
        _fail("operation_taxonomy occurrence counts do not match operation records")
    for operation in operations:
        if operation["native_type_key"].isdigit() and operation["operation_type"] != "unknown_native_operation_type":
            _fail("numeric native type keys must retain an unknown operation name until resolved by API evidence")

    features = payload["feature_taxonomy"]
    feature_ids = [item["feature_id"] for item in features]
    if len(feature_ids) != len(set(feature_ids)):
        _fail("feature_taxonomy contains duplicate feature_id")
    feature_id_set = set(feature_ids)
    for feature in features:
        if any(item not in operation_id_set for item in feature["operation_ids"]):
            _fail(f"feature {feature['feature_id']} references an unknown operation")
        if feature["requires_review"] is not True:
            _fail("native feature candidates must always require review")
    seen_links: set[tuple[str, str]] = set()
    for link in payload["feature_operation_links"]:
        key = (link["feature_id"], link["operation_id"])
        if key in seen_links:
            _fail("feature_operation_links contains duplicate feature/operation pair")
        seen_links.add(key)
        if link["feature_id"] not in feature_id_set:
            _fail(f"feature_operation_link references unknown feature {link['feature_id']}")
        if link["operation_id"] not in operation_id_set:
            _fail(f"feature_operation_link references unknown operation {link['operation_id']}")
        if link["requires_review"] is not True:
            _fail("feature-operation links must always require review")

    probe = payload["feature_probe"]
    if probe["native_feature_object"] == "not_exposed" and (features or payload["feature_operation_links"]):
        _fail("not_exposed feature probe cannot contain feature objects or links")
    if probe["object_count"] != len(features):
        _fail("feature_probe.object_count does not match feature_taxonomy")

    return {
        "contract_version": CONTRACT_VERSION,
        "project_id": project["project_id"],
        "project_sha256": digest,
        "setup_count": len(setups),
        "operation_count": len(operations),
        "operation_type_count": len(taxonomy),
        "feature_count": len(features),
        "feature_operation_link_count": len(payload["feature_operation_links"]),
        "native_feature_object": probe["native_feature_object"],
        "training_authorized": False,
        "operation_is_feature_label": False,
    }


def load_and_validate_native_taxonomy(
    path: Path,
    *,
    forbidden_project_sha256: Iterable[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, validate_native_taxonomy(payload, forbidden_project_sha256=forbidden_project_sha256)


def summarize_native_taxonomies(payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate validated native exports into a deterministic taxonomy map."""

    items = list(payloads)
    if not items:
        raise ValueError("at least one native taxonomy export is required")
    summaries = [validate_native_taxonomy(item) for item in items]
    project_hashes = [item["project_sha256"] for item in summaries]
    if len(project_hashes) != len(set(project_hashes)):
        raise ValueError("native taxonomy exports contain duplicate project hashes")
    operation_counts: Counter[tuple[str, str, str]] = Counter()
    feature_status_counts: Counter[str] = Counter()
    runtime_counts: Counter[str] = Counter()
    native_status_counts: Counter[str] = Counter()
    numeric_unknown_keys: Counter[str] = Counter()
    total_setups = total_operations = total_links = 0
    for payload in items:
        total_setups += len(payload["setups"])
        total_operations += len(payload["operations"])
        total_links += len(payload["feature_operation_links"])
        native_status_counts[payload["feature_probe"]["native_feature_object"]] += 1
        for item in payload["operation_taxonomy"]:
            operation_counts[(item["native_type_key"], item["operation_type"], item["runtime_class"])] += item["occurrence_count"]
            runtime_counts[item["runtime_class"]] += item["occurrence_count"]
            if item["native_type_key"].isdigit():
                numeric_unknown_keys[item["native_type_key"]] += item["occurrence_count"]
        for feature in payload["feature_taxonomy"]:
            feature_status_counts[feature["evidence_status"]] += 1
    operation_rows = [
        {"native_type_key": key[0], "operation_type": key[1], "runtime_class": key[2], "occurrence_count": count}
        for key, count in sorted(operation_counts.items())
    ]
    return {
        "schema_version": CONTRACT_VERSION,
        "project_count": len(items),
        "setup_count": total_setups,
        "operation_count": total_operations,
        "feature_operation_link_count": total_links,
        "native_feature_object_status_counts": dict(sorted(native_status_counts.items())),
        "feature_evidence_status_counts": dict(sorted(feature_status_counts.items())),
        "runtime_class_counts": dict(sorted(runtime_counts.items())),
        "numeric_native_type_counts": dict(sorted(numeric_unknown_keys.items())),
        "operation_taxonomy": operation_rows,
        "policy": {
            "operation_is_feature_label": False,
            "feature_instances_are_truth": False,
            "automatic_face_binding_authorized": False,
            "training_authorized": False,
        },
    }


def taxonomy_digest(payload: dict[str, Any]) -> str:
    """Return a stable digest for an already validated payload."""

    validate_native_taxonomy(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()


def _native_operation_type(raw: str) -> str:
    """Keep numeric Mastercam opcodes unresolved until native evidence names them."""

    return "unknown_native_operation_type" if str(raw).isdigit() else str(raw)


def native_taxonomy_from_readonly_export(
    readonly_payload: dict[str, Any],
    *,
    feature_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lift an accepted read-only export into the native taxonomy contract.

    This is an offline, lossless contract adapter: it does not invent native
    feature objects or infer STEP Face membership.  It is useful for auditing
    the existing 48-project cohort while the companion NET-Script is compiled
    and then run against representative Mastercam copies.
    """

    validate_readonly_export(readonly_payload)
    project = readonly_payload["project"]
    digest = project["project_sha256"]
    suffix = digest[:16].lower()
    operations = []
    for item in readonly_payload["operations"]:
        raw = str(item["operation_type"])
        selection = item["geometry_selection"]
        tool = item["tool"]
        operations.append(
            {
                "operation_id": item["operation_id"],
                "source_operation_id": item["source_operation_id"],
                "sequence": item["sequence"],
                "native_type_key": raw,
                "operation_type": _native_operation_type(raw),
                "runtime_class": item["runtime_class"],
                "setup_id": item["setup_id"],
                "machine_group_id": item["machine_group_id"],
                "toolpath_group_id": item["toolpath_group_id"],
                "planes": item["planes"],
                "tool_type": None if tool is None else tool["tool_type"],
                "tool_diameter": None if tool is None else tool["diameter"],
                "parameters": {
                    key: item["parameters"][key]
                    for key in ("feed_rate", "plunge_rate", "retract_rate", "spindle_speed", "minimum_z", "maximum_z")
                },
                "selection": {
                    "status": "not_exposed" if selection["status"] == "not_exposed_by_current_adapter" else selection["status"],
                    "chain_count": len(selection["chains"]),
                    "drill_point_count": len(selection["drill_points"]),
                },
            }
        )
    taxonomy_counter: Counter[tuple[str, str, str]] = Counter(
        (item["native_type_key"], item["operation_type"], item["runtime_class"])
        for item in operations
    )
    operation_taxonomy = [
        {
            "native_type_key": key[0],
            "operation_type": key[1],
            "runtime_class": key[2],
            "occurrence_count": count,
            "evidence_status": "direct_api",
        }
        for key, count in sorted(taxonomy_counter.items())
    ]
    if feature_probe is None:
        feature_probe = {
            "native_feature_object": "not_exposed",
            "object_count": 0,
            "api_type_candidates": [
                "Mastercam.Solids.HoleDefinition",
                "Mastercam.Solids.HoleManager",
                "Cnc.CAD.Solids.Hole.IHoleDef",
            ],
            "api_member_candidates": [
                "Mastercam.Solids.HoleDefinition::ContainsFaceTag",
                "Mastercam.Solids.HoleDefinition::SegmentPtrs",
            ],
            "methods_probed": [
                "Mastercam.Solids.HoleManager.GetHolesFromFeatureTree",
                "Mastercam.Solids.HoleManager.GetHolesFromBody",
            ],
            "notes": "Existing readonly export contains no native feature-object probe; status is not_exposed, not an absence claim.",
        }
    payload = {
        "schema_version": CONTRACT_VERSION,
        "export_id": f"mcent-{suffix}",
        "project": project,
        "authorization": {
            "data_role": "a4_non_factory3_semantic_discovery",
            "catalog_manifest_sha256": readonly_payload["authorization"]["catalog_manifest_sha256"],
            "asset_id": readonly_payload["authorization"]["asset_id"],
            "part_id": readonly_payload["authorization"]["part_id"],
            "factory3_excluded": True,
            "issued_by": "aicnc-mastercam-native-taxonomy-runner/0.1",
        },
        "host": {
            **readonly_payload["host"],
            "script_id": "aicnc-mastercam-native-taxonomy-exporter/0.1",
        },
        "policy": {
            "source_mutations_permitted": False,
            "mutation_calls_made": False,
            "toolpath_regeneration_permitted": False,
            "postprocessing_permitted": False,
            "gcode_generation_permitted": False,
            "operation_names_anonymized": True,
            "customer_fields_exported": False,
            "factory3_excluded": True,
            "operation_is_feature_label": False,
            "feature_instances_are_truth": False,
            "automatic_face_binding_authorized": False,
            "source_project_opened": False,
        },
        "setups": [
            {
                "setup_id": setup["setup_id"],
                "signature_sha256": setup["signature_sha256"],
                "planes": setup["planes"],
                "operation_ids": setup["operation_ids"],
            }
            for setup in readonly_payload["setups"]
        ],
        "operations": operations,
        "operation_taxonomy": operation_taxonomy,
        "feature_probe": feature_probe,
        "feature_taxonomy": [],
        "feature_operation_links": [],
        "training_authorized": False,
        "exported_utc": readonly_payload["exported_utc"],
    }
    validate_native_taxonomy(payload)
    return payload
