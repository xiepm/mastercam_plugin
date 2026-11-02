"""Regenerate the public synthetic plate using the pinned P01 OCCT environment."""
from pathlib import Path
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.gp import gp_Ax2,gp_Pnt,gp_Dir
from OCC.Core.STEPControl import STEPControl_Writer,STEPControl_AsIs
from OCC.Core.IFSelect import IFSelect_RetDone

root=Path(__file__).resolve().parents[2]/'ai/samples/planning'
root.mkdir(parents=True,exist_ok=True)
part=BRepPrimAPI_MakeBox(30,20,5).Shape()
for x in (8,22):
    cutter=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,10,-1),gp_Dir(0,0,1)),2,7).Shape()
    part=BRepAlgoAPI_Cut(part,cutter).Shape()
writer=STEPControl_Writer();writer.Transfer(part,STEPControl_AsIs)
assert writer.Write(str(root/'plate.step'))==IFSelect_RetDone
print('Wrote synthetic 30 x 20 x 5 plate with two diameter-4 through holes')
