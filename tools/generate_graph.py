#!/usr/bin/env python3
"""Regenerates assets/graph-rail.svg, a circuit-board drawing of the graph
in deg4-dia4-n104.edges, for splicing into index.html's graph-rail block.
"""

import itertools
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "deg4-dia4-n104.edges"
OUT = ROOT / "assets" / "graph-rail.svg"
INDEX = ROOT / "index.html"

W, H = 125, 1240

BLOCKS = ["A", "B", "C"]
GRID_CY = {"A": 150, "B": 590, "C": 1030}
ROW_DY = 15
COL_DX = 15
GRID_CX = 40

# the connector corridor runs beside the grids; stations are threaded
# through the vertical gaps between blocks (free_gaps()) so nothing collides
CORRIDOR_X = 100
BLOCK_MARGIN = 22
NODE_R = 2.6  # one radius for every node: hub, port, and connector alike


def f(x):
    return f"{x:.2f}"


def parse_edges():
    """The 208 edges, in the order the record lists them. Vertices carry the
    labels the record itself uses: A.L1, A.R1, A.P11 inside a block, X01a and
    its partner X01b for a connector pair."""
    edges = []
    for line in DATA.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        u, v = line.split()
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
    """Connectors are X01a..X16b; every block vertex is qualified by its
    block, so C.L1 is block C's first L branch, not a connector."""
    return v[0] == "X"


def block_positions(block):
    """Every coordinate in a block -- hubs and ports alike -- lands on the
    same COL_DX/ROW_DY grid rooted at (GRID_CX, cy0)."""
    cy0 = GRID_CY[block]
    pos = {}
    for i in range(1, 5):
        pos[f"{block}.L{i}"] = (GRID_CX - COL_DX, cy0 + (i - 1) * ROW_DY)
    for j in range(1, 5):
        pos[f"{block}.R{j}"] = (GRID_CX + (j - 1) * COL_DX, cy0 + 4 * ROW_DY)
    for i in range(1, 5):
        for j in range(1, 5):
            pos[f"{block}.P{i}{j}"] = (
                GRID_CX + (j - 1) * COL_DX,
                cy0 + (i - 1) * ROW_DY,
            )
    return pos


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
        y0, y1 = cy0 - BLOCK_MARGIN, cy0 + 4 * ROW_DY + BLOCK_MARGIN
        gaps.append([prev_end, y0])
        prev_end = y1
    gaps.append([prev_end, H - 20])
    return gaps


def connector_positions(edges):
    """Y positions along the corridor: connectors spread evenly through the
    block gaps, in the order the record's matching edges name them (X01a,
    X01b, X02a, ...) so each matching edge is a short local hop and the rail
    reads top to bottom in pair order."""
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

    return {label: (CORRIDOR_X + CONNECTOR_DX, yy) for label, yy in y.items()}


def elbow_spur(x1, y1, corridor_x):
    """Station -> corridor: a plain straight run into the rail."""
    return f"M {f(x1)} {f(y1)} L {f(corridor_x)} {f(y1)}"


def is_row_hub(v):
    return ".L" in v


def row_segments(row_block_edges, port_edges, positions, corridor_x):
    """A row's hub trunk and its ports' corridor-bound spurs share the same
    physical line; drawn separately they'd double-draw the overlap (same
    bug as block_edge_segments). Merges them into disjoint segments, each
    carrying whichever of hub/far/ids identities apply.

    Returns pieces: (x1, y, x2, y, hub, far, ids) straight runs.
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

    pieces = []
    for y, ports in by_row.items():
        ports.sort(key=lambda t: t[0])
        hub = hub_by_y.get(y)
        boundary_xs = {x for x, _, _ in ports} | {corridor_x}
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
    return pieces


def build_svg():
    edges = parse_edges()
    positions = {}
    for b in BLOCKS:
        positions.update(block_positions(b))
    conn_pos = connector_positions(edges)
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
    row_pieces = row_segments(row_block_edges, port_edges, positions, CORRIDOR_X)

    out = [
        f'<svg class="gdiagram" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    ]

    # full-canvas hit target so pointermove tracks over empty space too, not just .ghit circles
    out.append(
        f'<rect class="grail-bg" x="0" y="0" width="{W}" height="{H}" fill="transparent"/>'
    )

    # backbone bus: same currentColor as every other edge, just a touch
    # brighter at rest since every signal runs through it
    out.append(
        f'<line class="grail-bus" x1="{CORRIDOR_X}" y1="20" x2="{CORRIDOR_X}" y2="{H - 20}" '
        f'stroke="currentColor" stroke-width="1.1" stroke-linecap="round" opacity="0.9"/>'
    )

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
        cy = positions[conn][1]
        py = positions[port][1]
        out.append(
            f'<line class="gedge" data-u="{conn}" data-w="{port}" data-rail="1" opacity="0" '
            f'x1="{CORRIDOR_X}" y1="{f(min(cy, py))}" x2="{CORRIDOR_X}" y2="{f(max(cy, py))}"/>'
        )
    out.append("</g>")

    # every vertex -- hub, port, or connector -- reads as one uniform filled square
    out.append('<g fill="currentColor" stroke="none">')
    for label, (x, y) in positions.items():
        out.append(
            f'<rect class="gnode" data-v="{label}" x="{f(x - NODE_R)}" y="{f(y - NODE_R)}" '
            f'width="{f(2 * NODE_R)}" height="{f(2 * NODE_R)}"/>'
        )
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


def splice_index(svg):
    """index.html carries the rail inline rather than referencing the asset,
    so it paints with the page. That copy has to be kept in step."""
    html = INDEX.read_text()
    spliced, n = re.subn(
        r'<svg class="gdiagram".*?</svg>', lambda _: svg, html, count=1, flags=re.DOTALL
    )
    assert n == 1, "no rail block in index.html"
    INDEX.write_text(spliced)


if __name__ == "__main__":
    svg = build_svg()
    OUT.write_text(svg)
    splice_index(svg)
    print("wrote", OUT, f"({len(svg)} bytes), spliced into", INDEX.name)
