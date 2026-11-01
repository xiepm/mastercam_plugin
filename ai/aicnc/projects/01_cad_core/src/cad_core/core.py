"""OCCT-backed STEP import and deterministic Face registry.

The persistent Face key in the first production-compatible registry is the
pair ``(face_id_namespace, face_id)``.  ``F0000`` therefore never travels
without a namespace containing the STEP hash and exact importer contract.
The fixed occwl adjacency order is retained for compatibility with the pinned
AAGNet graph, while per-Face fingerprints make ordering drift auditable.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import OCC
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCC.Core.BRepBndLib import brepbndlib_Add
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.BRepGProp import brepgprop_LinearProperties, brepgprop_SurfaceProperties
from OCC.Core.GeomAbs import (
    GeomAbs_BSplineSurface,
    GeomAbs_BezierSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_OffsetSurface,
    GeomAbs_OtherSurface,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_SurfaceOfExtrusion,
    GeomAbs_SurfaceOfRevolution,
    GeomAbs_Torus,
)
from OCC.Core.GProp import GProp_GProps
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TColStd import TColStd_SequenceOfAsciiString
from OCC.Core.TopAbs import (
    TopAbs_EXTERNAL,
    TopAbs_FORWARD,
    TopAbs_INTERNAL,
    TopAbs_REVERSED,
)
from OCC.Core.TopoDS import TopoDS_Solid
from OCC.Extend.TopologyUtils import TopologyExplorer
from occwl.graph import face_adjacency
from occwl.solid import Solid

from .errors import FaceAlignmentError, StepImportError


CAD_CORE_SCHEMA = "aicnc.cad-core/1.0"
CAD_CORE_VERSION = "1.0.0"
PREPROCESS_VERSION = "p01-occwl-aag-order/1.0.0"
ROUND_DIGITS = 9

_SURFACE_TYPES = {
    GeomAbs_Plane: "plane",
    GeomAbs_Cylinder: "cylinder",
    GeomAbs_Cone: "cone",
    GeomAbs_Sphere: "sphere",
    GeomAbs_Torus: "torus",
    GeomAbs_BSplineSurface: "bspline",
    GeomAbs_BezierSurface: "bezier",
    GeomAbs_SurfaceOfRevolution: "revolution",
    GeomAbs_SurfaceOfExtrusion: "extrusion",
    GeomAbs_OffsetSurface: "offset",
    GeomAbs_OtherSurface: "other",
}

_ORIENTATIONS = {
    TopAbs_FORWARD: "forward",
    TopAbs_REVERSED: "reversed",
    TopAbs_INTERNAL: "internal",
    TopAbs_EXTERNAL: "external",
}


def _round(value: float, digits: int = ROUND_DIGITS) -> float:
    result = round(float(value), digits)
    return 0.0 if result == -0.0 else result


def _vector(values: Iterable[float], digits: int = ROUND_DIGITS) -> list[float]:
    return [_round(value, digits) for value in values]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _canonical_direction(values: Iterable[float]) -> list[float]:
    direction = [float(value) for value in values]
    norm = math.sqrt(sum(value * value for value in direction))
    if norm <= 1e-12:
        raise StepImportError("OCCT returned a zero-length analytic direction.")
    direction = [value / norm for value in direction]
    for value in direction:
        if abs(value) > 1e-12:
            if value < 0:
                direction = [-item for item in direction]
            break
    return _vector(direction, 12)


def _shape_bbox(shape) -> dict[str, list[float]]:
    box = Bnd_Box()
    brepbndlib_Add(shape, box)
    if box.IsVoid():
        raise StepImportError("OCCT returned an empty bounding box.")
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {
        "min": _vector((xmin, ymin, zmin)),
        "max": _vector((xmax, ymax, zmax)),
    }


def _surface_type(face) -> str:
    return _SURFACE_TYPES.get(BRepAdaptor_Surface(face).GetType(), "other")


def _surface_properties(face) -> tuple[float, list[float]]:
    properties = GProp_GProps()
    brepgprop_SurfaceProperties(face, properties)
    return _round(properties.Mass()), _vector(properties.CentreOfMass().Coord())


def _edge_length(edge) -> float:
    properties = GProp_GProps()
    brepgprop_LinearProperties(edge, properties)
    return _round(properties.Mass())


def _axis_record(axis) -> dict[str, list[float]]:
    direction = _canonical_direction(axis.Direction().Coord())
    location = [float(value) for value in axis.Location().Coord()]
    dot = sum(a * b for a, b in zip(location, direction))
    closest = [value - dot * component for value, component in zip(location, direction)]
    return {"direction": direction, "closest_point_to_origin": _vector(closest)}


def _analytic_surface(face) -> dict[str, Any] | None:
    adaptor = BRepAdaptor_Surface(face)
    surface_type = adaptor.GetType()
    if surface_type == GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        return {
            "kind": "cylinder",
            "radius": _round(cylinder.Radius()),
            "axis": _axis_record(cylinder.Axis()),
        }
    if surface_type == GeomAbs_Cone:
        cone = adaptor.Cone()
        return {
            "kind": "cone",
            "semi_angle_deg": _round(math.degrees(cone.SemiAngle())),
            "reference_radius": _round(cone.RefRadius()),
            "axis": _axis_record(cone.Axis()),
        }
    if surface_type == GeomAbs_Plane:
        plane = adaptor.Plane()
        direction = _canonical_direction(plane.Axis().Direction().Coord())
        location = [float(value) for value in plane.Location().Coord()]
        return {
            "kind": "plane",
            "normal": direction,
            "signed_offset": _round(sum(a * b for a, b in zip(location, direction))),
        }
    if surface_type == GeomAbs_Sphere:
        sphere = adaptor.Sphere()
        return {
            "kind": "sphere",
            "radius": _round(sphere.Radius()),
            "center": _vector(sphere.Location().Coord()),
        }
    if surface_type == GeomAbs_Torus:
        torus = adaptor.Torus()
        return {
            "kind": "torus",
            "major_radius": _round(torus.MajorRadius()),
            "minor_radius": _round(torus.MinorRadius()),
            "axis": _axis_record(torus.Axis()),
        }
    return None


def _file_units(reader: STEPControl_Reader) -> dict[str, list[str]]:
    sequences = [TColStd_SequenceOfAsciiString() for _ in range(3)]
    reader.FileUnits(*sequences)

    def values(sequence) -> list[str]:
        return [sequence.Value(index).ToCString() for index in range(1, sequence.Length() + 1)]

    return {
        "source_length": values(sequences[0]),
        "source_angle": values(sequences[1]),
        "source_solid_angle": values(sequences[2]),
        "internal_length": ["millimetre"],
    }


def _single_solid(shape) -> tuple[Any, list[str]]:
    if isinstance(shape, TopoDS_Solid):
        return shape, []
    solids = list(TopologyExplorer(shape, ignore_orientation=True).solids())
    if len(solids) == 1:
        return solids[0], ["STEP root was a compound/assembly; extracted its only Solid."]
    if not solids:
        raise StepImportError("STEP contains no Solid.")
    raise StepImportError(f"P01 currently accepts one Solid; STEP contains {len(solids)}.")


def _load_step(path: Path) -> tuple[Any, dict[str, list[str]], list[str]]:
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise StepImportError("OCCT could not read the STEP file.")
    units = _file_units(reader)
    if reader.TransferRoots() <= 0:
        raise StepImportError("OCCT could not transfer any STEP roots.")
    body, warnings = _single_solid(reader.OneShape())
    if not BRepCheck_Analyzer(body).IsValid(body):
        raise StepImportError("BRepCheck_Analyzer rejected the imported Solid.")
    return body, units, warnings


class CadDocument:
    """One immutable STEP import plus its in-memory OCCT entities."""

    def __init__(self, path: Path, body, units: dict[str, list[str]], warnings: list[str]):
        self.path = path
        self.body = body
        self.step_sha256 = _sha256(path)
        self.occt_version = str(getattr(OCC, "VERSION", "unknown"))
        self.units = units
        self.warnings = list(warnings)
        self.face_graph = face_adjacency(Solid(body))
        self.node_indices = sorted(self.face_graph.nodes)
        if self.node_indices != list(range(len(self.node_indices))):
            raise StepImportError("occwl Face nodes are not contiguous 0..N-1.")
        self.faces = {
            node: self.face_graph.nodes[node]["face"].topods_shape()
            for node in self.node_indices
        }
        self.face_id_by_node = {node: f"F{node:04d}" for node in self.node_indices}
        self.face_id_namespace = (
            f"aicnc-face-registry/1.0:{self.step_sha256}:"
            f"occt-{self.occt_version}:{PREPROCESS_VERSION}"
        )
        self._build_edges()
        self._build_face_records()

    @classmethod
    def from_step(cls, path: str | Path) -> "CadDocument":
        step_path = Path(path).resolve()
        if not step_path.is_file():
            raise StepImportError(f"STEP file does not exist: {step_path}")
        if step_path.suffix.lower() not in {".step", ".stp"}:
            raise StepImportError("P01 only accepts .step and .stp files.")
        body, units, warnings = _load_step(step_path)
        return cls(step_path, body, units, warnings)

    def _build_edges(self) -> None:
        explorer = TopologyExplorer(self.body, ignore_orientation=True)
        self.edges = list(explorer.edges())
        self.edge_id_by_shape = {edge: f"E{index:04d}" for index, edge in enumerate(self.edges)}
        self._edge_buckets: dict[int, list[tuple[Any, str]]] = {}
        for index, edge in enumerate(self.edges):
            self._edge_buckets.setdefault(edge.HashCode(2147483647), []).append(
                (edge, f"E{index:04d}")
            )
        face_buckets: dict[int, list[tuple[Any, int]]] = {}
        for node, face in self.faces.items():
            face_buckets.setdefault(face.HashCode(2147483647), []).append((face, node))

        def face_node(face) -> int | None:
            for candidate, node in face_buckets.get(face.HashCode(2147483647), []):
                if candidate.IsSame(face):
                    return node
            return None

        self.edge_records: list[dict[str, Any]] = []
        for index, edge in enumerate(self.edges):
            adjacent_nodes = sorted(
                node
                for node in (face_node(face) for face in explorer.faces_from_edge(edge))
                if node is not None
            )
            self.edge_records.append(
                {
                    "edge_id": f"E{index:04d}",
                    "curve_type_id": int(BRepAdaptor_Curve(edge).GetType()),
                    "length": _edge_length(edge),
                    "adjacent_face_ids": [self.face_id_by_node[node] for node in adjacent_nodes],
                }
            )

    def edge_id(self, edge) -> str | None:
        """Resolve an oriented Face edge to the registry's orientation-free ID."""

        for candidate, edge_id in self._edge_buckets.get(edge.HashCode(2147483647), []):
            if candidate.IsSame(edge):
                return edge_id
        return None

    def _build_face_records(self) -> None:
        edge_ids_by_face: dict[int, list[str]] = {}
        base_records: dict[int, dict[str, Any]] = {}
        for node, face in self.faces.items():
            edge_ids: list[str] = []
            for edge in TopologyExplorer(face, ignore_orientation=True).edges():
                edge_id = self.edge_id(edge)
                if edge_id is None:
                    raise StepImportError("A Face edge is missing from the Solid edge registry.")
                edge_ids.append(edge_id)
            edge_ids_by_face[node] = sorted(set(edge_ids))
            area, centroid = _surface_properties(face)
            base_records[node] = {
                "surface_type": _surface_type(face),
                "area": area,
                "centroid": centroid,
                "orientation": _ORIENTATIONS.get(face.Orientation(), "unknown"),
                "edge_count": len(edge_ids_by_face[node]),
                "perimeter": _round(
                    sum(self.edge_records[int(edge_id[1:])]["length"] for edge_id in edge_ids_by_face[node])
                ),
                "analytic": _analytic_surface(face),
            }

        self.face_records: list[dict[str, Any]] = []
        seen_fingerprints: dict[str, list[str]] = {}
        for node in self.node_indices:
            neighbors = sorted(set(self.face_graph.successors(node)) | set(self.face_graph.predecessors(node)))
            fingerprint_payload = {
                **base_records[node],
                "neighbor_surface_types": sorted(base_records[index]["surface_type"] for index in neighbors),
                "neighbor_count": len(neighbors),
            }
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest().upper()
            face_id = self.face_id_by_node[node]
            seen_fingerprints.setdefault(fingerprint, []).append(face_id)
            record = {
                "face_id": face_id,
                "node_index": node,
                "fingerprint_sha256": fingerprint,
                **base_records[node],
                "edge_ids": edge_ids_by_face[node],
                "adjacent_face_ids": [self.face_id_by_node[index] for index in neighbors],
            }
            self.face_records.append(record)
        collisions = [ids for ids in seen_fingerprints.values() if len(ids) > 1]
        if collisions:
            self.warnings.append(
                "Symmetric Faces share geometry fingerprints; fixed OCCT/occwl order remains the tie-breaker: "
                + ", ".join("/".join(ids) for ids in collisions)
            )

    def features_faces(self) -> list[dict[str, Any]]:
        """Return the exact Face subset accepted by features.json 2.2."""

        return [
            {
                "face_id": record["face_id"],
                "surface_type": record["surface_type"],
                "area": record["area"],
                "centroid": list(record["centroid"]),
                "orientation": record["orientation"],
            }
            for record in self.face_records
        ]

    def summary(self) -> dict[str, Any]:
        """Return the auditable, JSON-serializable P01 intermediate object."""

        return {
            "schema_version": CAD_CORE_SCHEMA,
            "source": {
                "step_file": self.path.name,
                "step_sha256": self.step_sha256,
                "occt_version": self.occt_version,
                "preprocess_version": PREPROCESS_VERSION,
            },
            "units": self.units,
            "coordinate_system": {
                "name": "PCS",
                "origin": [0.0, 0.0, 0.0],
                "x_axis": [1.0, 0.0, 0.0],
                "y_axis": [0.0, 1.0, 0.0],
                "z_axis": [0.0, 0.0, 1.0],
            },
            "face_id_namespace": self.face_id_namespace,
            "body_bounding_box": _shape_bbox(self.body),
            "faces": self.face_records,
            "edges": self.edge_records,
            "diagnostics": {
                "solid_count": 1,
                "face_count": len(self.face_records),
                "edge_count": len(self.edge_records),
                "brep_valid": True,
                "warnings": self.warnings,
            },
        }

    def scaled_alignment_signatures(self) -> list[dict[str, Any]]:
        """Reproduce the geometry-only signatures used by the P03 web adapter."""

        scaled = Solid(self.body, allow_compound=True).scale_to_unit_box(copy=True)
        graph = face_adjacency(scaled)
        nodes = sorted(graph.nodes)
        if nodes != self.node_indices:
            raise FaceAlignmentError("Scaling changed the Face node registry.")
        signatures: list[dict[str, Any]] = []
        primary = ("plane", "cylinder", "cone", "sphere", "torus")
        for node in nodes:
            face = graph.nodes[node]["face"].topods_shape()
            area, centroid = _surface_properties(face)
            surface = _surface_type(face)
            signatures.append(
                {
                    "primary_surface_flags": [1.0 if surface == name else 0.0 for name in primary],
                    "normalized_area": _round(area, 6),
                    "normalized_centroid": _vector(centroid, 6),
                }
            )
        return signatures

    def verify_prediction_alignment(self, prediction: dict[str, Any], tolerance: float = 2e-5) -> None:
        """Reject a model result whose graph order differs from this import."""

        predicted_faces = prediction.get("faces", [])
        if len(predicted_faces) != len(self.face_records):
            raise FaceAlignmentError(
                f"Face count mismatch: P01={len(self.face_records)}, P03={len(predicted_faces)}."
            )
        expected = self.scaled_alignment_signatures()
        for node, (record, signature) in enumerate(zip(predicted_faces, expected)):
            face_id = self.face_id_by_node[node]
            if record.get("node_index") != node or record.get("face_id") != face_id:
                raise FaceAlignmentError(f"P03 breaks the fixed node mapping at {face_id}.")
            actual = record.get("alignment_signature", {})
            if actual.get("primary_surface_flags") != signature["primary_surface_flags"]:
                raise FaceAlignmentError(f"Surface type mismatch at {face_id}.")
            for key in ("normalized_area",):
                if abs(float(actual.get(key, math.inf)) - float(signature[key])) > tolerance:
                    raise FaceAlignmentError(f"Normalized area mismatch at {face_id}.")
            actual_centroid = actual.get("normalized_centroid", [])
            if len(actual_centroid) != 3 or any(
                abs(float(left) - float(right)) > tolerance
                for left, right in zip(actual_centroid, signature["normalized_centroid"])
            ):
                raise FaceAlignmentError(f"Normalized centroid mismatch at {face_id}.")

    def bounding_box_for_face_ids(self, face_ids: Iterable[str]) -> dict[str, list[float]]:
        box = Bnd_Box()
        for face_id in face_ids:
            try:
                node = int(face_id[1:])
                face = self.faces[node]
            except (ValueError, KeyError):
                raise FaceAlignmentError(f"Unknown Face ID: {face_id}") from None
            brepbndlib_Add(face, box)
        if box.IsVoid():
            raise FaceAlignmentError("Cannot build a bounding box for an empty Face set.")
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return {"min": _vector((xmin, ymin, zmin)), "max": _vector((xmax, ymax, zmax))}
