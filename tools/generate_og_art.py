#!/usr/bin/env python3
"""Regenerates assets/og-art.svg, a decorative, non-interactive circuit
rendering of the real 104-vertex/208-edge graph. generate_og_card.py draws it
into the card; this module is also the drawing's own artifact.

The routing lives in pcb_layout.Layout, which /graph's figure shares. What is
decided here is only the card's dressing: the tight default spacing, one stroke
width and opacity for every cable, one square for every node, no labels.
"""

import pathlib

from generate_graph import f
from pcb_layout import Layout

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og-art.svg"

# a quarter of the lattice pitch, so the lattice reads as line work rather
# than as solid bands
WIRE_W_U = 0.25
WIRE_OPACITY = 0.5
INK = "#181a1e"

L = Layout()
W, H = L.W, L.H

# The staircase spans exactly two connector pitches, from the column's right
# face out to the last tread. Asserted rather than arranged -- at the card's
# spacing nothing is free to make it come out, so if it ever misses, a knob has
# moved.
assert L.match_bus_x0 + L.match_span - (L.conn_x + L.U) == 2 * L.conn_dy, (
    "staircase off band"
)


def path(points):
    head, rest = points[0], points[1:]
    d = f"M {f(head[0])} {f(head[1])}" + "".join(f" L {f(x)} {f(y)}" for x, y in rest)
    return f'<path d="{d}"/>'


def build_art():
    out = []
    out.append(
        f'<g fill="none" stroke="{INK}"'
        f' stroke-width="{f(WIRE_W_U * L.U)}"'
        f' opacity="{f(WIRE_OPACITY)}">'
    )
    for _u, _w, pts in L.wires:
        out.append(path(pts))
    out.append("</g>")

    out.append(f'<g fill="{INK}" stroke="none">')
    for x, y in L.positions.values():
        out.append(
            f'<rect x="{f(x - L.U)}" y="{f(y - L.U)}"'
            f' width="{f(L.pad)}" height="{f(L.pad)}"/>'
        )
    out.append("</g>")

    return "\n".join(out)


if __name__ == "__main__":
    markup = build_art()
    svg = (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{markup}</svg>'
    )
    OUT.write_text(svg)
    print("wrote", OUT, f"({len(svg)} bytes)")
