#!/usr/bin/env python3
"""Builds a decorative, non-interactive circuit rendering of the real
104-vertex/208-edge graph for use as og-card background art.

Everything sits on one lattice of pitch U. Every cable runs along a lattice
line, so any two adjacent parallel cables anywhere in the drawing -- inside a
block, in a corridor, in the channel, horizontal or vertical -- are exactly U
apart. There is no second spacing: no per-family fan pitch, no sub-pitch nudge
to separate cables that would otherwise coincide. Where cables are further
apart than U it is because the drawing is empty in between.

U is an eighth of the connector pitch -- the spacing of the 32-node column down
the right -- and every named distance in the layout is a whole number of those
pitches, so the blocks, the channel and the column all keep step with each
other and there is never a fraction of a lattice line to round away.

The figure reads left to right: the three blocks stacked in a column, then the
port channel the 96 port-connector cables run through, then the 32 connectors
in a single column down the right, then the match staircase beside it. The
blocks are registered against that connector column rather than spaced to
taste, which is what the block heights and corridors below are solving for.

One lattice works only because a node is a square pad of side 2U rather than a
point. A pad has nine lattice points on its boundary, so the four cables of a
degree-4 vertex each land on their own one and the routing never has to invent
a small offset to pull them apart. Cables approach a pad head-on, through the
middle or the corner of a face, the way a trace meets a pad on a board.

Within a block the four cables that have to cross a row (or a column) nest:
the one travelling furthest rides on the outermost lane, so its step onto that
lane always happens where the inner lanes have not started yet. The one with
nothing to cross needs no lane at all and goes straight in through the face.

The 96 port-connector edges are channel-routed: each is a port-side lane -> a
straight run out to its own vertical track -> the track -> the connector's
face, and tracks are assigned by first-fit interval packing (pack_tracks)
rather than one track per edge, so a track is reused by every edge whose span
doesn't overlap another occupant's. They are additionally split into two
directional bands (by whether the edge runs to a higher- or lower-y connector),
each packed by its own lower endpoint, mirroring how the reference PCB channel
keeps same-direction nets together. On the port side each port sends one of its
two connector edges out along its own row and drops the other into the corridor
below it, so no bundle anywhere is wider than four cables. The block rows'
outbound lanes and the connectors' inbound faces are kept off each other by
reserving disjoint residues mod 8U (see the lane plan), so the two families
cannot be colinear no matter which edge goes where.

The 16 connector-connector match edges get the opposite treatment. They would
pack onto two tracks -- each spans only two connector slots -- but they are the
one part of the graph whose structure is worth being able to read off the
picture, so each is given its own track, one lattice line further right than
the edge above it. Because the matching pairs slots two apart, the risers come
in two sizes, which is what makes it read as a staircase rather than as a fan.

Every stroke shares one width/opacity and every node is the same square. Every
path is built from axis-aligned steps only (no diagonal segments anywhere).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from generate_graph import f, is_conn, is_row_hub, parse_edges

BLOCKS = ["0", "1", "2"]
N_CONN = 32

CONN_DY = 64  # THE unit of the drawing: the connector pitch. Its absolute
              # value is free -- the card scales the art to fit -- and is only
              # picked large enough for an eighth of it to stay whole.

U = CONN_DY // 8  # THE lattice pitch. Every coordinate in the drawing is an
                  # integer multiple of it, so it is both the distance between
                  # adjacent cables and the resolution of the whole layout.
PAD = 2 * U  # every node -- hub, port, connector -- is this square, centred
             # exactly on the node's lattice point. One U each side of centre
             # gives a face three lattice points wide, which is what lets a
             # degree-4 vertex give each of its cables its own landing point.

NODE_D = 2 * CONN_DY   # the port grid's node pitch; the grid is square
HUB_GAP = 1 * CONN_DY  # how far an L or R hub stands off the port grid
FRAME = 2 * CONN_DY    # air between the ink and the page edge, the same on all
                       # four sides. The page is sized from the frame rather
                       # than the frame fitted into a chosen page.
MARGIN = FRAME + PAD // 2  # the first node in from any edge is a pad, and a pad
                           # reaches half its width past its own lattice point

BLOCK_H = 3 * NODE_D + HUB_GAP    # a block's top row down to its R-hub row
CONN_H = (N_CONN - 1) * CONN_DY   # the first connector down to the last

# The three blocks are registered against the connector column rather than
# stacked at some chosen spacing: every block row lands on a connector row, the
# two corridors are equal, and block 1's centre line is the column's. The last
# of those is not a third constraint -- the blocks are equal, so equal corridors
# and equal end room already centre the stack.
#
# The end room is the point of the arrangement. A row's three L-spoke lanes
# ride 7 to 9 lattice lines ABOVE it, so block 0's top row cannot itself sit on
# the first connector: its spokes would be drawn off the top of the page.
# HEAD_ROW is the standoff that gives them somewhere to go.
#
# The pieces have to fill the column exactly, 3*BLOCK_H + 2*GAP_ROW + 2*HEAD_ROW
# == CONN_H, and the corridors and the end room both come in pairs, so BLOCK_H
# has to be odd in pitches -- which makes the hub standoff odd, BLOCK_H being
# three node pitches plus the standoff. At a standoff of one that leaves ten
# pitches to split, and 3 + 2 is the split that clears the spokes without
# letting the blocks close up on each other.
GAP_ROW = 3 * CONN_DY   # from one block's R-hub row to the next block's top row
HEAD_ROW = 2 * CONN_DY  # from the first connector down to block 0's top row
assert 3 * BLOCK_H + 2 * GAP_ROW + 2 * HEAD_ROW == CONN_H, "stack does not fill"

H = MARGIN + CONN_H + MARGIN  # the column is the tallest thing on the page
CONN_Y0 = MARGIN
GRID_CX = MARGIN + HUB_GAP  # the left-most node is an L hub, a standoff outside
GRID_CY = {  # the port grid, so the grid itself starts one standoff further in
    b: CONN_Y0 + HEAD_ROW + i * (BLOCK_H + GAP_ROW) for i, b in enumerate(BLOCKS)
}
BLOCK_RIGHT = GRID_CX + 3 * NODE_D + HUB_GAP
assert GRID_CY["1"] + BLOCK_H // 2 == CONN_Y0 + CONN_H // 2, "middle block off centre"
assert all((y - CONN_Y0) % CONN_DY == 0 for y in GRID_CY.values()), "block off column"

# --- The lane plan, in lattice steps from the node the lane belongs to. ---
#
# Two families of long horizontal run share the channel: the eight cables a
# block row sends out to the right, and the three cables each connector takes
# in on its left face. Nothing about the two is coordinated, so they are kept
# off each other by residue rather than by inspection, the way the reference
# board separates its gutters from its pin drops.
#
# Block rows sit at whole multiples of 8U from the top (HEAD_ROW, NODE_D,
# HUB_GAP and GAP_ROW all are), as do connector rows, so a connector's left-face
# lines are always at -1, 0, +1 from a multiple of 8U. Reserving those three
# residues for connectors makes the two families provably never colinear:
# whatever a block row's y, its outbound lanes come from the other five.
#
# A row pitch is sixteen lattice lines and three residues in every eight are
# spoken for, which leaves ten usable against the twelve the plan needs. The
# two that do not fit are L-spoke lanes -- and an L-spoke lane is exactly the
# one kind that may sit on a reserved residue, since it never leaves its block
# and so can never meet a connector approach. So all three go there, and the
# eight lanes that do reach the channel take the free lines:
#
#   +1        the row's own pad edge                  (connector residue)
#   +2        where an R-spoke turns in under its port
#   +3..+6    this row's four C row-exit lanes
#   +7..+9    the next row's three L-spoke lanes      (connector residues)
#   +10       clear
#   +11..+14  this row's four C col-exit lanes
#   +15..+17  the next row's pad edge                 (connector residues)
LANE_L = (None, -7, -8, -9)   # L-spoke lane by port column; column 0 has no
                              # pad to cross and goes straight in through the
                              # port's left face instead
LANE_R = (-4, -3, -2, None)   # R-spoke lane by port row; row 3 is the one
                              # nearest its hub and goes straight up
LANE_XR = (6, 5, 4, 3)        # C row-exit lane by port column
LANE_XC = (14, 13, 12, 11)    # C col-exit lane by port column
R_TURN = 2      # how far under a row an R-spoke turns in towards its port
EXIT_STEP = 2   # how far right of a port a C row-exit steps before dropping

# the deepest lane above a row is an L-spoke's, and block 0's top row has only
# HEAD_ROW between it and the top of the page for all three of them
assert HEAD_ROW > -min(n for n in LANE_L if n) * U, "no room for block 0's spokes"

TRACK_GAP = 2 * U  # clearance along a shared track between two edges on it --
                   # one empty lattice line, as in the reference channel
BAND_GAP = 2       # empty tracks between the channel's two directional bands
CHANNEL_GAP = 2 * CONN_DY  # air on each side of the port channel: the same to
                           # the blocks on its left as to the column on its right
MATCH_STEP = U             # one tread of the match staircase
MATCH_BAND = 2 * CONN_DY   # what the whole staircase spans, from the column's
                           # right face out to the last tread. Asserted below
                           # rather than arranged -- nothing is free to make it
                           # come out, so if it ever misses, a knob has moved.

WIRE_W = U / 4  # a quarter of the pitch, so the lattice reads as line work
                # rather than as solid bands
WIRE_OPACITY = 0.5

INK = "#181a1e"


def block_positions(block):
    """The 24 nodes of one block: a 4x4 port grid, an L hub one standoff left of
    each row, and an R hub one standoff below each column."""
    cy0 = GRID_CY[block]
    rows = [cy0 + i * NODE_D for i in range(4)]
    cols = [GRID_CX + j * NODE_D for j in range(4)]
    pos = {f"{block}.L{i + 1}": (GRID_CX - HUB_GAP, y) for i, y in enumerate(rows)}
    pos.update({f"{block}.R{j + 1}": (x, rows[3] + HUB_GAP) for j, x in enumerate(cols)})
    pos.update({f"{block}.P{i + 1}{j + 1}": (x, y)
                for i, y in enumerate(rows) for j, x in enumerate(cols)})
    return pos


def port_col(port):
    """Which of the four columns a port label sits in -- "1.P34" -> 3."""
    return int(port.split(".", 1)[1][2]) - 1


def connector_order(edges):
    """Every connector label, first-seen order along match edges, sorted --
    just a stable assignment of the 32 labels to the 32 column slots."""
    labels, seen = [], set()
    for u, v in edges:
        if is_conn(u) and is_conn(v):
            for label in (u, v):
                if label not in seen:
                    seen.add(label)
                    labels.append(label)
    assert len(labels) == N_CONN, f"expected {N_CONN} connectors, found {len(labels)}"
    labels.sort()
    return labels


def classify(edges):
    row_hub_ports, col_hub_ports = {}, {}
    port_conn, match_edges = [], []
    for u, v in edges:
        cu, cv = is_conn(u), is_conn(v)
        if cu and cv:
            match_edges.append((u, v))
        elif cu or cv:
            conn, port = (u, v) if cu else (v, u)
            port_conn.append((conn, port))
        else:
            hub, port = (v, u) if ".P" in u else (u, v)
            bucket = row_hub_ports if is_row_hub(hub) else col_hub_ports
            bucket.setdefault(hub, []).append(port)
    return row_hub_ports, col_hub_ports, port_conn, match_edges


def pack_tracks(ids, lo, hi, key, gap):
    """First-fit interval packing on a shared 1-D axis: process ids in
    `key` order, placing each on the first existing track whose occupied
    intervals all clear it by `gap`, else opening a new track. Two ids
    sharing a track never overlap, so far fewer tracks are needed than
    ids -- this is what makes the bus read as densely, deliberately
    cabled rather than one permanent track per edge. Processed by lower
    endpoint, first-fit uses exactly the channel's density, which is the
    fewest tracks any packing could use."""
    tracks = []
    lane_of = {}
    for i in sorted(ids, key=key):
        for t, occ in enumerate(tracks):
            if all(hi[i] + gap <= a or b + gap <= lo[i] for a, b in occ):
                occ.append((lo[i], hi[i]))
                lane_of[i] = t
                break
        else:
            tracks.append([(lo[i], hi[i])])
            lane_of[i] = len(tracks) - 1
    return lane_of, len(tracks)


def split_port_exits(port_conn, positions):
    """Every port has exactly two connector edges, and sending both off to the
    right along the port's own row would make a row's outbound cables an
    eight-wide ribbon. So give a port's two edges two different exits: one
    leaves through the right face and runs out along the row, the other leaves
    through the bottom corner and drops into the corridor below the row. The
    rule is the same at every port, so every outbound bundle is four cables.
    Which edge takes which is decided by the connector it is heading for: the
    higher one keeps the row, the lower one takes the drop, so the edge that
    leaves downward is also the one that is going downward."""
    by_port = {}
    for e in port_conn:
        by_port.setdefault(e[1], []).append(e)
    kind = {}
    for es in by_port.values():
        es.sort(key=lambda e: positions[e[0]][1])
        for e, k in zip(es, ("row", "col")):
            kind[e] = k
    return kind


def conn_faces(port_conn, positions):
    """Each connector takes three port edges on its left face, at the face's
    three lattice points (-1, 0, +1 from centre), ordered by the port they come
    from so the topmost port lands on the topmost point. Its fourth edge, the
    match edge, has the whole right face to itself."""
    groups = {}
    for e in port_conn:
        groups.setdefault(e[0], []).append(e)
    off = {}
    for es in groups.values():
        es.sort(key=lambda e: positions[e[1]][1])
        for e, d in zip(es, (-1, 0, 1)):
            off[e] = d
    return off


def exit_y(e, kind, positions):
    """The lane a port-connector edge drops onto as it leaves its port: just
    under the row for a row exit, down in the corridor for a column exit."""
    lane = LANE_XC if kind == "col" else LANE_XR
    return positions[e[1]][1] + lane[port_col(e[1])] * U


def face_y(e, cd, positions):
    """The y the same edge arrives at, one of the three points of its
    connector's left face."""
    return positions[e[0]][1] + cd * U


def path(points):
    head, rest = points[0], points[1:]
    d = f"M {f(head[0])} {f(head[1])}" + "".join(f" L {f(x)} {f(y)}" for x, y in rest)
    return f'<path d="{d}"/>'


def l_spokes(hub, ports, positions):
    """The four L-P spokes of one row. The hub and all four ports share a y.
    Column 0 has no pad between it and the hub, so it runs straight across at
    the row's own height, face to face. The other three leave the hub's top
    face -- one lattice point apart, so the fan-out itself is on pitch -- climb
    to their own lane above the row, cross to their port and drop in through
    its top face. Lanes nest outward with distance: column 3 rides highest, so
    when it steps down onto its port the lanes of columns 1 and 2 have already
    ended to its left and it crosses nothing of theirs."""
    hx, hy = positions[hub]
    ports = sorted(ports, key=lambda p: positions[p][0])
    out = []
    for j, port in enumerate(ports):
        px, py = positions[port]
        if LANE_L[j] is None:
            out.append(path([(hx + U, hy), (px - U, py)]))
        else:
            lane = hy + LANE_L[j] * U
            sx = hx + (2 - j) * U
            out.append(path([(sx, hy - U), (sx, lane), (px, lane), (px, py - U)]))
    return out


def r_spokes(hub, ports, positions):
    """The four R-P spokes of one column -- the quarter-turn of l_spokes. The
    hub sits below its column and all four ports share its x. Row 3 is nearest
    and runs straight up the column's own centre line, face to face. The other
    three leave the hub's left face a lattice point apart, climb their own lane
    beside the column, turn in under their port and rise into its bottom-left
    corner; again the furthest (row 0) takes the outermost lane."""
    hx, hy = positions[hub]
    ports = sorted(ports, key=lambda p: positions[p][1])
    out = []
    for i, port in enumerate(ports):
        px, py = positions[port]
        if LANE_R[i] is None:
            out.append(path([(hx, hy - U), (hx, py + U)]))
        else:
            lane = hx + LANE_R[i] * U
            sy = hy + (1 - i) * U
            turn = py + R_TURN * U
            out.append(
                path([(hx - U, sy), (lane, sy), (lane, turn), (px - U, turn), (px - U, py + U)])
            )
    return out


def port_conn_path(e, kind, lane_x, cd, positions):
    """One port-connector edge: out of the port on its own lane, straight
    across to its track in the channel, down (or up) the track, and in through
    the connector's left face. The two port-side exits are the whole point of
    the split (see split_port_exits): the row exit leaves the right face, steps
    clear of its own pad and drops onto a lane just under the row; the column
    exit leaves the bottom-right corner and drops further, to a lane in the
    corridor. Both lane sets nest outward with distance -- the leftmost port
    has furthest to travel and takes the lane furthest from the row -- so a
    cable's drop only ever crosses lanes that have not begun yet at that x,
    and none of a row's eight outbound cables crosses another."""
    px, py = positions[e[1]]
    cx = positions[e[0]][0]
    ey = exit_y(e, kind, positions)
    if kind == "col":
        pts = [(px + U, py + U), (px + U, ey)]
    else:
        sx = px + EXIT_STEP * U
        pts = [(px + U, py), (sx, py), (sx, ey)]
    cy = face_y(e, cd, positions)
    return path(pts + [(lane_x, ey), (lane_x, cy), (cx - U, cy)])


def match_path(e, lane_x, positions):
    """A connector-connector match edge: out of each connector's right face --
    the only edge either of them puts there -- and over a shared track."""
    u, v = e
    x1, y1 = positions[u]
    x2, y2 = positions[v]
    return path([(x1 + U, y1), (lane_x, y1), (lane_x, y2), (x2 + U, y2)])


def route_port_conn(port_conn, positions, bus_x0):
    """Splits the 96 port-connector edges into two directional bands (by
    whether the edge runs to a higher-y connector or a lower one), packs each
    band by its own lower endpoint, and lays the bands out with a gap between
    them. Returns (track x, exit kind, connector face offset per edge, total
    track count)."""
    kind = split_port_exits(port_conn, positions)
    cd = conn_faces(port_conn, positions)

    lo, hi, down, up = {}, {}, [], []
    for e in port_conn:
        ey = exit_y(e, kind[e], positions)
        cy = face_y(e, cd[e], positions)
        lo[e], hi[e] = sorted((ey, cy))
        (down if cy > ey else up).append(e)

    lane1, n1 = pack_tracks(down, lo, hi, key=lambda e: lo[e], gap=TRACK_GAP)
    lane2, n2 = pack_tracks(up, lo, hi, key=lambda e: lo[e], gap=TRACK_GAP)

    lane_x = {e: bus_x0 + t * U for e, t in lane1.items()}
    base2 = bus_x0 + (n1 + BAND_GAP) * U
    lane_x.update({e: base2 + t * U for e, t in lane2.items()})
    return lane_x, kind, cd, n1 + BAND_GAP + n2


def route_match(match_edges, positions, bus_x0):
    """The 16 match edges get one track each, ordered down the column: the edge
    whose upper connector is highest turns first, and each one after it turns a
    single lattice line further right. Packing would be far cheaper (a match
    edge only ever spans two connector slots, so two tracks would hold all
    sixteen) but it would collapse the one part of the graph whose shape is
    worth reading off the picture.

    Stepping per edge rather than per connector slot is what keeps the band
    narrow -- sixteen treads instead of thirty -- and because the matching pairs
    slots two apart, the risers alternate between one and three slot heights.
    That alternation is the staircase: a constant step would draw the same
    sixteen turns as one straight ramp."""
    order = sorted(match_edges, key=lambda e: min(positions[e[0]][1], positions[e[1]][1]))
    lane_x = {e: bus_x0 + n * MATCH_STEP for n, e in enumerate(order)}
    return lane_x, (len(order) - 1) * MATCH_STEP


# --- one eager pass at import time: parse the graph, lay out every node,
# and run the channel router once, so W/H are real (not guessed) sizes and
# build_art() below just formats already-computed positions and routes.
_EDGES = parse_edges()
_POSITIONS = {}
for _b in BLOCKS:
    _POSITIONS.update(block_positions(_b))
_CONN_LABELS = connector_order(_EDGES)
for _i, _label in enumerate(_CONN_LABELS):
    _POSITIONS[_label] = (0, CONN_Y0 + _i * CONN_DY)  # x stands in until CONN_X

_ROW_HUB_PORTS, _COL_HUB_PORTS, _PORT_CONN, _MATCH_EDGES = classify(_EDGES)

# The channel's width is whatever the packing needs, so the column can only be
# placed once it has run -- which is why the connectors got a placeholder x.
PORT_BUS_X0 = BLOCK_RIGHT + CHANNEL_GAP
_PORT_LANE_X, _PORT_KIND, _CONN_FACE, _N_PORT_TRACKS = route_port_conn(
    _PORT_CONN, _POSITIONS, PORT_BUS_X0
)
CONN_X = PORT_BUS_X0 + _N_PORT_TRACKS * U + CHANNEL_GAP
for _label in _CONN_LABELS:
    _POSITIONS[_label] = (CONN_X, _POSITIONS[_label][1])

MATCH_BUS_X0 = CONN_X + 2 * U  # one clear lattice line off the column's pads
_MATCH_LANE_X, _MATCH_SPAN = route_match(_MATCH_EDGES, _POSITIONS, MATCH_BUS_X0)
assert MATCH_BUS_X0 + _MATCH_SPAN - (CONN_X + U) == MATCH_BAND, "staircase off band"

# The four outermost pieces of ink are known in closed form -- the leftmost L
# hub's pad, the first and last connector's pads, and the last match lane --
# so the page is sized from them and the frame is asserted, not measured.
_INK_L = GRID_CX - HUB_GAP - PAD // 2
_INK_R = MATCH_BUS_X0 + _MATCH_SPAN
_INK_T = CONN_Y0 - PAD // 2
_INK_B = CONN_Y0 + CONN_H + PAD // 2
W = _INK_R + FRAME
assert (_INK_L, _INK_T, H - _INK_B, W - _INK_R) == (FRAME,) * 4, "frame not uniform"


def build_art():
    out = [f'<g fill="none" stroke="{INK}" stroke-width="{f(WIRE_W)}"'
           f' opacity="{f(WIRE_OPACITY)}">']

    for hub, ports in _ROW_HUB_PORTS.items():
        out.extend(l_spokes(hub, ports, _POSITIONS))
    for hub, ports in _COL_HUB_PORTS.items():
        out.extend(r_spokes(hub, ports, _POSITIONS))
    for e in _PORT_CONN:
        out.append(port_conn_path(e, _PORT_KIND[e], _PORT_LANE_X[e], _CONN_FACE[e], _POSITIONS))
    for e in _MATCH_EDGES:
        out.append(match_path(e, _MATCH_LANE_X[e], _POSITIONS))
    out.append("</g>")

    out.append(f'<g fill="{INK}" stroke="none">')
    for x, y in _POSITIONS.values():
        out.append(f'<rect x="{f(x - U)}" y="{f(y - U)}" width="{f(PAD)}" height="{f(PAD)}"/>')
    out.append("</g>")

    return "\n".join(out)


if __name__ == "__main__":
    markup = build_art()
    svg = f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">{markup}</svg>'
    print(svg)
