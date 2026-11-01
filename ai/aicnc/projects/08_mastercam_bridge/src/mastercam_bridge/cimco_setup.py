"""CIMCO sidecar interchange for source-bound, three-axis software trials.

This does not post NC, run CIMCO, emulate a controller, or grant machine release.
The text grammar was round-tripped through CIMCO Edit 2026.01.02 Save Setup.
"""
from __future__ import annotations

import math
import re
import struct
from pathlib import Path


def _number(value, *, positive=False):
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('Finite positive dimension required' if positive else 'Nonfinite number')
    return format(value, '.12g')


def _quoted(value):
    value = str(value)
    if any(c in value for c in '\"\r\n\0'):
        raise ValueError('Unsupported quotation/control character')
    return '"' + value + '"'


def tool_lines(tool):
    """Map a native Mastercam tool; reject unsupported geometry instead of defaulting."""
    kinds = {'EndMill': 'END MILL', 'Drill': 'DRILL', 'ChamferMill': 'CHAMFER MILL'}
    kind = kinds[tool['ToolTypeID']]
    number = tool['Number']
    if type(number) is not int or number < 1 or tool['IsMetric'] is not True:
        raise ValueError('Positive tool number and native metric tool required')
    if tool['LengthOffset'] != number:
        raise ValueError('This bounded adapter requires matching T/H numbers')
    if tool.get('CornerRadius', 0) != 0 or tool.get('TaperLength', 0) != 0:
        raise ValueError('Rounded/tapered assembly requires another geometry mapping')
    keys = {'BL': 'Length', 'D': 'Diameter', 'FL': 'FluteLength',
            'AD': 'ShankDia', 'SD': 'ShoulderDia', 'SL': 'ShoulderLength'}
    params = ' '.join(k + _number(tool[v], positive=True) for k, v in keys.items())
    if not 0 < tool['FluteLength'] <= tool['ShoulderLength'] <= tool['Length']:
        raise ValueError('Invalid flute/shoulder/body lengths')
    if kind == 'END MILL':
        params += ' CD0 CR0 EMCT=FEM TL0'
    elif kind == 'DRILL':
        if not 0 < tool['TipAngle'] < 180:
            raise ValueError('Invalid drill included angle')
        params += ' AT' + _number(tool['TipAngle']) + ' TL0'
    else:
        if not 0 < tool['TipAngle'] < 90:
            raise ValueError('Invalid chamfer half angle')
        tip = tool['MillToolAttributes']['TipDia']
        if not 0 < tip < tool['Diameter']:
            raise ValueError('Invalid chamfer tip diameter')
        params += ' A' + _number(tool['TipAngle']) + ' TD' + _number(tip) + ' CHTYPE=CHTYPESA'
    hd = _number(tool['HolderDia'], positive=True)
    hl = _number(tool['HolderLength'], positive=True)
    return [f'TOOL {number} {_quoted(kind)} HOLDER={number} COMMENT={_quoted(tool["Name"])} '
            + params + ' CPI=T8 IS=B US=UM',
            f'HOLDER BEGIN {number} "SIMULATION_ONLY_NATIVE_CYLINDER" UM',
            f'{hd}, {hd}, {hl}', 'HOLDER END']


def setup_text(tools, target, work_offset, *, stock_bounds=None, stock_stl=None):
    """All meshes must already be in this setup's right-handed local frame."""
    if work_offset not in range(54, 60):
        raise ValueError('Only G54..G59 supported')
    if (stock_bounds is None) == (stock_stl is None):
        raise ValueError('Exactly one explicit stock source required')
    lines = [f'WORKPIECE ID1 {_quoted(target)} X0 Y0 Z0 A0 B0 C0 UM']
    if stock_stl is not None:
        lines += [f'STOCK STL X0 Y0 Z0 A0 B0 C0 UM PATH={_quoted(stock_stl)} RGB=180,180,180']
    else:
        low, high = stock_bounds
        if len(low) != 3 or len(high) != 3 or any(a >= b for a, b in zip(low, high)):
            raise ValueError('Invalid stock bounds')
        for name, point in [('MIN', low), ('MAX', high)]:
            lines += [f'STOCK {name} ' + ' '.join(a + _number(v) for a, v in zip('XYZ', point))
                      + ' RGB=180,180,180 UM']
    lines += [f'WCS ID{work_offset-53} X0 Y0 Z0 A0 B0 C0 UM',
              'WCS ID-1 X0 Y0 Z0 A0 B0 C0 UM']
    numbers = set()
    for tool in tools:
        if tool['Number'] in numbers:
            raise ValueError('Duplicate tool number')
        numbers.add(tool['Number'])
        lines.extend(tool_lines(tool))
    if not numbers:
        raise ValueError('Tools required')
    return '\n'.join(lines) + '\n'


def transform_binary_stl(data, rotation, translation):
    """Rigid frame change; no vertex repair, resampling, scaling, or seam welding.

    CIMCO emits NaN normals on some degenerate facets. Recompute only such
    normals from the unchanged vertices (zero for exactly zero-area facets).
    This does not repair a nonmanifold mesh or establish geometric acceptance.
    """
    r, t = rotation, translation
    if len(r) != 3 or any(len(row) != 3 for row in r) or len(t) != 3:
        raise ValueError('Expected 3x3 rotation and 3-vector translation')
    if not all(math.isfinite(x) for x in [*t, *(v for row in r for v in row)]):
        raise ValueError('Nonfinite transform')
    for i in range(3):
        for j in range(3):
            if abs(sum(r[i][k]*r[j][k] for k in range(3)) - int(i == j)) > 1e-9:
                raise ValueError('Rotation must be orthonormal')
    det = sum(r[0][i]*(r[1][(i+1)%3]*r[2][(i+2)%3]-r[1][(i+2)%3]*r[2][(i+1)%3]) for i in range(3))
    if abs(det - 1) > 1e-9:
        raise ValueError('Reflection forbidden: setup frame must be right-handed')
    if len(data) < 84:
        raise ValueError('Truncated binary STL')
    n = struct.unpack_from('<I', data, 80)[0]
    if not 0 < n <= 2000000 or len(data) != 84 + 50*n:
        raise ValueError('Invalid binary STL count/length')
    out = bytearray(data)
    for i in range(n):
        for k in range(4):
            offset = 84 + 50*i + 12*k
            v = struct.unpack_from('<fff', data, offset)
            if not all(math.isfinite(x) for x in v):
                if k:
                    raise ValueError('Nonfinite STL vertex')
                verts = struct.unpack_from('<9f', data, 84 + 50*i + 12)
                if not all(math.isfinite(x) for x in verts):
                    raise ValueError('Nonfinite STL vertex')
                a = [verts[3+j]-verts[j] for j in range(3)]
                b = [verts[6+j]-verts[j] for j in range(3)]
                v = [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
                length = math.sqrt(sum(x*x for x in v))
                if length:
                    v = [x/length for x in v]
            result = [sum(row[j]*v[j] for j in range(3)) + (t[a] if k else 0) for a, row in enumerate(r)]
            struct.pack_into('<fff', out, offset, *result)
    return bytes(out)


def check_nc_scope(text, work_offset, operation_names, tool_numbers):
    """Structural gate for this simple posted subset, NOT a G-code interpreter."""
    clean = re.sub(r'\([^()]*\)', '', text.upper())
    if '(' in clean or ')' in clean or '#' in clean:
        raise ValueError('Nested comments/macros not supported by this gate')
    words = re.findall(r'([A-Z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))', clean)
    gs = [float(v) for k, v in words if k == 'G']
    ms = [float(v) for k, v in words if k == 'M']
    if any(k in 'ABC' for k, _ in words):
        raise ValueError('Rotary-axis words forbidden in manual 3-axis setup')
    if {g for g in gs if 54 <= g < 60} != {work_offset}:
        raise ValueError('Mixed or missing work offsets; post each setup independently')
    if 21 not in gs or 20 in gs or 90 not in gs or 30 not in ms or any(m in ms for m in (98, 99)):
        raise ValueError('Expected standalone metric absolute program with M30')
    actual = re.findall(r'^\s*\(\s*(S[12]_[A-Z0-9_]+)\s*\)\s*$', text.upper(), re.M)
    if actual != [x.upper() for x in operation_names]:
        raise ValueError('Native posted operation order differs')
    if {int(v) for k, v in words if k == 'T'} != set(tool_numbers):
        raise ValueError('Posted tool set differs from native readback')
    if {int(v) for k, v in words if k == 'H'} != set(tool_numbers):
        raise ValueError('Posted H offset set differs from supported tool mapping')


def verify_tool_readback(text, tools):
    """Check native Save Setup semantics, allowing CIMCO ordering/default spelling."""
    for tool in tools:
        expected = tool_lines(tool)
        number = tool['Number']
        matches = re.findall(rf'^TOOL {number} (.+)$', text, re.M)
        if len(matches) != 1:
            raise ValueError(f'Missing/duplicate tool {number}')
        row = matches[0]
        if row.split('"')[1] != expected[0].split('"')[1] or f'HOLDER={number} ' not in row:
            raise ValueError(f'Tool {number} type/holder mismatch')
        for key in ['BL','D','FL','AD','SL'] + (['AT'] if tool['ToolTypeID']=='Drill' else ['A','TD'] if tool['ToolTypeID']=='ChamferMill' else ['SD']):
            pattern = rf'(?:^|\s){key}([+-]?[\d.]+)(?=\s|$)'
            a = re.search(pattern, expected[0]); b = re.search(pattern, row)
            if not a or not b or not math.isclose(float(a[1]), float(b[1]), abs_tol=1e-8):
                raise ValueError(f'Tool {number} {key} mismatch')
        holder = re.search(rf'^HOLDER BEGIN {number} [^\r\n]+\r?\n([^\r\n]+)\r?\nHOLDER END', text, re.M)
        if not holder or [float(v.strip()) for v in holder[1].split(',')] != [tool['HolderDia'],tool['HolderDia'],tool['HolderLength']]:
            raise ValueError(f'Holder {number} mismatch')
