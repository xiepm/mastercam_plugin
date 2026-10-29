"""Strict public request contracts. Lengths use current document units; vectors are world coordinates unless stated."""
from typing import Annotated, Literal, Union, get_origin, get_args
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,strict=True)
    @model_validator(mode='before')
    @classmethod
    def exact_booleans(cls,value):
        if isinstance(value,dict):
            for name,field in cls.model_fields.items():
                t=field.annotation
                if t is bool or (get_origin(t) is Literal and all(type(x) is bool for x in get_args(t))):
                    if name in value and type(value[name]) is not bool:raise ValueError(name+' requires a JSON boolean')
        return value

Id=Annotated[int,Field(strict=True,gt=0)]
Ids=Annotated[list[Id],Field(min_length=1,max_length=100)]
Positive=Annotated[float,Field(gt=0)]
Nonnegative=Annotated[float,Field(ge=0)]

class Depth(Contract):
    Depth: float=Field(description='Depth in tool-plane coordinates; interpreted according to Incremental.')
    Incremental: bool
    DetachAssociativeDepth: bool=Field(description='Explicitly permit removing existing depth association.')

class ExistingTool(Contract):
    ExistingSlot: Id=Field(description='Internal slot from mc_inspect; not the displayed tool number.')
    Diameter: Positive
    Kind: Literal['FlatEndMill','ChamferMill']
    TipAngleDegrees: Nonnegative=0
    CreateIfMissing: Literal[False]=False
    @model_validator(mode='after')
    def actual_chamfer_angle(self):
        if self.Kind=='ChamferMill' and not 0<self.TipAngleDegrees<180:
            raise ValueError('ChamferMill requires the actual TipAngle from mc_inspect, strictly between 0 and 180 degrees')
        return self

class Cutting(Contract):
    Feed: Positive
    Plunge: Positive
    Retract: Positive
    Rpm: Id
    ConfirmOriginalFeedMode: Literal[True]=Field(description='True only after confirming feed-per-minute/revolution mode and user-supplied values. Does not convert feed mode.')

class Finish(Contract):
    Tool: ExistingTool
    Cutting: Cutting
    Compensation: Literal['Computer','Control','Wear','ReverseWear']
    Side: Literal['Left','Right']
    UseDepthCuts: bool
    MaximumStepDown: Nonnegative

class Chamfer(Contract):
    Tool: ExistingTool
    Cutting: Cutting
    Compensation: Literal['Computer','Control','Wear','ReverseWear']
    Side: Literal['Left','Right']
    Width: Positive
    ToolTipOffset: Nonnegative
    ChamferDepth: Nonnegative

class Pocket(Contract):
    Name: str=Field(min_length=1,max_length=50)
    Metric: bool
    ToolSlot: Id
    ToolDiameter: Positive
    Strategy: Literal['HighSpeed','ConstantOverlapSpiral','TrueSpiral']
    Climb: bool
    StepOver: Positive
    StepDown: Positive
    WallStock: Nonnegative
    FloorStock: Nonnegative
    Tolerance: Positive
    MinimizeBurial: bool
    SpiralOut: bool
    Trochoid: Literal['Off','FullMaterialOnly','EntirePocket']
    LoopRadius: Nonnegative
    LoopSpacing: Nonnegative
    SmoothingRadius: Nonnegative
    Entry: Literal['Helix','Ramp']
    EntryMinimum: Positive
    EntryMaximum: Positive
    EntryAngle: Annotated[float,Field(gt=0,lt=90)]
    EntryClearanceXY: Nonnegative
    EntryClearanceZ: Nonnegative
    Clearance: float
    Retract: float
    FeedPlane: float
    Top: float
    Bottom: float
    Feed: Positive
    Plunge: Positive
    RetractFeed: Positive
    Rpm: Id
    ReviewedCuttingData: Literal[True]

class Vector(Contract):
    x:float
    y:float
    z:float

class MeshParameters(Contract):
    mesh_tolerance:Positive
    weld_tolerance:Positive
    @model_validator(mode='after')
    def tolerance_order(self):
        if self.weld_tolerance>self.mesh_tolerance:raise ValueError('weld_tolerance must not exceed mesh_tolerance')
        return self

class Sections(MeshParameters):
    origin:Vector
    normal:Vector
    count:Annotated[int,Field(strict=True,ge=1,le=200)]
    spacing:Nonnegative
    mesh_tolerance:Positive
    weld_tolerance:Positive

class Draft(MeshParameters):
    pull:Vector
    threshold_degrees:Annotated[float,Field(gt=0,lt=90)]
    mesh_tolerance:Positive
    weld_tolerance:Positive
    transition_edges:bool
    normal_glyphs:bool
    glyph_length:Nonnegative
    maximum_glyphs:Annotated[int,Field(strict=True,ge=0,le=10000)]

class Request(Contract):
    expected_document:str=Field(min_length=1,description='Exact saved active .mcam path returned by mc_inspect. No file is opened or saved by this tool.')
    @model_validator(mode='after')
    def unique_ids(self):
        for key in ('operation_ids','solid_ids'):
            values=getattr(self,key,[])
            if len(values)!=len(set(values)):raise ValueError(key+' must contain unique IDs')
        return self

class DepthRequest(Request):
    action:Literal['operation.depth']
    operation_ids:Ids
    parameters:Depth
class FinishRequest(Request):
    action:Literal['operation.finish']
    operation_ids:Ids
    parameters:Finish
class ChamferRequest(Request):
    action:Literal['operation.chamfer']
    operation_ids:Ids
    parameters:Chamfer
class PocketRequest(Request):
    action:Literal['hsm.pocket']
    reference_id:Id
    parameters:Pocket
class SectionsRequest(Request):
    action:Literal['mp.sections']
    solid_ids:Ids
    output_level:Annotated[int,Field(strict=True,ge=1,le=2000000000)]
    parameters:Sections
class DraftRequest(Request):
    action:Literal['mp.draft']
    solid_ids:Ids
    output_level:Annotated[int,Field(strict=True,ge=1,le=2000000000)]
    parameters:Draft

ChangeRequest=Annotated[Union[DepthRequest,FinishRequest,ChamferRequest,PocketRequest,SectionsRequest,DraftRequest],Field(discriminator='action')]
