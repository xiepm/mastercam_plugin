"""Build a bounded Stand preview post with compensated Z before later XY moves.

Consumes the hash-bound local5mm external post. This is not a T7 machine post:
M6 controller/machine motion is retained and cannot be bounded by G-code Z5.
--full-initial-point emits XYZ/H together at program start so a relative
backplot has a defined first point; it is not a real machine approach strategy.
"""
import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = '6c826288062aff6f1252482a4dfebd3e84480c4b424739c4aca6f3e135adce49'


def build(source: bytes, full_initial_point: bool = False) -> bytes:
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unsupported local5mm source post')
    for plane in (b'', b'*sgplane, '):
        old = (b'      pcan1, pbld, n$, *sgcode, *sgabsinc, ' + plane
               + b'pwcs, pfxout, pfyout,\r\n'
               b'        [if nextdc$ <> 7, *speed, *spindle], pgear, strcantext, e$\r\n'
               b'      pbld, n$, sg43, *tlngno$, pfzout, pscool, pstagetool, e$')
        new = (b'      # AI-CNC: establish compensated local clearance before XY\r\n'
               b'      pcan1, pbld, n$, *sgcode, *sgabsinc, ' + plane
               + b'pwcs, sg43, *tlngno$, pfzout,\r\n'
               b'        [if nextdc$ <> 7, *speed, *spindle], pgear, strcantext, e$\r\n'
               b'      pbld, n$, pfxout, pfyout, pscool, pstagetool, e$')
        if source.count(old) != 1:
            raise ValueError('Expected one exact tool start block')
        if not plane and full_initial_point:
            new = (b'      # AI-CNC: complete first compensated tool-tip point for relative backplot\r\n'
                   b'      pcan1, pbld, n$, *sgcode, *sgabsinc, pwcs, sg43, *tlngno$, pfxout, pfyout, pfzout,\r\n'
                   b'        [if nextdc$ <> 7, *speed, *spindle], pgear, strcantext, pscool, pstagetool, e$')
        source = source.replace(old, new)
    return source


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--full-initial-point', action='store_true')
    args = parser.parse_args()
    output = build(args.source.read_bytes(), args.full_initial_point)
    with args.destination.open('xb') as stream:
        stream.write(output)
    print(hashlib.sha256(output).hexdigest(), args.destination)
