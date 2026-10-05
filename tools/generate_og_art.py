#!/usr/bin/env python3
"""Regenerates assets/og-art.svg, a decorative, non-interactive circuit
rendering of the real 104-vertex/208-edge graph. generate_og_card.py draws it
into the card; this module is also the drawing's own artifact.

The routing lives in pcb_layout.Layout, which /graph's figure shares. What is
decided here is only the card's dressing: the tight default spacing, one stroke
width and opacity for every cable, one circle for every node, no labels.
"""

import pathlib

from generate_graph import f
from pcb_layout import Layout

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og-art.svg"

# A fraction of the lattice pitch, so the lattice reads as line work rather
# than as solid bands
WIRE_W_U = 0.375
WIRE_OPACITY = 0.6
INK = "#192b46"

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
        f' opacity="{f(WIRE_OPACITY)}" stroke-linejoin="round">'
    )
    for u, w, pts in L.wires:
        out.append(path([L.positions[u], *pts, L.positions[w]]))
    out.append("</g>")

    out.append(f'<g fill="{INK}" stroke="none">')
    for x, y in L.positions.values():
        out.append(
            f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(L.pad / 2)}"/>'
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
