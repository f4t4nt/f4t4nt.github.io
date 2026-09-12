#!/usr/bin/env python3
"""Regenerates assets/graph-rail.svg, a circuit-board drawing of the graph
in n104-deg4-dia4.edges, for splicing into index.html's graph-rail block.
"""

import itertools
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "tools" / "n104-deg4-dia4.edges"
OUT = ROOT / "assets" / "graph-rail.svg"

W, H = 125, 1240
BEND = 4.0  # one consistent elbow radius for every spur -> corridor junction

BLOCKS = ["0", "1", "2"]
GRID_CY = {"0": 150, "1": 590, "2": 1030}
ROW_DY = 15
COL_DX = 15
GRID_CX = 40

# the connector corridor runs beside the grids; stations are threaded
# through the vertical gaps between blocks (free_gaps()) so nothing collides
CORRIDOR_X = 100
BLOCK_MARGIN = 22
CHIP_PAD = 13  # outline margin around the grid; stays inside BLOCK_MARGIN


def f(x):
    return f"{x:.2f}"


def decode_vertex(n):
    """Inverse of the id scheme documented atop n104-deg4-dia4.edges."""
    if n < 24:
        block, off = str(n // 8), n % 8
        return f"{block}.L{off + 1}" if off < 4 else f"{block}.R{off - 3}"
    if n < 72:
        block, off = str((n - 24) // 16), (n - 24) % 16
        return f"{block}.P{off // 4 + 1}{off % 4 + 1}"
    return f"M{n:03d}"


def parse_edges():
    edges = []
    for line in DATA.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        u, v = (decode_vertex(int(n)) for n in line.split())
        edges.append((u, v))
    assert len(edges) == 208, len(edges)
    deg = {}
    for u, v in edges:
        deg[u] = deg.get(u, 0) + 1
        deg[v] = deg.get(v, 0) + 1
    assert len(deg) == 104, len(deg)
    assert set(deg.values()) == {4}, set(deg.values())
    return edges


def is_conn(v):
    return v[0] == "M"


def block_positions(block):
    cy0 = GRID_CY[block]
    pos = {}
    for i in range(1, 5):
        pos[f"{block}.L{i}"] = (GRID_CX - 16, cy0 + (i - 1) * ROW_DY)
    for j in range(1, 5):
        pos[f"{block}.R{j}"] = (GRID_CX + (j - 1) * COL_DX, cy0 + 3 * ROW_DY + 16)
    for i in range(1, 5):
        for j in range(1, 5):
            pos[f"{block}.P{i}{j}"] = (
                GRID_CX + (j - 1) * COL_DX,
                cy0 + (i - 1) * ROW_DY,
            )
    return pos


def chip_outline(block):
    """Bounding box of a block's grid, padded into an IC-style package footprint."""
    cy0 = GRID_CY[block]
    x0, x1 = GRID_CX - 16 - CHIP_PAD, GRID_CX + 3 * COL_DX + 9
    y0, y1 = cy0 - CHIP_PAD, cy0 + 3 * ROW_DY + 16 + CHIP_PAD
    return x0, y0, x1, y1


def block_edge_segments(edges, positions):
    """Slices each hub's 4 spokes into disjoint segments (cut at each port)
    so a dim spoke never paints over a bright onpath one where they'd
    otherwise overlap. Returns (x1, y1, x2, y2, hub, far_ports) per segment.
    """
    bundles = {}
    for u, v in edges:
        hub, port = (v, u) if ".P" in u else (u, v)
        bundles.setdefault(hub, []).append(port)

    segments = []
    for hub in sorted(bundles):
        hx, hy = positions[hub]
        ports = sorted(
            bundles[hub],
            key=lambda p: (positions[p][0] - hx) ** 2 + (positions[p][1] - hy) ** 2,
        )
        points = [(hx, hy)] + [positions[p] for p in ports]
        for k in range(len(ports)):
            x1, y1 = points[k]
            x2, y2 = points[k + 1]
            segments.append((x1, y1, x2, y2, hub, ports[k:]))
    return segments


# stations sit left of the corridor, offset to land flush with the grids'
# rightmost (R/P4) column
CONNECTOR_DX = -(CORRIDOR_X - (GRID_CX + 3 * COL_DX))


def free_gaps():
    """Vertical bands with no grid block, top to bottom -- connectors are
    threaded through these so they never collide with a block."""
    gaps = []
    prev_end = 20
    for b in BLOCKS:
        cy0 = GRID_CY[b]
        y0, y1 = cy0 - BLOCK_MARGIN, cy0 + 3 * ROW_DY + 16 + BLOCK_MARGIN
        gaps.append([prev_end, y0])
        prev_end = y1
    gaps.append([prev_end, H - 20])
    return gaps


def connector_positions(edges):
    """Y positions along the corridor: connectors spread evenly through the
    block gaps, ordered to match the file's matching-edge pairs (72 74, then
    73 75, then 76 78, ...) so each matching edge is a short local hop and
    the rail reads top to bottom in that same pairing order."""
    labels = []
    seen = set()
    for u, v in edges:
        if is_conn(u) and is_conn(v):
            for label in (u, v):
                if label not in seen:
                    seen.add(label)
                    labels.append(label)

    gaps = free_gaps()
    lengths = [max(0.0, e - s) for s, e in gaps]
    total = sum(lengths)
    n = len(labels)
    counts = [round(n * l / total) for l in lengths]
    while sum(counts) < n:
        counts[lengths.index(max(lengths))] += 1
    while sum(counts) > n:
        counts[counts.index(max(counts))] -= 1

    y = {}
    it = iter(labels)
    for (s, e), c in zip(gaps, counts):
        for k in range(c):
            y[next(it)] = s + (k + 0.5) * (e - s) / c

    positions = {label: (CORRIDOR_X + CONNECTOR_DX, yy) for label, yy in y.items()}
    order = sorted(positions, key=lambda label: positions[label][1])
    return positions, order


def elbow_spur(x1, y1, corridor_x):
    """Station -> corridor as an orthogonal run with one BEND-sized
    45-degree chamfer, matching how real board routing turns a corner."""
    direction = 1 if corridor_x > x1 else -1
    elbow_x = corridor_x - direction * BEND
    return f"M {f(x1)} {f(y1)} L {f(elbow_x)} {f(y1)} L {f(corridor_x)} {f(y1 + BEND)}"


def is_row_hub(v):
    return ".L" in v


def row_segments(row_block_edges, port_edges, positions, corridor_x):
    """A row's hub trunk and its ports' corridor-bound spurs share the same
    physical line; drawn separately they'd double-draw the overlap (same
    bug as block_edge_segments). Merges them into disjoint segments, each
    carrying whichever of hub/far/ids identities apply.

    Returns (pieces, tails): pieces are (x1, y, x2, y, hub, far, ids)
    straight runs; tails are (row_y, far) shared corridor-elbow curves.
    """
    hub_ports = {}
    for u, v in row_block_edges:
        hub, port = (v, u) if ".P" in u else (u, v)
        hub_ports.setdefault(hub, []).append(port)
    hub_by_y = {positions[hub][1]: hub for hub in hub_ports}

    by_port = {}
    for conn, port in port_edges:
        by_port.setdefault(port, []).append(conn)

    by_row = {}
    for port, conns in by_port.items():
        x, y = positions[port]
        by_row.setdefault(y, []).append((x, port, conns))

    def far_list(owners):
        far = set()
        for port, conns in owners:
            for conn in conns:
                far.add(conn)
                far.add(port)
        return sorted(far)

    elbow_x = corridor_x - BEND
    pieces = []
    tails = []
    for y, ports in by_row.items():
        ports.sort(key=lambda t: t[0])
        hub = hub_by_y.get(y)
        boundary_xs = {x for x, _, _ in ports} | {elbow_x}
        if hub is not None:
            boundary_xs.add(positions[hub][0])
        xs = sorted(boundary_xs)
        for a, b in itertools.pairwise(xs):
            if b - a < 1e-6:
                continue
            spur_owners = [(port, conns) for x, port, conns in ports if x <= a + 1e-9]
            ids = far_list(spur_owners) if spur_owners else None
            far = (
                sorted(p for p in hub_ports[hub] if positions[p][0] >= b - 1e-9)
                if hub is not None
                else None
            )
            if not far:
                far = None
            pieces.append((a, y, b, y, hub if far else None, far, ids))
        tails.append((y, far_list([(port, conns) for _, port, conns in ports])))
    return pieces, tails


def build_svg():
    edges = parse_edges()
    positions = {}
    for b in BLOCKS:
        positions.update(block_positions(b))
    conn_pos, order = connector_positions(edges)
    positions.update(conn_pos)

    block_edges, match_edges, port_edges = [], [], []
    for u, v in edges:
        cu, cv = is_conn(u), is_conn(v)
        if not cu and not cv:
            block_edges.append((u, v))
        elif cu and cv:
            match_edges.append((u, v))
        else:
            conn, port = (u, v) if cu else (v, u)
            port_edges.append((conn, port))

    row_block_edges = [
        (u, v) for u, v in block_edges if is_row_hub(v if ".P" in u else u)
    ]
    col_block_edges = [
        (u, v) for u, v in block_edges if not is_row_hub(v if ".P" in u else u)
    ]
    row_pieces, row_tails = row_segments(
        row_block_edges, port_edges, positions, CORRIDOR_X
    )

    out = [
        f'<svg class="gdiagram" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    ]

    # full-canvas hit target so pointermove tracks over empty space too, not just .ghit circles
    out.append(
        f'<rect class="grail-bg" x="0" y="0" width="{W}" height="{H}" fill="transparent"/>'
    )

    # backbone bus: bright at rest (every signal runs through it), but still
    # dims on hover like any other edge
    out.append(
        f'<line class="grail-bus" x1="{CORRIDOR_X}" y1="20" x2="{CORRIDOR_X}" y2="{H - 20}" '
        f'stroke="var(--ink-lit)" stroke-width="1.1" stroke-linecap="round" opacity="0.9"/>'
    )

    # faint package outline + pin-1 dot per block, so each grid reads as a component
    out.append('<g stroke="currentColor" fill="none" stroke-width="0.9" opacity="0.3">')
    for b in BLOCKS:
        x0, y0, x1, y1 = chip_outline(b)
        out.append(
            f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(x1 - x0)}" height="{f(y1 - y0)}" rx="3"/>'
        )
        out.append(
            f'<circle cx="{f(x0 + 3.4)}" cy="{f(y0 + 3.4)}" r="1.3" fill="currentColor" stroke="none"/>'
        )
    out.append("</g>")

    def ids_attrs(far):
        return f'data-ids="{",".join(far)}"'

    # thick spokes: column hubs plus row pieces that still carry a hub
    # identity, so the shared stretch reads as one trunk
    out.append('<g stroke="currentColor" fill="none" stroke-width="1.3">')
    for x1, y1, x2, y2, hub, far in block_edge_segments(col_block_edges, positions):
        out.append(
            f'<line class="gedge" data-hub="{hub}" data-far="{",".join(far)}" opacity="0.85" '
            f'x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}"/>'
        )
    for x1, y1, x2, y2, hub, far, ids in row_pieces:
        if hub is None:
            continue
        attrs = f'data-hub="{hub}" data-far="{",".join(far)}"'
        if ids is not None:
            attrs += " " + ids_attrs(ids)
        out.append(
            f'<line class="gedge" {attrs} opacity="0.85" x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}"/>'
        )
    out.append("</g>")

    # opacity lives per-element, not on the wrapping <g> -- a group opacity
    # would cap every child, including an onpath one CSS pushes to 1
    out.append(
        '<g stroke="currentColor" fill="none" stroke-width="1.3" stroke-linecap="round">'
    )
    for conn, port in port_edges:
        x1, y1 = positions[conn]
        if abs(x1 - CORRIDOR_X) > 1e-6:
            out.append(
                f'<path class="gedge" data-u="{conn}" data-w="{port}" opacity="0.85" d="{elbow_spur(x1, y1, CORRIDOR_X)}"/>'
            )

    # row pieces past the row's own farthest port: pure spur, no hub trunk to merge with
    for x1, y1, x2, y2, hub, far, ids in row_pieces:
        if hub is not None:
            continue
        out.append(
            f'<line class="gedge" {ids_attrs(ids)} opacity="0.85" x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}"/>'
        )
    for row_y, far in row_tails:
        elbow_x = CORRIDOR_X - BEND
        d = f"M {f(elbow_x)} {f(row_y)} L {f(CORRIDOR_X)} {f(row_y + BEND)}"
        out.append(f'<path class="gedge" {ids_attrs(far)} opacity="0.85" d="{d}"/>')
    out.append("</g>")

    out.append('<g stroke="currentColor" fill="none" stroke-width="1.3">')
    for u, v in match_edges:
        x1, y1 = positions[u]
        x2, y2 = positions[v]
        out.append(
            f'<line class="gedge" data-u="{u}" data-w="{v}" opacity="0.85" x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}"/>'
        )
    out.append("</g>")

    # corridor trunk: invisible at rest, lit only when onpath, so a hovered
    # edge's highlight reads as one continuous path across the gaps between spurs
    out.append(
        '<g stroke="currentColor" fill="none" stroke-width="1.1" stroke-linecap="round">'
    )
    for conn, port in port_edges:
        cy = positions[conn][1] + BEND
        py = positions[port][1] + BEND
        out.append(
            f'<line class="gedge" data-u="{conn}" data-w="{port}" data-rail="1" opacity="0" '
            f'x1="{CORRIDOR_X}" y1="{f(min(cy, py))}" x2="{CORRIDOR_X}" y2="{f(max(cy, py))}"/>'
        )
    out.append("</g>")

    # hubs carry no port identity of their own, just a layer hop, so they read as small filled vias
    out.append('<g fill="currentColor" stroke="none">')
    for label, (x, y) in positions.items():
        if not is_conn(label) and ".P" not in label:
            out.append(
                f'<circle class="gnode" data-v="{label}" cx="{f(x)}" cy="{f(y)}" r="1.6"/>'
            )
    out.append("</g>")

    # every named pin reads as a square pad, the via/pad distinction from real board silkscreen
    def pad(label, x, y, half, stroke_w):
        return f'<rect class="gnode" data-v="{label}" x="{f(x - half)}" y="{f(y - half)}" width="{f(2 * half)}" height="{f(2 * half)}" rx="{f(half * 0.32)}" stroke-width="{stroke_w}"/>'

    out.append('<g fill="var(--paper)" stroke="currentColor" stroke-width="1.1">')
    for label, (x, y) in positions.items():
        if not is_conn(label) and ".P" in label:
            out.append(pad(label, x, y, 2.4, 1.1))
    out.append("</g>")

    out.append('<g fill="var(--paper)" stroke="currentColor" stroke-width="1.1">')
    for label in order:
        x, y = positions[label]
        out.append(pad(label, x, y, 1.9, 1.1))
    out.append("</g>")

    # invisible, larger hit-targets layered on top so hover works without shrinking the drawn dots
    out.append('<g class="ghit-layer">')
    for label, (x, y) in positions.items():
        out.append(
            f'<circle class="ghit" data-v="{label}" cx="{f(x)}" cy="{f(y)}" r="5.5" fill="transparent"/>'
        )
    out.append("</g>")

    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    svg = build_svg()
    OUT.write_text(svg)
    print("wrote", OUT, f"({len(svg)} bytes)")
