"""Geometry-only NX/P01 correspondence, deliberately limited to a 1:1 control.

Names, NX tags (except as opaque local keys), feature membership, and boundary
witnesses never choose a candidate. Unsupported/split/merged/ambiguous topology
is not repaired or turned into annotation here.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

SCHEMA = "aicnc.nx-step-face-mapping/0.1"
TOLERANCES = {"distance_mm": 0.001, "area_absolute_mm2": 0.001,
              "area_relative": 1e-5, "direction_residual": 1e-6}
SUPPORTED = {"plane", "cylinder"}


def _number(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError("Expected finite number")
    return float(x)


def _vector(x):
    if not isinstance(x, list) or len(x) != 3:
        raise ValueError("Expected three-dimensional vector")
    return [_number(v) for v in x]


def _direction(x):
    v = _vector(x)
    if abs(math.sqrt(sum(t*t for t in v)) - 1) > 1e-6:
        raise ValueError("Analytic direction must be unit length")
    return v


def _distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def _angle(a, b):
    return min(_distance(a, b), _distance(a, [-x for x in b]))


def _index(rows, key, adjacent):
    if not isinstance(rows, list) or not rows or len(rows) > 2048:
        raise ValueError("Face list empty or outside bounded control budget")
    result = {}
    for row in rows:
        identifier = row[key]
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ValueError("Invalid/duplicate Face identifier")
        if _number(row["area"]) <= 0:
            raise ValueError("Area must be positive")
        _vector(row["centroid"])
        if row["surface_type"] in SUPPORTED:
            a = row["analytic"]
            if a["kind"] != row["surface_type"]:
                raise ValueError("Analytic kind conflict")
            if a["kind"] == "plane":
                _direction(a["normal"]); _number(a["signed_offset"])
            else:
                if _number(a["radius"]) <= 0:
                    raise ValueError("Cylinder radius must be positive")
                d = _direction(a["axis"]["direction"])
                o = _vector(a["axis"]["closest_point_to_origin"])
                if abs(sum(x*y for x,y in zip(d,o))) > 0.001:
                    raise ValueError("Cylinder axis origin is not canonical")
        neighbors = row[adjacent]
        if not isinstance(neighbors, list) or not all(isinstance(v, str) for v in neighbors):
            raise ValueError("Invalid adjacency")
        if len(set(neighbors)) != len(neighbors) or identifier in neighbors:
            raise ValueError("Repeated/self adjacency")
        result[identifier] = row
    for identifier, row in result.items():
        for neighbor in row[adjacent]:
            if neighbor not in result or identifier not in result[neighbor][adjacent]:
                raise ValueError("Dangling or asymmetric adjacency")
    return result


def _residual(a, b):
    if a["surface_type"] not in SUPPORTED or a["surface_type"] != b["surface_type"]:
        return None
    distances = {"centroid_mm": _distance(a["centroid"], b["centroid"])}
    aa, bb = a["analytic"], b["analytic"]
    if aa["kind"] == "plane":
        an, bn = aa["normal"], bb["normal"]
        sign = 1 if sum(x*y for x,y in zip(an,bn)) >= 0 else -1
        distances["plane_offset_mm"] = abs(aa["signed_offset"]-sign*bb["signed_offset"])
        angular = _angle(an, bn)
    else:
        distances["radius_mm"] = abs(aa["radius"]-bb["radius"])
        distances["axis_origin_mm"] = _distance(aa["axis"]["closest_point_to_origin"], bb["axis"]["closest_point_to_origin"])
        angular = _angle(aa["axis"]["direction"], bb["axis"]["direction"])
    area = abs(a["area"]-b["area"])
    area_limit = TOLERANCES["area_absolute_mm2"] + TOLERANCES["area_relative"]*max(a["area"], b["area"])
    if max(distances.values()) > TOLERANCES["distance_mm"] or angular > TOLERANCES["direction_residual"] or area > area_limit:
        return None
    return {**distances, "area_mm2": area, "direction_residual": angular}


def build_mapping(native: dict[str, Any], p01: dict[str, Any]) -> dict[str, Any]:
    """Validate provenance first, then match, then inspect the held-out feature."""
    if native["schema_version"] != "aicnc.nx-step-face-export/0.1" or p01["schema_version"] != "aicnc.cad-core/1.0":
        raise ValueError("Unsupported input contract")
    if native["status"] != "completed" or native["error_count"] != 0 or not native["close_succeeded"]:
        raise ValueError("NX runtime incomplete")
    for field in ("save_called", "cam_builder_commit_called", "marker_write_called", "automatic_recognition_called", "make_feature_called", "truth_labels_generated", "training_authorized"):
        if native[field] is not False:
            raise ValueError("Disallowed runtime action: " + field)
    if native["factory_access_count"] != 0 or not native["step_export_commit_called"]:
        raise ValueError("Control scope violated")
    sha = native["input_sha256"]
    if not re.fullmatch(r"[A-F0-9]{64}", sha) or sha != native["input_sha256_after"]:
        raise ValueError("Source PRT hash changed")
    step_sha = native["step_sha256"]
    if not re.fullmatch(r"[A-F0-9]{64}", step_sha) or step_sha != p01["source"]["step_sha256"]:
        raise ValueError("Export/import STEP hash mismatch")
    source = p01["source"]
    expected_ns = f'aicnc-face-registry/1.0:{step_sha}:occt-{source["occt_version"]}:{source["preprocess_version"]}'
    if p01["face_id_namespace"] != expected_ns:
        raise ValueError("Invalid P01 Face namespace")
    if native["units"] != "millimetre" or native["coordinate_system"] != "absolute" or p01["units"]["internal_length"] != ["millimetre"]:
        raise ValueError("Only absolute mm export/import supported")
    cs = p01["coordinate_system"]
    if any(cs[k] != v for k,v in {"origin":[0,0,0], "x_axis":[1,0,0], "y_axis":[0,1,0], "z_axis":[0,0,1]}.items()):
        raise ValueError("Nonidentity coordinate contract")
    e = native["export_settings"]
    if e["reference"] != "Absolute" or e["representation"] != "Precise" or e["format"] != "Ap214" or e["attributes"] is not False or e["file_save_flag"] is not False or e["process_hold"] is not True:
        raise ValueError("STEP export settings changed")
    if native["body_count"] != 1 or e["selected_body_refs"] != [native["body_ref"]] or native["part_count_after_export"] != 1:
        raise ValueError("Single prototype body required")
    if p01["diagnostics"]["solid_count"] != 1 or not p01["diagnostics"]["brep_valid"]:
        raise ValueError("P01 solid invalid")
    left = _index(native["faces"], "native_ref", "adjacent_refs")
    right = _index(p01["faces"], "face_id", "adjacent_face_ids")
    if p01["diagnostics"]["face_count"] != len(right):
        raise ValueError("P01 Face count inconsistent")
    if any(r["body_ref"] != native["body_ref"] or r["is_occurrence"] is not False or r["is_approximate"] is not False for r in left.values()):
        raise ValueError("Native ownership/exact measurement required")
    # Only these numeric descriptors enter candidate selection. IDs are local keys.
    candidates = {n: {f: residual for f, b in right.items() if (residual := _residual(a,b)) is not None} for n,a in left.items()}
    indegree = Counter(f for pool in candidates.values() for f in pool)
    unique = {n: next(iter(pool)) for n,pool in candidates.items() if len(pool) == 1 and indegree[next(iter(pool))] == 1}
    complete = len(unique) == len(left) == len(right)
    topology = complete and all({unique[v] for v in left[n]["adjacent_refs"]} == set(right[f]["adjacent_face_ids"]) for n,f in unique.items())
    rows = []
    for n in sorted(left):
        pool = candidates[n]
        status = ("unsupported_surface" if left[n]["surface_type"] not in SUPPORTED else
                  "unmapped" if not pool else "ambiguous" if n not in unique else
                  "verified_one_to_one" if topology else "topology_conflict" if complete else "topology_unverified")
        rows.append({"native_ref": n, "candidate_face_ids": sorted(pool), "p01_face_id": unique.get(n),
                     "status": status, "residuals": pool.get(unique.get(n)), "is_ground_truth": False})
    w = native["feature_witness"]
    selected = w["face_refs"]
    witness_ok = (isinstance(selected, list) and len(selected) > 0 and len(set(selected)) == len(selected)
                  and set(selected) <= set(left) and set(selected) == set(w["geometry_refs"]) == set(w["marker_refs"])
                  and w["status"] == "UpToDate" and w["operation_count"] == w["linked_operation_count"] == 0)
    transferred = bool(witness_ok and topology and all(n in unique for n in selected))
    return {
        "schema_version": SCHEMA, "status": "control_geometry_mapping_passed" if transferred else "needs_review",
        "binding": {"prt_sha256": sha, "step_sha256": step_sha, "face_id_namespace": expected_ns},
        "tolerances": dict(TOLERANCES), "counts": {"native_faces":len(left), "p01_faces":len(right),
            "mutually_unique":len(unique), "verified":len(unique) if topology else 0,
            "ambiguous":sum(r["status"]=="ambiguous" for r in rows), "unmapped":sum(not pool for pool in candidates.values())},
        "topology_verified":bool(topology), "mappings":rows,
        "feature_transfer": {"status":"geometry_mapped_pending_boundary_witness" if transferred else "needs_review",
            "source_native_feature_ref":w["native_ref"], "native_face_refs":sorted(selected),
            "p01_face_ids":sorted(unique[n] for n in selected) if transferred else [],
            "native_witness_consistent":bool(witness_ok), "is_ground_truth":False},
        "matching_inputs":["surface_type","area","centroid","analytic"],
        "held_out_checks":["adjacency","feature_membership","marker_membership","boundary_vertices"],
        "training_authorized":False, "automatic_factory_binding_authorized":False, "factory_test_defined":False,
        "limitations":["one explicit 54-Face fixture, not factory recognition accuracy", "plane/cylinder only; no split/merge repair", "boundary witness and repeated import required separately"]}


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root
    output = root / "mapping.json"
    if output.exists():
        raise ValueError("Mapping already exists; do not overwrite")
    native = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "p01-summary-1.json").read_text(encoding="utf-8"))
    result = build_mapping(native, summary)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status":result["status"], "counts":result["counts"], "feature_transfer":result["feature_transfer"]}))


if __name__ == "__main__":
    main()
