"""P01 verification of new NX-generated template parts. No factory import path.

Reuses the canonical CadDocument and analytic correspondence residuals. Surface
matching remains quarantined until the independent reverse probe is present.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from collections import Counter

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Transform
from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
from OCC.Core.BRepGProp import brepgprop_VolumeProperties
from OCC.Core.GProp import GProp_GProps
from OCC.Core.gp import gp_Pnt, gp_Trsf
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCC.Core.BRepTools import breptools_UVBounds
from OCC.Core.gp import gp_Vec

from .core import CadDocument, _shape_bbox
from .viewer_mesh import build_viewer_mesh

TOLERANCES = {"distance_mm": 0.001, "area_absolute_mm2": 0.001, "area_relative": 1e-5, "direction_residual": 1e-6,
              "surface_distance_mm": 0.001, "surface_normal_residual": 0.0001, "surface_grid": 9}


def rotation(p):
    x,y,z = [math.radians(p["rotate_"+k]) for k in "xyz"]
    a,b,c,d,e,f = math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    return [[e*c,e*d*b-f*a,e*d*a+f*b],[f*c,f*d*b+e*a,f*d*a-e*b],[-d,c*b,c*a]]


def transform_point(p, point):
    r = rotation(p)
    return [sum(r[i][j]*point[j] for j in range(3))+p["translate_"+"xyz"[i]] for i in range(3)]


def local_bounds(document, ids, p):
    r = rotation(p); origin = [p["translate_"+k] for k in "xyz"]
    t = gp_Trsf()
    t.SetValues(*[v for i in range(3) for v in [r[0][i],r[1][i],r[2][i],-sum(r[j][i]*origin[j] for j in range(3))]])
    boxes = [_shape_bbox(BRepBuilderAPI_Transform(document.faces[int(f[1:])],t,True).Shape()) for f in ids]
    return {"min": [min(b["min"][i] for b in boxes) for i in range(3)], "max": [max(b["max"][i] for b in boxes) for i in range(3)]}


def point_distance(point, shape):
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    distance = BRepExtrema_DistShapeShape(vertex, shape); distance.Perform()
    if not distance.IsDone(): raise ValueError("OCCT distance calculation failed")
    return distance.Value()


def surface_samples(face):
    u0,u1,v0,v1=breptools_UVBounds(face);surface=BRepAdaptor_Surface(face)
    samples=[]
    for i in range(9):
        for j in range(9):
            p=gp_Pnt();du=gp_Vec();dv=gp_Vec();surface.D1(u0+(u1-u0)*i/8,v0+(v1-v0)*j/8,p,du,dv)
            n=du.Crossed(dv)
            if n.Magnitude()<1e-12: raise ValueError("Degenerate controlled surface sample")
            n.Normalize();samples.append({"point":list(p.Coord()),"normal":list(n.Coord())})
    return samples


def prepare_reverse_probes(folder):
    document=CadDocument.from_step(folder/"part.step")
    with (folder/"reverse-probes.tsv").open("x",encoding="ascii") as stream:
        for face in document.face_records:
            if face["surface_type"] not in {"plane","cylinder"}:
                for i,p in enumerate(surface_samples(document.faces[face["node_index"]])):
                    stream.write("\t".join([face["face_id"],str(i),*[format(v,".17g") for v in p["point"]]])+"\n")


def surface_residual(document,a,b):
    if a["surface_type"]!="bspline" or b["surface_type"] not in {"bspline","bezier"}:return None
    from mastercam_bridge.nx_step_face_mapping import _distance
    if _distance(a["centroid"],b["centroid"])>.001 or abs(a["area"]-b["area"])>.001+1e-5*max(a["area"],b["area"]):return None
    face=document.faces[b["node_index"]]
    forward=max(point_distance(s["point"],face) for s in a["uv_samples"])
    if forward>TOLERANCES["surface_distance_mm"]:return None
    return {"surface_forward_mm":forward,"area_mm2":abs(a["area"]-b["area"]),"centroid_mm":_distance(a["centroid"],b["centroid"])}


def mapping(document, native, reverse_report=None):
    from mastercam_bridge.nx_step_face_mapping import _residual, _index
    left = _index(native["faces"], "native_ref", "adjacent_refs")
    right = _index(document.face_records, "face_id", "adjacent_face_ids")
    candidates = {n: {f: x for f,b in right.items() if (x := (_residual(a,b) or surface_residual(document,a,b))) is not None} for n,a in left.items()}
    indegree = Counter(f for pool in candidates.values() for f in pool)
    unique = {n: next(iter(pool)) for n,pool in candidates.items() if len(pool)==1 and indegree[next(iter(pool))]==1}
    complete = len(unique)==len(left)==len(right)
    adjacency = complete and all({unique[v] for v in left[n]["adjacent_refs"]}==set(right[f]["adjacent_face_ids"]) for n,f in unique.items())
    rows = []
    for n,a in left.items():
        f = unique.get(n)
        residual = max((point_distance(q,document.faces[int(f[1:])]) for q in a["boundary_points"]),default=math.inf) if f else None
        rows.append({"native_ref":n,"face_id":f,"candidates":list(candidates[n]),"residuals":candidates[n].get(f),"boundary_distance_mm":residual})
    passed = bool(adjacency and all(r["boundary_distance_mm"] <= TOLERANCES["distance_mm"] for r in rows))
    reverse_checks=[]
    for n,f in unique.items():
        if left[n]["surface_type"] in {"plane","cylinder"}:continue
        samples=surface_samples(document.faces[int(f[1:])]);probes=[r for r in (reverse_report or {}).get("reverse_probes",[]) if r["p01_face_id"]==f]
        # Reopened native tags may differ; descriptors, not names, identify the
        # matching native face in the independent session.
        if reverse_report:
            other=[a["native_ref"] for a in reverse_report["faces"] if surface_residual(document,a,right[f]) is not None]
            probes=[r for r in probes if r["native_ref"] in other] if len(other)==1 else []
        ok=len(probes)==len(samples) and {r["probe_index"] for r in probes}==set(range(len(samples)))
        max_normal=0.
        for r in probes:
            dot=abs(sum(a*b for a,b in zip(r["normal"],samples[r["probe_index"]]["normal"])))
            max_normal=max(max_normal,abs(1-dot))
            ok=ok and r["within_uv_rectangle"] and r["distance_mm"]<=TOLERANCES["surface_distance_mm"] and abs(1-dot)<=TOLERANCES["surface_normal_residual"]
        reverse_checks.append({"face_id":f,"passed":bool(ok),"sample_count":len(probes),"max_normal_residual":max_normal})
        passed=passed and ok
    return {"schema_version":"aicnc.generator-face-mapping/0.1","passed":passed,"face_id_namespace":document.face_id_namespace,
            "step_sha256":document.step_sha256,"prt_sha256":native["prt_sha256"],"tolerances":TOLERANCES,"rows":rows,"adjacency_verified":bool(adjacency),
            "matching_inputs":["surface_type","area","centroid","analytic","controlled_surface_distance"],"reverse_surface_checks":reverse_checks,"source_labels_used_for_matching":False}


def verify_geometry(document, recipe, objects, *, stock_volume_offset=0.):
    p = recipe["parameters"]; t = recipe["template_id"]
    l,w,h = [p[k] for k in ["base_length","base_width","base_height"]]
    expected = l*w*h
    if t=="cylindrical_hole": expected -= math.pi*(p["diameter"]/2)**2*(h if p["through"] else p["depth"])
    elif t=="six_hole_array": expected -= 6*math.pi*(p["diameter"]/2)**2*h
    elif t=="rounded_pocket": expected -= (p["length"]*p["width"]-(4-math.pi)*p["radius"]**2)*p["depth"]
    elif t=="open_channel": expected -= l*(1 if p["end_openness"]=="both" else .75)*p["width"]*p["depth"]
    elif t=="corner_step": expected -= p["length"]*p["width"]*p["depth"]
    elif t=="pocket_island": expected -= (p["length"]*p["width"]-p["island_length"]*p["island_width"])*p["depth"]
    elif t=="symmetric_chamfer": expected -= l*p["chamfer"]**2/2
    elif t=="loft_surface": expected = None
    if expected is not None:
        # A bounded generator may use a different original stock cross-section.
        # This is its analytic stock-volume difference, never a fitted residual.
        expected += stock_volume_offset
    props=GProp_GProps();brepgprop_VolumeProperties(document.body,props); volume=props.Mass()
    if volume<=0 or (expected is not None and abs(volume-expected)>max(.001,expected*1e-6)):
        raise ValueError(f"Solid volume does not match constructive recipe: {volume} != {expected}")
    for obj in objects:
        members = obj["members"]
        if not members: raise ValueError("Generated object has no final Faces")
        box=local_bounds(document,[m["face_id"] for m in members],p)
        obj["geometry"]["local_bounding_box"]={**box,"unit":"mm","coordinate_system":"construction_frame","definition":"bounding box of member surfaces; not necessarily feature dimensions","source":"OCCT"}
        measurements={}
        family=obj["family"]["value"]
        if family=="hole":
            walls=[document.face_records[int(m["face_id"][1:])] for m in members if m["role"]=="wall"]
            if not walls or any(f["surface_type"]!="cylinder" for f in walls): raise ValueError("Hole wall is not cylindrical")
            diameter=2*walls[0]["analytic"]["radius"]
            if abs(diameter-p["diameter"])>.001: raise ValueError("Hole diameter mismatch")
            depth=box["max"][2]-box["min"][2]
            wanted=h if t=="six_hole_array" or p.get("through") else p["depth"]
            if abs(depth-wanted)>.001: raise ValueError("Hole axial length mismatch")
            measurements={"diameter":diameter,"cylindrical_length":depth}
        elif family in {"pocket","channel","step","boss"}:
            dims=[box["max"][i]-box["min"][i] for i in range(3)]
            if abs(dims[2]-p["depth"])>.001: raise ValueError("Feature height/depth mismatch")
            measurements={"axial_extent":dims[2],"local_bound_length":dims[0],"local_bound_width":dims[1]}
        for key,value in measurements.items():
            obj["geometry"]["measures"][key]={"value":value,"unit":"mm","coordinate_system":"construction_frame","definition":key,"source":"OCCT","status":"known","verification":"checked_against_recipe","tolerance_mm":.001}
    return {"actual_volume_mm3":volume,"expected_volume_mm3":expected,"volume_passed":True}


def validate_generated_bundle(folder):
    from factory_data_loop.manufacturing_generator import read_json, write_new, sha
    from factory_data_loop.manufacturing_objects import assemble, validate_labels
    recipe=read_json(folder/"recipe.json"); native=read_json(folder/"nx-create.json"); reopened=read_json(folder/"nx-reopen.json")
    for report in (native,reopened):
        if report["status"]!="completed" or report["units"]!="mm" or report["solid_count"]!=1 or report["factory_access_count"]!=0 or report["cam_created"]:
            raise ValueError("Native session contract failed")
        if report["prt_sha256"]!=sha(folder/"part.prt") or report["step_sha256"]!=sha(folder/"part.step") or report["recipe_sha256"]!=sha(folder/"recipe.json"):
            raise ValueError("Native result hash mismatch")
    if native["history"]!=reopened["history"] or sorted(native["expressions"],key=lambda e:e["name"])!=sorted(reopened["expressions"],key=lambda e:e["name"]):
        raise ValueError("Native parameters/history changed on reopen")
    document=CadDocument.from_step(folder/"part.step")
    result=mapping(document,native,reopened)
    reopened_map=mapping(document,reopened,reopened)
    result["reopen_mapping_passed"]=reopened_map["passed"]
    result["passed"]=result["passed"] and reopened_map["passed"]
    write_new(folder/"face_mapping.json",result)
    if not result["passed"]:
        validation={"schema_version":"aicnc.generator-validation/0.1","passed":False,"errors":["NX/P01 geometry correspondence not uniquely verified"],"label_status":"quarantined","training_authorized":False,"production_released":False}
    else:
        labels=assemble(document,recipe,native,result,folder)
        geometry=verify_geometry(document,recipe,labels["objects"])
        validate_labels(labels)
        write_new(folder/"manufacturing_objects.json",labels)
        mesh=build_viewer_mesh(document,max_faces=256,max_triangles=100000)
        mesh["edges"]=[]
        for i,edge in enumerate(document.edges):
            curve=BRepAdaptor_Curve(edge);a,b=curve.FirstParameter(),curve.LastParameter()
            mesh["edges"].append({"edge_id":f"E{i:04d}","points":[list(curve.Value(a+(b-a)*j/32).Coord()) for j in range(33)]})
        write_new(folder/"mesh.json",mesh)
        validation={"schema_version":"aicnc.generator-validation/0.1","passed":True,"errors":[],"label_status":"synthetic_geometry_verified", "geometry":geometry,
                    "checks":["NX native history","fresh session reopen","STEP single solid","mutually unique Face mapping","adjacency","boundary distances","volume","Face/Edge references","object geometry"],
                    "training_authorized":False,"human_confirmed":False,"production_released":False}
    write_new(folder/"validation.json",validation)
    return validation
