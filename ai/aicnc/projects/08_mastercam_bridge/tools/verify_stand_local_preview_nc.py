"""Compare this bounded Stand preview with its native-posted reference NC.

This verifies a restricted NC delta, not machine suitability or collision freedom.
"""
import argparse
import hashlib
import re
from pathlib import Path


def blocks(path: Path) -> list[str]:
    return [re.sub(r'^N\d+\s*', '', line.strip())
            for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('(')]


def verify(reference: Path, preview: Path) -> str:
    results = ['SIMULATION ONLY: restricted native NC delta verification.']
    for name in ('S1-G54.nc', 'S2-G55.nc'):
        before, after = blocks(reference / name), blocks(preview / name)
        if before.count('G91 G28 Z0.') != 3 or before.count('G28 X0. Y0.') != 1:
            raise ValueError(f'{name}: unsupported reference returns')
        expected = ['G90 G0 Z5.' if b == 'G91 G28 Z0.' else b
                    for b in before if b != 'G28 X0. Y0.']
        if after != expected:
            raise ValueError(f'{name}: unexpected change outside reference returns')
        if any(re.search(r'\bG(?:28|30|53)(?:\D|$)', b) for b in after):
            raise ValueError(f'{name}: unexpected machine/reference move')
        z = [float(v) for b in after for v in re.findall(r'Z([-+]?\d*\.?\d+)', b)]
        if max(z) != 5:
            raise ValueError(f'{name}: unexpected Z maximum')
        digest = hashlib.sha256((preview / name).read_bytes()).hexdigest()
        results.append(f'{name}: PASS; only 3 G28 Z returns replaced and final G28 XY omitted; '
                       f'all other executable blocks identical; Z words [{min(z)}, {max(z)}]; SHA256={digest}')
    return '\n'.join(results) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('preview', type=Path)
    args = parser.parse_args()
    print(verify(args.reference, args.preview), end='')
