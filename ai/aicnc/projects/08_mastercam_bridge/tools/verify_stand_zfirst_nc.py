"""Check native Stand NC against the prior local5mm output, byte-independent.

Allows only the requested tool-start changes, including the optional complete
first point; this does not validate
implicit M6 motions or fixture clearance on a real machine.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def blocks(path):
    # Native files use the Windows codepage in comments. Executable words are ASCII.
    text = path.read_bytes().decode('latin1')
    return [re.sub(r'^N\d+\s*', '', s.strip()) for s in text.splitlines()
            if s.strip() and not s.lstrip().startswith(('(', 'O'))]


def verify(reference, actual, expected_starts, full_initial_point=False):
    before, after = blocks(reference), blocks(actual)
    expected, changes = [], []
    i = 0
    while i < len(before):
        m = re.fullmatch(r'(G0 G90 (?:G17 )?G5[45]) (X\S+ Y\S+) (S\S+ M3)', before[i])
        if m:
            if i + 1 >= len(before) or not re.fullmatch(r'G43 H\d+ Z5\.', before[i+1]):
                raise ValueError('Unsupported compensated tool start')
            if full_initial_point and not changes:
                h, z = before[i+1].rsplit(' ', 1)
                new = [m[1] + ' ' + h + ' ' + m[2] + ' ' + z + ' ' + m[3]]
            else:
                new = [m[1] + ' ' + before[i+1] + ' ' + m[3], m[2]]
            expected.extend(new)
            changes.append({'before': before[i:i+2], 'after': new})
            i += 2
        else:
            expected.append(before[i])
            i += 1
    if len(changes) != expected_starts or expected != after:
        raise ValueError('Unexpected executable NC change or tool-start count')
    if any(re.search(r'\bG(?:28|30|53|92)(?=\s|$)', line) for line in after):
        raise ValueError('Unexpected reference return or coordinate reset')
    z = [float(v) for line in after for v in re.findall(r'Z([-+]?\d*\.?\d+)', line)]
    if max(z) != 5:
        raise ValueError('Unexpected explicit Z maximum')
    return {'scope': 'NC explicit commands only; M6 machine motions not bounded',
            'native_file': str(actual), 'sha256': hashlib.sha256(actual.read_bytes()).hexdigest(),
            'tool_start_pairs_reordered': changes,
            'all_other_executable_blocks_identical': True,
            'z_word_range': [min(z), max(z)],
            'g28_g30_g53_g92_absent': True,
            'm6_retained': sum(bool(re.search(r'\bM0?6$', line)) for line in after)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path)
    p.add_argument('actual', type=Path)
    p.add_argument('--tool-starts', type=int, required=True)
    p.add_argument('--full-initial-point', action='store_true')
    args = p.parse_args()
    print(json.dumps(verify(args.reference, args.actual, args.tool_starts, args.full_initial_point), indent=2))
