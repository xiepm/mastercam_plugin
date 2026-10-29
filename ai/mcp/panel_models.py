"""Parameter contracts extracted from the remaining interactive workflows."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from models import Contract, Request, Vector, Id, Ids, Positive, Nonnegative

class StageCutting(Contract):
    Feed:Positive
    Plunge:Positive
    Retract:Positive
    Rpm:Id
    NativeFeedModeReviewed:Literal[True]
class StageTool(Contract):
    Slot:Id
    Kind:Literal['CenterDrill','SpotDrill','Drill','CounterBore','CounterSink','TapRH']
    Diameter:Positive
    LengthOffset:Annotated[int,Field(ge=0,le=32767)]
    DiameterOffset:Annotated[int,Field(ge=0,le=32767)]
class TapTarget(Contract):
    MachineGroupId:Id
    MachineName:Annotated[str,Field(min_length=1,max_length=512)]
    PostName:Annotated[str,Field(min_length=1,max_length=2048)]
    ExplicitFeedReviewed:Literal[True]
class DrillStage(Contract):
    Name:Annotated[str,Field(min_length=1,max_length=80)]
    Purpose:Literal['Center','Drill','Counterbore','Chamfer','Tap']
    Cycle:Literal['Drill','PeckDrill','ChipBreak','Tap']
    Sorting:Literal['SelectionOrder','XPlusYPlus','ZBidirectionalPlusCounterclockwise']
    Tool:StageTool
    Cutting:StageCutting
    Depth:float
    Clearance:float
    Retract:float
    FeedPlane:float
    Peck1:Nonnegative
    Peck2:Nonnegative
    PeckClearance:Nonnegative
    ChipBreak:Nonnegative
    Dwell:Nonnegative
    ThreadPitch:Nonnegative
    TapTarget:TapTarget|None
    @model_validator(mode='after')
    def tap_contract(self):
        if self.Purpose=='Tap':
            if self.Cycle!='Tap' or self.Tool.Kind!='TapRH' or self.ThreadPitch<=0 or self.TapTarget is None:
                raise ValueError('Tap requires RH tool, Tap cycle, explicit pitch and live target')
        elif self.Cycle=='Tap' or self.Tool.Kind=='TapRH' or self.ThreadPitch!=0 or self.TapTarget is not None:
            raise ValueError('Tap-only fields are not allowed on other stages')
        return self
class DrillSet(Contract):
    name:Annotated[str,Field(min_length=1,max_length=80)]
    reference_id:Id
    local_points:Annotated[list[Vector],Field(min_length=1,max_length=10000)]
    top:float
    stages:Annotated[list[DrillStage],Field(min_length=1,max_length=5)]
class DrillParameters(Contract):
    sets:Annotated[list[DrillSet],Field(min_length=1,max_length=100)]
class DrillingRequest(Request):
    action:Literal['drilling.stages','drilling.tap']
    parameters:DrillParameters
    @model_validator(mode='after')
    def mode(self):
        taps=[s for h in self.parameters.sets for s in h.stages if s.Purpose=='Tap']
        if (self.action=='drilling.tap')!=bool(taps):raise ValueError('Use drilling.tap for chains containing tapping')
        if sum(len(h.local_points)*len(h.stages) for h in self.parameters.sets)>20000:raise ValueError('Request exceeds 20000 stage-points')
        return self
class ConvexBoundaryParameters(Contract):
    origin:Vector
    depth:float
    tolerance:Annotated[float,Field(ge=1e-9,le=.01)]
    output_level:Id
    clockwise:bool
class ConvexBoundaryRequest(Request):
    action:Literal['geometry.convex_boundary']
    source_id:Id
    parameters:ConvexBoundaryParameters
class MiddleParameters(Contract):
    enabled:bool
    maximum_click_milliseconds:Annotated[int,Field(ge=100,le=600)]
class MiddleRequest(Request):
    action:Literal['interface.middle_confirm']
    parameters:MiddleParameters

class ParameterEdit(Contract):
    feed:Positive|None
    spindle:Id|None
    wall:Nonnegative|None
    floor:Nonnegative|None
    @model_validator(mode='after')
    def nonempty(self):
        if all(x is None for x in (self.feed,self.spindle,self.wall,self.floor)):raise ValueError('Choose at least one parameter')
        return self
class ParameterRequest(Request):
    action:Literal['operation.parameters']
    operation_ids:Ids
    parameters:ParameterEdit
class PlaneEdit(Contract):
    plane_id:Id
class PlaneEditRequest(Request):
    action:Literal['operation.planes']
    operation_ids:Ids
    parameters:PlaneEdit
class CopyParameters(Contract):
    target_group_id:Id
class CopyRequest(Request):
    action:Literal['operation.copy']
    operation_ids:Ids
    parameters:CopyParameters
class GroupCreateParameters(Contract):
    parent_id:Id
    prefix:Annotated[str,Field(min_length=1,max_length=40)]
    start:Annotated[int,Field(ge=0,le=999799)]
    count:Annotated[int,Field(ge=1,le=200)]
class GroupCreateRequest(Request):
    action:Literal['groups.create']
    parameters:GroupCreateParameters
class GroupName(Contract):
    group_id:Id
    name:Annotated[str,Field(min_length=1,max_length=60,pattern=r'^[^\x00-\x1f]+$')]
class GroupRenameParameters(Contract):
    names:Annotated[list[GroupName],Field(min_length=1,max_length=100)]
    @model_validator(mode='after')
    def unique(self):
        if len(set(x.group_id for x in self.names))!=len(self.names):raise ValueError('Duplicate group IDs')
        return self
class GroupRenameRequest(Request):
    action:Literal['groups.rename']
    parameters:GroupRenameParameters
class StockParameters(Contract):
    machine_group_id:Id
    size:Vector
    origin:Vector
    anchor:Annotated[str,Field(min_length=1,max_length=50)]
    plane_id:Id
    @model_validator(mode='after')
    def dimensions(self):
        if min(self.size.x,self.size.y,self.size.z)<=0:raise ValueError('Stock dimensions must be positive')
        return self
class StockRequest(Request):
    action:Literal['stock.rectangle']
    parameters:StockParameters
class ViewParameters(Contract):
    wcs_id:Id
    construction_id:Id
    tool_id:Id
    graphics_id:Id
    cplane_follows_graphics:bool
    cplane_follows_wcs:bool
    graphics_follows_wcs:bool
class ViewRequest(Request):
    action:Literal['view.planes']
    parameters:ViewParameters

class ChainParameters(Contract):
    expected_chain_count:Annotated[int,Field(ge=1,le=100)]
    require_closed:bool
    mode:Literal['add','replace']
class ChainsRequest(Request):
    action:Literal['selection.chains']
    entity_ids:Ids
    parameters:ChainParameters
class EdgeChamferParameters(Contract):
    edge_tags:Ids
    distance:Positive
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.edge_tags))!=len(self.edge_tags):raise ValueError('Duplicate edge tags')
        return self
class EdgeChamferRequest(Request):
    action:Literal['geometry.chamfer_edges']
    source_id:Id
    parameters:EdgeChamferParameters
class MaterialInput(Contract):
    Id:Annotated[str,Field(min_length=1,max_length=80)]
    Name:Annotated[str,Field(min_length=1,max_length=1000)]
    Density:Annotated[float,Field(gt=0,le=100)]
    PricePerKg:Annotated[float,Field(ge=0,le=1000000000)]
    Currency:Annotated[str,Field(min_length=1,max_length=16)]
    Reference:Annotated[str,Field(min_length=1,max_length=10000)]
class StockInput(Contract):
    Id:Annotated[str,Field(min_length=1,max_length=80)]
    Name:Annotated[str,Field(min_length=1,max_length=1000)]
    MaterialId:Annotated[str,Field(min_length=1,max_length=80)]
    Shape:Literal['长方体','圆棒','圆管']
    Unit:Literal['mm','inch']
    X:Positive
    Y:Positive
    Z:Nonnegative
    AddX:Nonnegative
    AddY:Nonnegative
    AddZ:Nonnegative
    Quantity:Annotated[int,Field(ge=1,le=100000000)]
class MaterialParameters(Contract):
    material:MaterialInput
    stock:StockInput
    @model_validator(mode='after')
    def material_link(self):
        if self.stock.MaterialId!=self.material.Id:raise ValueError('Stock MaterialId must match material Id')
        return self
class MaterialRequest(Request):
    action:Literal['materials.estimate']
    parameters:MaterialParameters
class ExportParameters(Contract):
    include_geometry:bool
class ExportRequest(Request):
    action:Literal['operations.export']
    operation_ids:Ids
    parameters:ExportParameters
class ImportParameters(Contract):
    path:Annotated[str,Field(min_length=1,max_length=2048)]
    sha256:Annotated[str,Field(pattern=r'^[A-Fa-f0-9]{64}$')]
    library_operation_ids:Ids
    target_group_id:Id
    include_geometry:Literal[False]
    set_views_to_current:bool
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.library_operation_ids))!=len(self.library_operation_ids):raise ValueError('Duplicate library operation IDs')
        return self
class ImportRequest(Request):
    action:Literal['operations.import']
    parameters:ImportParameters

PANEL_REQUESTS=(DrillingRequest,ConvexBoundaryRequest,MiddleRequest,ParameterRequest,PlaneEditRequest,CopyRequest,GroupCreateRequest,GroupRenameRequest,StockRequest,ViewRequest,ChainsRequest,EdgeChamferRequest,MaterialRequest,ExportRequest,ImportRequest)
