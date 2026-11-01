"""Build P04 geometry context from a real, unscaled OCCT import."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCC.Core.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane
from OCC.Core.TopAbs import TopAbs_REVERSED
from OCC.Extend.TopologyUtils import TopologyExplorer

from .core import CAD_CORE_VERSION, PREPROCESS_VERSION, CadDocument, _round, _vector
from .errors import FaceAlignmentError


GEOMETRY_ADAPTER_VERSION = "p01-p04-occt/1.7.0"


def _requirements_not_provided() -> dict[str, Any]:
    return {
        "status": "not_provided",
        "dimensional": [],
        "geometric": [],
        "surface": [],
    }


def _model_instance_boundary() -> dict[str, Any]:
    return {
        "source": "model",
        "split_from_raw_instance": None,
        "partition_id": None,
        "method": None,
    }


def _default_enrichment(
    raw_instance_id: str,
    bottom_face_id: str | None,
    member_face_ids: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "raw_instance_id": raw_instance_id,
        "member_face_ids": list(member_face_ids),
        "instance_boundary": _model_instance_boundary(),
        "topology_roles": {
            "side_face_ids": [],
            "bottom_face_ids": [] if bottom_face_id is None else [bottom_face_id],
            "transition_face_ids": [],
            "opening_edge_ids": [],
            "roles_complete": False,
        },
        "placement": {
            "coordinate_system": "PCS",
            "origin": None,
            "origin_role": "unknown",
            "axis": None,
            "local_frame": None,
            "access_directions": [],
            "source": "unknown",
        },
        "geometry": {
            "measurements": [],
            "reference_points": [],
            "complete": False,
        },
        "requirements": _requirements_not_provided(),
    }


def _dot(point: Iterable[float], direction: Iterable[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(point, direction))


def _negate(direction: Iterable[float]) -> list[float]:
    return _vector((-float(value) for value in direction), 12)


def _normalize(direction: Iterable[float]) -> list[float]:
    values = [float(value) for value in direction]
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1e-12:
        raise FaceAlignmentError("Cannot build a feature frame from a zero direction.")
    return _vector((value / norm for value in values), 12)


def _canonical_direction(direction: Iterable[float]) -> list[float]:
    result = _normalize(direction)
    for value in result:
        if abs(value) > 1e-12:
            return _negate(result) if value < 0 else result
    return result


def _cross(first: Iterable[float], second: Iterable[float]) -> list[float]:
    a = [float(value) for value in first]
    b = [float(value) for value in second]
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _axial_local_frame(z_axis: list[float]) -> dict[str, Any]:
    """Return a deterministic right-handed frame for an axially symmetric feature.

    The cylinder determines only the Z axis.  X is the PCS basis direction with
    the smallest absolute projection onto Z, projected into the normal plane;
    Y completes a right-handed frame.  The explicit orientation state prevents
    the arbitrary axial rotation from being mistaken for manufacturing truth.
    """

    z_axis = _normalize(z_axis)
    references = ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])
    reference = min(references, key=lambda item: abs(_dot(item, z_axis)))
    projection = _dot(reference, z_axis)
    x_axis = _normalize(
        value - projection * component
        for value, component in zip(reference, z_axis)
    )
    y_axis = _normalize(_cross(z_axis, x_axis))
    return {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": z_axis,
        "definition_method": "analytic_axis_with_pcs_reference_projection",
        "orientation_state": "axial_rotation_underdetermined",
    }


def _reference_point(
    name: str,
    point: list[float],
    face_ids: list[str],
    method: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "point": point,
        "coordinate_system": "PCS",
        "source": "occt",
        "method": method,
        "face_ids": face_ids,
    }


def _analytic_cylinder_obb(
    center: list[float],
    frame: dict[str, Any],
    radius: float,
    axial_length: float,
) -> dict[str, Any]:
    return {
        "center": center,
        "x_axis": list(frame["x_axis"]),
        "y_axis": list(frame["y_axis"]),
        "z_axis": list(frame["z_axis"]),
        "half_sizes": [_round(radius), _round(radius), _round(axial_length / 2.0)],
        "coordinate_system": "PCS",
        "source": "occt",
        "method": "analytic_cylinder_radius_and_axis_extent",
    }


def _axis_line(adaptor: BRepAdaptor_Surface) -> tuple[list[float], list[float], float]:
    cylinder = adaptor.Cylinder()
    direction = [float(value) for value in cylinder.Axis().Direction().Coord()]
    norm = math.sqrt(sum(value * value for value in direction))
    direction = [value / norm for value in direction]
    for value in direction:
        if abs(value) > 1e-12:
            if value < 0:
                direction = [-item for item in direction]
            break
    location = [float(value) for value in cylinder.Axis().Location().Coord()]
    projection = _dot(location, direction)
    closest = [value - projection * component for value, component in zip(location, direction)]
    return _vector(direction, 12), _vector(closest), float(cylinder.Radius())


def _face_projection_extents(face, direction: list[float]) -> list[float]:
    values: list[float] = []
    for vertex in TopologyExplorer(face, ignore_orientation=True).vertices():
        values.append(_dot(BRep_Tool.Pnt(vertex).Coord(), direction))
    return values


def _face_points(face) -> list[list[float]]:
    points: dict[tuple[float, float, float], list[float]] = {}
    for vertex in TopologyExplorer(face, ignore_orientation=True).vertices():
        point = _vector(BRep_Tool.Pnt(vertex).Coord())
        points[tuple(point)] = point
    return list(points.values())


def _edge_id(document: CadDocument, edge) -> str:
    value = document.edge_id(edge)
    if value is None:
        raise FaceAlignmentError("Feature edge is missing from the P01 edge registry.")
    return value


def _circular_boundary_edges(
    document: CadDocument,
    side_face_ids: list[str],
    direction: list[float],
) -> list[tuple[str, float]]:
    result: dict[str, float] = {}
    for face_id in side_face_ids:
        face = document.faces[int(face_id[1:])]
        for edge in TopologyExplorer(face, ignore_orientation=True).edges():
            adaptor = BRepAdaptor_Curve(edge)
            if adaptor.GetType() != GeomAbs_Circle:
                continue
            result[_edge_id(document, edge)] = _dot(adaptor.Circle().Location().Coord(), direction)
    return sorted(result.items())


def _consistent_cylinders(
    document: CadDocument,
    side_face_ids: list[str],
) -> tuple[list[float], list[float], float] | None:
    axes: list[tuple[list[float], list[float], float]] = []
    for face_id in side_face_ids:
        adaptor = BRepAdaptor_Surface(document.faces[int(face_id[1:])])
        if adaptor.GetType() == GeomAbs_Cylinder:
            axes.append(_axis_line(adaptor))
    if not axes:
        return None
    direction, closest, radius = axes[0]
    tolerance = max(1e-6, abs(radius) * 1e-6)
    for other_direction, other_closest, other_radius in axes[1:]:
        if abs(other_radius - radius) > tolerance:
            return None
        if any(abs(a - b) > 1e-7 for a, b in zip(other_direction, direction)):
            return None
        if math.sqrt(sum((a - b) ** 2 for a, b in zip(other_closest, closest))) > tolerance:
            return None
    return direction, closest, radius


def _same_cylinder_signature(
    first: tuple[list[float], list[float], float],
    second: tuple[list[float], list[float], float],
) -> bool:
    first_direction, first_closest, first_radius = first
    second_direction, second_closest, second_radius = second
    tolerance = max(1e-6, abs(first_radius) * 1e-6, abs(second_radius) * 1e-6)
    return (
        abs(first_radius - second_radius) <= tolerance
        and all(abs(a - b) <= 1e-7 for a, b in zip(first_direction, second_direction))
        and math.sqrt(
            sum((a - b) ** 2 for a, b in zip(first_closest, second_closest))
        )
        <= tolerance
    )


def _connected_components(
    document: CadDocument,
    face_ids: list[str],
) -> list[list[str]]:
    allowed = set(face_ids)
    unseen = set(face_ids)
    components: list[list[str]] = []
    while unseen:
        seed = min(unseen)
        stack = [seed]
        unseen.remove(seed)
        component: list[str] = []
        while stack:
            face_id = stack.pop()
            component.append(face_id)
            adjacent = set(
                document.face_records[int(face_id[1:])]["adjacent_face_ids"]
            )
            for neighbor in sorted(adjacent & allowed & unseen, reverse=True):
                unseen.remove(neighbor)
                stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda item: item[0])


def _cylinder_partitions(
    document: CadDocument,
    member_face_ids: list[str],
) -> list[list[str]] | None:
    """Partition a raw hole into exact analytic-cylinder topology components.

    This deliberately refuses partial assignment: every raw member Face must be
    cylindrical and must belong to exactly one returned component.  Non-cylinder
    transition Faces cannot yet be assigned uniquely and therefore keep the raw
    instance in ``needs_review``.
    """

    signature_groups: list[
        tuple[tuple[list[float], list[float], float], list[str]]
    ] = []
    for face_id in member_face_ids:
        adaptor = BRepAdaptor_Surface(document.faces[int(face_id[1:])])
        if adaptor.GetType() != GeomAbs_Cylinder:
            return None
        signature = _axis_line(adaptor)
        for existing_signature, grouped_face_ids in signature_groups:
            if _same_cylinder_signature(existing_signature, signature):
                grouped_face_ids.append(face_id)
                break
        else:
            signature_groups.append((signature, [face_id]))

    partitions = [
        component
        for _, grouped_face_ids in signature_groups
        for component in _connected_components(document, grouped_face_ids)
    ]
    partitions.sort(key=lambda item: item[0])
    flattened = [face_id for partition in partitions for face_id in partition]
    if sorted(flattened) != sorted(member_face_ids) or len(flattened) != len(set(flattened)):
        return None
    return partitions


def _point_on_axis(closest: list[float], direction: list[float], parameter: float) -> list[float]:
    return _vector(
        (value + parameter * component for value, component in zip(closest, direction))
    )


def _hole_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview["bottom_face_id"]
    side_face_ids = [
        face_id
        for face_id in member_face_ids
        if document.face_records[int(face_id[1:])]["surface_type"] == "cylinder"
    ]
    bottom_face_ids = (
        [bottom_face_id]
        if bottom_face_id is not None and bottom_face_id in member_face_ids
        else []
    )
    transition_face_ids = [
        face_id
        for face_id in member_face_ids
        if face_id not in side_face_ids and face_id not in bottom_face_ids
    ]
    roles_complete = bool(side_face_ids) and set(member_face_ids) == set(
        side_face_ids + bottom_face_ids + transition_face_ids
    )
    result = _default_enrichment(raw_instance_id, None, member_face_ids)
    result["topology_roles"].update(
        {
            "side_face_ids": side_face_ids,
            "bottom_face_ids": bottom_face_ids,
            "transition_face_ids": transition_face_ids,
            "roles_complete": roles_complete,
        }
    )

    cylinder = _consistent_cylinders(document, side_face_ids)
    if cylinder is None:
        return result
    direction, closest, radius = cylinder
    projections = [
        value
        for face_id in side_face_ids
        for value in _face_projection_extents(document.faces[int(face_id[1:])], direction)
    ]
    if not projections:
        return result
    low, high = min(projections), max(projections)
    edge_projections = _circular_boundary_edges(document, side_face_ids, direction)
    diameter = {
        "name": "diameter",
        "value": _round(2.0 * radius),
        "unit": "mm",
        "source": "occt",
        "method": "cylindrical_surface_radius_x2",
        "face_ids": side_face_ids,
    }
    measurements = [diameter]
    class_name = preview["predicted_class"]

    if class_name == "through_hole":
        through_length = high - low
        if through_length <= max(1e-7, radius * 1e-7):
            return result
        endpoint_tolerance = max(1e-6, abs(high - low) * 1e-6)
        opening_edges = [
            edge_id
            for edge_id, parameter in edge_projections
            if abs(parameter - low) <= endpoint_tolerance or abs(parameter - high) <= endpoint_tolerance
        ]
        result["topology_roles"]["bottom_face_ids"] = []
        result["topology_roles"]["transition_face_ids"] = [
            face_id for face_id in member_face_ids if face_id not in side_face_ids
        ]
        result["topology_roles"]["opening_edge_ids"] = opening_edges
        origin = _point_on_axis(closest, direction, low)
        exit_center = _point_on_axis(closest, direction, high)
        frame = _axial_local_frame(direction)
        measurements.append(
            {
                "name": "through_length",
                "value": _round(through_length),
                "unit": "mm",
                "source": "occt",
                "method": "cylindrical_side_face_axis_extent",
                "face_ids": side_face_ids,
            }
        )
        result["placement"] = {
            "coordinate_system": "PCS",
            "origin": origin,
            "origin_role": "opening_center",
            "axis": direction,
            "local_frame": frame,
            "access_directions": [direction, _negate(direction)],
            "source": "occt",
        }
        result["geometry"] = {
            "measurements": measurements,
            "reference_points": [
                _reference_point(
                    "opening_center_low",
                    origin,
                    side_face_ids,
                    "cylinder_axis_at_lower_side_extent",
                ),
                _reference_point(
                    "opening_center_high",
                    exit_center,
                    side_face_ids,
                    "cylinder_axis_at_upper_side_extent",
                ),
            ],
            "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
            "oriented_bounding_box": _analytic_cylinder_obb(
                _point_on_axis(closest, direction, (low + high) / 2.0),
                frame,
                radius,
                through_length,
            ),
            "complete": True,
        }
        return result

    if class_name != "blind_hole" or not bottom_face_ids:
        return result
    bottom_record = document.face_records[int(bottom_face_ids[0][1:])]
    if bottom_record["surface_type"] != "plane":
        return result
    bottom_t = _dot(bottom_record["centroid"], direction)
    if edge_projections:
        opening_t = max(edge_projections, key=lambda item: abs(item[1] - bottom_t))[1]
    else:
        opening_t = low if abs(low - bottom_t) >= abs(high - bottom_t) else high
    depth = abs(bottom_t - opening_t)
    if depth <= max(1e-7, radius * 1e-7):
        return result
    inward = direction if bottom_t > opening_t else _negate(direction)
    edge_tolerance = max(1e-6, depth * 1e-6)
    opening_edges = [
        edge_id
        for edge_id, parameter in edge_projections
        if abs(parameter - opening_t) <= edge_tolerance
    ]
    measurements.append(
        {
            "name": "depth",
            "value": _round(depth),
            "unit": "mm",
            "source": "occt",
            "method": "opening_circle_axis_projection_to_planar_bottom_centroid",
            "face_ids": side_face_ids + bottom_face_ids,
        }
    )
    result["topology_roles"]["opening_edge_ids"] = opening_edges
    opening_center = _point_on_axis(closest, direction, opening_t)
    bottom_center = _point_on_axis(closest, direction, bottom_t)
    frame = _axial_local_frame(inward)
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": inward,
        "local_frame": frame,
        "access_directions": [inward],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": measurements,
        "reference_points": [
            _reference_point(
                "opening_center",
                opening_center,
                side_face_ids,
                "cylinder_axis_at_opening_circle",
            ),
            _reference_point(
                "bottom_center",
                bottom_center,
                side_face_ids + bottom_face_ids,
                "cylinder_axis_at_planar_bottom_projection",
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": _analytic_cylinder_obb(
            _point_on_axis(closest, direction, (opening_t + bottom_t) / 2.0),
            frame,
            radius,
            depth,
        ),
        "complete": True,
    }
    return result


def _hole_enrichments(
    document: CadDocument,
    preview: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return one model-boundary enrichment or safe OCCT child partitions."""

    original = _hole_enrichment(document, preview)
    if preview["predicted_class"] != "through_hole":
        return [original]

    member_face_ids = list(preview["face_ids"])
    partitions = _cylinder_partitions(document, member_face_ids)
    if partitions is None or len(partitions) <= 1:
        return [original]

    children: list[dict[str, Any]] = []
    for partition_index, partition_face_ids in enumerate(partitions, start=1):
        child_preview = dict(preview)
        child_preview["face_ids"] = partition_face_ids
        child_preview["bottom_face_id"] = None
        child = _hole_enrichment(document, child_preview)
        if not child["topology_roles"]["roles_complete"] or not child["geometry"]["complete"]:
            return [original]
        child["instance_boundary"] = {
            "source": "occt_partition",
            "split_from_raw_instance": preview["instance_id"],
            "partition_id": f"{preview['instance_id']}:occt:{partition_index:04d}",
            "method": "analytic_cylinder_signature_and_topology_component",
        }
        children.append(child)

    child_faces = [
        face_id for child in children for face_id in child["member_face_ids"]
    ]
    if sorted(child_faces) != sorted(member_face_ids) or len(child_faces) != len(set(child_faces)):
        return [original]
    return children


def _plane_normal(document: CadDocument, face_id: str) -> list[float] | None:
    adaptor = BRepAdaptor_Surface(document.faces[int(face_id[1:])])
    if adaptor.GetType() != GeomAbs_Plane:
        return None
    return _canonical_direction(adaptor.Plane().Axis().Direction().Coord())


def _oriented_plane_normal(document: CadDocument, face_id: str) -> list[float] | None:
    """Return the material-outward normal of a planar Face.

    ``_plane_normal`` deliberately canonicalizes sign for dimension frames.
    Edge-transition access directions instead need the TopoDS orientation, so
    this helper keeps the geometric plane direction and applies Face reversal.
    """

    face = document.faces[int(face_id[1:])]
    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_Plane:
        return None
    normal = _normalize(adaptor.Plane().Axis().Direction().Coord())
    return _negate(normal) if face.Orientation() == TopAbs_REVERSED else normal


def _bottom_rectangle_frame(
    document: CadDocument,
    bottom_face_id: str,
    z_axis: list[float],
) -> tuple[dict[str, Any], float, float] | None:
    bottom_face = document.faces[int(bottom_face_id[1:])]
    direction_groups: list[list[float]] = []
    edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    if len(edges) < 4:
        return None
    for edge in edges:
        adaptor = BRepAdaptor_Curve(edge)
        if adaptor.GetType() != GeomAbs_Line:
            return None
        direction = _canonical_direction(adaptor.Line().Direction().Coord())
        projection = _dot(direction, z_axis)
        if abs(projection) > 1e-6:
            return None
        direction = _canonical_direction(
            value - projection * component
            for value, component in zip(direction, z_axis)
        )
        if not any(abs(_dot(direction, existing)) >= 1.0 - 1e-7 for existing in direction_groups):
            direction_groups.append(direction)
    if len(direction_groups) != 2 or abs(_dot(*direction_groups)) > 1e-6:
        return None

    points = _face_points(bottom_face)
    if len(points) < 4:
        return None

    candidates = []
    for direction in direction_groups:
        projections = [_dot(point, direction) for point in points]
        candidates.append((max(projections) - min(projections), direction))
    candidates.sort(key=lambda item: (-item[0], tuple(item[1])))
    length, x_axis = candidates[0]
    y_axis = _normalize(_cross(z_axis, x_axis))
    y_projections = [_dot(point, y_axis) for point in points]
    width = max(y_projections) - min(y_projections)
    if length <= 1e-7 or width <= 1e-7:
        return None
    return (
        {
            "x_axis": x_axis,
            "y_axis": y_axis,
            "z_axis": list(z_axis),
            "definition_method": "planar_bottom_linear_edges_and_opening_to_bottom_axis",
            "orientation_state": "complete",
        },
        length,
        width,
    )


def _opening_edges_on_plane(
    document: CadDocument,
    side_face_ids: list[str],
    direction: list[float],
    opening_parameter: float,
    tolerance: float,
) -> list[str]:
    opening_edges: set[str] = set()
    for face_id in side_face_ids:
        face = document.faces[int(face_id[1:])]
        for edge in TopologyExplorer(face, ignore_orientation=True).edges():
            projections = [
                _dot(BRep_Tool.Pnt(vertex).Coord(), direction)
                for vertex in TopologyExplorer(edge, ignore_orientation=True).vertices()
            ]
            if projections and all(
                abs(value - opening_parameter) <= tolerance for value in projections
            ):
                opening_edges.add(_edge_id(document, edge))
    return sorted(opening_edges)


def _blind_axis_parameters(
    document: CadDocument,
    side_face_ids: list[str],
    bottom_face_id: str,
    axis: list[float],
) -> tuple[float, float, float, list[float]] | None:
    """Return bottom/opening parameters and the opening-to-bottom direction.

    Every supplied side Face must span the same two axial planes, and the
    labelled bottom must coincide with exactly one of them.  This prevents a
    partial or unrelated wall from manufacturing a plausible-looking depth.
    """

    side_extents: list[tuple[float, float]] = []
    for face_id in side_face_ids:
        values = _face_projection_extents(document.faces[int(face_id[1:])], axis)
        if not values:
            return None
        side_extents.append((min(values), max(values)))
    if not side_extents:
        return None
    low = min(value[0] for value in side_extents)
    high = max(value[1] for value in side_extents)
    tolerance = max(1e-6, abs(high - low) * 1e-6)
    if any(abs(face_low - low) > tolerance or abs(face_high - high) > tolerance
           for face_low, face_high in side_extents):
        return None
    bottom_center = document.face_records[int(bottom_face_id[1:])]["centroid"]
    bottom_parameter = _dot(bottom_center, axis)
    if abs(bottom_parameter - low) <= tolerance:
        opening_parameter = high
    elif abs(bottom_parameter - high) <= tolerance:
        opening_parameter = low
    else:
        return None
    depth = abs(bottom_parameter - opening_parameter)
    if depth <= tolerance:
        return None
    machining_direction = axis if bottom_parameter > opening_parameter else _negate(axis)
    return bottom_parameter, opening_parameter, depth, machining_direction


def _local_extents_obb(
    document: CadDocument,
    member_face_ids: list[str],
    frame: dict[str, Any],
    method: str,
) -> dict[str, Any] | None:
    points = [
        point
        for face_id in member_face_ids
        for point in _face_points(document.faces[int(face_id[1:])])
    ]
    if not points:
        return None
    axes = [frame["x_axis"], frame["y_axis"], frame["z_axis"]]
    extents = []
    for axis in axes:
        parameters = [_dot(point, axis) for point in points]
        extents.append((min(parameters), max(parameters)))
    half_sizes = [(high - low) / 2.0 for low, high in extents]
    if any(value <= 1e-7 for value in half_sizes):
        return None
    center_parameters = [(low + high) / 2.0 for low, high in extents]
    center = _point_from_local_parameters(*center_parameters, frame)
    return {
        "center": center,
        "x_axis": list(frame["x_axis"]),
        "y_axis": list(frame["y_axis"]),
        "z_axis": list(frame["z_axis"]),
        "half_sizes": [_round(value) for value in half_sizes],
        "coordinate_system": "PCS",
        "source": "occt",
        "method": method,
    }


def _rectangular_blind_step_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Measure a strict corner-open rectangular blind step.

    The supported topology is the AAGNet generator contract: one rectangular
    planar bottom and exactly two mutually perpendicular planar side walls.
    The other two profile sides are open on the stock boundary.
    """

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 3
        or len(set(member_face_ids)) != 3
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    side_normals = [_plane_normal(document, face_id) for face_id in side_face_ids]
    if any(normal is None for normal in side_normals):
        return result
    if any(abs(_dot(normal, bottom_normal)) > 1e-6 for normal in side_normals):
        return result
    if abs(_dot(side_normals[0], side_normals[1])) > 1e-6:
        return result
    if any(
        BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line
        for face_id in member_face_ids
        for edge in TopologyExplorer(document.faces[int(face_id[1:])], ignore_orientation=True).edges()
    ):
        return result
    allowed = set(member_face_ids)
    if any(
        set(document.face_records[int(face_id[1:])]["adjacent_face_ids"]) & allowed
        != allowed - {face_id}
        for face_id in member_face_ids
    ):
        return result
    axis_parameters = _blind_axis_parameters(
        document, side_face_ids, bottom_face_id, bottom_normal
    )
    if axis_parameters is None:
        return result
    _, opening_parameter, depth, machining_direction = axis_parameters
    frame_and_size = _bottom_rectangle_frame(
        document, bottom_face_id, machining_direction
    )
    if frame_and_size is None:
        return result
    frame, length, width = frame_and_size
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(
        value - depth * component
        for value, component in zip(bottom_center, machining_direction)
    )
    tolerance = max(1e-6, depth * 1e-6)
    opening_edge_ids = _opening_edges_on_plane(
        document, side_face_ids, bottom_normal, opening_parameter, tolerance
    )
    if len(opening_edge_ids) != 2:
        return result
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        "corner_open_rectangular_step_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": side_face_ids,
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    measurement_faces = side_face_ids + [bottom_face_id]
    result["geometry"] = {
        "measurements": [
            {
                "name": "length",
                "value": _round(length),
                "unit": "mm",
                "source": "occt",
                "method": "rectangular_step_bottom_extent_along_local_x",
                "face_ids": [bottom_face_id],
            },
            {
                "name": "width",
                "value": _round(width),
                "unit": "mm",
                "source": "occt",
                "method": "rectangular_step_bottom_extent_along_local_y",
                "face_ids": [bottom_face_id],
            },
            {
                "name": "depth",
                "value": _round(depth),
                "unit": "mm",
                "source": "occt",
                "method": "opening_plane_to_rectangular_step_bottom",
                "face_ids": measurement_faces,
            },
        ],
        "reference_points": [
            _reference_point(
                "opening_center",
                opening_center,
                side_face_ids,
                "rectangular_step_bottom_centroid_projected_to_opening_plane",
            ),
            _reference_point(
                "bottom_center",
                bottom_center,
                [bottom_face_id],
                "rectangular_step_planar_bottom_centroid",
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _rectangular_blind_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if bottom_face_id is None or bottom_face_id not in member_face_ids:
        return result

    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    if len(side_face_ids) < 4:
        return result
    for face_id in side_face_ids:
        side_normal = _plane_normal(document, face_id)
        if side_normal is None or abs(_dot(side_normal, bottom_normal)) > 1e-6:
            return result
        if bottom_face_id not in document.face_records[int(face_id[1:])]["adjacent_face_ids"]:
            return result

    projections = [
        value
        for face_id in member_face_ids
        for value in _face_projection_extents(
            document.faces[int(face_id[1:])], bottom_normal
        )
    ]
    if not projections:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    bottom_parameter = _dot(bottom_center, bottom_normal)
    low, high = min(projections), max(projections)
    opening_parameter = low if abs(low - bottom_parameter) >= abs(high - bottom_parameter) else high
    depth = abs(opening_parameter - bottom_parameter)
    if depth <= 1e-7:
        return result
    machining_direction = (
        bottom_normal
        if bottom_parameter > opening_parameter
        else _negate(bottom_normal)
    )
    frame_and_size = _bottom_rectangle_frame(
        document, bottom_face_id, machining_direction
    )
    if frame_and_size is None:
        return result
    frame, length, width = frame_and_size
    opening_center = _vector(
        value - depth * component
        for value, component in zip(bottom_center, machining_direction)
    )
    tolerance = max(1e-6, depth * 1e-6)
    opening_edge_ids = _opening_edges_on_plane(
        document,
        side_face_ids,
        bottom_normal,
        opening_parameter,
        tolerance,
    )
    if not opening_edge_ids:
        return result

    result["topology_roles"] = {
        "side_face_ids": side_face_ids,
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    measurement_face_ids = side_face_ids + [bottom_face_id]
    measurements = [
        {
            "name": "length",
            "value": _round(length),
            "unit": "mm",
            "source": "occt",
            "method": "planar_bottom_extent_along_local_x",
            "face_ids": [bottom_face_id],
        },
        {
            "name": "width",
            "value": _round(width),
            "unit": "mm",
            "source": "occt",
            "method": "planar_bottom_extent_along_local_y",
            "face_ids": [bottom_face_id],
        },
        {
            "name": "depth",
            "value": _round(depth),
            "unit": "mm",
            "source": "occt",
            "method": "opening_plane_to_planar_bottom_along_machining_axis",
            "face_ids": measurement_face_ids,
        },
    ]
    obb_center = _vector(
        (opening + bottom) / 2.0
        for opening, bottom in zip(opening_center, bottom_center)
    )
    result["geometry"] = {
        "measurements": measurements,
        "reference_points": [
            _reference_point(
                "opening_center",
                opening_center,
                side_face_ids,
                "bottom_centroid_projected_to_opening_plane",
            ),
            _reference_point(
                "bottom_center",
                bottom_center,
                [bottom_face_id],
                "planar_bottom_surface_centroid",
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": {
            "center": obb_center,
            "x_axis": list(frame["x_axis"]),
            "y_axis": list(frame["y_axis"]),
            "z_axis": list(frame["z_axis"]),
            "half_sizes": [
                _round(length / 2.0),
                _round(width / 2.0),
                _round(depth / 2.0),
            ],
            "coordinate_system": "PCS",
            "source": "occt",
            "method": "planar_rectangular_prism_local_extents",
        },
        "complete": True,
    }
    return result


def _point_from_local_parameters(
    x_parameter: float,
    y_parameter: float,
    z_parameter: float,
    frame: dict[str, Any],
) -> list[float]:
    return _vector(
        x_parameter * frame["x_axis"][index]
        + y_parameter * frame["y_axis"][index]
        + z_parameter * frame["z_axis"][index]
        for index in range(3)
    )


def _right_triangle_frame(
    document: CadDocument,
    bottom_face_id: str,
    z_axis: list[float],
) -> tuple[dict[str, Any], float, float, list[float], float] | None:
    bottom_face = document.faces[int(bottom_face_id[1:])]
    edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    if len(edges) != 3 or any(
        BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in edges
    ):
        return None
    points = _face_points(bottom_face)
    if len(points) != 3:
        return None
    candidates = []
    for index, corner in enumerate(points):
        others = [point for other_index, point in enumerate(points) if other_index != index]
        first_vector = [value - base for value, base in zip(others[0], corner)]
        second_vector = [value - base for value, base in zip(others[1], corner)]
        first_length = math.sqrt(_dot(first_vector, first_vector))
        second_length = math.sqrt(_dot(second_vector, second_vector))
        if first_length <= 1e-7 or second_length <= 1e-7:
            continue
        cosine = _dot(first_vector, second_vector) / (first_length * second_length)
        if abs(cosine) <= 1e-6:
            candidates.append(
                (corner, first_vector, first_length, second_vector, second_length)
            )
    if len(candidates) != 1:
        return None
    corner, first_vector, first_length, second_vector, second_length = candidates[0]
    if first_length >= second_length:
        x_vector, length, width = first_vector, first_length, second_length
    else:
        x_vector, length, width = second_vector, second_length, first_length
    x_axis = _normalize(x_vector)
    y_axis = _normalize(_cross(z_axis, x_axis))
    frame = {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": list(z_axis),
        "definition_method": "right_triangle_legs_and_opening_to_bottom_axis",
        "orientation_state": "complete",
    }
    return frame, length, width, corner, length * width / 2.0


def _triangular_blind_step_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 2
        or len(set(member_face_ids)) != 2
    ):
        return result
    side_face_id = next(face_id for face_id in member_face_ids if face_id != bottom_face_id)
    bottom_normal = _plane_normal(document, bottom_face_id)
    side_normal = _plane_normal(document, side_face_id)
    if (
        bottom_normal is None
        or side_normal is None
        or abs(_dot(bottom_normal, side_normal)) > 1e-6
    ):
        return result
    bottom_edge_ids = set(document.face_records[int(bottom_face_id[1:])]["edge_ids"])
    side_edge_ids = set(document.face_records[int(side_face_id[1:])]["edge_ids"])
    shared_edge_ids = bottom_edge_ids & side_edge_ids
    if len(shared_edge_ids) != 1:
        return result
    shared_edge_id = next(iter(shared_edge_ids))
    shared_edge = document.edge_records[int(shared_edge_id[1:])]
    if shared_edge["curve_type_id"] != int(GeomAbs_Line):
        return result
    if any(
        BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line
        for edge in TopologyExplorer(
            document.faces[int(side_face_id[1:])], ignore_orientation=True
        ).edges()
    ):
        return result
    axis_parameters = _blind_axis_parameters(
        document, [side_face_id], bottom_face_id, bottom_normal
    )
    if axis_parameters is None:
        return result
    _, opening_parameter, depth, machining_direction = axis_parameters
    triangle = _right_triangle_frame(document, bottom_face_id, machining_direction)
    if triangle is None:
        return result
    frame, length, width, bottom_corner, floor_area = triangle
    hypotenuse = math.sqrt(length * length + width * width)
    tolerance = max(1e-6, hypotenuse * 1e-6)
    if abs(float(shared_edge["length"]) - hypotenuse) > tolerance:
        return result
    opening_corner = _vector(
        value - depth * component
        for value, component in zip(bottom_corner, machining_direction)
    )
    opening_edge_ids = _opening_edges_on_plane(
        document,
        [side_face_id],
        bottom_normal,
        opening_parameter,
        max(1e-6, depth * 1e-6),
    )
    if len(opening_edge_ids) != 1:
        return result
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        "corner_open_right_triangular_step_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": [side_face_id],
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_corner,
        "origin_role": "reference_corner",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    measurement_faces = [side_face_id, bottom_face_id]
    result["geometry"] = {
        "measurements": [
            {
                "name": "length",
                "value": _round(length),
                "unit": "mm",
                "source": "occt",
                "method": "right_triangle_long_leg",
                "face_ids": [bottom_face_id],
            },
            {
                "name": "width",
                "value": _round(width),
                "unit": "mm",
                "source": "occt",
                "method": "right_triangle_short_leg",
                "face_ids": [bottom_face_id],
            },
            {
                "name": "depth",
                "value": _round(depth),
                "unit": "mm",
                "source": "occt",
                "method": "opening_plane_to_triangular_step_bottom",
                "face_ids": measurement_faces,
            },
            {
                "name": "floor_area",
                "value": _round(floor_area),
                "unit": "mm^2",
                "source": "derived",
                "method": "right_triangle_leg_product_over_two",
                "face_ids": [bottom_face_id],
            },
        ],
        "reference_points": [
            _reference_point(
                "opening_reference_corner",
                opening_corner,
                [side_face_id],
                "right_angle_corner_projected_to_opening_plane",
            ),
            _reference_point(
                "bottom_reference_corner",
                bottom_corner,
                [bottom_face_id],
                "right_angle_vertex_of_triangular_bottom",
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _circular_sector_frame(
    bottom_face,
    bottom_center: list[float],
    z_axis: list[float],
    radius: float,
) -> dict[str, Any] | None:
    points = _face_points(bottom_face)
    tolerance = max(1e-6, radius * 1e-6)
    radial_vectors = []
    center_matches = 0
    for point in points:
        vector = [value - base for value, base in zip(point, bottom_center)]
        distance = math.sqrt(_dot(vector, vector))
        if distance <= tolerance:
            center_matches += 1
        elif abs(distance - radius) <= tolerance:
            radial_vectors.append(_normalize(vector))
        else:
            return None
    if center_matches != 1 or len(radial_vectors) != 2:
        return None
    if abs(_dot(radial_vectors[0], radial_vectors[1])) > 1e-6:
        return None
    radial_vectors.sort(key=lambda value: tuple(_round(item, 12) for item in value))
    x_axis, y_axis = radial_vectors
    if _dot(_cross(x_axis, y_axis), z_axis) < 0:
        x_axis, y_axis = y_axis, x_axis
    if _dot(_cross(x_axis, y_axis), z_axis) < 1.0 - 1e-6:
        return None
    return {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": list(z_axis),
        "definition_method": "quarter_circle_radial_edges_and_opening_to_bottom_axis",
        "orientation_state": "complete",
    }


def _circular_blind_step_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 2
        or len(set(member_face_ids)) != 2
    ):
        return result
    side_face_id = next(face_id for face_id in member_face_ids if face_id != bottom_face_id)
    bottom_normal = _plane_normal(document, bottom_face_id)
    side_adaptor = BRepAdaptor_Surface(document.faces[int(side_face_id[1:])])
    if bottom_normal is None or side_adaptor.GetType() != GeomAbs_Cylinder:
        return result
    cylinder_axis, closest, radius = _axis_line(side_adaptor)
    if abs(_dot(bottom_normal, cylinder_axis)) < 1.0 - 1e-7 or radius <= 1e-7:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    bottom_types = [BRepAdaptor_Curve(edge).GetType() for edge in bottom_edges]
    if (
        len(bottom_edges) != 3
        or bottom_types.count(GeomAbs_Line) != 2
        or bottom_types.count(GeomAbs_Circle) != 1
    ):
        return result
    side_edges = list(
        TopologyExplorer(
            document.faces[int(side_face_id[1:])], ignore_orientation=True
        ).edges()
    )
    side_types = [BRepAdaptor_Curve(edge).GetType() for edge in side_edges]
    if (
        len(side_edges) != 4
        or side_types.count(GeomAbs_Line) != 2
        or side_types.count(GeomAbs_Circle) != 2
    ):
        return result
    shared_edge_ids = (
        set(document.face_records[int(bottom_face_id[1:])]["edge_ids"])
        & set(document.face_records[int(side_face_id[1:])]["edge_ids"])
    )
    if len(shared_edge_ids) != 1:
        return result
    shared_edge_id = next(iter(shared_edge_ids))
    if document.edge_records[int(shared_edge_id[1:])]["curve_type_id"] != int(GeomAbs_Circle):
        return result
    circular_edges = _circular_boundary_edges(
        document, [side_face_id], cylinder_axis
    )
    if len(circular_edges) != 2:
        return result
    bottom_parameter = _dot(
        document.face_records[int(bottom_face_id[1:])]["centroid"], cylinder_axis
    )
    tolerance = max(1e-6, radius * 1e-6)
    bottom_matches = [
        item for item in circular_edges if abs(item[1] - bottom_parameter) <= tolerance
    ]
    if len(bottom_matches) != 1 or bottom_matches[0][0] != shared_edge_id:
        return result
    opening_edges = [item for item in circular_edges if item[0] != shared_edge_id]
    if len(opening_edges) != 1:
        return result
    opening_edge_id, opening_parameter = opening_edges[0]
    depth = abs(bottom_parameter - opening_parameter)
    if depth <= tolerance:
        return result
    machining_direction = (
        cylinder_axis if bottom_parameter > opening_parameter else _negate(cylinder_axis)
    )
    bottom_center = _point_on_axis(closest, cylinder_axis, bottom_parameter)
    opening_center = _point_on_axis(closest, cylinder_axis, opening_parameter)
    frame = _circular_sector_frame(
        bottom_face, bottom_center, machining_direction, radius
    )
    if frame is None:
        return result
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        "corner_open_quarter_circular_step_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": [side_face_id],
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": [opening_edge_id],
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "reference_corner",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    measurement_faces = [side_face_id, bottom_face_id]
    result["geometry"] = {
        "measurements": [
            {
                "name": "radius",
                "value": _round(radius),
                "unit": "mm",
                "source": "occt",
                "method": "analytic_cylindrical_step_side",
                "face_ids": [side_face_id],
            },
            {
                "name": "depth",
                "value": _round(depth),
                "unit": "mm",
                "source": "occt",
                "method": "opening_arc_to_circular_step_bottom_along_axis",
                "face_ids": measurement_faces,
            },
            {
                "name": "floor_area",
                "value": _round(math.pi * radius * radius / 4.0),
                "unit": "mm^2",
                "source": "derived",
                "method": "quarter_circle_radius_area",
                "face_ids": [bottom_face_id],
            },
        ],
        "reference_points": [
            _reference_point(
                "opening_reference_corner",
                opening_center,
                [side_face_id],
                "cylinder_axis_intersection_with_opening_arc_plane",
            ),
            _reference_point(
                "bottom_reference_corner",
                bottom_center,
                [bottom_face_id, side_face_id],
                "cylinder_axis_intersection_with_bottom_sector_plane",
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _edge_points(edge) -> list[list[float]]:
    points: dict[tuple[float, float, float], list[float]] = {}
    for vertex in TopologyExplorer(edge, ignore_orientation=True).vertices():
        point = _vector(BRep_Tool.Pnt(vertex).Coord())
        points[tuple(point)] = point
    return list(points.values())


def _edge_midpoint(edge) -> list[float] | None:
    points = _edge_points(edge)
    if len(points) != 2:
        return None
    return _vector((first + second) / 2.0 for first, second in zip(*points))


def _profile_frame_from_linear_edges(
    bottom_face,
    z_axis: list[float],
) -> tuple[dict[str, Any], float, float] | None:
    candidates: list[tuple[float, list[float]]] = []
    for edge in TopologyExplorer(bottom_face, ignore_orientation=True).edges():
        adaptor = BRepAdaptor_Curve(edge)
        if adaptor.GetType() != GeomAbs_Line:
            continue
        direction = _canonical_direction(adaptor.Line().Direction().Coord())
        if abs(_dot(direction, z_axis)) > 1e-6:
            return None
        points = _edge_points(edge)
        if len(points) != 2:
            return None
        length = math.sqrt(sum((a - b) ** 2 for a, b in zip(*points)))
        candidates.append((length, direction))
    if not candidates:
        return None
    maximum = max(item[0] for item in candidates)
    tolerance = max(1e-6, maximum * 1e-6)
    x_axis = min(
        (direction for length, direction in candidates if abs(length - maximum) <= tolerance),
        key=lambda value: tuple(value),
    )
    y_axis = _normalize(_cross(z_axis, x_axis))
    points = _face_points(bottom_face)
    x_values = [_dot(point, x_axis) for point in points]
    y_values = [_dot(point, y_axis) for point in points]
    length = max(x_values) - min(x_values)
    width = max(y_values) - min(y_values)
    if length <= 1e-7 or width <= 1e-7:
        return None
    return (
        {
            "x_axis": x_axis,
            "y_axis": y_axis,
            "z_axis": list(z_axis),
            "definition_method": "longest_profile_edge_and_opening_to_bottom_axis",
            "orientation_state": "complete",
        },
        length,
        width,
    )


def _bottom_vertex_reference_points(
    bottom_face,
    bottom_face_id: str,
    frame: dict[str, Any],
) -> list[dict[str, Any]]:
    points = sorted(
        _face_points(bottom_face),
        key=lambda point: (
            _round(_dot(point, frame["x_axis"]), 9),
            _round(_dot(point, frame["y_axis"]), 9),
            _round(_dot(point, frame["z_axis"]), 9),
        ),
    )
    return [
        _reference_point(
            f"bottom_profile_vertex_{index:02d}",
            point,
            [bottom_face_id],
            "occt_bottom_profile_vertex",
        )
        for index, point in enumerate(points, start=1)
    ]


def _polygon_blind_pocket_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
    side_count: int,
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != side_count + 1
        or len(set(member_face_ids)) != side_count + 1
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    if len(bottom_edges) != side_count or any(
        BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in bottom_edges
    ):
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    allowed_sides = set(side_face_ids)
    for face_id in side_face_ids:
        normal = _plane_normal(document, face_id)
        face = document.faces[int(face_id[1:])]
        if normal is None or abs(_dot(normal, bottom_normal)) > 1e-6:
            return result
        edges = list(TopologyExplorer(face, ignore_orientation=True).edges())
        if len(edges) != 4 or any(
            BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in edges
        ):
            return result
        adjacent = set(document.face_records[int(face_id[1:])]["adjacent_face_ids"])
        if bottom_face_id not in adjacent or len(adjacent & allowed_sides) != 2:
            return result
    bottom_edge_ids = {
        _edge_id(document, edge) for edge in bottom_edges
    }
    shared_bottom_edges: list[str] = []
    for face_id in side_face_ids:
        shared = bottom_edge_ids & set(
            document.face_records[int(face_id[1:])]["edge_ids"]
        )
        if len(shared) != 1:
            return result
        shared_bottom_edges.extend(shared)
    if set(shared_bottom_edges) != bottom_edge_ids or len(shared_bottom_edges) != side_count:
        return result
    axis_parameters = _blind_axis_parameters(
        document, side_face_ids, bottom_face_id, bottom_normal
    )
    if axis_parameters is None:
        return result
    _, opening_parameter, depth, machining_direction = axis_parameters
    frame_and_size = _profile_frame_from_linear_edges(
        bottom_face, machining_direction
    )
    if frame_and_size is None:
        return result
    frame, length, width = frame_and_size
    opening_edge_ids = _opening_edges_on_plane(
        document,
        side_face_ids,
        bottom_normal,
        opening_parameter,
        max(1e-6, depth * 1e-6),
    )
    if len(opening_edge_ids) != side_count:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(
        value - depth * component
        for value, component in zip(bottom_center, machining_direction)
    )
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        f"strict_{side_count}_sided_blind_pocket_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": side_face_ids,
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    measurement_faces = side_face_ids + [bottom_face_id]
    result["geometry"] = {
        "measurements": [
            {
                "name": "length",
                "value": _round(length),
                "unit": "mm",
                "source": "occt",
                "method": "bottom_profile_extent_along_local_x",
                "face_ids": [bottom_face_id],
            },
            {
                "name": "width",
                "value": _round(width),
                "unit": "mm",
                "source": "occt",
                "method": "bottom_profile_extent_along_local_y",
                "face_ids": [bottom_face_id],
            },
            {
                "name": "depth",
                "value": _round(depth),
                "unit": "mm",
                "source": "occt",
                "method": "opening_plane_to_polygonal_pocket_bottom",
                "face_ids": measurement_faces,
            },
            {
                "name": "floor_area",
                "value": _round(document.face_records[int(bottom_face_id[1:])]["area"]),
                "unit": "mm^2",
                "source": "occt",
                "method": "bottom_face_surface_properties",
                "face_ids": [bottom_face_id],
            },
        ],
        "reference_points": [
            _reference_point(
                "opening_center",
                opening_center,
                side_face_ids,
                "bottom_centroid_projected_to_opening_plane",
            ),
            _reference_point(
                "bottom_center",
                bottom_center,
                [bottom_face_id],
                "polygonal_bottom_surface_centroid",
            ),
            *_bottom_vertex_reference_points(
                bottom_face, bottom_face_id, frame
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _rounded_side_groups(
    document: CadDocument,
    side_face_ids: list[str],
    bottom_face_id: str,
    bottom_normal: list[float],
) -> tuple[list[str], list[tuple[str, list[float], list[float], float]]] | None:
    plane_face_ids: list[str] = []
    cylinders: list[tuple[str, list[float], list[float], float]] = []
    for face_id in side_face_ids:
        adaptor = BRepAdaptor_Surface(document.faces[int(face_id[1:])])
        adjacent = set(document.face_records[int(face_id[1:])]["adjacent_face_ids"])
        if bottom_face_id not in adjacent:
            return None
        if adaptor.GetType() == GeomAbs_Plane:
            normal = _canonical_direction(adaptor.Plane().Axis().Direction().Coord())
            if abs(_dot(normal, bottom_normal)) > 1e-6:
                return None
            plane_face_ids.append(face_id)
        elif adaptor.GetType() == GeomAbs_Cylinder:
            direction, closest, radius = _axis_line(adaptor)
            if abs(_dot(direction, bottom_normal)) < 1.0 - 1e-7 or radius <= 1e-7:
                return None
            cylinders.append((face_id, direction, closest, radius))
        else:
            return None
    return plane_face_ids, cylinders


def _bottom_shared_edges(
    document: CadDocument,
    bottom_face_id: str,
    side_face_ids: list[str],
) -> tuple[dict[str, str], list[str]] | None:
    bottom_edge_ids = set(document.face_records[int(bottom_face_id[1:])]["edge_ids"])
    edge_to_side: dict[str, str] = {}
    for side_face_id in side_face_ids:
        shared = bottom_edge_ids & set(
            document.face_records[int(side_face_id[1:])]["edge_ids"]
        )
        if len(shared) != 1:
            return None
        edge_id = next(iter(shared))
        if edge_id in edge_to_side:
            return None
        edge_to_side[edge_id] = side_face_id
    return edge_to_side, sorted(bottom_edge_ids - set(edge_to_side))


def _rounded_feature_result(
    document: CadDocument,
    result: dict[str, Any],
    member_face_ids: list[str],
    side_face_ids: list[str],
    bottom_face_id: str,
    opening_edge_ids: list[str],
    machining_direction: list[float],
    frame: dict[str, Any],
    opening_center: list[float],
    bottom_center: list[float],
    measurements: list[dict[str, Any]],
    extra_reference_points: list[dict[str, Any]],
    obb_method: str,
) -> dict[str, Any]:
    oriented_box = _local_extents_obb(
        document, member_face_ids, frame, obb_method
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": side_face_ids,
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": measurements,
        "reference_points": [
            _reference_point(
                "opening_center",
                opening_center,
                side_face_ids,
                "bottom_centroid_projected_to_opening_plane",
            ),
            _reference_point(
                "bottom_center",
                bottom_center,
                [bottom_face_id],
                "profile_bottom_surface_centroid",
            ),
            *extra_reference_points,
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _circular_end_pocket_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 5
        or len(set(member_face_ids)) != 5
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    bottom_types = [BRepAdaptor_Curve(edge).GetType() for edge in bottom_edges]
    if (
        len(bottom_edges) != 4
        or bottom_types.count(GeomAbs_Line) != 2
        or bottom_types.count(GeomAbs_Circle) != 2
    ):
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    grouped = _rounded_side_groups(
        document, side_face_ids, bottom_face_id, bottom_normal
    )
    if grouped is None:
        return result
    plane_face_ids, cylinders = grouped
    if len(plane_face_ids) != 2 or len(cylinders) != 2:
        return result
    shared = _bottom_shared_edges(document, bottom_face_id, side_face_ids)
    if shared is None or shared[1]:
        return result
    edge_to_side, _ = shared
    circular_edge_ids = {
        edge_id
        for edge_id in edge_to_side
        if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Circle)
    }
    linear_edge_ids = set(edge_to_side) - circular_edge_ids
    if (
        len(circular_edge_ids) != 2
        or {edge_to_side[edge_id] for edge_id in circular_edge_ids}
        != {item[0] for item in cylinders}
        or {edge_to_side[edge_id] for edge_id in linear_edge_ids}
        != set(plane_face_ids)
    ):
        return result
    radii = [item[3] for item in cylinders]
    radius = radii[0]
    tolerance = max(1e-6, radius * 1e-6)
    if abs(radii[1] - radius) > tolerance:
        return result
    axis_parameters = _blind_axis_parameters(
        document, side_face_ids, bottom_face_id, bottom_normal
    )
    if axis_parameters is None:
        return result
    bottom_parameter, opening_parameter, depth, machining_direction = axis_parameters
    centers = [
        _point_on_axis(closest, direction, bottom_parameter)
        for _, direction, closest, _ in cylinders
    ]
    center_vector = [value - base for value, base in zip(centers[1], centers[0])]
    center_distance = math.sqrt(_dot(center_vector, center_vector))
    if center_distance <= tolerance:
        return result
    x_axis = _canonical_direction(center_vector)
    y_axis = _normalize(_cross(machining_direction, x_axis))
    frame = {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": machining_direction,
        "definition_method": "dual_semicylinder_centers_and_opening_to_bottom_axis",
        "orientation_state": "complete",
    }
    line_lengths = sorted(
        document.edge_records[int(edge_id[1:])]["length"]
        for edge_id in edge_to_side
        if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Line)
    )
    arc_lengths = sorted(
        document.edge_records[int(edge_id[1:])]["length"]
        for edge_id in edge_to_side
        if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Circle)
    )
    if (
        len(line_lengths) != 2
        or len(arc_lengths) != 2
        or any(abs(value - center_distance) > max(tolerance, center_distance * 1e-6) for value in line_lengths)
        or any(abs(value - math.pi * radius) > max(tolerance, math.pi * radius * 1e-6) for value in arc_lengths)
    ):
        return result
    expected_area = 2.0 * radius * center_distance + math.pi * radius * radius
    floor_area = float(document.face_records[int(bottom_face_id[1:])]["area"])
    if abs(floor_area - expected_area) > max(1e-5, expected_area * 1e-5):
        return result
    opening_edge_ids = _opening_edges_on_plane(
        document,
        side_face_ids,
        bottom_normal,
        opening_parameter,
        max(1e-6, depth * 1e-6),
    )
    if len(opening_edge_ids) != 4:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(
        value - depth * component
        for value, component in zip(bottom_center, machining_direction)
    )
    measurement_faces = side_face_ids + [bottom_face_id]
    measurements = [
        {"name": "length", "value": _round(center_distance + 2.0 * radius), "unit": "mm", "source": "occt", "method": "semicylinder_center_distance_plus_diameter", "face_ids": measurement_faces},
        {"name": "width", "value": _round(2.0 * radius), "unit": "mm", "source": "occt", "method": "dual_semicylinder_diameter", "face_ids": [item[0] for item in cylinders]},
        {"name": "corner_radius", "value": _round(radius), "unit": "mm", "source": "occt", "method": "analytic_semicylinder_radius", "face_ids": [item[0] for item in cylinders]},
        {"name": "depth", "value": _round(depth), "unit": "mm", "source": "occt", "method": "opening_plane_to_circular_end_pocket_bottom", "face_ids": measurement_faces},
        {"name": "floor_area", "value": _round(floor_area), "unit": "mm^2", "source": "occt", "method": "bottom_face_surface_properties", "face_ids": [bottom_face_id]},
    ]
    return _rounded_feature_result(
        document,
        result,
        member_face_ids,
        side_face_ids,
        bottom_face_id,
        opening_edge_ids,
        machining_direction,
        frame,
        opening_center,
        bottom_center,
        measurements,
        [
            _reference_point("bottom_end_center_01", centers[0], [cylinders[0][0]], "first_semicylinder_axis_at_bottom"),
            _reference_point("bottom_end_center_02", centers[1], [cylinders[1][0]], "second_semicylinder_axis_at_bottom"),
        ],
        "closed_capsule_pocket_local_extents",
    )


def _v_circular_end_blind_slot_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 4
        or len(set(member_face_ids)) != 4
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    bottom_types = [BRepAdaptor_Curve(edge).GetType() for edge in bottom_edges]
    if len(bottom_edges) != 4 or bottom_types.count(GeomAbs_Line) != 3 or bottom_types.count(GeomAbs_Circle) != 1:
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    grouped = _rounded_side_groups(document, side_face_ids, bottom_face_id, bottom_normal)
    if grouped is None:
        return result
    plane_face_ids, cylinders = grouped
    if len(plane_face_ids) != 2 or len(cylinders) != 1:
        return result
    shared = _bottom_shared_edges(document, bottom_face_id, side_face_ids)
    if shared is None or len(shared[1]) != 1:
        return result
    edge_to_side, unshared_edge_ids = shared
    open_edge_id = unshared_edge_ids[0]
    open_edge_record = document.edge_records[int(open_edge_id[1:])]
    if open_edge_record["curve_type_id"] != int(GeomAbs_Line):
        return result
    circular_shared = [
        edge_id
        for edge_id in edge_to_side
        if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Circle)
    ]
    linear_shared = [
        edge_id
        for edge_id in edge_to_side
        if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Line)
    ]
    if len(circular_shared) != 1 or len(linear_shared) != 2:
        return result
    cylinder_face_id, cylinder_direction, closest, radius = cylinders[0]
    if (
        edge_to_side[circular_shared[0]] != cylinder_face_id
        or {edge_to_side[edge_id] for edge_id in linear_shared} != set(plane_face_ids)
    ):
        return result
    tolerance = max(1e-6, radius * 1e-6)
    arc_length = document.edge_records[int(circular_shared[0][1:])]["length"]
    if (
        abs(arc_length - math.pi * radius) > max(tolerance, math.pi * radius * 1e-6)
        or abs(open_edge_record["length"] - 2.0 * radius) > max(tolerance, 2.0 * radius * 1e-6)
    ):
        return result
    side_lengths = [document.edge_records[int(edge_id[1:])]["length"] for edge_id in linear_shared]
    if abs(side_lengths[0] - side_lengths[1]) > max(tolerance, max(side_lengths) * 1e-6):
        return result
    axis_parameters = _blind_axis_parameters(document, side_face_ids, bottom_face_id, bottom_normal)
    if axis_parameters is None:
        return result
    bottom_parameter, opening_parameter, depth, machining_direction = axis_parameters
    open_edge = document.edges[int(open_edge_id[1:])]
    open_midpoint = _edge_midpoint(open_edge)
    if open_midpoint is None:
        return result
    round_center = _point_on_axis(closest, cylinder_direction, bottom_parameter)
    long_vector = [value - base for value, base in zip(round_center, open_midpoint)]
    side_length = math.sqrt(_dot(long_vector, long_vector))
    if side_length <= tolerance or abs(side_length - side_lengths[0]) > max(tolerance, side_length * 1e-6):
        return result
    x_axis = _normalize(long_vector)
    y_axis = _normalize(_cross(machining_direction, x_axis))
    frame = {"x_axis": x_axis, "y_axis": y_axis, "z_axis": machining_direction, "definition_method": "flat_open_end_to_semicylinder_center_and_depth_axis", "orientation_state": "complete"}
    floor_area = float(document.face_records[int(bottom_face_id[1:])]["area"])
    expected_area = 2.0 * radius * side_length + math.pi * radius * radius / 2.0
    if abs(floor_area - expected_area) > max(1e-5, expected_area * 1e-5):
        return result
    opening_edge_ids = _opening_edges_on_plane(document, side_face_ids, bottom_normal, opening_parameter, max(1e-6, depth * 1e-6))
    if len(opening_edge_ids) != 3:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(value - depth * component for value, component in zip(bottom_center, machining_direction))
    measurement_faces = side_face_ids + [bottom_face_id]
    measurements = [
        {"name": "length", "value": _round(side_length + radius), "unit": "mm", "source": "occt", "method": "flat_end_to_semicircle_far_extent", "face_ids": measurement_faces},
        {"name": "width", "value": _round(2.0 * radius), "unit": "mm", "source": "occt", "method": "semicylinder_diameter", "face_ids": [cylinder_face_id]},
        {"name": "corner_radius", "value": _round(radius), "unit": "mm", "source": "occt", "method": "analytic_semicylinder_radius", "face_ids": [cylinder_face_id]},
        {"name": "depth", "value": _round(depth), "unit": "mm", "source": "occt", "method": "opening_plane_to_vertical_circular_end_slot_bottom", "face_ids": measurement_faces},
        {"name": "floor_area", "value": _round(floor_area), "unit": "mm^2", "source": "occt", "method": "bottom_face_surface_properties", "face_ids": [bottom_face_id]},
    ]
    return _rounded_feature_result(
        document, result, member_face_ids, side_face_ids, bottom_face_id,
        opening_edge_ids, machining_direction, frame, opening_center, bottom_center,
        measurements,
        [
            _reference_point("bottom_flat_end_center", open_midpoint, [bottom_face_id], "unshared_flat_profile_edge_midpoint"),
            _reference_point("bottom_rounded_end_center", round_center, [bottom_face_id, cylinder_face_id], "semicylinder_axis_at_bottom"),
        ],
        "edge_open_single_circular_end_slot_local_extents",
    )


def _h_circular_end_blind_slot_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 4
        or len(set(member_face_ids)) != 4
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    bottom_types = [BRepAdaptor_Curve(edge).GetType() for edge in bottom_edges]
    if len(bottom_edges) != 4 or bottom_types.count(GeomAbs_Line) != 2 or bottom_types.count(GeomAbs_Circle) != 2:
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    grouped = _rounded_side_groups(document, side_face_ids, bottom_face_id, bottom_normal)
    if grouped is None:
        return result
    plane_face_ids, cylinders = grouped
    if len(plane_face_ids) != 1 or len(cylinders) != 2:
        return result
    shared = _bottom_shared_edges(document, bottom_face_id, side_face_ids)
    if shared is None or len(shared[1]) != 1:
        return result
    edge_to_side, unshared_edge_ids = shared
    open_edge_id = unshared_edge_ids[0]
    open_edge_record = document.edge_records[int(open_edge_id[1:])]
    shared_line_ids = [edge_id for edge_id in edge_to_side if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Line)]
    shared_arc_ids = [edge_id for edge_id in edge_to_side if document.edge_records[int(edge_id[1:])]["curve_type_id"] == int(GeomAbs_Circle)]
    if open_edge_record["curve_type_id"] != int(GeomAbs_Line) or len(shared_line_ids) != 1 or len(shared_arc_ids) != 2:
        return result
    if (
        edge_to_side[shared_line_ids[0]] != plane_face_ids[0]
        or {edge_to_side[edge_id] for edge_id in shared_arc_ids}
        != {item[0] for item in cylinders}
    ):
        return result
    radii = [item[3] for item in cylinders]
    radius = radii[0]
    tolerance = max(1e-6, radius * 1e-6)
    if abs(radii[1] - radius) > tolerance:
        return result
    arc_lengths = [document.edge_records[int(edge_id[1:])]["length"] for edge_id in shared_arc_ids]
    if any(abs(value - math.pi * radius / 2.0) > max(tolerance, math.pi * radius * 5e-7) for value in arc_lengths):
        return result
    inner_edge_id = shared_line_ids[0]
    inner_length = float(document.edge_records[int(inner_edge_id[1:])]["length"])
    open_length = float(open_edge_record["length"])
    if abs(open_length - inner_length - 2.0 * radius) > max(tolerance, open_length * 1e-6):
        return result
    open_edge = document.edges[int(open_edge_id[1:])]
    inner_edge = document.edges[int(inner_edge_id[1:])]
    open_adaptor = BRepAdaptor_Curve(open_edge)
    inner_adaptor = BRepAdaptor_Curve(inner_edge)
    if open_adaptor.GetType() != GeomAbs_Line or inner_adaptor.GetType() != GeomAbs_Line:
        return result
    open_direction = _canonical_direction(open_adaptor.Line().Direction().Coord())
    inner_direction = _canonical_direction(inner_adaptor.Line().Direction().Coord())
    if abs(_dot(open_direction, inner_direction)) < 1.0 - 1e-7:
        return result
    open_midpoint = _edge_midpoint(open_edge)
    inner_midpoint = _edge_midpoint(inner_edge)
    if open_midpoint is None or inner_midpoint is None:
        return result
    inward_vector = [value - base for value, base in zip(inner_midpoint, open_midpoint)]
    width = math.sqrt(_dot(inward_vector, inward_vector))
    if width <= tolerance or abs(width - radius) > max(tolerance, radius * 1e-6):
        return result
    axis_parameters = _blind_axis_parameters(document, side_face_ids, bottom_face_id, bottom_normal)
    if axis_parameters is None:
        return result
    _, opening_parameter, depth, machining_direction = axis_parameters
    x_axis = open_direction
    y_axis = _normalize(_cross(machining_direction, x_axis))
    if _dot(y_axis, inward_vector) < 0:
        x_axis = _negate(x_axis)
        y_axis = _normalize(_cross(machining_direction, x_axis))
    frame = {"x_axis": x_axis, "y_axis": y_axis, "z_axis": machining_direction, "definition_method": "open_and_inner_parallel_edges_with_quarter_rounds", "orientation_state": "complete"}
    floor_area = float(document.face_records[int(bottom_face_id[1:])]["area"])
    expected_area = inner_length * radius + math.pi * radius * radius / 2.0
    if abs(floor_area - expected_area) > max(1e-5, expected_area * 1e-5):
        return result
    opening_edge_ids = _opening_edges_on_plane(document, side_face_ids, bottom_normal, opening_parameter, max(1e-6, depth * 1e-6))
    if len(opening_edge_ids) != 3:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(value - depth * component for value, component in zip(bottom_center, machining_direction))
    measurement_faces = side_face_ids + [bottom_face_id]
    measurements = [
        {"name": "length", "value": _round(open_length), "unit": "mm", "source": "occt", "method": "unshared_open_profile_edge_length", "face_ids": [bottom_face_id]},
        {"name": "width", "value": _round(width), "unit": "mm", "source": "occt", "method": "open_edge_to_inner_wall_distance", "face_ids": measurement_faces},
        {"name": "corner_radius", "value": _round(radius), "unit": "mm", "source": "occt", "method": "analytic_quarter_cylinder_radius", "face_ids": [item[0] for item in cylinders]},
        {"name": "depth", "value": _round(depth), "unit": "mm", "source": "occt", "method": "opening_plane_to_horizontal_circular_end_slot_bottom", "face_ids": measurement_faces},
        {"name": "floor_area", "value": _round(floor_area), "unit": "mm^2", "source": "occt", "method": "bottom_face_surface_properties", "face_ids": [bottom_face_id]},
    ]
    return _rounded_feature_result(
        document, result, member_face_ids, side_face_ids, bottom_face_id,
        opening_edge_ids, machining_direction, frame, opening_center, bottom_center,
        measurements,
        [
            _reference_point("bottom_open_edge_midpoint", open_midpoint, [bottom_face_id], "unshared_open_profile_edge_midpoint"),
            _reference_point("bottom_inner_edge_midpoint", inner_midpoint, [bottom_face_id, plane_face_ids[0]], "inner_profile_wall_edge_midpoint"),
        ],
        "edge_open_dual_quarter_round_slot_local_extents",
    )


def _member_internal_linear_axis(
    document: CadDocument,
    member_face_ids: list[str],
    expected_edge_count: int,
) -> tuple[list[float], list[str]] | None:
    member_set = set(member_face_ids)
    internal_edge_ids: set[str] = set()
    for face_id in member_face_ids:
        for edge_id in document.face_records[int(face_id[1:])]["edge_ids"]:
            adjacent = set(document.edge_records[int(edge_id[1:])]["adjacent_face_ids"])
            if len(adjacent & member_set) == 2:
                internal_edge_ids.add(edge_id)
    if len(internal_edge_ids) != expected_edge_count:
        return None
    directions: list[list[float]] = []
    for edge_id in sorted(internal_edge_ids):
        edge = document.edges[int(edge_id[1:])]
        adaptor = BRepAdaptor_Curve(edge)
        if adaptor.GetType() != GeomAbs_Line:
            return None
        directions.append(_canonical_direction(adaptor.Line().Direction().Coord()))
    axis = directions[0]
    if any(abs(_dot(axis, direction)) < 1.0 - 1e-7 for direction in directions[1:]):
        return None
    return axis, sorted(internal_edge_ids)


def _through_member_extents(
    document: CadDocument,
    member_face_ids: list[str],
    axis: list[float],
) -> tuple[float, float, float] | None:
    extents: list[tuple[float, float]] = []
    for face_id in member_face_ids:
        values = _face_projection_extents(document.faces[int(face_id[1:])], axis)
        if not values:
            return None
        extents.append((min(values), max(values)))
    low = min(item[0] for item in extents)
    high = max(item[1] for item in extents)
    length = high - low
    if length <= 1e-7:
        return None
    tolerance = max(1e-6, length * 1e-6)
    if any(
        abs(face_low - low) > tolerance or abs(face_high - high) > tolerance
        for face_low, face_high in extents
    ):
        return None
    return low, high, tolerance


def _closed_opening_profile(
    document: CadDocument,
    edge_ids: list[str],
    z_axis: list[float],
    z_parameter: float,
) -> tuple[dict[str, Any], float, float, float, list[float], list[list[float]]] | None:
    point_counts: dict[tuple[float, float, float], int] = {}
    edge_directions: list[tuple[float, list[float]]] = []
    for edge_id in edge_ids:
        edge = document.edges[int(edge_id[1:])]
        adaptor = BRepAdaptor_Curve(edge)
        if adaptor.GetType() != GeomAbs_Line:
            return None
        points = _edge_points(edge)
        if len(points) != 2:
            return None
        direction = _canonical_direction(adaptor.Line().Direction().Coord())
        if abs(_dot(direction, z_axis)) > 1e-6:
            return None
        length = math.sqrt(sum((a - b) ** 2 for a, b in zip(*points)))
        edge_directions.append((length, direction))
        for point in points:
            key = tuple(point)
            point_counts[key] = point_counts.get(key, 0) + 1
    if len(point_counts) != len(edge_ids) or any(value != 2 for value in point_counts.values()):
        return None
    points = [list(point) for point in point_counts]
    maximum = max(item[0] for item in edge_directions)
    tolerance = max(1e-6, maximum * 1e-6)
    x_axis = min(
        (
            direction
            for length, direction in edge_directions
            if abs(length - maximum) <= tolerance
        ),
        key=lambda value: tuple(value),
    )
    y_axis = _normalize(_cross(z_axis, x_axis))
    frame = {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": list(z_axis),
        "definition_method": "longest_opening_edge_and_common_prism_axis",
        "orientation_state": "complete",
    }
    average_x = sum(_dot(point, x_axis) for point in points) / len(points)
    average_y = sum(_dot(point, y_axis) for point in points) / len(points)
    ordered = sorted(
        points,
        key=lambda point: math.atan2(
            _dot(point, y_axis) - average_y,
            _dot(point, x_axis) - average_x,
        ),
    )
    local = [(_dot(point, x_axis), _dot(point, y_axis)) for point in ordered]
    signed_twice_area = 0.0
    centroid_x_numerator = 0.0
    centroid_y_numerator = 0.0
    for index, (x_value, y_value) in enumerate(local):
        next_x, next_y = local[(index + 1) % len(local)]
        cross_value = x_value * next_y - next_x * y_value
        signed_twice_area += cross_value
        centroid_x_numerator += (x_value + next_x) * cross_value
        centroid_y_numerator += (y_value + next_y) * cross_value
    if abs(signed_twice_area) <= 1e-10:
        return None
    area = abs(signed_twice_area) / 2.0
    centroid_x = centroid_x_numerator / (3.0 * signed_twice_area)
    centroid_y = centroid_y_numerator / (3.0 * signed_twice_area)
    center = _point_from_local_parameters(centroid_x, centroid_y, z_parameter, frame)
    x_values = [item[0] for item in local]
    y_values = [item[1] for item in local]
    length = max(x_values) - min(x_values)
    width = max(y_values) - min(y_values)
    if length <= 1e-7 or width <= 1e-7:
        return None
    return frame, length, width, area, center, ordered


def _polygon_through_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
    side_count: int,
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is not None
        or len(member_face_ids) != side_count
        or len(set(member_face_ids)) != side_count
    ):
        return result
    member_set = set(member_face_ids)
    for face_id in member_face_ids:
        normal = _plane_normal(document, face_id)
        face = document.faces[int(face_id[1:])]
        if normal is None:
            return result
        edges = list(TopologyExplorer(face, ignore_orientation=True).edges())
        if len(edges) != 4 or any(
            BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in edges
        ):
            return result
        adjacent = set(document.face_records[int(face_id[1:])]["adjacent_face_ids"])
        if len(adjacent & member_set) != 2:
            return result
    axis_and_edges = _member_internal_linear_axis(
        document, member_face_ids, side_count
    )
    if axis_and_edges is None:
        return result
    through_axis, internal_edge_ids = axis_and_edges
    if any(
        abs(_dot(_plane_normal(document, face_id), through_axis)) > 1e-6
        for face_id in member_face_ids
    ):
        return result
    extents = _through_member_extents(document, member_face_ids, through_axis)
    if extents is None:
        return result
    z_low, z_high, tolerance = extents
    through_length = z_high - z_low
    if any(
        abs(document.edge_records[int(edge_id[1:])]["length"] - through_length)
        > tolerance
        for edge_id in internal_edge_ids
    ):
        return result
    low_edges = _opening_edges_on_plane(
        document, member_face_ids, through_axis, z_low, tolerance
    )
    high_edges = _opening_edges_on_plane(
        document, member_face_ids, through_axis, z_high, tolerance
    )
    if len(low_edges) != side_count or len(high_edges) != side_count:
        return result
    low_profile = _closed_opening_profile(
        document, low_edges, through_axis, z_low
    )
    high_profile = _closed_opening_profile(
        document, high_edges, through_axis, z_high
    )
    if low_profile is None or high_profile is None:
        return result
    frame, length, width, area, low_center, low_vertices = low_profile
    _, high_length, high_width, high_area, high_center, high_vertices = high_profile
    metric_tolerance = max(1e-6, length * 1e-6, width * 1e-6)
    if (
        abs(length - high_length) > metric_tolerance
        or abs(width - high_width) > metric_tolerance
        or abs(area - high_area) > max(1e-6, area * 1e-6)
    ):
        return result
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        f"strict_{side_count}_sided_through_prism_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": member_face_ids,
        "bottom_face_ids": [],
        "transition_face_ids": [],
        "opening_edge_ids": sorted(low_edges + high_edges),
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": low_center,
        "origin_role": "opening_center",
        "axis": list(through_axis),
        "local_frame": frame,
        "access_directions": [list(through_axis), _negate(through_axis)],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "length", "value": _round(length), "unit": "mm", "source": "occt", "method": "polygon_opening_extent_along_local_x", "face_ids": member_face_ids},
            {"name": "width", "value": _round(width), "unit": "mm", "source": "occt", "method": "polygon_opening_extent_along_local_y", "face_ids": member_face_ids},
            {"name": "through_length", "value": _round(through_length), "unit": "mm", "source": "occt", "method": "dual_opening_plane_distance_along_local_z", "face_ids": member_face_ids},
            {"name": "cross_section_area", "value": _round(area), "unit": "mm^2", "source": "derived", "method": "ordered_linear_opening_polygon", "face_ids": member_face_ids},
        ],
        "reference_points": [
            _reference_point("opening_center_low", low_center, member_face_ids, "polygon_area_centroid_on_low_opening_plane"),
            _reference_point("opening_center_high", high_center, member_face_ids, "polygon_area_centroid_on_high_opening_plane"),
            *[
                _reference_point(
                    f"opening_low_vertex_{index:02d}", point, member_face_ids,
                    "occt_linear_opening_vertex",
                )
                for index, point in enumerate(low_vertices, start=1)
            ],
            *[
                _reference_point(
                    f"opening_high_vertex_{index:02d}", point, member_face_ids,
                    "occt_linear_opening_vertex",
                )
                for index, point in enumerate(high_vertices, start=1)
            ],
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _triangular_slot_profile(
    document: CadDocument,
    edge_ids: list[str],
    z_axis: list[float],
    z_parameter: float,
) -> tuple[dict[str, Any], float, float, list[float], list[float], list[float]] | None:
    if len(edge_ids) != 2:
        return None
    counts: dict[tuple[float, float, float], int] = {}
    for edge_id in edge_ids:
        edge = document.edges[int(edge_id[1:])]
        if BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line:
            return None
        for point in _edge_points(edge):
            key = tuple(point)
            counts[key] = counts.get(key, 0) + 1
    tip_points = [list(point) for point, count in counts.items() if count == 2]
    open_points = [list(point) for point, count in counts.items() if count == 1]
    if len(tip_points) != 1 or len(open_points) != 2:
        return None
    tip = tip_points[0]
    open_first, open_second = open_points
    base_vector = [a - b for a, b in zip(open_second, open_first)]
    opening_width = math.sqrt(_dot(base_vector, base_vector))
    if opening_width <= 1e-7:
        return None
    open_midpoint = _vector(
        (a + b) / 2.0 for a, b in zip(open_first, open_second)
    )
    inward = [a - b for a, b in zip(tip, open_midpoint)]
    profile_depth = math.sqrt(_dot(inward, inward))
    if profile_depth <= 1e-7 or abs(_dot(base_vector, inward)) > max(
        1e-6, opening_width * profile_depth * 1e-6
    ):
        return None
    x_axis = _canonical_direction(base_vector)
    y_axis = _normalize(_cross(z_axis, x_axis))
    if _dot(y_axis, inward) < 0:
        x_axis = _negate(x_axis)
        y_axis = _normalize(_cross(z_axis, x_axis))
    frame = {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": list(z_axis),
        "definition_method": "open_base_endpoints_and_shared_v_tip_axis",
        "orientation_state": "complete",
    }
    center = _vector(
        (open_first[index] + open_second[index] + tip[index]) / 3.0
        for index in range(3)
    )
    if abs(_dot(center, z_axis) - z_parameter) > 1e-6:
        return None
    return frame, opening_width, profile_depth, center, open_midpoint, tip


def _triangular_through_slot_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if bottom_face_id is not None or len(member_face_ids) != 2 or len(set(member_face_ids)) != 2:
        return result
    member_set = set(member_face_ids)
    for face_id in member_face_ids:
        if _plane_normal(document, face_id) is None:
            return result
        edges = list(TopologyExplorer(document.faces[int(face_id[1:])], ignore_orientation=True).edges())
        if len(edges) != 4 or any(BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in edges):
            return result
        adjacent = set(document.face_records[int(face_id[1:])]["adjacent_face_ids"])
        if len(adjacent & member_set) != 1:
            return result
    axis_and_edges = _member_internal_linear_axis(document, member_face_ids, 1)
    if axis_and_edges is None:
        return result
    through_axis, internal_edge_ids = axis_and_edges
    if any(abs(_dot(_plane_normal(document, face_id), through_axis)) > 1e-6 for face_id in member_face_ids):
        return result
    extents = _through_member_extents(document, member_face_ids, through_axis)
    if extents is None:
        return result
    z_low, z_high, tolerance = extents
    through_length = z_high - z_low
    if abs(document.edge_records[int(internal_edge_ids[0][1:])]["length"] - through_length) > tolerance:
        return result
    low_edges = _opening_edges_on_plane(document, member_face_ids, through_axis, z_low, tolerance)
    high_edges = _opening_edges_on_plane(document, member_face_ids, through_axis, z_high, tolerance)
    low_profile = _triangular_slot_profile(document, low_edges, through_axis, z_low)
    high_profile = _triangular_slot_profile(document, high_edges, through_axis, z_high)
    if low_profile is None or high_profile is None:
        return result
    frame, opening_width, profile_depth, low_center, low_midpoint, low_tip = low_profile
    _, high_width, high_depth, high_center, high_midpoint, high_tip = high_profile
    if abs(opening_width - high_width) > max(1e-6, opening_width * 1e-6) or abs(profile_depth - high_depth) > max(1e-6, profile_depth * 1e-6):
        return result
    oriented_box = _local_extents_obb(document, member_face_ids, frame, "strict_v_open_triangular_through_slot_local_extents")
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": member_face_ids,
        "bottom_face_ids": [],
        "transition_face_ids": [],
        "opening_edge_ids": sorted(low_edges + high_edges),
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": low_center,
        "origin_role": "opening_center",
        "axis": list(through_axis),
        "local_frame": frame,
        "access_directions": [list(through_axis), _negate(through_axis)],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "width", "value": _round(opening_width), "unit": "mm", "source": "occt", "method": "distance_between_open_profile_endpoints", "face_ids": member_face_ids},
            {"name": "height", "value": _round(profile_depth), "unit": "mm", "source": "occt", "method": "open_base_midpoint_to_v_tip_distance", "face_ids": member_face_ids},
            {"name": "through_length", "value": _round(through_length), "unit": "mm", "source": "occt", "method": "dual_opening_plane_distance_along_local_z", "face_ids": member_face_ids},
        ],
        "reference_points": [
            _reference_point("opening_center_low", low_center, member_face_ids, "triangular_profile_centroid_on_low_opening_plane"),
            _reference_point("opening_center_high", high_center, member_face_ids, "triangular_profile_centroid_on_high_opening_plane"),
            _reference_point("open_base_midpoint_low", low_midpoint, member_face_ids, "open_profile_endpoint_midpoint"),
            _reference_point("v_tip_low", low_tip, member_face_ids, "shared_v_wall_vertex"),
            _reference_point("open_base_midpoint_high", high_midpoint, member_face_ids, "open_profile_endpoint_midpoint"),
            _reference_point("v_tip_high", high_tip, member_face_ids, "shared_v_wall_vertex"),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _circular_through_slot_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if bottom_face_id is not None or len(member_face_ids) != 1:
        return result
    side_face_id = member_face_ids[0]
    side_face = document.faces[int(side_face_id[1:])]
    adaptor = BRepAdaptor_Surface(side_face)
    if adaptor.GetType() != GeomAbs_Cylinder:
        return result
    through_axis, closest, radius = _axis_line(adaptor)
    if radius <= 1e-7:
        return result
    edges = list(TopologyExplorer(side_face, ignore_orientation=True).edges())
    types = [BRepAdaptor_Curve(edge).GetType() for edge in edges]
    if len(edges) != 4 or types.count(GeomAbs_Circle) != 2 or types.count(GeomAbs_Line) != 2:
        return result
    circular_edges = _circular_boundary_edges(document, [side_face_id], through_axis)
    if len(circular_edges) != 2:
        return result
    circular_edges.sort(key=lambda item: item[1])
    low_edge_id, z_low = circular_edges[0]
    high_edge_id, z_high = circular_edges[1]
    through_length = z_high - z_low
    tolerance = max(1e-6, through_length * 1e-6, radius * 1e-6)
    if through_length <= tolerance:
        return result
    expected_arc_length = math.pi * radius
    if any(
        abs(document.edge_records[int(edge_id[1:])]["length"] - expected_arc_length)
        > max(1e-6, expected_arc_length * 1e-6)
        for edge_id, _ in circular_edges
    ):
        return result
    linear_edges = [edge for edge in edges if BRepAdaptor_Curve(edge).GetType() == GeomAbs_Line]
    linear_midpoints: list[list[float]] = []
    for edge in linear_edges:
        direction = _canonical_direction(BRepAdaptor_Curve(edge).Line().Direction().Coord())
        if abs(_dot(direction, through_axis)) < 1.0 - 1e-7:
            return result
        points = _edge_points(edge)
        if len(points) != 2:
            return result
        length = math.sqrt(sum((a - b) ** 2 for a, b in zip(*points)))
        if abs(length - through_length) > tolerance:
            return result
        midpoint = _edge_midpoint(edge)
        if midpoint is None:
            return result
        linear_midpoints.append(midpoint)
    chord_vector = [a - b for a, b in zip(linear_midpoints[1], linear_midpoints[0])]
    opening_width = math.sqrt(_dot(chord_vector, chord_vector))
    if abs(opening_width - 2.0 * radius) > max(1e-6, radius * 1e-6):
        return result
    x_axis = _canonical_direction(chord_vector)
    y_axis = _normalize(_cross(through_axis, x_axis))
    axis_midpoint = _point_on_axis(closest, through_axis, (z_low + z_high) / 2.0)
    surface_centroid = document.face_records[int(side_face_id[1:])]["centroid"]
    inward = [a - b for a, b in zip(surface_centroid, axis_midpoint)]
    inward = [
        value - _dot(inward, through_axis) * component
        for value, component in zip(inward, through_axis)
    ]
    if math.sqrt(_dot(inward, inward)) <= tolerance:
        return result
    if _dot(y_axis, inward) < 0:
        x_axis = _negate(x_axis)
        y_axis = _normalize(_cross(through_axis, x_axis))
    frame = {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": list(through_axis),
        "definition_method": "half_cylinder_chord_and_analytic_axis",
        "orientation_state": "complete",
    }
    low_center = _point_on_axis(closest, through_axis, z_low)
    high_center = _point_on_axis(closest, through_axis, z_high)
    obb_center = _vector(
        axis_midpoint[index] + radius * y_axis[index] / 2.0
        for index in range(3)
    )
    result["topology_roles"] = {
        "side_face_ids": [side_face_id],
        "bottom_face_ids": [],
        "transition_face_ids": [],
        "opening_edge_ids": [low_edge_id, high_edge_id],
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": low_center,
        "origin_role": "opening_center",
        "axis": list(through_axis),
        "local_frame": frame,
        "access_directions": [list(through_axis), _negate(through_axis)],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "radius", "value": _round(radius), "unit": "mm", "source": "occt", "method": "analytic_half_cylindrical_slot_wall", "face_ids": [side_face_id]},
            {"name": "width", "value": _round(opening_width), "unit": "mm", "source": "occt", "method": "half_circle_chord_endpoint_distance", "face_ids": [side_face_id]},
            {"name": "height", "value": _round(radius), "unit": "mm", "source": "derived", "method": "semicircle_radius", "face_ids": [side_face_id]},
            {"name": "through_length", "value": _round(through_length), "unit": "mm", "source": "occt", "method": "circular_opening_plane_distance_along_axis", "face_ids": [side_face_id]},
        ],
        "reference_points": [
            _reference_point("opening_center_low", low_center, [side_face_id], "cylinder_axis_intersection_with_low_semicircle"),
            _reference_point("opening_center_high", high_center, [side_face_id], "cylinder_axis_intersection_with_high_semicircle"),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": {
            "center": obb_center,
            "x_axis": list(frame["x_axis"]),
            "y_axis": list(frame["y_axis"]),
            "z_axis": list(frame["z_axis"]),
            "half_sizes": [_round(radius), _round(radius / 2.0), _round(through_length / 2.0)],
            "coordinate_system": "PCS",
            "source": "occt",
            "method": "analytic_half_cylinder_local_extents",
        },
        "complete": True,
    }
    return result


def _rectangular_through_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Measure a strict planar rectangular passage or edge-open through slot.

    A passage must contain four planar side Faces in a closed cycle.  A through
    slot must contain three planar side Faces in a U-shaped chain and its
    predicted bottom must be the unique wall opposite the open profile side.
    Both variants must span the same two opening planes along a unique axis.
    Any split, curved, tapered, incomplete, or topologically ambiguous member
    set remains an explicit incomplete enrichment.
    """

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    feature_class = preview.get("predicted_class")
    expected_count = 4 if feature_class == "rectangular_passage" else 3
    if len(member_face_ids) != expected_count or len(set(member_face_ids)) != expected_count:
        return result

    normal_groups: list[dict[str, Any]] = []
    for face_id in member_face_ids:
        face = document.faces[int(face_id[1:])]
        normal = _plane_normal(document, face_id)
        if normal is None:
            return result
        if any(
            BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line
            for edge in TopologyExplorer(face, ignore_orientation=True).edges()
        ):
            return result
        matching = next(
            (
                group
                for group in normal_groups
                if abs(_dot(normal, group["axis"])) >= 1.0 - 1e-7
            ),
            None,
        )
        if matching is None:
            normal_groups.append({"axis": normal, "face_ids": [face_id]})
        else:
            matching["face_ids"].append(face_id)
    if len(normal_groups) != 2:
        return result
    if abs(_dot(normal_groups[0]["axis"], normal_groups[1]["axis"])) > 1e-6:
        return result

    group_sizes = sorted(len(group["face_ids"]) for group in normal_groups)
    expected_group_sizes = [2, 2] if feature_class == "rectangular_passage" else [1, 2]
    if group_sizes != expected_group_sizes:
        return result
    if feature_class == "rectangular_passage":
        if bottom_face_id is not None:
            return result
    else:
        unique_wall = next(group["face_ids"][0] for group in normal_groups if len(group["face_ids"]) == 1)
        if bottom_face_id != unique_wall:
            return result

    member_set = set(member_face_ids)
    internal_degrees = sorted(
        len(
            member_set.intersection(
                document.face_records[int(face_id[1:])]["adjacent_face_ids"]
            )
        )
        for face_id in member_face_ids
    )
    expected_degrees = [2, 2, 2, 2] if feature_class == "rectangular_passage" else [1, 1, 2]
    if internal_degrees != expected_degrees:
        return result

    through_axis = _canonical_direction(
        _cross(normal_groups[0]["axis"], normal_groups[1]["axis"])
    )
    points = [
        point
        for face_id in member_face_ids
        for point in _face_points(document.faces[int(face_id[1:])])
    ]
    if len(points) < expected_count * 4:
        return result
    z_values = [_dot(point, through_axis) for point in points]
    z_low, z_high = min(z_values), max(z_values)
    through_length = z_high - z_low
    if through_length <= 1e-7:
        return result
    tolerance = max(1e-6, through_length * 1e-6)
    for face_id in member_face_ids:
        face_values = _face_projection_extents(
            document.faces[int(face_id[1:])], through_axis
        )
        if (
            not face_values
            or abs(min(face_values) - z_low) > tolerance
            or abs(max(face_values) - z_high) > tolerance
        ):
            return result

    profile_candidates: list[tuple[float, list[float]]] = []
    for group in normal_groups:
        axis = group["axis"]
        values = [_dot(point, axis) for point in points]
        profile_candidates.append((max(values) - min(values), axis))
    profile_candidates.sort(key=lambda item: (-item[0], tuple(item[1])))
    length, x_axis = profile_candidates[0]
    y_axis = _normalize(_cross(through_axis, x_axis))
    x_values = [_dot(point, x_axis) for point in points]
    y_values = [_dot(point, y_axis) for point in points]
    x_low, x_high = min(x_values), max(x_values)
    y_low, y_high = min(y_values), max(y_values)
    width = y_high - y_low
    if length <= 1e-7 or width <= 1e-7:
        return result

    frame = {
        "x_axis": list(x_axis),
        "y_axis": list(y_axis),
        "z_axis": list(through_axis),
        "definition_method": "orthogonal_planar_side_faces_and_dual_opening_planes",
        "orientation_state": "complete",
    }
    x_mid = (x_low + x_high) / 2.0
    y_mid = (y_low + y_high) / 2.0
    entry_center = _point_from_local_parameters(x_mid, y_mid, z_low, frame)
    exit_center = _point_from_local_parameters(x_mid, y_mid, z_high, frame)
    obb_center = _point_from_local_parameters(
        x_mid, y_mid, (z_low + z_high) / 2.0, frame
    )

    entry_edges = _opening_edges_on_plane(
        document, member_face_ids, through_axis, z_low, tolerance
    )
    exit_edges = _opening_edges_on_plane(
        document, member_face_ids, through_axis, z_high, tolerance
    )
    required_opening_edges = 4 if feature_class == "rectangular_passage" else 3
    if len(entry_edges) != required_opening_edges or len(exit_edges) != required_opening_edges:
        return result

    result["topology_roles"] = {
        "side_face_ids": member_face_ids,
        "bottom_face_ids": [] if bottom_face_id is None else [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": sorted(set(entry_edges + exit_edges)),
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": entry_center,
        "origin_role": "opening_center",
        "axis": list(through_axis),
        "local_frame": frame,
        "access_directions": [list(through_axis), _negate(through_axis)],
        "source": "occt",
    }
    measurement_method = "orthogonal_planar_profile_extent"
    result["geometry"] = {
        "measurements": [
            {
                "name": "length",
                "value": _round(length),
                "unit": "mm",
                "source": "occt",
                "method": measurement_method + "_along_local_x",
                "face_ids": member_face_ids,
            },
            {
                "name": "width",
                "value": _round(width),
                "unit": "mm",
                "source": "occt",
                "method": measurement_method + "_along_local_y",
                "face_ids": member_face_ids,
            },
            {
                "name": "through_length",
                "value": _round(through_length),
                "unit": "mm",
                "source": "occt",
                "method": "dual_opening_plane_distance_along_local_z",
                "face_ids": member_face_ids,
            },
        ],
        "reference_points": [
            _reference_point(
                "opening_center_low",
                entry_center,
                member_face_ids,
                "rectangular_profile_center_on_low_opening_plane",
            ),
            _reference_point(
                "opening_center_high",
                exit_center,
                member_face_ids,
                "rectangular_profile_center_on_high_opening_plane",
            ),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": {
            "center": obb_center,
            "x_axis": list(frame["x_axis"]),
            "y_axis": list(frame["y_axis"]),
            "z_axis": list(frame["z_axis"]),
            "half_sizes": [
                _round(length / 2.0),
                _round(width / 2.0),
                _round(through_length / 2.0),
            ],
            "coordinate_system": "PCS",
            "source": "occt",
            "method": "strict_rectangular_through_prism_local_extents",
        },
        "complete": True,
    }
    return result


def _rectangular_through_step_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Measure the generator's ledge-like rectangular through step.

    The source taxonomy deliberately labels the ledge Face as the bottom even
    though the Boolean prism is produced from a different context Face.  The
    ledge normal is therefore the manufacturing depth axis; the shared ledge
    edge is the through direction and the remaining ledge extent is its width.
    """

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 2
        or len(set(member_face_ids)) != 2
    ):
        return result
    side_face_id = next(face_id for face_id in member_face_ids if face_id != bottom_face_id)
    bottom_normal = _plane_normal(document, bottom_face_id)
    side_normal = _plane_normal(document, side_face_id)
    if bottom_normal is None or side_normal is None or abs(_dot(bottom_normal, side_normal)) > 1e-6:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    side_face = document.faces[int(side_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    side_edges = list(TopologyExplorer(side_face, ignore_orientation=True).edges())
    if (
        len(bottom_edges) != 4
        or len(side_edges) != 4
        or any(BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in bottom_edges + side_edges)
    ):
        return result
    shared_edge_ids = (
        set(document.face_records[int(bottom_face_id[1:])]["edge_ids"])
        & set(document.face_records[int(side_face_id[1:])]["edge_ids"])
    )
    if len(shared_edge_ids) != 1:
        return result
    shared_edge_id = next(iter(shared_edge_ids))
    shared_edge = document.edges[int(shared_edge_id[1:])]
    shared_adaptor = BRepAdaptor_Curve(shared_edge)
    if shared_adaptor.GetType() != GeomAbs_Line:
        return result
    axis_parameters = _blind_axis_parameters(
        document, [side_face_id], bottom_face_id, bottom_normal
    )
    if axis_parameters is None:
        return result
    _, opening_parameter, depth, machining_direction = axis_parameters
    x_axis = _canonical_direction(shared_adaptor.Line().Direction().Coord())
    if abs(_dot(x_axis, machining_direction)) > 1e-6:
        return result
    y_axis = _normalize(_cross(machining_direction, x_axis))
    bottom_points = _face_points(bottom_face)
    x_values = [_dot(point, x_axis) for point in bottom_points]
    y_values = [_dot(point, y_axis) for point in bottom_points]
    through_length = max(x_values) - min(x_values)
    width = max(y_values) - min(y_values)
    tolerance = max(1e-6, through_length * 1e-6, width * 1e-6)
    if (
        through_length <= tolerance
        or width <= tolerance
        or abs(document.edge_records[int(shared_edge_id[1:])]["length"] - through_length) > tolerance
    ):
        return result
    frame = {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": machining_direction,
        "definition_method": "labelled_ledge_shared_through_edge_and_opening_to_bottom_axis",
        "orientation_state": "complete",
    }
    opening_edge_ids = _opening_edges_on_plane(
        document,
        [side_face_id],
        bottom_normal,
        opening_parameter,
        max(1e-6, depth * 1e-6),
    )
    if len(opening_edge_ids) != 1:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(
        value - depth * component
        for value, component in zip(bottom_center, machining_direction)
    )
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        "rectangular_through_step_ledge_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": [side_face_id],
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "length", "value": _round(through_length), "unit": "mm", "source": "occt", "method": "labelled_ledge_extent_along_local_x", "face_ids": [bottom_face_id]},
            {"name": "through_length", "value": _round(through_length), "unit": "mm", "source": "occt", "method": "shared_ledge_edge_extent_along_local_x", "face_ids": member_face_ids},
            {"name": "width", "value": _round(width), "unit": "mm", "source": "occt", "method": "labelled_ledge_extent_along_local_y", "face_ids": [bottom_face_id]},
            {"name": "depth", "value": _round(depth), "unit": "mm", "source": "occt", "method": "opening_plane_to_labelled_ledge_along_local_z", "face_ids": member_face_ids},
            {"name": "floor_area", "value": _round(document.face_records[int(bottom_face_id[1:])]["area"]), "unit": "mm^2", "source": "occt", "method": "labelled_ledge_surface_properties", "face_ids": [bottom_face_id]},
        ],
        "reference_points": [
            _reference_point("opening_center", opening_center, [side_face_id], "labelled_ledge_centroid_projected_to_opening_plane"),
            _reference_point("bottom_center", bottom_center, [bottom_face_id], "labelled_ledge_surface_centroid"),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _open_step_axis_parameters(
    document: CadDocument,
    side_face_ids: list[str],
    bottom_face_id: str,
    axis: list[float],
) -> tuple[float, float, float, list[float]] | None:
    """Resolve a shared opening plane when side walls clip one another.

    A two-sided through step can trim one generated wall before it reaches the
    labelled Boolean floor.  All walls must still terminate on one common
    opening plane, remain inside the floor/opening interval, and at least one
    wall must reach the labelled floor.  This is narrower than accepting an
    arbitrary partial wall set and preserves safe failure on ambiguous input.
    """

    extents: list[tuple[float, float]] = []
    for face_id in side_face_ids:
        values = _face_projection_extents(document.faces[int(face_id[1:])], axis)
        if not values:
            return None
        extents.append((min(values), max(values)))
    bottom_parameter = _dot(
        document.face_records[int(bottom_face_id[1:])]["centroid"], axis
    )
    global_low = min(item[0] for item in extents)
    global_high = max(item[1] for item in extents)
    span = global_high - global_low
    if span <= 1e-7:
        return None
    tolerance = max(1e-6, span * 1e-6)
    lows = [item[0] for item in extents]
    highs = [item[1] for item in extents]
    if (
        abs(bottom_parameter - global_low) <= tolerance
        and max(highs) - min(highs) <= tolerance
        and all(value >= bottom_parameter - tolerance for value in lows)
        and any(abs(value - bottom_parameter) <= tolerance for value in lows)
    ):
        opening_parameter = sum(highs) / len(highs)
    elif (
        abs(bottom_parameter - global_high) <= tolerance
        and max(lows) - min(lows) <= tolerance
        and all(value <= bottom_parameter + tolerance for value in highs)
        and any(abs(value - bottom_parameter) <= tolerance for value in highs)
    ):
        opening_parameter = sum(lows) / len(lows)
    else:
        return None
    depth = abs(bottom_parameter - opening_parameter)
    if depth <= tolerance:
        return None
    machining_direction = (
        axis if bottom_parameter > opening_parameter else _negate(axis)
    )
    return bottom_parameter, opening_parameter, depth, machining_direction


def _open_profile_through_step_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
    side_count: int,
    bottom_edge_count: int,
) -> dict[str, Any]:
    """Measure the source-labelled open-profile two-sided or slanted step."""

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != side_count + 1
        or len(set(member_face_ids)) != side_count + 1
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if bottom_normal is None:
        return result
    bottom_face = document.faces[int(bottom_face_id[1:])]
    bottom_edges = list(TopologyExplorer(bottom_face, ignore_orientation=True).edges())
    if len(bottom_edges) != bottom_edge_count or any(
        BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line for edge in bottom_edges
    ):
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    for face_id in side_face_ids:
        normal = _plane_normal(document, face_id)
        if normal is None or abs(_dot(normal, bottom_normal)) > 1e-6:
            return result
    member_set = set(member_face_ids)
    degrees = sorted(
        len(
            member_set
            & set(document.face_records[int(face_id[1:])]["adjacent_face_ids"])
        )
        for face_id in member_face_ids
    )
    expected_degrees = (
        [[1, 1]]
        if side_count == 1
        else [[1, 1, 2], [2, 2, 2]]
    )
    if degrees not in expected_degrees:
        return result
    axis_parameters = _open_step_axis_parameters(
        document, side_face_ids, bottom_face_id, bottom_normal
    )
    if axis_parameters is None:
        return result
    _, opening_parameter, depth, machining_direction = axis_parameters
    frame_and_size = _profile_frame_from_linear_edges(
        bottom_face, machining_direction
    )
    if frame_and_size is None:
        return result
    frame, length, width = frame_and_size
    opening_edge_ids = _opening_edges_on_plane(
        document,
        side_face_ids,
        bottom_normal,
        opening_parameter,
        max(1e-6, depth * 1e-6),
    )
    if len(opening_edge_ids) != side_count:
        return result
    bottom_center = list(document.face_records[int(bottom_face_id[1:])]["centroid"])
    opening_center = _vector(
        value - depth * component
        for value, component in zip(bottom_center, machining_direction)
    )
    oriented_box = _local_extents_obb(
        document,
        member_face_ids,
        frame,
        f"open_profile_{side_count}_wall_through_step_local_extents",
    )
    if oriented_box is None:
        return result
    result["topology_roles"] = {
        "side_face_ids": side_face_ids,
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": opening_edge_ids,
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "length", "value": _round(length), "unit": "mm", "source": "occt", "method": "open_step_bottom_profile_extent_along_local_x", "face_ids": [bottom_face_id]},
            {"name": "width", "value": _round(width), "unit": "mm", "source": "occt", "method": "open_step_bottom_profile_extent_along_local_y", "face_ids": [bottom_face_id]},
            {"name": "depth", "value": _round(depth), "unit": "mm", "source": "occt", "method": "opening_plane_to_open_step_bottom_along_local_z", "face_ids": member_face_ids},
            {"name": "floor_area", "value": _round(document.face_records[int(bottom_face_id[1:])]["area"]), "unit": "mm^2", "source": "occt", "method": "source_labelled_bottom_surface_properties", "face_ids": [bottom_face_id]},
        ],
        "reference_points": [
            _reference_point("opening_center", opening_center, side_face_ids, "bottom_centroid_projected_to_opening_plane"),
            _reference_point("bottom_center", bottom_center, [bottom_face_id], "source_labelled_bottom_surface_centroid"),
            *_bottom_vertex_reference_points(bottom_face, bottom_face_id, frame),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": oriented_box,
        "complete": True,
    }
    return result


def _linear_edge_direction(edge) -> list[float] | None:
    adaptor = BRepAdaptor_Curve(edge)
    if adaptor.GetType() != GeomAbs_Line:
        return None
    return _canonical_direction(adaptor.Line().Direction().Coord())


def _chamfer_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Measure a strict, symmetric planar chamfer transition.

    The predicted instance owns only the newly generated chamfer Face.  The two
    adjacent support Faces are consulted as read-only OCCT context to disambiguate
    the original edge direction and to verify one symmetric chamfer angle.  They
    are intentionally not added to the model-owned member Face set.
    """

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    result = _default_enrichment(raw_instance_id, None, member_face_ids)
    if len(member_face_ids) != 1 or len(set(member_face_ids)) != 1:
        return result
    transition_face_id = member_face_ids[0]
    face = document.faces[int(transition_face_id[1:])]
    chamfer_normal = _plane_normal(document, transition_face_id)
    outward_normal = _oriented_plane_normal(document, transition_face_id)
    if chamfer_normal is None or outward_normal is None:
        return result
    edges = list(TopologyExplorer(face, ignore_orientation=True).edges())
    if len(edges) != 4:
        return result
    directions = [_linear_edge_direction(edge) for edge in edges]
    if any(direction is None for direction in directions):
        return result

    direction_groups: list[tuple[list[float], list[Any]]] = []
    for edge, direction in zip(edges, directions):
        for existing_direction, grouped_edges in direction_groups:
            if abs(_dot(direction, existing_direction)) >= 1.0 - 1e-7:
                grouped_edges.append(edge)
                break
        else:
            direction_groups.append((direction, [edge]))
    if len(direction_groups) != 2 or any(
        len(grouped_edges) != 2 for _, grouped_edges in direction_groups
    ):
        return result

    all_points = _face_points(face)
    if len(all_points) != 4:
        return result
    candidates: list[tuple[list[float], list[float], float, float, list[str]]] = []
    for axis, boundary_edges in direction_groups:
        support_face_ids: list[str] = []
        for edge in boundary_edges:
            edge_id = _edge_id(document, edge)
            adjacent = [
                face_id
                for face_id in document.edge_records[int(edge_id[1:])]["adjacent_face_ids"]
                if face_id != transition_face_id
            ]
            if len(adjacent) != 1:
                break
            support_face_ids.append(adjacent[0])
        if len(support_face_ids) != 2 or len(set(support_face_ids)) != 2:
            continue
        support_normals = [
            _plane_normal(document, face_id) for face_id in support_face_ids
        ]
        if any(normal is None for normal in support_normals):
            continue
        if abs(_dot(support_normals[0], support_normals[1])) >= 1.0 - 1e-7:
            continue
        angles = [
            math.degrees(
                math.acos(min(1.0, max(-1.0, abs(_dot(chamfer_normal, normal)))))
            )
            for normal in support_normals
        ]
        if min(angles) <= 1e-6 or abs(angles[0] - angles[1]) > 1e-5:
            continue
        width_axis = _canonical_direction(_cross(chamfer_normal, axis))
        width_parameters = [_dot(point, width_axis) for point in all_points]
        low_width, high_width = min(width_parameters), max(width_parameters)
        width = high_width - low_width
        axis_parameters = [_dot(point, axis) for point in all_points]
        length = max(axis_parameters) - min(axis_parameters)
        tolerance = max(1e-6, width * 1e-6, length * 1e-6)
        if width <= tolerance or length <= tolerance:
            continue
        boundary_parameters: list[float] = []
        for edge in boundary_edges:
            values = [_dot(point, width_axis) for point in _edge_points(edge)]
            if len(values) != 2 or abs(values[0] - values[1]) > tolerance:
                break
            boundary_parameters.append(sum(values) / 2.0)
        if len(boundary_parameters) != 2:
            continue
        if not (
            abs(min(boundary_parameters) - low_width) <= tolerance
            and abs(max(boundary_parameters) - high_width) <= tolerance
        ):
            continue
        candidates.append(
            (axis, width_axis, width, length, sorted(support_face_ids))
        )
    if len(candidates) != 1:
        return result

    axis, width_axis, width, length, support_face_ids = candidates[0]
    support_normals = [_plane_normal(document, face_id) for face_id in support_face_ids]
    chamfer_angle = sum(
        math.degrees(
            math.acos(min(1.0, max(-1.0, abs(_dot(chamfer_normal, normal)))))
        )
        for normal in support_normals
    ) / 2.0
    normal_axis = _normalize(_cross(axis, width_axis))
    frame = {
        "x_axis": width_axis,
        "y_axis": normal_axis,
        "z_axis": axis,
        "definition_method": "planar_chamfer_boundaries_and_two_planar_support_faces",
        "orientation_state": "complete",
    }
    extents = []
    for frame_axis in (width_axis, normal_axis, axis):
        parameters = [_dot(point, frame_axis) for point in all_points]
        extents.append((min(parameters), max(parameters)))
    center = _point_from_local_parameters(
        (extents[0][0] + extents[0][1]) / 2.0,
        (extents[1][0] + extents[1][1]) / 2.0,
        (extents[2][0] + extents[2][1]) / 2.0,
        frame,
    )
    start = _point_from_local_parameters(
        (extents[0][0] + extents[0][1]) / 2.0,
        (extents[1][0] + extents[1][1]) / 2.0,
        extents[2][0],
        frame,
    )
    end = _point_from_local_parameters(
        (extents[0][0] + extents[0][1]) / 2.0,
        (extents[1][0] + extents[1][1]) / 2.0,
        extents[2][1],
        frame,
    )
    result["topology_roles"] = {
        "side_face_ids": [],
        "bottom_face_ids": [],
        "transition_face_ids": member_face_ids,
        "opening_edge_ids": [],
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": center,
        "origin_role": "edge_chain_midpoint",
        "axis": axis,
        "local_frame": frame,
        "access_directions": [_negate(outward_normal)],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "chamfer_width", "value": _round(width), "unit": "mm", "source": "occt", "method": "distance_between_support_boundary_lines_on_chamfer_plane", "face_ids": member_face_ids},
            {"name": "chamfer_angle", "value": _round(chamfer_angle), "unit": "deg", "source": "occt", "method": "equal_acute_plane_angle_to_two_adjacent_support_faces", "face_ids": member_face_ids},
            {"name": "length", "value": _round(length), "unit": "mm", "source": "occt", "method": "chamfer_boundary_extent_along_original_edge_axis", "face_ids": member_face_ids},
        ],
        "reference_points": [
            _reference_point("edge_chain_midpoint", center, member_face_ids, "chamfer_local_bounds_midpoint"),
            _reference_point("edge_chain_start", start, member_face_ids, "chamfer_axis_low_extent"),
            _reference_point("edge_chain_end", end, member_face_ids, "chamfer_axis_high_extent"),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": {
            "center": center,
            "x_axis": width_axis,
            "y_axis": normal_axis,
            "z_axis": axis,
            "half_sizes": [_round(width / 2.0), 0.0, _round(length / 2.0)],
            "coordinate_system": "PCS",
            "source": "occt",
            "method": "zero_thickness_planar_chamfer_local_bounds",
        },
        "complete": True,
    }
    return result


def _round_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Measure a single analytic cylindrical edge-round transition."""

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    result = _default_enrichment(raw_instance_id, None, member_face_ids)
    if len(member_face_ids) != 1 or len(set(member_face_ids)) != 1:
        return result
    transition_face_id = member_face_ids[0]
    face = document.faces[int(transition_face_id[1:])]
    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_Cylinder:
        return result
    axis, closest, radius = _axis_line(adaptor)
    edges = list(TopologyExplorer(face, ignore_orientation=True).edges())
    line_edges = [edge for edge in edges if BRepAdaptor_Curve(edge).GetType() == GeomAbs_Line]
    circle_edges = [edge for edge in edges if BRepAdaptor_Curve(edge).GetType() == GeomAbs_Circle]
    if len(edges) != 4 or len(line_edges) != 2 or len(circle_edges) != 2:
        return result
    if any(
        abs(_dot(_linear_edge_direction(edge), axis)) < 1.0 - 1e-7
        for edge in line_edges
    ):
        return result
    projections = _face_projection_extents(face, axis)
    if not projections:
        return result
    low, high = min(projections), max(projections)
    length = high - low
    tolerance = max(1e-6, radius * 1e-6, length * 1e-6)
    if radius <= tolerance or length <= tolerance:
        return result
    for edge in line_edges:
        values = [_dot(point, axis) for point in _edge_points(edge)]
        if len(values) != 2 or abs(min(values) - low) > tolerance or abs(max(values) - high) > tolerance:
            return result
    circle_parameters: list[float] = []
    for edge in circle_edges:
        circle = BRepAdaptor_Curve(edge).Circle()
        if abs(float(circle.Radius()) - radius) > tolerance:
            return result
        circle_axis = _normalize(circle.Axis().Direction().Coord())
        if abs(_dot(circle_axis, axis)) < 1.0 - 1e-7:
            return result
        circle_parameters.append(_dot(circle.Location().Coord(), axis))
    if not (
        abs(min(circle_parameters) - low) <= tolerance
        and abs(max(circle_parameters) - high) <= tolerance
    ):
        return result

    axis_midpoint = _point_on_axis(closest, axis, (low + high) / 2.0)
    centroid = list(document.face_records[int(transition_face_id[1:])]["centroid"])
    centroid_axis_point = _point_on_axis(closest, axis, _dot(centroid, axis))
    radial = [value - center for value, center in zip(centroid, centroid_axis_point)]
    if math.sqrt(sum(value * value for value in radial)) <= tolerance:
        return result
    native_radial = _normalize(radial)
    outward = _negate(native_radial) if face.Orientation() == TopAbs_REVERSED else native_radial
    radial_axis = _canonical_direction(native_radial)
    tangent_axis = _normalize(_cross(axis, radial_axis))
    frame = {
        "x_axis": radial_axis,
        "y_axis": tangent_axis,
        "z_axis": axis,
        "definition_method": "analytic_fillet_cylinder_axis_and_surface_radial_bisector",
        "orientation_state": "complete",
    }
    start = _point_on_axis(closest, axis, low)
    end = _point_on_axis(closest, axis, high)
    result["topology_roles"] = {
        "side_face_ids": [],
        "bottom_face_ids": [],
        "transition_face_ids": member_face_ids,
        "opening_edge_ids": [],
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": axis_midpoint,
        "origin_role": "edge_chain_midpoint",
        "axis": axis,
        "local_frame": frame,
        "access_directions": [_negate(outward)],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "radius", "value": _round(radius), "unit": "mm", "source": "occt", "method": "analytic_transition_cylinder_radius", "face_ids": member_face_ids},
            {"name": "length", "value": _round(length), "unit": "mm", "source": "occt", "method": "analytic_transition_cylinder_axis_extent", "face_ids": member_face_ids},
        ],
        "reference_points": [
            _reference_point("edge_chain_midpoint", axis_midpoint, member_face_ids, "transition_cylinder_axis_midpoint"),
            _reference_point("edge_chain_start", start, member_face_ids, "transition_cylinder_axis_low_extent"),
            _reference_point("edge_chain_end", end, member_face_ids, "transition_cylinder_axis_high_extent"),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": _analytic_cylinder_obb(
            axis_midpoint, frame, radius, length
        ),
        "complete": True,
    }
    return result


def _oring_enrichment(
    document: CadDocument,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Measure a strict flat-bottom annular O-ring groove."""

    raw_instance_id = preview["instance_id"]
    member_face_ids = list(preview["face_ids"])
    bottom_face_id = preview.get("bottom_face_id")
    result = _default_enrichment(raw_instance_id, bottom_face_id, member_face_ids)
    if (
        bottom_face_id is None
        or bottom_face_id not in member_face_ids
        or len(member_face_ids) != 3
        or len(set(member_face_ids)) != 3
    ):
        return result
    side_face_ids = [face_id for face_id in member_face_ids if face_id != bottom_face_id]
    if len(side_face_ids) != 2 or _plane_normal(document, bottom_face_id) is None:
        return result
    signatures: list[tuple[str, list[float], list[float], float]] = []
    for face_id in side_face_ids:
        adaptor = BRepAdaptor_Surface(document.faces[int(face_id[1:])])
        if adaptor.GetType() != GeomAbs_Cylinder:
            return result
        direction, closest, radius = _axis_line(adaptor)
        signatures.append((face_id, direction, closest, radius))
    signatures.sort(key=lambda item: item[3])
    inner_face_id, axis, closest, inner_radius = signatures[0]
    outer_face_id, outer_axis, outer_closest, outer_radius = signatures[1]
    tolerance = max(1e-6, outer_radius * 1e-6)
    if (
        outer_radius - inner_radius <= tolerance
        or abs(_dot(axis, outer_axis)) < 1.0 - 1e-7
        or math.sqrt(sum((a - b) ** 2 for a, b in zip(closest, outer_closest))) > tolerance
    ):
        return result
    bottom_normal = _plane_normal(document, bottom_face_id)
    if abs(_dot(bottom_normal, axis)) < 1.0 - 1e-7:
        return result
    axis_parameters = _blind_axis_parameters(
        document, side_face_ids, bottom_face_id, axis
    )
    if axis_parameters is None:
        return result
    bottom_parameter, opening_parameter, depth, machining_direction = axis_parameters
    expected_floor_area = math.pi * (outer_radius * outer_radius - inner_radius * inner_radius)
    floor_area = float(document.face_records[int(bottom_face_id[1:])]["area"])
    if abs(floor_area - expected_floor_area) > max(1e-5, expected_floor_area * 1e-6):
        return result
    opening_edges: list[str] = []
    for face_id in side_face_ids:
        matches = [
            edge_id
            for edge_id, parameter in _circular_boundary_edges(document, [face_id], axis)
            if abs(parameter - opening_parameter) <= max(1e-6, depth * 1e-6)
        ]
        if len(matches) != 1:
            return result
        opening_edges.extend(matches)
    if len(set(opening_edges)) != 2:
        return result

    opening_center = _point_on_axis(closest, axis, opening_parameter)
    bottom_center = _point_on_axis(closest, axis, bottom_parameter)
    center = _point_on_axis(
        closest, axis, (opening_parameter + bottom_parameter) / 2.0
    )
    frame = _axial_local_frame(machining_direction)
    groove_width = outer_radius - inner_radius
    result["topology_roles"] = {
        "side_face_ids": [inner_face_id, outer_face_id],
        "bottom_face_ids": [bottom_face_id],
        "transition_face_ids": [],
        "opening_edge_ids": sorted(opening_edges),
        "roles_complete": True,
    }
    result["placement"] = {
        "coordinate_system": "PCS",
        "origin": opening_center,
        "origin_role": "opening_center",
        "axis": machining_direction,
        "local_frame": frame,
        "access_directions": [machining_direction],
        "source": "occt",
    }
    result["geometry"] = {
        "measurements": [
            {"name": "inner_diameter", "value": _round(2.0 * inner_radius), "unit": "mm", "source": "occt", "method": "inner_cylindrical_wall_radius_x2", "face_ids": [inner_face_id]},
            {"name": "outer_diameter", "value": _round(2.0 * outer_radius), "unit": "mm", "source": "occt", "method": "outer_cylindrical_wall_radius_x2", "face_ids": [outer_face_id]},
            {"name": "centerline_diameter", "value": _round(inner_radius + outer_radius), "unit": "mm", "source": "occt", "method": "annular_groove_mean_radius_x2", "face_ids": side_face_ids},
            {"name": "width", "value": _round(groove_width), "unit": "mm", "source": "occt", "method": "outer_radius_minus_inner_radius", "face_ids": side_face_ids},
            {"name": "depth", "value": _round(depth), "unit": "mm", "source": "occt", "method": "opening_plane_to_annular_bottom_along_common_axis", "face_ids": member_face_ids},
            {"name": "floor_area", "value": _round(floor_area), "unit": "mm^2", "source": "occt", "method": "annular_bottom_surface_properties", "face_ids": [bottom_face_id]},
        ],
        "reference_points": [
            _reference_point("opening_center", opening_center, side_face_ids, "common_cylinder_axis_at_opening_plane"),
            _reference_point("bottom_center", bottom_center, member_face_ids, "common_cylinder_axis_at_bottom_plane"),
        ],
        "bounding_box": document.bounding_box_for_face_ids(member_face_ids),
        "oriented_bounding_box": _analytic_cylinder_obb(
            center, frame, outer_radius, depth
        ),
        "complete": True,
    }
    return result


def build_postprocess_context(
    step_path: str | Path,
    prediction: dict[str, Any],
    *,
    part_id: str | None = None,
    postprocess_code_commit: str = "working-tree",
    model_code_commit: str = "e0e36b7a12a7f01a29d7be36efc22730d293a1bd",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(P04 context, P01 audit summary)`` for one AAGNet result.

    The function never derives dimensions from AAGNet's normalized body.  It
    imports the original STEP in OCCT, validates graph alignment in normalized
    space, and measures the unscaled B-Rep in OCCT's millimetre system.
    """

    document = CadDocument.from_step(step_path)
    request = prediction.get("request", {})
    if str(request.get("sha256", "")).upper() != document.step_sha256:
        raise FaceAlignmentError("Prediction STEP hash differs from the P01 input.")
    document.verify_prediction_alignment(prediction)

    enrichments: list[dict[str, Any]] = []
    for preview in prediction.get("features_preview", []):
        if preview["predicted_class"] == "chamfer":
            enrichments.append(_chamfer_enrichment(document, preview))
        elif preview["predicted_class"] == "round":
            enrichments.append(_round_enrichment(document, preview))
        elif preview["predicted_class"] == "Oring":
            enrichments.append(_oring_enrichment(document, preview))
        elif preview["predicted_class"] in {"through_hole", "blind_hole"}:
            enrichments.extend(_hole_enrichments(document, preview))
        elif preview["predicted_class"] in {
            "rectangular_pocket",
            "rectangular_blind_slot",
        }:
            enrichments.append(_rectangular_blind_enrichment(document, preview))
        elif preview["predicted_class"] in {
            "rectangular_passage",
            "rectangular_through_slot",
        }:
            enrichments.append(_rectangular_through_enrichment(document, preview))
        elif preview["predicted_class"] == "triangular_passage":
            enrichments.append(_polygon_through_enrichment(document, preview, 3))
        elif preview["predicted_class"] == "6sides_passage":
            enrichments.append(_polygon_through_enrichment(document, preview, 6))
        elif preview["predicted_class"] == "triangular_through_slot":
            enrichments.append(_triangular_through_slot_enrichment(document, preview))
        elif preview["predicted_class"] == "circular_through_slot":
            enrichments.append(_circular_through_slot_enrichment(document, preview))
        elif preview["predicted_class"] == "rectangular_through_step":
            enrichments.append(_rectangular_through_step_enrichment(document, preview))
        elif preview["predicted_class"] == "2sides_through_step":
            enrichments.append(
                _open_profile_through_step_enrichment(document, preview, 2, 5)
            )
        elif preview["predicted_class"] == "slanted_through_step":
            enrichments.append(
                _open_profile_through_step_enrichment(document, preview, 1, 4)
            )
        elif preview["predicted_class"] == "rectangular_blind_step":
            enrichments.append(_rectangular_blind_step_enrichment(document, preview))
        elif preview["predicted_class"] == "triangular_blind_step":
            enrichments.append(_triangular_blind_step_enrichment(document, preview))
        elif preview["predicted_class"] == "circular_blind_step":
            enrichments.append(_circular_blind_step_enrichment(document, preview))
        elif preview["predicted_class"] == "triangular_pocket":
            enrichments.append(_polygon_blind_pocket_enrichment(document, preview, 3))
        elif preview["predicted_class"] == "6sides_pocket":
            enrichments.append(_polygon_blind_pocket_enrichment(document, preview, 6))
        elif preview["predicted_class"] == "circular_end_pocket":
            enrichments.append(_circular_end_pocket_enrichment(document, preview))
        elif preview["predicted_class"] == "v_circular_end_blind_slot":
            enrichments.append(_v_circular_end_blind_slot_enrichment(document, preview))
        elif preview["predicted_class"] == "h_circular_end_blind_slot":
            enrichments.append(_h_circular_end_blind_slot_enrichment(document, preview))
        else:
            enrichments.append(
                _default_enrichment(
                    preview["instance_id"],
                    preview.get("bottom_face_id"),
                    preview.get("face_ids", []),
                )
            )

    resolved_part_id = part_id or f"factory-{document.step_sha256[:16].lower()}"
    warnings = list(document.warnings)
    if document.units["source_length"] and document.units["source_length"] != ["millimetre"]:
        warnings.append(
            "STEP source length unit is "
            + ", ".join(document.units["source_length"])
            + "; OCCT converted geometry to its millimetre transfer unit."
        )
    context = {
        "schema_version": "aicnc.feature-postprocess-context/1.2",
        "part_id": resolved_part_id,
        "source": {
            "step_file": request.get("filename") or document.path.name,
            "step_sha256": document.step_sha256,
            "occt_version": document.occt_version,
            "preprocess_version": PREPROCESS_VERSION,
        },
        "units": {"length": "mm", "angle": "deg"},
        "coordinate_system": {
            "name": "PCS",
            "origin": [0.0, 0.0, 0.0],
            "x_axis": [1.0, 0.0, 0.0],
            "y_axis": [0.0, 1.0, 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        },
        "face_id_namespace": document.face_id_namespace,
        "faces": document.features_faces(),
        "enrichments": enrichments,
        "relations": [],
        "warnings": warnings,
        "pipeline_metadata": {
            "postprocess_version": "0.9.0",
            "postprocess_code_commit": postprocess_code_commit,
            "model_code_commit": model_code_commit,
            "geometry_adapter_version": GEOMETRY_ADAPTER_VERSION,
        },
    }
    return context, document.summary()
