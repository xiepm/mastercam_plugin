"""Validate this source-bound stand's manual 3-axis setup correction.

Consumes readback; never changes a CAM document or grants production release.
"""
import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_native(data):
    require(data.get('ok') is True, 'Native readback failed')
    require('MILL 3 - AXIS VMC MM.mcam-mmd' in data['machine_name'], 'Wrong machine')
    require(data['stock']['size'] == [18, 18, 10] and data['stock']['origin'] == [0, 0, 10], 'Stock changed')
    names=['S1_external','S1_through','S1_top_chamfer','S2_counterbore',
           'S2_blind_14','S2_blind_16','S2_blind_18','S2_blind_20','S2_bottom_chamfer']
    require([o['name'] for o in data['operations']] == names, 'Operation count/order changed')
    ids=[]
    groups=[]
    for i,o in enumerate(data['operations']):
        s=0 if i<3 else 1
        sign=1 if s==0 else -1
        require(not o['dirty'], 'Dirty toolpath')
        require(o['group_name']==['装夹1_正面_3道','装夹2_翻面_6道'][s], 'Wrong toolpath group')
        require(o['program']==1001+s and o['top']==0 and o['depth']<=0, 'Incorrect setup-local heights/program')
        for field in ['wcs','tool_plane','construction_plane']:
            v=o[field]
            require(v['name']==['S1_TOP_G54','S2_FLIP_G55'][s], 'Wrong setup plane')
            require(v['origin']==[0,0,10 if s==0 else 0], 'Wrong setup origin')
            require([v['x'],v['y'],v['z']]==[[1,0,0],[0,sign,0],[0,0,sign]], 'Not the required fixed 3-axis frame')
            require(v['work_offset']==s, 'Wrong work offset')
            require(v['id']==o['wcs']['id'], 'Tilted tool relative to setup WCS')
        ids.append(o['wcs']['id']);groups.append(o['group_id'])
    require(len(set(ids[:3]))==len(set(ids[3:]))==1 and ids[0]!=ids[3], 'Setups share WCS')
    require(len(set(groups[:3]))==len(set(groups[3:]))==1 and groups[0]!=groups[3], 'Setups share group')
    require(len(data['view_sheets'])==2, 'Two setup views required')
    for i,v in enumerate(data['view_sheets']):
        require(v['name']==['装夹1_正面_G54','装夹2_翻面_G55'][i], 'View labels did not persist')
        require(v['has_bookmark'], 'View bookmark missing')
        require(all(v[f]==ids[0 if i==0 else 3] for f in ['wcs_id','tool_plane_id','construction_plane_id','graphics_plane_id']), 'View is not aligned with setup')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt',type=Path)
    p.add_argument('model',type=Path)
    a=p.parse_args()
    n=json.loads(a.receipt.read_text(encoding='utf-8-sig'))
    validate_native(n)
    require(n['model_sha256']==digest(a.model), 'Model changed after native readback')
    print('PASS: 3-axis machine, 3+6 groups, independent aligned frames and persisted views')
