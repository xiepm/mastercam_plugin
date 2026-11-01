"""Explicit faceted-volume diagnostics, never analytic or dimensional acceptance."""
import argparse
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path


def require(value, reason):
    if not value:
        raise ValueError('faceted_material_' + reason)


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest().upper()


def budget(value):
    require(type(value) is int and 1 <= value <= 2000000, 'invalid_triangle_budget')
    return value


def solid(triangles, max_triangles):
    import manifold3d
    import numpy as np

    budget(max_triangles)
    require(isinstance(triangles, list) and 1 <= len(triangles) <= max_triangles, 'triangle_budget_exceeded')
    for triangle in triangles:
        require(isinstance(triangle, list) and len(triangle) == 3, 'triangles_required')
        for point in triangle:
            require(isinstance(point, list) and len(point) == 3 and all(
                type(value) in (int, float) and math.isfinite(value) for value in point), 'invalid_coordinate')
    points = np.asarray(triangles, dtype=np.float64)
    require(bool(np.all(np.linalg.norm(np.cross(points[:, 1] - points[:, 0],
        points[:, 2] - points[:, 0]), axis=1) > 0)), 'degenerate_triangle')
    vertices, indices = np.unique(points.reshape((-1, 3)), axis=0, return_inverse=True)
    faces = indices.reshape((-1, 3)).astype(np.uint64)
    canonical = np.sort(faces, axis=1)
    require(len(np.unique(canonical, axis=0)) == len(faces), 'duplicate_triangle')
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    undirected, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    require(bool(np.all(counts == 2)), 'open_or_nonmanifold_edges')
    balance = np.bincount(inverse, weights=np.where(edges[:, 0] < edges[:, 1], 1, -1), minlength=len(undirected))
    require(bool(np.all(balance == 0)), 'inconsistent_orientation')
    shape = manifold3d.Manifold(manifold3d.Mesh64(vertices, faces))
    require(shape.status() == manifold3d.Error.NoError and not shape.is_empty(), 'kernel_rejected_mesh')
    require(math.isfinite(shape.volume()) and shape.volume() > 0, 'nonpositive_volume')
    tolerance = shape.get_tolerance()
    require(math.isfinite(tolerance) and tolerance >= 0, 'invalid_kernel_tolerance')
    return shape, dict(input_triangles=len(triangles), kernel_triangles=shape.num_tri(),
        kernel_tolerance_mm=tolerance, approximate_seam_welding=False)


def compare(target, ipw):
    import manifold3d

    shapes = dict(missing_material_mm3=target-ipw, extra_material_mm3=ipw-target,
                  common_material_mm3=target^ipw)
    require(all(shape.status() == manifold3d.Error.NoError for shape in shapes.values()), 'boolean_failed')
    values = {name: shape.volume() for name, shape in shapes.items()}
    values.update(target_volume_mm3=target.volume(), ipw_volume_mm3=ipw.volume())
    require(all(math.isfinite(value) and value >= 0 for value in values.values()), 'nonphysical_volume')
    require(values['target_volume_mm3'] > 0 and values['ipw_volume_mm3'] > 0, 'nonpositive_volume')
    numerical_budget = max(values['target_volume_mm3'], values['ipw_volume_mm3']) * 1.e-8
    for difference, total in (('missing_material_mm3', 'target_volume_mm3'), ('extra_material_mm3', 'ipw_volume_mm3')):
        require(abs(values[difference] + values['common_material_mm3'] - values[total]) <= numerical_budget,
            'volume_partition_failed')
    return values


def triangulate(shape, deflection, max_triangles):
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepCheck import BRepCheck_Analyzer
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.TopAbs import TopAbs_REVERSED
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Extend.TopologyUtils import TopologyExplorer

    require(not shape.IsNull() and BRepCheck_Analyzer(shape).IsValid(), 'invalid_target')
    require(len(list(TopologyExplorer(shape).solids())) == 1, 'one_target_solid_required')
    mesher = BRepMesh_IncrementalMesh(shape, deflection, False, .1, False)
    require(mesher.IsDone(), 'meshing_failed')
    triangles = []
    for face in TopologyExplorer(shape).faces():
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation(face, location)
        require(mesh is not None and mesh.NbTriangles() > 0, 'missing_face_mesh')
        require(len(triangles) + mesh.NbTriangles() <= max_triangles, 'target_triangle_budget_exceeded')
        for index in range(1, mesh.NbTriangles() + 1):
            corners = list(mesh.Triangles().Value(index).Get())
            if face.Orientation() == TopAbs_REVERSED:
                corners.reverse()
            points = [mesh.Nodes().Value(corner).Transformed(location.Transformation()) for corner in corners]
            triangles.append([[point.X(), point.Y(), point.Z()] for point in points])
    return triangles


def native_triangles(data):
    """Accept explicit source contracts without relabelling Mastercam as NX."""
    streamed = isinstance(data, dict) and set(data) == {'units', 'source', 'triangles'} and data.get('source') == 'NX_native_toolpath_IPW'
    mastercam = isinstance(data, dict) and set(data) == {'schema_version','units','geometry_frame','approximation','polygons','source_stl_sha256'} and data.get('schema_version') == 'aicnc.native-ipw-polygons/1.0' and data.get('geometry_frame') == 'PCS' and data.get('approximation') == 'Mastercam_native_faceted_IPW_not_exact_STEP'
    if mastercam:
        import re
        require(isinstance(data['source_stl_sha256'],str) and re.fullmatch('[a-f0-9]{64}',data['source_stl_sha256']) is not None,'invalid_STL_digest')
    require((streamed or mastercam) and data['units'] == 'mm', 'native_stream_required')
    return data['triangles'] if streamed else data['polygons']


def measure(target_path, mesh_path, target_sha256, mesh_sha256, deflection_mm, max_triangles=2000000):
    budget(max_triangles)
    require(type(deflection_mm) in (int, float) and math.isfinite(deflection_mm) and 0 < deflection_mm <= 1.,
        'invalid_requested_deflection')
    paths = [Path(target_path).resolve(strict=True), Path(mesh_path).resolve(strict=True)]
    expected = [target_sha256, mesh_sha256]
    require(all(path.stat().st_size <= 1024**3 for path in paths), 'file_budget_exceeded')
    require([digest(path) for path in paths] == expected, 'input_hash_mismatch')
    sources = [Path(__file__), Path(__file__).with_name('core.py')]
    implementation = {str(path): digest(path) for path in sources}
    data = json.loads(paths[1].read_text(encoding='utf-8'))
    ipw, ipw_metadata = solid(native_triangles(data), max_triangles)
    from .core import CadDocument
    target, target_metadata = solid(triangulate(CadDocument.from_step(paths[0]).body,
        deflection_mm, max_triangles), max_triangles)
    values = compare(target, ipw)
    require([digest(path) for path in paths] == expected, 'input_changed')
    require(all(digest(path) == expected_hash for path, expected_hash in implementation.items()), 'implementation_changed')
    return dict(schema_version='aicnc.faceted-material-difference/1.0', status='measured',
        backend=dict(name='manifold3d', version=version('manifold3d'), numpy_version=version('numpy')),
        inputs={role: dict(path=str(path), sha256=expected_hash) for role, path, expected_hash in zip(
            ('target', 'mesh'), paths, expected)}, implementation=implementation,
        requested_deflection_mm=deflection_mm, max_triangles=max_triangles, geometry_frame='PCS', units='mm',
        target=target_metadata, ipw=ipw_metadata, **values,
        scope='faceted_target_vs_faceted_IPW_only', certified_target_deflection_bound=False,
        stock_to_ipw_bound=False, self_intersection_free_verified=False,
        dimensional_conformance='not_verified', production_released=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--target-sha256', required=True)
    parser.add_argument('--mesh-sha256', required=True)
    parser.add_argument('--deflection-mm', type=float, required=True)
    parser.add_argument('--max-triangles', type=int, default=2000000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'output_already_exists')
    result = measure(args.target, args.mesh, args.target_sha256, args.mesh_sha256,
        args.deflection_mm, args.max_triangles)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
