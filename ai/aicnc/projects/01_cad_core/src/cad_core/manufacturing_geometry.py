"""Candidate source-independent measurement entrance to the existing P01 kernels.

This is deliberately not an AAGNet result converter. It checks a digest of the
complete imported P01 summary, then measures the supplied instance boundaries.
No Face membership, source semantics, or instance split is inferred here.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from .core import CadDocument
from .errors import FaceAlignmentError
from . import postprocess_context as kernels


ROOT = Path(__file__).resolve().parents[4]
REQUEST_SCHEMA = ROOT / "schemas" / "manufacturing_geometry_request.schema.json"
GEOMETRY_ADAPTER_VERSION = "p01-manufacturing-geometry/0.1.0"


def summary_canonical_sha256(summary: dict[str, Any]) -> str:
    """Digest exact JSON content, including Face order and import-version scope."""

    data = json.dumps(
        summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest().upper()


def _no_external_schema(uri: str) -> Resource:
    raise NoSuchResource(ref=uri)


def _schema_validator(path: Path) -> Draft202012Validator:
    paths = (
        REQUEST_SCHEMA,
        ROOT / "schemas" / "feature_taxonomy.schema.json",
        ROOT / "schemas" / "features.schema.json",
        ROOT / "projects" / "04_feature_postprocess" / "configs" / "postprocess_context.schema.json",
    )
    schemas = [json.loads(item.read_text(encoding="utf-8")) for item in paths]
    registry = Registry(retrieve=_no_external_schema).with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    target = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(target, registry=registry)


def validate_manufacturing_geometry_request(
    request: dict[str, Any], summary: dict[str, Any],
) -> None:
    """Validate schema, complete P01 identity, and primary Face membership."""

    _schema_validator(REQUEST_SCHEMA).validate(request)
    if request["p01_summary_canonical_sha256"] != summary_canonical_sha256(summary):
        raise FaceAlignmentError("Manufacturing request differs from the complete P01 summary digest.")
    registered = [face["face_id"] for face in summary["faces"]]
    if len(registered) != len(set(registered)):
        raise FaceAlignmentError("P01 summary has duplicate Face IDs.")
    face_set = set(registered)
    instance_ids: set[str] = set()
    assigned: set[str] = set()
    for instance in request["instances"]:
        instance_id = instance["instance_id"]
        if instance_id in instance_ids:
            raise FaceAlignmentError("Duplicate manufacturing instance ID.")
        instance_ids.add(instance_id)
        members = set(instance["face_ids"])
        if not members <= face_set:
            raise FaceAlignmentError(f"{instance_id} references an unregistered Face.")
        if members & assigned:
            raise FaceAlignmentError("A Face cannot have two primary manufacturing instances.")
        if not set(instance["bottom_face_ids"]) <= members:
            raise FaceAlignmentError(f"{instance_id} bottom Face is outside its members.")
        assigned.update(members)


def _kernel_mode(label: dict[str, Any]) -> str | None:
    """Select an existing strict geometric template, never a source class ID.

    Unknown attributes do not assert a shape. Required attributes must still
    be explicitly present. Unsupported extra assertions fail closed rather
    than being discarded, notably thread specifications or conical bottoms.
    """

    family = label["family"]
    attrs = {key: value for key, value in label["attributes"].items() if value != "unknown"}
    if attrs.get("thread") == "none":
        attrs.pop("thread")
    if "thread" in attrs:
        return None
    termination = attrs.get("termination")
    bottom = attrs.get("bottom_condition")
    if bottom is not None:
        if (termination, bottom) not in {("blind", "flat"), ("through", "none")}:
            return None
        attrs.pop("bottom_condition")
    # Openness is not a part-wide tool-access or collision assertion. Only
    # closed pockets/passages and round holes have a supported equivalence.
    openness = attrs.get("openness")
    if openness is not None:
        if family not in {"pocket", "passage", "hole"} or openness != "closed":
            return None
        attrs.pop("openness")
    key = (family, tuple(sorted(attrs.items())))
    definitions = [
        ("hole", {"profile": "circular", "termination": "through"}, "circular_hole_through"),
        ("hole", {"profile": "circular", "termination": "blind"}, "circular_hole_blind"),
        ("pocket", {"profile": "rectangular", "termination": "blind"}, "rectangular_blind"),
        ("slot", {"profile": "rectangular", "termination": "blind"}, "rectangular_blind"),
        ("passage", {"profile": "rectangular", "termination": "through"}, "rectangular_closed_through"),
        ("slot", {"profile": "rectangular", "termination": "through"}, "rectangular_open_through"),
        ("passage", {"profile": "triangular", "termination": "through"}, "polygon3_through"),
        ("passage", {"profile": "six_sided", "termination": "through"}, "polygon6_through"),
        ("pocket", {"profile": "triangular", "termination": "blind"}, "polygon3_blind"),
        ("pocket", {"profile": "six_sided", "termination": "blind"}, "polygon6_blind"),
        ("slot", {"profile": "triangular", "termination": "through"}, "triangular_slot_through"),
        ("slot", {"profile": "circular", "termination": "through"}, "circular_slot_through"),
        ("step", {"profile": "rectangular", "termination": "through"}, "rectangular_step_through"),
        ("step", {"boundary_form": "two_sided", "termination": "through"}, "two_sided_step_through"),
        ("step", {"boundary_form": "slanted", "termination": "through"}, "slanted_step_through"),
        ("step", {"profile": "rectangular", "termination": "blind"}, "rectangular_step_blind"),
        ("step", {"profile": "triangular", "termination": "blind"}, "triangular_step_blind"),
        ("step", {"profile": "circular", "termination": "blind"}, "circular_step_blind"),
        ("pocket", {"boundary_form": "circular_end", "termination": "blind"}, "circular_end_pocket"),
        ("slot", {"boundary_form": "vertical_circular_end", "termination": "blind"}, "vertical_end_slot_blind"),
        ("slot", {"boundary_form": "horizontal_circular_end", "termination": "blind"}, "horizontal_end_slot_blind"),
        ("groove", {"profile": "annular"}, "annular_groove"),
        ("edge_transition", {"edge_form": "chamfer", "termination": "not_applicable"}, "planar_chamfer"),
        ("edge_transition", {"edge_form": "round", "termination": "not_applicable"}, "cylindrical_round"),
    ]
    return {(fam, tuple(sorted(attributes.items()))): mode for fam, attributes, mode in definitions}.get(key)


def _measure(document: CadDocument, instance: dict[str, Any], mode: str) -> dict[str, Any]:
    members = list(instance["face_ids"])
    bottoms = instance["bottom_face_ids"]
    data = {
        "instance_id": instance["instance_id"], "face_ids": members,
        "bottom_face_id": bottoms[0] if bottoms else None,
    }
    # Two legacy kernels branch on a string named predicted_class. These are
    # private call-local algorithm selectors, NOT an AAGNet prediction, source
    # label mapping, probability, or persisted class ID. No classifier runs.
    if mode.startswith("circular_hole_"):
        data["predicted_class"] = "through_hole" if mode.endswith("through") else "blind_hole"
        return kernels._hole_enrichment(document, data)  # Never auto-partition.
    if mode in {"rectangular_closed_through", "rectangular_open_through"}:
        data["predicted_class"] = "rectangular_passage" if mode == "rectangular_closed_through" else "rectangular_through_slot"
        return kernels._rectangular_through_enrichment(document, data)
    single = {
        "rectangular_blind": kernels._rectangular_blind_enrichment,
        "triangular_slot_through": kernels._triangular_through_slot_enrichment,
        "circular_slot_through": kernels._circular_through_slot_enrichment,
        "rectangular_step_through": kernels._rectangular_through_step_enrichment,
        "rectangular_step_blind": kernels._rectangular_blind_step_enrichment,
        "triangular_step_blind": kernels._triangular_blind_step_enrichment,
        "circular_step_blind": kernels._circular_blind_step_enrichment,
        "circular_end_pocket": kernels._circular_end_pocket_enrichment,
        "vertical_end_slot_blind": kernels._v_circular_end_blind_slot_enrichment,
        "horizontal_end_slot_blind": kernels._h_circular_end_blind_slot_enrichment,
        "annular_groove": kernels._oring_enrichment,
        "planar_chamfer": kernels._chamfer_enrichment,
        "cylindrical_round": kernels._round_enrichment,
    }
    if mode in single:
        return single[mode](document, data)
    if mode in {"polygon3_through", "polygon6_through"}:
        return kernels._polygon_through_enrichment(document, data, 3 if mode.startswith("polygon3") else 6)
    if mode in {"polygon3_blind", "polygon6_blind"}:
        return kernels._polygon_blind_pocket_enrichment(document, data, 3 if mode.startswith("polygon3") else 6)
    if mode == "two_sided_step_through":
        return kernels._open_profile_through_step_enrichment(document, data, 2, 5)
    if mode == "slanted_step_through":
        return kernels._open_profile_through_step_enrichment(document, data, 1, 4)
    raise RuntimeError(f"Unimplemented geometry kernel mode: {mode}")


def build_manufacturing_geometry_context(
    document: CadDocument,
    request: dict[str, Any],
    *,
    postprocess_code_commit: str = "working-tree",
) -> dict[str, Any]:
    """Measure supplied manual/model instances without mutating or splitting them.

    A complete measurement does not establish feature truth, review approval,
    collision-free access, or CAPP authorization. Missing/unsupported evidence
    stays incomplete. P04 remains responsible for output provenance/requirements.
    """

    if not isinstance(document, CadDocument):
        raise TypeError("document must be an imported P01 CadDocument.")
    summary = document.summary()
    validate_manufacturing_geometry_request(request, summary)
    warnings = list(document.warnings)
    enrichments = []
    for instance in request["instances"]:
        instance_id = instance["instance_id"]
        mode = _kernel_mode(instance["canonical_label"])
        bottoms = instance["bottom_face_ids"]
        result = kernels._default_enrichment(instance_id, None, instance["face_ids"])
        result["topology_roles"]["bottom_face_ids"] = list(bottoms)
        if len(bottoms) > 1:
            warnings.append(f"{instance_id}: multiple_bottom_faces_require_review; no geometry kernel selected.")
        elif mode is None:
            warnings.append(f"{instance_id}: unsupported_or_incomplete_canonical_shape; geometry remains incomplete.")
        elif mode in {"circular_hole_through", "planar_chamfer", "cylindrical_round"} and bottoms:
            warnings.append(f"{instance_id}: declared_bottom_conflicts_with_geometry_template; preserved for review.")
        else:
            try:
                result = _measure(document, instance, mode)
            except Exception as exc:
                # Failure isolation does not erase a malformed request: those
                # fail before this loop. Runtime kernel failures are local.
                warnings.append(f"{instance_id}: geometry_kernel_failed:{type(exc).__name__}; preserved for review.")
            if not result["geometry"]["complete"]:
                warnings.append(f"{instance_id}: geometry_incomplete; supplied instance boundary was not changed.")
        result["instance_boundary"] = {
            "source": instance["source"], "split_from_raw_instance": None,
            "partition_id": None, "method": None,
        }
        # Membership and bottom declarations are checked again across the
        # kernel boundary. No guessed/manual bottom can disappear silently.
        if result["member_face_ids"] != instance["face_ids"]:
            raise FaceAlignmentError("Geometry kernel changed the supplied instance boundary.")
        if set(result["topology_roles"]["bottom_face_ids"]) != set(bottoms):
            result = kernels._default_enrichment(instance_id, None, instance["face_ids"])
            result["topology_roles"]["bottom_face_ids"] = list(bottoms)
            result["instance_boundary"]["source"] = instance["source"]
            warnings.append(f"{instance_id}: geometry_bottom_role_conflict; declarations preserved, geometry incomplete.")
        enrichments.append(result)
    if document.units["source_length"] and document.units["source_length"] != ["millimetre"]:
        warnings.append("STEP source length unit converted by OCCT to millimetres; no normalized-body dimensions used.")
    context = {
        "schema_version": "aicnc.feature-postprocess-context/1.2",
        "part_id": f"factory-{document.step_sha256[:16].lower()}",
        "source": copy.deepcopy(summary["source"]),
        "units": {"length": "mm", "angle": "deg"},
        "coordinate_system": copy.deepcopy(summary["coordinate_system"]),
        "face_id_namespace": document.face_id_namespace,
        "faces": document.features_faces(),
        "enrichments": enrichments,
        "relations": [],
        "warnings": warnings,
        "pipeline_metadata": {
            "postprocess_version": "0.9.0",
            "postprocess_code_commit": postprocess_code_commit,
            "model_code_commit": "not-applicable",
            "geometry_adapter_version": GEOMETRY_ADAPTER_VERSION,
        },
    }
    context_path = ROOT / "projects" / "04_feature_postprocess" / "configs" / "postprocess_context.schema.json"
    _schema_validator(context_path).validate(context)
    return context
