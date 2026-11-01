"""Deterministic PCS samples for the existing P01 stable Edge registry.

This is a sidecar contract.  It deliberately does not add fields to the
frozen ``aicnc.cad-core/1.0`` summary, so existing summaries and cache hashes
remain byte-for-byte comparable.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
from OCC.Core.GeomAbs import (
    GeomAbs_BSplineCurve,
    GeomAbs_BezierCurve,
    GeomAbs_Circle,
    GeomAbs_Ellipse,
    GeomAbs_Hyperbola,
    GeomAbs_Line,
    GeomAbs_OffsetCurve,
    GeomAbs_OtherCurve,
    GeomAbs_Parabola,
)

from .core import (
    PREPROCESS_VERSION,
    CadDocument,
    _axis_record,
    _round,
    _shape_bbox,
    _vector,
)
from .errors import StepImportError


EDGE_PROJECTION_SCHEMA = "aicnc.cad-edge-projection/1.0"
DEFAULT_SAMPLE_COUNT = 9

_CURVE_TYPES = {
    int(GeomAbs_Line): "line",
    int(GeomAbs_Circle): "circle",
    int(GeomAbs_Ellipse): "ellipse",
    int(GeomAbs_Hyperbola): "hyperbola",
    int(GeomAbs_Parabola): "parabola",
    int(GeomAbs_BezierCurve): "bezier",
    int(GeomAbs_BSplineCurve): "bspline",
    int(GeomAbs_OffsetCurve): "offset",
    int(GeomAbs_OtherCurve): "other",
}


def _schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "configs" / "edge_projection.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_edge_projection(payload: dict[str, Any]) -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].absolute_path) or "<root>"
        raise ValueError(f"cad_edge_projection.{location}: {errors[0].message}")


def _distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def _edge_projection_record(
    document: CadDocument, index: int, *, sample_count: int
) -> dict[str, Any]:
    edge = document.edges[index]
    base = document.edge_records[index]
    adaptor = BRepAdaptor_Curve(edge)
    first = float(adaptor.FirstParameter())
    last = float(adaptor.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or last < first:
        raise StepImportError(f"{base['edge_id']} has an invalid finite parameter range.")
    points = [
        _vector(adaptor.Value(first + (last - first) * i / (sample_count - 1)).Coord())
        for i in range(sample_count)
    ]
    start, end = points[0], points[-1]
    curve_type_id = int(adaptor.GetType())
    analytic = None
    if curve_type_id == int(GeomAbs_Circle):
        circle = adaptor.Circle()
        analytic = {
            "kind": "circle",
            "center": _vector(circle.Location().Coord()),
            "radius": _round(circle.Radius()),
            "axis": _axis_record(circle.Axis()),
            "parameter_sweep": _round(last - first, 12),
        }
    return {
        "edge_id": base["edge_id"],
        "curve_type_id": curve_type_id,
        "curve_type": _CURVE_TYPES.get(curve_type_id, "other"),
        "analytic": analytic,
        "length": base["length"],
        "is_degenerate": bool(BRep_Tool.Degenerated(edge)),
        "is_closed_by_endpoints": _distance(start, end) <= 1e-8,
        "parameter_range": [_round(first, 12), _round(last, 12)],
        "start": start,
        "end": end,
        "chord_length": _round(_distance(start, end)),
        "sample_points": points,
        "bounding_box": _shape_bbox(edge),
        "adjacent_face_ids": list(base["adjacent_face_ids"]),
    }


def build_edge_projection(
    document: CadDocument, *, sample_count: int = DEFAULT_SAMPLE_COUNT
) -> dict[str, Any]:
    """Build and validate an immutable PCS Edge projection sidecar."""

    if sample_count < 3 or sample_count % 2 == 0:
        raise ValueError("sample_count must be an odd integer greater than or equal to 3")
    payload = {
        "schema_version": EDGE_PROJECTION_SCHEMA,
        "source": {
            "step_file": document.path.name,
            "step_sha256": document.step_sha256,
            "occt_version": document.occt_version,
            "preprocess_version": PREPROCESS_VERSION,
        },
        "coordinate_system": {
            "name": "PCS",
            "length_unit": "millimetre",
        },
        "face_id_namespace": document.face_id_namespace,
        "edge_id_namespace": (
            f"aicnc-edge-registry/1.0:{document.step_sha256}:"
            f"occt-{document.occt_version}:{PREPROCESS_VERSION}"
        ),
        "sampling": {
            "method": "uniform_occt_parameter_including_endpoints",
            "sample_count_per_edge": sample_count,
        },
        "edges": [
            _edge_projection_record(document, index, sample_count=sample_count)
            for index in range(len(document.edges))
        ],
        "diagnostics": {
            "edge_count": len(document.edges),
            "degenerate_edge_count": sum(
                bool(BRep_Tool.Degenerated(edge)) for edge in document.edges
            ),
        },
    }
    validate_edge_projection(payload)
    return payload
