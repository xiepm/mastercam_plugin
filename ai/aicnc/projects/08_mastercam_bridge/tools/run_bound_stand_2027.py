"""CLI for the explicit source-bound profile in P08's existing executor."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from mastercam_bridge.plan_simulation import execute_bound_stand_2027
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--label',required=True);p.add_argument('--mode',choices=['create','reopen'],required=True);a=p.parse_args()
execute_bound_stand_2027(a.directory,a.label,a.mode)
