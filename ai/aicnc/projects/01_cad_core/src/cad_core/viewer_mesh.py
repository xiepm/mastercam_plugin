"""PCS/mm display triangles from the existing P01 Face registry.

No STEP import, node reordering, graph reconstruction or measurement from mesh.
The caller serializes OCCT access. Meshing uses a topology-preserving copy so
display caches cannot change P01's bounding-box calculation or Face namespace.
"""
from __future__ import annotations

import math

from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.TopAbs import TopAbs_REVERSED
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import topods

from .errors import FaceAlignmentError
from .manufacturing_geometry import summary_canonical_sha256


def build_viewer_mesh(document, *, max_faces=128, max_triangles=20000):
    """Return unnormalized, undecimated triangles bound to P01 Face IDs."""
    before = summary_canonical_sha256(document.summary())
    if not 0 < len(document.faces) <= max_faces:
        raise ValueError("Viewer Face budget exceeded")
    if document.units["internal_length"] != ["millimetre"]:
        raise ValueError("Viewer requires P01 millimetre coordinates")
    copied = BRepBuilderAPI_Copy(document.body, True, False)
    mesher = BRepMesh_IncrementalMesh(copied.Shape(), 0.1, False, 0.25, False)
    mesher.Perform()
    if not mesher.IsDone():
        raise ValueError("OCCT display meshing did not complete")
    meshes, total = [], 0
    for node in document.node_indices:
        face = topods.Face(copied.ModifiedShape(document.faces[node]))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, location)
        if triangulation is None or triangulation.NbTriangles() == 0:
            raise ValueError("Missing display triangles for a registered Face")
        total += triangulation.NbTriangles()
        if total > max_triangles:
            raise ValueError("Viewer triangle budget exceeded; no Face is silently omitted")
        nodes, triangles = triangulation.Nodes(), triangulation.Triangles()
        transform = location.Transformation()
        positions = []
        for index in range(1, triangulation.NbTriangles() + 1):
            a, b, c = triangles.Value(index).Get()
            if face.Orientation() == TopAbs_REVERSED:
                b, c = c, b
            for vertex in (a, b, c):
                point = nodes.Value(vertex).Transformed(transform)
                xyz = [float(point.X()), float(point.Y()), float(point.Z())]
                if not all(math.isfinite(number) for number in xyz):
                    raise ValueError("Nonfinite OCCT display coordinate")
                positions.extend(xyz)
        meshes.append({"face_id": document.face_id_by_node[node], "node_index": node, "positions": positions})
    if before != summary_canonical_sha256(document.summary()):
        raise FaceAlignmentError("Display meshing changed the P01 summary")
    return {"coordinate_space": "PCS", "length_unit": "mm", "decimated": False,
            "triangle_count": total, "p01_summary_canonical_sha256": before, "faces": meshes}
