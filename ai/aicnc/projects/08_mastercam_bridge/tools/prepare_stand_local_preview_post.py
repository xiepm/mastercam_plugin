"""Build a source-bound 5 mm *toolpath preview* post, never a production post.

The vendor post is an external asset. Only the exact two reference-return
output statements in pretract are replaced; cutting motion blocks are retained.
The native project must bind this new file before native posting.
"""
import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = 'c7e22f33ddb5a63c930209fa03ec7a6d3430734c600970a4f72afd95ba9d3eb0'


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unsupported vendor post version')
    old = (b'      pbld, n$, sgabsinc, sgcode, *sg28ref, "Z0.", scoolant, e$\r\n'
           b'      if nextop$ = 1003 | tlchg_home, pbld, n$, *sg28ref, "X0.", "Y0.", e$')
    new = (b'      # AI-CNC LOCAL TOOLPATH PREVIEW ONLY - NOT MACHINE TOOLCHANGE\r\n'
           b'      absinc$ = zero\r\n'
           b'      pbld, n$, "G90", "G0", "Z5.", scoolant, e$')
    if source.count(old) != 1:
        raise ValueError('Expected one exact pretract block')
    source = source.replace(old, new)
    marker = b'      pbld, n$, *smetric, e$'
    if source.count(marker) != 1:
        raise ValueError('Expected one metric header')
    source = source.replace(marker, b'      "(SIMULATION ONLY - LOCAL 5MM TOOLPATH PREVIEW - NOT FOR MACHINE)", e$\r\n'+marker)
    return source


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('destination', type=Path)
    args = p.parse_args()
    output = build(args.source.read_bytes())
    with args.destination.open('xb') as f:
        f.write(output)
    print(hashlib.sha256(output).hexdigest(), args.destination)
