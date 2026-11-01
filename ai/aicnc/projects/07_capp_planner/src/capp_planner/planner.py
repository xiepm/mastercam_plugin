from __future__ import annotations

import math
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable

from .errors import PlannerError
from .schema_validation import validate_context, validate_features, validate_plan


PLANNER_VERSION = "0.1.0"
CAM_PLAN_SCHEMA_VERSION = "1.1.0"
_VECTOR_TOLERANCE = 1e-6


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalize(vector: list[float], *, label: str) -> list[float]:
    if len(vector) != 3 or not all(math.isfinite(float(value)) for value in vector):
        raise PlannerError(f"{label} must be a finite 3-vector")
    length = math.sqrt(sum(float(value) ** 2 for value in vector))
    if length <= _VECTOR_TOLERANCE:
        raise PlannerError(f"{label} must be non-zero")
    return [round(float(value) / length, 10) for value in vector]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _validate_context_geometry(context: dict[str, Any]) -> None:
    fixture = context["fixture"]
    if context["status"] == "validated" and fixture["direction_policy"] != "listed_only":
        raise PlannerError("validated manufacturing context requires listed_only fixture directions")
    frame = fixture["work_coordinate_system"]
    x_axis = _normalize(frame["x_axis"], label="fixture WCS x_axis")
    y_axis = _normalize(frame["y_axis"], label="fixture WCS y_axis")
    z_axis = _normalize(frame["z_axis"], label="fixture WCS z_axis")
    if abs(_dot(x_axis, y_axis)) > _VECTOR_TOLERANCE:
        raise PlannerError("fixture WCS x_axis and y_axis must be orthogonal")
    if _dot(_normalize(_cross(x_axis, y_axis), label="fixture WCS x cross y"), z_axis) < 1 - _VECTOR_TOLERANCE:
        raise PlannerError("fixture WCS must be right-handed")
    for index, direction in enumerate(fixture["allowed_machining_directions"]):
        _normalize(direction, label=f"allowed machining direction {index}")


def _measurements(feature: dict[str, Any]) -> tuple[dict[str, float], set[str]]:
    values: dict[str, float] = {}
    ambiguous: set[str] = set()
    for measurement in feature["geometry"]["measurements"]:
        name = measurement["name"]
        value = float(measurement["value"])
        if name in values and not math.isclose(values[name], value, rel_tol=1e-7, abs_tol=1e-7):
            ambiguous.add(name)
        else:
            values[name] = value
    return values, ambiguous


def _operation_policy(feature: dict[str, Any], measurements: dict[str, float]) -> tuple[dict[str, Any] | None, list[str]]:
    label = feature["canonical_label"]
    family = label["family"]
    attributes = label.get("attributes", {})
    policy: dict[str, Any]
    required: list[str]

    if family == "hole":
        policy = {
            "rule_id": "G8-HOLE-DRILL-EXACT-DIAMETER-V1",
            "operation_type": "drilling",
            "tool_type": "drill",
            "tool_mode": "exact",
            "tool_limit_measurement": "diameter",
        }
        required = ["diameter"]
    elif family in {"pocket", "slot"}:
        policy = {
            "rule_id": f"G8-{family.upper()}-FLAT-END-MILL-V1",
            "operation_type": "pocketing",
            "tool_type": "flat_end_mill",
            "tool_mode": "largest_within_80_percent",
            "tool_limit_measurement": "width",
        }
        required = ["width", "depth"]
    elif family in {"passage", "step"}:
        policy = {
            "rule_id": f"G8-{family.upper()}-CONTOUR-V1",
            "operation_type": "contouring",
            "tool_type": "flat_end_mill",
            "tool_mode": "largest_within_80_percent",
            "tool_limit_measurement": "width",
        }
        required = ["width", "depth"]
    elif family == "groove" and attributes.get("profile") == "annular":
        policy = {
            "rule_id": "G8-ANNULAR-GROOVE-CONTOUR-V1",
            "operation_type": "contouring",
            "tool_type": "flat_end_mill",
            "tool_mode": "largest_within_80_percent",
            "tool_limit_measurement": "width",
        }
        required = ["width", "depth", "inner_diameter", "outer_diameter"]
    elif family == "edge_transition" and attributes.get("edge_form") == "chamfer":
        policy = {
            "rule_id": "G8-EDGE-CHAMFER-V1",
            "operation_type": "chamfering",
            "tool_type": "chamfer_mill",
            "tool_mode": "smallest_available",
            "tool_limit_measurement": None,
        }
        required = ["chamfer_width", "chamfer_angle"]
    elif family == "edge_transition" and attributes.get("edge_form") in {"round", "fillet"}:
        policy = {
            "rule_id": "G8-EDGE-ROUND-BALL-END-MILL-V1",
            "operation_type": "contouring",
            "tool_type": "ball_end_mill",
            "tool_mode": "largest_not_above_diameter",
            "tool_limit_measurement": "diameter",
        }
        required = ["radius"]
        measurements = dict(measurements)
        measurements["diameter"] = measurements.get("radius", 0.0) * 2.0
    else:
        return None, ["unsupported_feature_taxonomy"]

    missing = [name for name in required if name not in measurements or measurements[name] <= 0]
    if missing:
        return None, [f"missing_required_measurement:{name}" for name in missing]
    policy["required_measurements"] = required
    policy["measurements"] = measurements
    return policy, []


def _measurement_unit_reasons(
    feature: dict[str, Any], policy: dict[str, Any], context: dict[str, Any]
) -> list[str]:
    by_name = {
        item["name"]: item["unit"] for item in feature["geometry"]["measurements"]
    }
    reasons: list[str] = []
    for name in policy["required_measurements"]:
        expected = (
            context["units"]["angle"]
            if name in {"angle", "chamfer_angle"}
            else context["units"]["length"]
        )
        if by_name.get(name) != expected:
            reasons.append(f"measurement_unit_mismatch:{name}")
    return reasons


def _select_direction(feature: dict[str, Any], context: dict[str, Any]) -> tuple[list[float] | None, list[str]]:
    access_directions = feature["placement"].get("access_directions", [])
    if not access_directions:
        return None, ["missing_access_direction"]
    normalized: list[list[float]] = []
    for index, direction in enumerate(access_directions):
        try:
            normalized.append(_normalize(direction, label=f"feature access direction {index}"))
        except PlannerError:
            continue
    if not normalized:
        return None, ["invalid_access_direction"]
    fixture = context["fixture"]
    if fixture["direction_policy"] == "any_normalized":
        return normalized[0], []
    allowed = [
        _normalize(direction, label="fixture allowed direction")
        for direction in fixture["allowed_machining_directions"]
    ]
    for direction in normalized:
        if any(_dot(direction, candidate) >= 1 - _VECTOR_TOLERANCE for candidate in allowed):
            return direction, []
    return None, ["fixture_direction_not_allowed"]


def _select_tool(policy: dict[str, Any], context: dict[str, Any], feature: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    tools = [
        tool
        for tool in context["tools"]
        if tool["status"] == "available" and tool["tool_type"] == policy["tool_type"]
    ]
    if not tools:
        return None, ["no_available_tool_type"]
    measurements = policy["measurements"]
    mode = policy["tool_mode"]
    if mode == "exact":
        target = measurements[policy["tool_limit_measurement"]]
        tolerance = max(1e-6, abs(target) * 1e-4)
        tools = [tool for tool in tools if math.isclose(tool["diameter"], target, abs_tol=tolerance)]
    elif mode == "largest_within_80_percent":
        limit = measurements[policy["tool_limit_measurement"]] * 0.8
        tools = [tool for tool in tools if tool["diameter"] <= limit + _VECTOR_TOLERANCE]
    elif mode == "largest_not_above_diameter":
        limit = measurements[policy["tool_limit_measurement"]]
        tools = [tool for tool in tools if tool["diameter"] <= limit + _VECTOR_TOLERANCE]
    if not tools:
        return None, ["no_dimensionally_compatible_tool"]

    depth = max(
        measurements.get("depth", 0.0),
        measurements.get("through_length", 0.0),
    )
    if depth > 0:
        tools = [tool for tool in tools if tool["stickout"] >= depth + context["safety"]["retract"]]
        if not tools:
            return None, ["tool_stickout_insufficient"]

    reverse = mode != "smallest_available"
    selected = sorted(tools, key=lambda tool: (tool["diameter"], tool["tool_id"]), reverse=reverse)[0]
    return selected, []


def _select_preset(policy: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    matches = [
        preset
        for preset in context["technology_presets"]
        if preset["material_id"] == context["material"]["material_id"]
        and preset["operation_type"] == policy["operation_type"]
        and preset["tool_type"] == policy["tool_type"]
    ]
    if not matches:
        return None, ["missing_technology_preset"]
    preset = sorted(matches, key=lambda item: item["preset_id"])[0]
    if context["status"] == "validated" and preset["status"] != "validated":
        return None, ["technology_preset_not_validated"]
    return preset, []


def _hole_milling_fallback(policy: dict[str, Any]) -> dict[str, Any]:
    fallback = deepcopy(policy)
    fallback.update(
        {
            "rule_id": "G8-HOLE-HELICAL-MILL-FALLBACK-V1",
            "operation_type": "contouring",
            "tool_type": "flat_end_mill",
            "tool_mode": "largest_within_80_percent",
            "tool_limit_measurement": "diameter",
        }
    )
    return fallback


def _confidence(feature: dict[str, Any]) -> float:
    prediction = feature["prediction"]
    values = [prediction["confidence"]]
    values.extend(
        value
        for value in (prediction.get("instance_confidence"), prediction.get("bottom_confidence"))
        if value is not None
    )
    return round(min(values), 6)


def _candidate_review_reasons(feature: dict[str, Any], context: dict[str, Any], preset: dict[str, Any]) -> list[str]:
    reasons = [
        "mastercam_simulation_not_run",
        "manufacturing_parameters_require_review",
        "stock_geometry_not_verified",
    ]
    if context["status"] == "prototype":
        reasons.append("prototype_manufacturing_context")
    if preset["status"] == "prototype":
        reasons.append("prototype_technology_preset")
    if feature["prediction"]["status"] != "confirmed":
        reasons.append("model_recognition_not_manually_confirmed")
    if feature["requirements"]["status"] != "complete":
        reasons.append("quality_requirements_not_complete")
    return _unique(reasons)


def _feature_gate(feature: dict[str, Any], face_ids: set[str]) -> list[str]:
    reasons: list[str] = []
    prediction = feature["prediction"]
    if prediction["status"] not in {"recognized", "confirmed"}:
        reasons.append(f"feature_prediction_status:{prediction['status']}")
    if not feature["topology"]["roles_complete"]:
        reasons.append("topology_roles_incomplete")
    if not feature["geometry"]["complete"]:
        reasons.append("geometry_incomplete")
    unknown_faces = [face_id for face_id in feature["topology"]["face_ids"] if face_id not in face_ids]
    if unknown_faces:
        reasons.append("feature_references_unknown_face")
    measurements, ambiguous = _measurements(feature)
    del measurements
    reasons.extend(f"ambiguous_measurement:{name}" for name in sorted(ambiguous))
    return reasons


def _public_tool(tool: dict[str, Any]) -> dict[str, Any]:
    result = {
        "tool_id": tool["tool_id"],
        "tool_type": tool["tool_type"],
        "diameter": tool["diameter"],
        "stickout": tool["stickout"],
    }
    if "corner_radius" in tool:
        result["corner_radius"] = tool["corner_radius"]
    return result


def _safe_part_name(part_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", part_id).strip("._")
    return value or "part"


def _validate_trace(plan: dict[str, Any], features: dict[str, Any]) -> None:
    source = {feature["instance_id"]: set(feature["topology"]["face_ids"]) for feature in features["features"]}
    seen: list[str] = []
    for setup in plan["setups"]:
        for operation in setup["operations"]:
            instance_ids = operation["feature_instance_ids"]
            if len(instance_ids) != 1:
                raise PlannerError("G8 operations must trace to exactly one feature instance")
            instance_id = instance_ids[0]
            if instance_id not in source:
                raise PlannerError(f"operation references unknown feature {instance_id}")
            if set(operation["face_ids"]) != source[instance_id]:
                raise PlannerError(f"operation face trace differs from {instance_id}")
            seen.append(instance_id)
    for unplanned in plan["unplanned_features"]:
        instance_id = unplanned["feature_instance_id"]
        if instance_id not in source or set(unplanned["face_ids"]) != source[instance_id]:
            raise PlannerError(f"unplanned feature trace differs from {instance_id}")
        seen.append(instance_id)
    expected = list(source)
    if sorted(seen) != sorted(expected) or len(seen) != len(set(seen)):
        raise PlannerError("every feature must appear exactly once as planned or unplanned")


def build_cam_plan(
    features: dict[str, Any],
    context: dict[str, Any],
    *,
    features_path: str,
    features_sha256: str,
    context_path: str,
    context_sha256: str,
    code_commit: str = "working-tree",
) -> dict[str, Any]:
    """Build a deterministic, traceable and review-only CAPP candidate plan."""

    validate_features(features)
    validate_context(context)
    _validate_context_geometry(context)
    if features["units"]["length"] != context["units"]["length"]:
        raise PlannerError("features and manufacturing context length units differ")
    if features["units"]["angle"] != context["units"]["angle"]:
        raise PlannerError("features and manufacturing context angle units differ")
    for label, digest in (("features", features_sha256), ("context", context_sha256)):
        if not re.fullmatch(r"[A-Fa-f0-9]{64}", digest):
            raise PlannerError(f"{label} sha256 must contain 64 hexadecimal characters")

    face_ids = {face["face_id"] for face in features["faces"]}
    candidates: list[dict[str, Any]] = []
    unplanned: list[dict[str, Any]] = []

    for feature in features["features"]:
        instance_id = feature["instance_id"]
        trace_faces = feature["topology"]["face_ids"]
        reasons = _feature_gate(feature, face_ids)
        measurements, _ = _measurements(feature)
        policy, policy_reasons = _operation_policy(feature, measurements)
        reasons.extend(policy_reasons)
        if policy is not None:
            reasons.extend(_measurement_unit_reasons(feature, policy, context))
        direction, direction_reasons = _select_direction(feature, context)
        reasons.extend(direction_reasons)

        tool = None
        preset = None
        if policy is not None:
            tool, tool_reasons = _select_tool(policy, context, feature)
            preset, preset_reasons = _select_preset(policy, context)
            if feature["canonical_label"]["family"] == "hole" and (tool is None or preset is None):
                fallback = _hole_milling_fallback(policy)
                fallback_tool, fallback_tool_reasons = _select_tool(fallback, context, feature)
                fallback_preset, fallback_preset_reasons = _select_preset(fallback, context)
                if fallback_tool is not None and fallback_preset is not None:
                    policy = fallback
                    tool = fallback_tool
                    preset = fallback_preset
                    tool_reasons = []
                    preset_reasons = []
                else:
                    tool_reasons.extend(f"milling_fallback:{reason}" for reason in fallback_tool_reasons)
                    preset_reasons.extend(f"milling_fallback:{reason}" for reason in fallback_preset_reasons)
            if policy["operation_type"] not in context["machine"]["supported_operation_types"]:
                reasons.append("machine_operation_not_supported")
            reasons.extend(tool_reasons)
            reasons.extend(preset_reasons)

        if reasons or policy is None or direction is None or tool is None or preset is None:
            unplanned.append(
                {
                    "feature_instance_id": instance_id,
                    "face_ids": trace_faces,
                    "reason_codes": _unique(reasons or ["internal_planning_gate_failed"]),
                    "notes": "No operation emitted; no missing manufacturing value was guessed.",
                }
            )
            continue

        review_reasons = _candidate_review_reasons(feature, context, preset)
        candidates.append(
            {
                "instance_id": instance_id,
                "face_ids": trace_faces,
                "direction": direction,
                "policy": policy,
                "tool": tool,
                "preset": preset,
                "confidence": _confidence(feature),
                "recognition_status": feature["prediction"]["status"],
                "review_reasons": review_reasons,
            }
        )

    grouped: dict[tuple[float, float, float], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[tuple(candidate["direction"])].append(candidate)

    setups: list[dict[str, Any]] = []
    operation_counter = 0
    for setup_sequence, direction_key in enumerate(sorted(grouped), start=1):
        operations: list[dict[str, Any]] = []
        for operation_sequence, candidate in enumerate(
            sorted(grouped[direction_key], key=lambda item: item["instance_id"]), start=1
        ):
            operation_counter += 1
            tool = candidate["tool"]
            preset = candidate["preset"]
            operations.append(
                {
                    "operation_id": f"operation:{operation_counter:04d}",
                    "sequence": operation_sequence,
                    "operation_type": candidate["policy"]["operation_type"],
                    "feature_instance_ids": [candidate["instance_id"]],
                    "face_ids": candidate["face_ids"],
                    "strategy": preset["strategy"],
                    "tool": _public_tool(tool),
                    "cutting_parameters": deepcopy(preset["cutting_parameters"]),
                    "safety": {
                        key: context["safety"][key]
                        for key in (
                            "clearance",
                            "retract",
                            "stock_to_leave_radial",
                            "stock_to_leave_axial",
                        )
                    },
                    "confidence": candidate["confidence"],
                    "status": "needs_review",
                    "decision_trace": {
                        "rule_id": candidate["policy"]["rule_id"],
                        "strategy_source": f"manufacturing_context:{preset['preset_id']}",
                        "tool_source": f"manufacturing_context:{tool['tool_id']}",
                        "parameter_source": f"manufacturing_context:{preset['preset_id']}",
                        "recognition_status": candidate["recognition_status"],
                    },
                    "review_reasons": candidate["review_reasons"],
                    "notes": "Review-only G8 candidate; no toolpath or executable NC was generated.",
                }
            )
        setup_reasons = _unique(
            [reason for operation in operations for reason in operation["review_reasons"]]
            + (["fixture_not_validated"] if context["status"] == "prototype" else [])
        )
        setups.append(
            {
                "setup_id": f"setup:{setup_sequence}",
                "sequence": setup_sequence,
                "name": f"Direction setup {setup_sequence}",
                "work_coordinate_system": deepcopy(context["fixture"]["work_coordinate_system"]),
                "machining_direction": list(direction_key),
                "stock": {
                    "type": context["stock"]["type"],
                    "dimensions": deepcopy(context["stock"]["dimensions"]),
                    "material": context["material"]["designation"],
                },
                "fixture_id": context["fixture"]["fixture_id"],
                "operations": operations,
                "review_reasons": setup_reasons,
            }
        )

    top_reasons = ["mastercam_simulation_not_run"]
    if context["status"] == "prototype":
        top_reasons.append("prototype_manufacturing_context")
    if candidates:
        top_reasons.append("operations_require_review")
    if unplanned:
        top_reasons.append("contains_unplanned_features")

    extension = context["postprocessing"]["output_extension"]
    plan = {
        "schema_version": CAM_PLAN_SCHEMA_VERSION,
        "plan_id": f"PLAN-{_safe_part_name(features['part_id'])}-{features_sha256[:8]}-{context_sha256[:8]}",
        "part_id": features["part_id"],
        "source_features": {
            "path": features_path,
            "sha256": features_sha256.lower(),
            "schema_version": features["schema_version"],
            "face_id_namespace": features["face_id_namespace"],
        },
        "manufacturing_context": {
            "path": context_path,
            "sha256": context_sha256.lower(),
            "schema_version": context["schema_version"],
            "context_id": context["context_id"],
            "status": context["status"],
        },
        "planner_metadata": {
            "producer": "P07 CAPP Planner",
            "producer_version": PLANNER_VERSION,
            "code_commit": code_commit,
            "planning_mode": "review_candidates" if context["status"] == "prototype" else "validated_context",
        },
        "units": deepcopy(context["units"]),
        "status": "needs_review",
        "review_reasons": _unique(top_reasons),
        "setups": setups,
        "unplanned_features": unplanned,
        "postprocessing": {
            "target_system": "Mastercam",
            "machine_id": context["machine"]["machine_id"],
            "controller": context["machine"]["controller"],
            "postprocessor": {
                "name": context["postprocessing"]["postprocessor_name"],
                "version": context["postprocessing"]["postprocessor_version"],
                "sha256": context["postprocessing"]["postprocessor_sha256"],
            },
            "output_file": f"{_safe_part_name(features['part_id'])}{extension}",
        },
    }
    _validate_trace(plan, features)
    validate_plan(plan)
    return plan
