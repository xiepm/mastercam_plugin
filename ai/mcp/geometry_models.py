"""Typed MP/X+ contracts; imported after common model definitions."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from models import Contract, Request, Vector, UnitVector, Id, Ids, Positive, Nonnegative

Color=Annotated[int,Field(ge=1,le=255)]
class EntityRequest(Request):
    entity_ids:Ids
    @model_validator(mode='after')
    def unique_entities(self):
        if len(self.entity_ids)!=len(set(self.entity_ids)):raise ValueError('entity_ids must be unique')
        return self
class EdgeParameters(Contract):
    mode:Literal['Edges3D','ProjectWorldXY']
    output_level:Id
    output_z:float
    tolerance:Positive
    color:Color
class EdgesRequest(Request):
    action:Literal['mp.edges']
    source_id:Id
    parameters:EdgeParameters
class Empty(Contract):pass
class NormalsRequest(EntityRequest):
    action:Literal['mp.reverse_normals']
    parameters:Empty
class SurfaceTypes(Contract):
    types:Annotated[list[str],Field(min_length=1,max_length=30)]
class SurfaceRequest(Request):
    action:Literal['mp.select_surface_types']
    parameters:SurfaceTypes
class RadiusParameters(Contract):
    kinds:Annotated[list[Literal['Cylinder','Sphere','TorusMinor','TorusMajor','ConeReference']],Field(min_length=1,max_length=5)]
    minimum:Nonnegative
    maximum:Positive
    @model_validator(mode='after')
    def interval(self):
        if self.maximum<self.minimum or len(set(self.kinds))!=len(self.kinds):raise ValueError('Invalid radius interval/kinds')
        return self
class RadiusRequest(Request):
    action:Literal['mp.select_radius']
    solid_ids:Ids
    parameters:RadiusParameters
class SvgOptions(Contract):
    Scale:Positive
    OffsetX:float
    OffsetY:float
    Z:float
    FlipY:bool
    ChordTolerance:Positive
    Level:Id
    Color:Color
    MaxSegments:Annotated[int,Field(ge=1,le=20000)]
class SvgRequest(Request):
    action:Literal['xplus.svg']
    svg_xml:Annotated[str,Field(min_length=1,max_length=1000000)]
    parameters:SvgOptions
class Point2(Contract):
    x:float
    y:float
class SketchMachining(Contract):
    Name:Annotated[str,Field(min_length=1,max_length=60)]
    Feed:Positive
    Plunge:Positive
    Rpm:Id
    Top:float
    FeedPlane:float
    Retract:float
    Clearance:float
    Regenerate:bool
class SketchParameters(Contract):
    depth:float
    diameter:Annotated[float,Field(ge=.01,le=500)]
    level:Id
    color:Color
    chains:Annotated[list[Annotated[list[Point2],Field(min_length=2,max_length=10001)]],Field(min_length=1,max_length=100)]
    machining:SketchMachining|None
    existing_tool_slot:Id|None
    @model_validator(mode='after')
    def mode(self):
        if (self.machining is None)!=(self.existing_tool_slot is None):raise ValueError('Machining and existing tool slot must both be supplied, or both null')
        if sum(len(c)-1 for c in self.chains)>10000:raise ValueError('At most 10000 segments')
        return self
class SketchRequest(Request):
    action:Literal['xplus.sketch']
    plane_id:Id
    parameters:SketchParameters
class FixtureParameters(Contract):
    reference:Vector
    target:Vector
    translation:Vector
    world_z_degrees:int
    @model_validator(mode='after')
    def quarter_turn(self):
        if self.world_z_degrees not in (0,90,180,270,-90,-180,-270):raise ValueError('World Z rotation must be a quarter turn')
        return self
class FixtureRequest(EntityRequest):
    action:Literal['xplus.fixture_copy']
    parameters:FixtureParameters
class AxisGrid(Contract):
    Label:Annotated[str,Field(min_length=1,max_length=16)]
    Direction:UnitVector
    MinimumDegrees:float
    MaximumDegrees:float
    StepDegrees:Positive
class FitParameters(Contract):
    tilt:AxisGrid
    rotary:AxisGrid
    tolerance_degrees:Annotated[float,Field(ge=0,le=1)]
    maximum_candidates:Annotated[int,Field(ge=1,le=1000000)]
    name_prefix:Annotated[str,Field(min_length=1,max_length=24)]
    reuse_matching:bool
    activate:bool
class FitRequest(Request):
    action:Literal['xplus.fit_plane']
    plane_id:Id
    parameters:FitParameters
class SetupParameters(Contract):
    all_operations:bool
    include_screenshot:bool
class SetupRequest(Request):
    action:Literal['xplus.setup_sheet']
    parameters:SetupParameters
class StlParameters(Contract):
    tolerance:Annotated[float,Field(gt=0,le=1)]
class StlRequest(Request):
    action:Literal['xplus.levels_to_stl']
    parameters:StlParameters
class CaptureParameters(Contract):
    show_view_axes:bool
    show_wcs_axes:bool
class CaptureRequest(Request):
    action:Literal['xplus.capture']
    parameters:CaptureParameters
class GradientParameters(Contract):
    option:Literal['Off','Horizontal','Vertical','Diagonal']
class GradientRequest(Request):
    action:Literal['xplus.gradient']
    parameters:GradientParameters
class ElectrodeReference(Contract):
    entity_id:Id
    label:Annotated[str,Field(min_length=1,max_length=120)]
    source:Literal['Unspecified','UserWorldCoordinate','SelectedLineStart']
    world_coordinate:Vector|None
    user_c_degrees:float|None
class ElectrodeParameters(Contract):
    title:Annotated[str,Field(min_length=1,max_length=120)]
    precision:Annotated[int,Field(ge=0,le=8)]
    references:Annotated[list[ElectrodeReference],Field(max_length=100)]
class ElectrodeRequest(EntityRequest):
    action:Literal['xplus.electrode_report']
    plane_id:Id
    parameters:ElectrodeParameters

class GeometryCopyParameters(Contract):
    command:Literal['CenterXY','CenterXYZ','RotateX90','RotateY90','RotateZ90','AlignCplane','PaintZPlanes','PaintVerticalPlanes','DimensionBounds','MergeCurves','AssignLevel']
    destination:Vector
    quarter_turns:Annotated[int,Field(ge=-4,le=4)]
    color:Color
    level:Id
    angle_tolerance:Positive
    curve_tolerance:Annotated[float,Field(gt=0,le=1)]
    text_height:Positive
    dimension_offset:Positive
    decimals:Annotated[int,Field(ge=0,le=6)]
    @model_validator(mode='after')
    def nonzero_turn(self):
        if self.quarter_turns==0:raise ValueError('quarter_turns must be nonzero')
        return self
class GeometryCopyRequest(EntityRequest):
    action:Literal['geometry.copy_edit']
    parameters:GeometryCopyParameters
class HolderSection(Contract):
    TopDiameter:Positive
    BottomDiameter:Positive
    Height:Positive
class HolderParameters(Contract):
    Name:Annotated[str,Field(min_length=1,max_length=64)]
    Metric:bool
    Sections:Annotated[list[HolderSection],Field(min_length=1,max_length=128)]
class HolderRequest(Request):
    action:Literal['xplus.holder_library']
    parameters:HolderParameters
class ChainSelectionRequest(Request):
    action:Literal['xplus.select_operation_chains']
    operation_ids:Ids
    parameters:Empty
class WorkOffsetParameters(Contract):
    number:Annotated[int,Field(ge=0,le=32767)]
class WorkOffsetRequest(Request):
    action:Literal['xplus.work_offset']
    plane_id:Id
    parameters:WorkOffsetParameters
class NciName(Contract):
    operation_id:Id
    name:Annotated[str,Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')]
class NciParameters(Contract):
    names:Annotated[list[NciName],Field(min_length=1,max_length=100)]
    @model_validator(mode='after')
    def unique(self):
        if len({n.operation_id for n in self.names})!=len(self.names):raise ValueError('Duplicate operation IDs')
        return self
class NciRequest(Request):
    action:Literal['xplus.rename_nci']
    parameters:NciParameters

GEOMETRY_REQUESTS=(EdgesRequest,NormalsRequest,SurfaceRequest,RadiusRequest,SvgRequest,SketchRequest,FixtureRequest,FitRequest,SetupRequest,StlRequest,CaptureRequest,GradientRequest,ElectrodeRequest,GeometryCopyRequest,HolderRequest,ChainSelectionRequest,WorkOffsetRequest,NciRequest)
