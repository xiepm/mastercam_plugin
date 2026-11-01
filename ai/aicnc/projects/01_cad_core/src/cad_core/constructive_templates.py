"""Known synthetic constructions and round-trip verification; NOT a recognizer.

The only STEP reader is P01 CadDocument. Source face labels are assigned before
export from bounded template geometry, then independently mapped to final STEP.
No NX history, factory data, model inference or process planning is implied.
"""
from __future__ import annotations
import math
from collections import Counter

from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Transform)
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.BRepGProp import brepgprop_VolumeProperties
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCC.Core.BRepTools import breptools_UVBounds
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCC.Core.GProp import GProp_GProps
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Trsf
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Interface import Interface_Static_SetCVal
from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.TopoDS import topods
from OCC.Extend.TopologyUtils import TopologyExplorer

from .core import CadDocument, _surface_type, _surface_properties, _analytic_surface
from .generated_object_validation import rotation, transform_point, point_distance

VERSION = "occt-nine-family/0.1.0"
TOLERANCES = {"distance_mm": 0.001, "area_absolute_mm2": 0.001,
              "area_relative": 1e-5, "normal_residual": 0.0001, "surface_grid": 5,
              "volume_absolute_mm3": 0.001, "volume_relative": 1e-6}


def box(x, y, z, l, w, h):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), l, w, h).Shape()


def boolean(op, a, b):
    build = op(a, b)
    build.Build()
    if not build.IsDone():
        raise ValueError("Constructive Boolean failed")
    # Unify coplanar seams of the rounded rectangular cutter, not final IDs.
    build.SimplifyResult(True, True)
    return build.Shape()


def wire(points):
    make = BRepBuilderAPI_MakePolygon()
    for p in points:
        make.Add(gp_Pnt(*p))
    make.Close()
    if not make.IsDone():
        raise ValueError("Invalid constructive wire")
    return make.Wire()


def volume(shape):
    prop = GProp_GProps()
    brepgprop_VolumeProperties(shape, prop)
    return prop.Mass()


def make_local(recipe):
    p = recipe["parameters"]; t = recipe["template_id"]
    l, w, h = [p[k] for k in ("base_length", "base_width", "base_height")]
    body = box(0, 0, 0, l, w, h)
    if t in {"cylindrical_hole", "six_hole_array"}:
        points = [(p["x"], p["y"])] if t == "cylindrical_hole" else [
            (l/2+(i%3-1)*p["pitch_x"], w/2+(i//3-.5)*p["pitch_y"]) for i in range(6)]
        through = t == "six_hole_array" or p["through"]
        bottom = -1 if through else h-p["depth"]
        for x, y in points:
            cut = BRepPrimAPI_MakeCylinder(p["diameter"]/2, h-bottom+1).Shape()
            tr = gp_Trsf(); tr.SetTranslation(gp_Vec(x, y, bottom))
            cut = BRepBuilderAPI_Transform(cut, tr, True).Shape()
            body = boolean(BRepAlgoAPI_Cut, body, cut)
    elif t in {"rounded_pocket", "pocket_island"}:
        a,b,d = p["length"],p["width"],p["depth"]
        x,y,z = p["x"]-a/2,p["y"]-b/2,h-d
        if t == "rounded_pocket":
            r = p["radius"]
            tool = boolean(BRepAlgoAPI_Fuse, box(x+r,y,z,a-2*r,b,d+1), box(x,y+r,z,a,b-2*r,d+1))
            for cx,cy in [(x+r,y+r),(x+a-r,y+r),(x+r,y+b-r),(x+a-r,y+b-r)]:
                cyl = BRepPrimAPI_MakeCylinder(r,d+1).Shape()
                tr=gp_Trsf(); tr.SetTranslation(gp_Vec(cx,cy,z))
                tool=boolean(BRepAlgoAPI_Fuse, tool, BRepBuilderAPI_Transform(cyl,tr,True).Shape())
        else:
            ia,ib=p["island_length"],p["island_width"]
            tool=boolean(BRepAlgoAPI_Cut,box(x,y,z,a,b,d+1),
                box(p["x"]-ia/2,p["y"]-ib/2,z-1,ia,ib,d+3))
        body=boolean(BRepAlgoAPI_Cut,body,tool)
    elif t == "open_channel":
        end=l+1 if p["end_openness"]=="both" else .75*l
        body=boolean(BRepAlgoAPI_Cut,body,box(-1,p["y"]-p["width"]/2,h-p["depth"],end+1,p["width"],p["depth"]+1))
    elif t == "corner_step":
        body=boolean(BRepAlgoAPI_Cut,body,box(-1,-1,h-p["depth"],p["length"]+1,p["width"]+1,p["depth"]+1))
    elif t == "symmetric_chamfer":
        c=p["chamfer"]
        triangle=wire([(-1,0,h-c),(-1,0,h+1),(-1,c+1,h+1)])
        tool=BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(triangle).Face(),gp_Vec(l+2,0,0)).Shape()
        body=boolean(BRepAlgoAPI_Cut,body,tool)
    elif t == "loft_surface":
        loft=BRepOffsetAPI_ThruSections(True,False,1e-7)
        loft.CheckCompatibility(False)
        for y,z in [(0,h),(w/2,h+p["rise"]),(w,h)]:
            loft.AddWire(wire([(0,y,0),(l,y,0),(l,y,z),(0,y,z)]))
        loft.Build()
        if not loft.IsDone(): raise ValueError("Controlled B-Rep loft failed")
        body=loft.Shape()
    elif t not in {"target_plane","outer_profile"}:
        raise ValueError("Unsupported constructive template")
    if not BRepCheck_Analyzer(body).IsValid() or len(list(TopologyExplorer(body).solids()))!=1:
        raise ValueError("Construction did not produce one valid solid")
    return body


def source_labels(body, recipe):
    """Template-local truth on constructed geometry, never arbitrary STEP input.

    Plane coordinates here refer to frozen cutter definitions, not learned or
    guessed manufacturing intent. Nonunique/unexpected topology is rejected.
    """
    p=recipe["parameters"]; t=recipe["template_id"]
    l,w,h=[p[k] for k in ("base_length","base_width","base_height")]
    out=[]
    for face in TopologyExplorer(body).faces():
        area,c=_surface_properties(face); typ=_surface_type(face); a=_analytic_surface(face)
        on=lambda axis,v: typ=="plane" and abs(abs(a["normal"][axis])-1)<1e-7 and abs(c[axis]-v)<1e-5
        stock=any(on(axis,v) for axis,vals in enumerate([(0,l),(0,w),(0,h)]) for v in vals)
        oid=1; role=None
        if t in {"cylindrical_hole","six_hole_array"}:
            if typ=="cylinder":
                role="wall"
                if t=="six_hole_array":
                    cx,cy=a["axis"]["closest_point_to_origin"][:2]
                    targets=[(l/2+(i%3-1)*p["pitch_x"],w/2+(i//3-.5)*p["pitch_y"]) for i in range(6)]
                    matched=[i+1 for i,(x,y) in enumerate(targets) if math.hypot(cx-x,cy-y)<1e-5]
                    if len(matched)!=1: raise ValueError("Ambiguous constructive hole ownership")
                    oid=matched[0]
            elif t=="cylindrical_hole" and not p["through"] and on(2,h-p["depth"]): role="terminal"
        elif t in {"rounded_pocket","open_channel","corner_step","pocket_island"}:
            if on(2,h-p["depth"]): role="floor"
            elif not stock: role="wall"
            if t=="pocket_island":
                island=abs(c[0]-p["x"])<=p["island_length"]/2+1e-5 and abs(c[1]-p["y"])<=p["island_width"]/2+1e-5
                # A trimmed outer top face can have its centroid in the island's
                # hole. Its centroid alone is not a point-on-face witness.
                island_top=on(2,h) and abs(area-p["island_length"]*p["island_width"])<.001
                if island and (role=="wall" or island_top):
                    oid=2;role="top" if on(2,h) else "wall"
        elif t=="target_plane" and on(2,h): role="target_surface"
        elif t=="outer_profile" and not on(2,0) and not on(2,h): role="wall"
        elif t=="loft_surface" and c[2]>h-1e-5: role="target_surface"
        elif t=="symmetric_chamfer" and not stock: role="transition"
        out.append((face,[{"object_id":f"object:{oid:04d}","usage":"member","role":role}] if role else []))
    count=Counter(label["role"] for _,ls in out for label in ls)
    expected={"cylindrical_hole":{"wall":1,**({} if p.get("through") else {"terminal":1})},
        "six_hole_array":{"wall":6},"rounded_pocket":{"wall":8,"floor":1},
        "open_channel":{"wall":2 if p.get("end_openness")=="both" else 3,"floor":1},
        "corner_step":{"wall":2,"floor":1},"pocket_island":{"wall":8,"floor":1,"top":1},
        "target_plane":{"target_surface":1},"outer_profile":{"wall":4},
        "loft_surface":{"target_surface":1},"symmetric_chamfer":{"transition":1}}[t]
    if dict(count)!=expected: raise ValueError(f"Constructive topology mismatch: {dict(count)} != {expected}")
    return out


def describe(faces):
    result=[]; edges=[list(TopologyExplorer(f).edges()) for f in faces]
    for i,f in enumerate(faces):
        area,center=_surface_properties(f)
        neighbors=[f"S{j:04d}" for j in range(len(faces)) if i!=j and any(a.IsSame(b) for a in edges[i] for b in edges[j])]
        result.append({"native_ref":f"S{i:04d}","surface_type":_surface_type(f),"area":area,
            "centroid":center,"analytic":_analytic_surface(f),"adjacent_refs":neighbors})
    return result


def samples(face, grid=5):
    u0,u1,v0,v1=breptools_UVBounds(face); s=BRepAdaptor_Surface(face)
    for i in range(grid):
        for j in range(grid):
            pt=gp_Pnt();du=gp_Vec();dv=gp_Vec()
            s.D1(u0+(u1-u0)*(i+.5)/grid,v0+(v1-v0)*(j+.5)/grid,pt,du,dv)
            n=du.Crossed(dv)
            if n.Magnitude()<1e-12: raise ValueError("Singular controlled surface")
            n.Normalize()
            yield pt,n


def surface_check(source, target):
    max_distance=0.; max_normal=0.
    surf=BRep_Tool.Surface(target)
    for p,n in samples(source,TOLERANCES["surface_grid"]):
        distance=point_distance(p.Coord(),target)
        proj=GeomAPI_ProjectPointOnSurf(p,surf)
        if proj.NbPoints()<1: raise ValueError("Surface projection failed")
        u,v=proj.LowerDistanceParameters()
        point=gp_Pnt();du=gp_Vec();dv=gp_Vec();surf.D1(u,v,point,du,dv)
        normal=du.Crossed(dv);normal.Normalize()
        max_distance=max(max_distance,distance)
        max_normal=max(max_normal,abs(1-abs(n.Dot(normal))))
    if max_distance>TOLERANCES["distance_mm"] or max_normal>TOLERANCES["normal_residual"]:
        raise ValueError("Bidirectional curved surface check failed")
    return {"max_distance_mm":max_distance,"max_normal_residual":max_normal}


def map_faces(source_faces, source_rows, document):
    pools={}
    compatible=lambda a,b: a==b or {a,b}<={"bspline","bezier"}
    for row in source_rows:
        pools[row["native_ref"]]=[f["face_id"] for f in document.face_records
            if compatible(row["surface_type"],f["surface_type"])
            and math.dist(row["centroid"],f["centroid"])<=TOLERANCES["distance_mm"]
            and abs(row["area"]-f["area"])<=TOLERANCES["area_absolute_mm2"]+TOLERANCES["area_relative"]*row["area"]]
    degree=Counter(f for ids in pools.values() for f in ids)
    if len(source_rows)!=len(document.face_records) or any(len(ids)!=1 or degree[ids[0]]!=1 for ids in pools.values()):
        raise ValueError("Nonunique source-to-STEP Face mapping; labels quarantined")
    matched={k:v[0] for k,v in pools.items()};rows=[]
    for i,a in enumerate(source_rows):
        fid=matched[a["native_ref"]];b=document.face_records[int(fid[1:])];target=document.faces[b["node_index"]]
        if {matched[n] for n in a["adjacent_refs"]}!=set(b["adjacent_face_ids"]):
            raise ValueError("Source-to-STEP adjacency mismatch")
        boundary=[]
        for start,end in [(source_faces[i],target),(target,source_faces[i])]:
            boundary.extend(point_distance(BRep_Tool.Pnt(v).Coord(),end) for v in TopologyExplorer(start).vertices())
        if max(boundary,default=0)>TOLERANCES["distance_mm"]:raise ValueError("Boundary correspondence mismatch")
        analytic_a,analytic_b=a["analytic"],b["analytic"]
        if a["surface_type"]=="plane":
            if abs(abs(sum(x*y for x,y in zip(analytic_a["normal"],analytic_b["normal"]))) - 1)>1e-6:
                raise ValueError("Plane normal mismatch")
        if a["surface_type"]=="cylinder":
            if abs(analytic_a["radius"]-analytic_b["radius"])>.001 or math.dist(analytic_a["axis"]["closest_point_to_origin"],analytic_b["axis"]["closest_point_to_origin"])>.001:
                raise ValueError("Cylinder radius/axis mismatch")
        curved=[]
        if a["surface_type"] not in {"plane","cylinder"}:
            curved=[surface_check(source_faces[i],target),surface_check(target,source_faces[i])]
        rows.append({"native_ref":a["native_ref"],"face_id":fid,"candidate_count":1,
            "boundary_distance_mm":max(boundary,default=0),"bidirectional_surface":curved})
    return {"schema_version":"aicnc.generator-face-mapping/0.1","backend":"occt",
        "passed":True,"step_sha256":document.step_sha256,"face_id_namespace":document.face_id_namespace,
        "tolerances":TOLERANCES,"rows":rows,"adjacency_verified":True,"source_labels_used_for_matching":False}


def construct_and_import(recipe, step_path):
    if step_path.exists():raise FileExistsError("Refusing to overwrite generated STEP")
    local=make_local(recipe); labelled=source_labels(local,recipe)
    p=recipe["parameters"];r=rotation(p);tr=gp_Trsf()
    tr.SetValues(*[v for i in range(3) for v in [*r[i],p["translate_"+"xyz"[i]]]])
    transform=BRepBuilderAPI_Transform(local,tr,True);body=transform.Shape()
    faces=[topods.Face(transform.ModifiedShape(f)) for f,_ in labelled]
    descriptions=describe(faces)
    for row,(_,ls) in zip(descriptions,labelled):row["construction_labels"]=ls
    Interface_Static_SetCVal("write.step.unit","MM")
    writer=STEPControl_Writer()
    if writer.Transfer(body,STEPControl_AsIs)!=IFSelect_RetDone or writer.Write(str(step_path))!=IFSelect_RetDone:
        raise ValueError("STEP export failed")
    document=CadDocument.from_step(step_path)
    match=map_faces(faces,descriptions,document)
    a,b=volume(body),volume(document.body)
    if abs(a-b)>max(TOLERANCES["volume_absolute_mm3"],a*TOLERANCES["volume_relative"]):
        raise ValueError("Round-trip volume mismatch")
    if recipe["template_id"]=="loft_surface":
        top=[faces[i] for i,(_,ls) in enumerate(labelled) if ls]
        normals=[n for _,n in samples(top[0])]
        curvature=max(1-abs(normals[0].Dot(n)) for n in normals)
        if curvature<1e-4:raise ValueError("Surface representative is not genuinely curved")
        match["curved_top_normal_variation"]=curvature
    native={"backend":"occt","generator_version":VERSION,"nx_version":None,"faces":descriptions,
        "volume_mm3":a,"native_history_available":False}
    return document,native,match
