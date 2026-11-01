"""Independent closed-mesh material comparison using shared P01's implementation.

Run in the P01 OCCT/manifold environment. This is a faceted diagnostic, not
an exact STEP dimensional acceptance test. No seam welding or mesh repair.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'projects/01_cad_core/src'))
from cad_core.faceted_material_difference import solid, compare


def read_mesh(path):
    raw = path.read_bytes()
    if len(raw) < 84:
        raise ValueError('Binary STL header missing')
    count = struct.unpack_from('<I', raw, 80)[0]
    if count > 2000000 or len(raw) != 84 + 50 * count:
        raise ValueError('Invalid binary STL length/count')
    triangles = []
    for index in range(count):
        row = struct.unpack_from('<12fH', raw, 84 + 50 * index)
        triangles.append([list(row[j:j+3]) for j in (3, 6, 9)])
    shape, stats = solid(triangles, 2000000)
    return shape, dict(stats, sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('ipw', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    target, target_stats = read_mesh(args.target)
    ipw, ipw_stats = read_mesh(args.ipw)
    result = dict(method='P01_faceted_material_difference', exact_STEP_dimensional_acceptance=False,
                  target=target_stats, ipw=ipw_stats, volumes=compare(target, ipw))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
