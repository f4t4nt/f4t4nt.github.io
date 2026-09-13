#!/usr/bin/env python3
"""The circuit-board layout engine for the 104-vertex graph, as a Layout whose
spacing is set by constructor knobs. generate_og_art.py builds the card's
drawing from it; generate_graph_doc.py builds /graph's roomier, quarter-turned
figure from the same router, so the two pictures cannot disagree about the
graph.

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

The 16 connector-connector match edges get the opposite treatment. A pair sits
in adjacent slots, so all sixteen would pack onto a single track -- but they
are the one part of the graph whose structure is worth being able to read off
the picture, so match_step can give each its own, one tread further right than
the edge above it, and the sixteen staples fan out into a staircase. At
match_step=0 they collapse back onto the one track they would have packed onto,
which is the right answer wherever the drawing is being read for the graph
rather than admired as a board.

Every path is built from axis-aligned steps only (no diagonal segments
anywhere), and the router emits one path per graph edge, each carrying the two
labels it joins -- so a rendering can hand the whole drawing to the page's
hover code without any further bookkeeping.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from generate_graph import is_conn, is_row_hub, parse_edges

BLOCKS = ["A", "B", "C"]
N_CONN = 32

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
#   +3..+6    this row's four X row-exit lanes
#   +7..+9    the next row's three L-spoke lanes      (connector residues)
#   +10       clear
#   +11..+14  this row's four X col-exit lanes
#   +15..+17  the next row's pad edge                 (connector residues)
#
# The plan is stated in lattice steps, so it holds at any pitch; it is the one
# part of the layout that is not a knob.
# fmt: off
LANE_L = (None, -7, -8, -9)   # L-spoke lane by port column; column 0 has no
                              # pad to cross and goes straight in through the
                              # port's left face instead
LANE_R = (-4, -3, -2, None)   # R-spoke lane by port row; row 3 is the one
                              # nearest its hub and goes straight up
LANE_XR = (6, 5, 4, 3)        # X row-exit lane by port column
LANE_XC = (14, 13, 12, 11)    # X col-exit lane by port column
R_TURN = 2      # how far under a row an R-spoke turns in towards its port
# fmt: on

# How far right of its port each of the two X exits steps before it drops.
# They must differ, since both leave the port's right-hand side and then run
# down the same stretch of block. The col exit gets the inner line and the row
# exit the outer one, which is forced: the col exit turns a lattice line lower
# than the row exit does, so if it stepped further it would have to cross the
# row exit's drop to get there.
#
# The col exit clearing the pad by a whole line rather than grazing it is the
# point of the pair. A row-3 port has its own R hub directly below, and the
# hub's pad reaches one line out to either side -- so a col exit dropping at
# +1 would run the pad's full height exactly along its face, reading as an
# edge into a node it has nothing to do with. At +2 it passes clear.
ROW_STEP = 3
COL_STEP = 2


def port_col(port):
    """Which of the four columns a port label sits in -- "A.P34" -> 3."""
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


class Layout:
    """One routed drawing of the graph. Construction does the whole job --
    parse, place, route, size the page -- so `wires`, `positions` and the page
    box are real measurements by the time anything asks for them, and a caller
    only has to decide how to paint them.

    The spacing knobs are given in whole pitches: node_d, hub_gap, gap_row,
    head_row, tail_row, channel_gap and frame in connector pitches, track_gap,
    match_out and match_step in lattice pitches. The vertical ones are not
    independent -- the blocks have to fill the connector column exactly (see the
    registration assert) -- so widening the drawing is mostly a matter of the
    channel and matching knobs, which nothing else is registered against.
    """

    def _pitch(self, n):
        """A knob given in connector pitches, in pixels, checked to land on the
        lattice. A knob is normally a whole pitch; a fraction is allowed only
        where it still comes out a whole number of lattice pitches, since every
        coordinate in the drawing has to."""
        px = n * self.conn_dy
        assert px == int(px) and int(px) % self.U == 0, (
            f"{n} pitches is not a whole number of lattice pitches"
        )
        return int(px)

    def __init__(
        self,
        conn_dy=64,
        node_d=2,
        hub_gap=1,
        gap_row=3,
        head_row=2,
        tail_row=None,
        channel_gap=2,
        frame=2,
        track_gap=2,
        band_gap=2,
        match_out=1,
        match_step=1,
        rotate=False,
    ):
        self.conn_dy = conn_dy
        # THE lattice pitch. Every coordinate in the drawing is an integer
        # multiple of it, so it is both the distance between adjacent cables
        # and the resolution of the whole layout.
        self.U = U = conn_dy // 8
        assert U * 8 == conn_dy, "connector pitch must divide into eight lattice lines"
        # every node -- hub, port, connector -- is this square, centred exactly
        # on the node's lattice point. One U each side of centre gives a face
        # three lattice points wide, which is what lets a degree-4 vertex give
        # each of its cables its own landing point.
        self.pad = 2 * U

        self.node_d = self._pitch(node_d)  # the port grid's node pitch; square
        self.hub_gap = self._pitch(hub_gap)  # how far an L or R hub stands off it
        self.gap_row = self._pitch(gap_row)  # one block's R-hub row to the next's top
        self.head_row = self._pitch(head_row)  # first connector down to block A's top
        # the room at the other end, which is free to differ by the pitch the
        # registration cannot split evenly
        self.tail_row = self._pitch(head_row if tail_row is None else tail_row)
        self.channel_gap = self._pitch(channel_gap)  # air each side of the channel
        self.frame = self._pitch(frame)  # air between ink and page edge, all four sides
        self.track_gap = track_gap * U  # clearance between two edges on one track
        self.band_gap = band_gap  # empty tracks between the two bands
        self.match_out = match_out * U  # first match track, clear of the pads
        self.match_step = match_step * U  # one tread of the match staircase
        self.rotate = rotate

        # the first node in from any edge is a pad, and a pad reaches half its
        # width past its own lattice point
        self.margin = self.frame + self.pad // 2
        self.block_h = 3 * self.node_d + self.hub_gap  # top row to R-hub row
        self.conn_h = (N_CONN - 1) * conn_dy  # first connector to last

        # The three blocks are registered against the connector column rather
        # than stacked at some chosen spacing: every block row lands on a
        # connector row, and the two corridors are equal.
        #
        # Landing on a connector row is the load-bearing half of that. The lane
        # plan gives each cable an offset in lattice pitches from its own row,
        # and it is a whole connector pitch between rows that keeps two rows'
        # lanes in different residue classes; a block placed half a pitch off
        # puts its lanes on top of another block's.
        #
        # The end room is the point of the arrangement. A row's three L-spoke
        # lanes ride 7 to 9 lattice lines ABOVE it, so block A's top row cannot
        # itself sit on the first connector: its spokes would be drawn off the
        # top of the page. head_row is the standoff that gives them somewhere
        # to go.
        #
        # The pieces have to fill the column exactly, which at 32 connectors is
        # an odd number of pitches. The corridors come in a pair, so the two end
        # rooms carry whatever parity is left over: equal (3 + 2 + 2 at a hub
        # standoff of one pitch, which is the card) when the blocks leave an
        # even remainder, and differing by one pitch when they do not. A pitch
        # of slack at one end of a drawing this size is not visible; unequal
        # corridors would be, which is why the parity is spent here.
        assert (
            3 * self.block_h + 2 * self.gap_row + self.head_row + self.tail_row
            == self.conn_h
        ), "stack does not fill the connector column"
        # the deepest lane above a row is an L-spoke's, and block A's top row
        # has only head_row between it and the top of the page for all three
        assert self.head_row > -min(n for n in LANE_L if n) * U, (
            "no room for block A's spokes"
        )

        self._place()
        self._route()
        self._size()

    # --- placement -------------------------------------------------------

    def reading_order(self, labels):
        """Labels in the order their slots should be filled, top to bottom of
        the flat page.

        Down the flat page is left to right once the drawing is turned, but a
        quarter turn clockwise sends the top of the flat page to the right-hand
        side, which would leave the blocks reading C, B, A and the connectors
        counting down from X16. So when the turn is on, the slots are filled in
        reverse and the drawing comes out reading forwards. This only permutes
        which label lands where -- the geometry is the same either way."""
        return labels[::-1] if self.rotate else list(labels)

    def _place(self):
        self.edges = parse_edges()
        self.conn_y0 = self.margin
        # the left-most node is an L hub, a standoff outside the port grid, so
        # the grid itself starts one standoff further in
        self.grid_cx = self.margin + self.hub_gap
        self.grid_cy = {
            b: self.conn_y0 + self.head_row + i * (self.block_h + self.gap_row)
            for i, b in enumerate(self.reading_order(BLOCKS))
        }
        self.block_right = self.grid_cx + 3 * self.node_d + self.hub_gap
        # the stack is centred on the column to within the pitch the end rooms
        # could not split, which is the whole of the asymmetry the registration
        # allows itself
        assert (
            abs(
                (self.grid_cy["B"] + self.block_h // 2)
                - (self.conn_y0 + self.conn_h // 2)
            )
            <= self.conn_dy // 2
        ), "middle block off centre"
        assert all(
            (y - self.conn_y0) % self.conn_dy == 0 for y in self.grid_cy.values()
        ), "block off column"

        self.positions = {}
        for b in BLOCKS:
            self.positions.update(self.block_positions(b))
        self.conn_labels = self.reading_order(connector_order(self.edges))
        # x stands in until the channel's width is known
        for i, label in enumerate(self.conn_labels):
            self.positions[label] = (0, self.conn_y0 + i * self.conn_dy)

    def block_positions(self, block):
        """The 24 nodes of one block: a 4x4 port grid, an L hub one standoff
        left of each row, and an R hub one standoff below each column.

        The rows are handed out in reading order too, so L1 and the ports that
        subdivide its edges come out on the side the reader starts from. The
        columns need no such care: the flat page's left-to-right becomes the
        turned page's top-to-bottom, which already reads forwards."""
        cy0 = self.grid_cy[block]
        rows = self.reading_order([cy0 + i * self.node_d for i in range(4)])
        cols = [self.grid_cx + j * self.node_d for j in range(4)]
        last_row = max(rows)
        pos = {
            f"{block}.L{i + 1}": (self.grid_cx - self.hub_gap, y)
            for i, y in enumerate(rows)
        }
        pos.update(
            {
                f"{block}.R{j + 1}": (x, last_row + self.hub_gap)
                for j, x in enumerate(cols)
            }
        )
        pos.update(
            {
                f"{block}.P{i + 1}{j + 1}": (x, y)
                for i, y in enumerate(rows)
                for j, x in enumerate(cols)
            }
        )
        return pos

    # --- routing ---------------------------------------------------------

    def _route(self):
        (self.row_hub_ports, self.col_hub_ports, self.port_conn, self.match_edges) = (
            classify(self.edges)
        )

        # The channel's width is whatever the packing needs, so the column can
        # only be placed once it has run -- which is why the connectors got a
        # placeholder x.
        self.port_bus_x0 = self.block_right + self.channel_gap
        lane_x, kind, cd, n_tracks = self.route_port_conn(self.port_bus_x0)
        self.conn_x = self.port_bus_x0 + n_tracks * self.U + self.channel_gap
        for label in self.conn_labels:
            self.positions[label] = (self.conn_x, self.positions[label][1])

        # measured from the pads' right face, so match_out is the clearance a
        # reader actually sees rather than a distance to the pads' centre line
        self.match_bus_x0 = self.conn_x + self.pad // 2 + self.match_out
        match_lane_x, self.match_span = self.route_match(self.match_bus_x0)

        wires = []
        for hub, ports in self.row_hub_ports.items():
            wires.extend(self.l_spokes(hub, ports))
        for hub, ports in self.col_hub_ports.items():
            wires.extend(self.r_spokes(hub, ports))
        for e in self.port_conn:
            wires.append((e[1], e[0], self.port_conn_pts(e, kind[e], lane_x[e], cd[e])))
        for e in self.match_edges:
            wires.append((e[0], e[1], self.match_pts(e, match_lane_x[e])))
        assert len(wires) == len(self.edges), "one path per edge"
        # (u, w, points): every wire is a plain two-endpoint edge, since each
        # hub spoke is routed on its own rather than merged into a trunk
        self.wires = wires

    def split_port_exits(self):
        """Every port has exactly two connector edges, and sending both off to
        the right along the port's own row would make a row's outbound cables
        an eight-wide ribbon. So give a port's two edges two different exits:
        one leaves through the right face and runs out along the row, the other
        leaves through the bottom corner and drops into the corridor below the
        row. The rule is the same at every port, so every outbound bundle is
        four cables. Which edge takes which is decided by the connector it is
        heading for: the higher one keeps the row, the lower one takes the
        drop, so the edge that leaves downward is also the one that is going
        downward."""
        by_port = {}
        for e in self.port_conn:
            by_port.setdefault(e[1], []).append(e)
        kind = {}
        for es in by_port.values():
            es.sort(key=lambda e: self.positions[e[0]][1])
            for e, k in zip(es, ("row", "col")):
                kind[e] = k
        return kind

    def conn_faces(self):
        """Each connector takes three port edges on its left face, at the
        face's three lattice points (-1, 0, +1 from centre), ordered by the
        port they come from so the topmost port lands on the topmost point.
        Its fourth edge, the match edge, has the whole right face to itself."""
        groups = {}
        for e in self.port_conn:
            groups.setdefault(e[0], []).append(e)
        off = {}
        for es in groups.values():
            es.sort(key=lambda e: self.positions[e[1]][1])
            for e, d in zip(es, (-1, 0, 1)):
                off[e] = d
        return off

    def exit_y(self, e, kind):
        """The lane a port-connector edge drops onto as it leaves its port:
        just under the row for a row exit, down in the corridor for a column
        exit."""
        lane = LANE_XC if kind == "col" else LANE_XR
        return self.positions[e[1]][1] + lane[port_col(e[1])] * self.U

    def face_y(self, e, cd):
        """The y the same edge arrives at, one of the three points of its
        connector's left face."""
        return self.positions[e[0]][1] + cd * self.U

    def route_port_conn(self, bus_x0):
        """Splits the 96 port-connector edges into two directional bands (by
        whether the edge runs to a higher-y connector or a lower one), packs
        each band by its own lower endpoint, and lays the bands out with a gap
        between them. Returns (track x, exit kind, connector face offset per
        edge, total track count)."""
        kind = self.split_port_exits()
        cd = self.conn_faces()

        lo, hi, down, up = {}, {}, [], []
        for e in self.port_conn:
            ey = self.exit_y(e, kind[e])
            cy = self.face_y(e, cd[e])
            lo[e], hi[e] = sorted((ey, cy))
            (down if cy > ey else up).append(e)

        lane1, n1 = pack_tracks(down, lo, hi, key=lambda e: lo[e], gap=self.track_gap)
        lane2, n2 = pack_tracks(up, lo, hi, key=lambda e: lo[e], gap=self.track_gap)

        lane_x = {e: bus_x0 + t * self.U for e, t in lane1.items()}
        base2 = bus_x0 + (n1 + self.band_gap) * self.U
        lane_x.update({e: base2 + t * self.U for e, t in lane2.items()})
        return lane_x, kind, cd, n1 + self.band_gap + n2

    def route_match(self, bus_x0):
        """The 16 match edges, ordered down the column, each turning match_step
        further right than the one above it. At a step of one that draws the
        staircase; at a step of zero all sixteen share a single track.

        Sharing is safe because a pair occupies adjacent slots, so the sixteen
        spans are disjoint and no two of the staples can ever run over each
        other -- which is asserted here rather than assumed, since it is a fact
        about the connector ordering and not about this routine."""
        order = sorted(
            self.match_edges,
            key=lambda e: min(self.positions[e[0]][1], self.positions[e[1]][1]),
        )
        lane_x = {e: bus_x0 + n * self.match_step for n, e in enumerate(order)}
        spans = {}
        for e in order:
            lo, hi = sorted((self.positions[e[0]][1], self.positions[e[1]][1]))
            for a, b in spans.setdefault(lane_x[e], []):
                assert hi < a or b < lo, f"match edges overlap on one track: {e}"
            spans[lane_x[e]].append((lo, hi))
        return lane_x, (len(order) - 1) * self.match_step

    # --- the four path shapes -------------------------------------------

    def l_spokes(self, hub, ports):
        """The four L-P spokes of one row. The hub and all four ports share a
        y. Column 0 has no pad between it and the hub, so it runs straight
        across at the row's own height, face to face. The other three leave the
        hub's top face -- one lattice point apart, so the fan-out itself is on
        pitch -- climb to their own lane above the row, cross to their port and
        drop in through its top face. Lanes nest outward with distance: column
        3 rides highest, so when it steps down onto its port the lanes of
        columns 1 and 2 have already ended to its left and it crosses nothing
        of theirs."""
        U = self.U
        hx, hy = self.positions[hub]
        ports = sorted(ports, key=lambda p: self.positions[p][0])
        out = []
        for j, port in enumerate(ports):
            px, py = self.positions[port]
            if LANE_L[j] is None:
                pts = [(hx + U, hy), (px - U, py)]
            else:
                lane = hy + LANE_L[j] * U
                sx = hx + (2 - j) * U
                pts = [(sx, hy - U), (sx, lane), (px, lane), (px, py - U)]
            out.append((hub, port, pts))
        return out

    def r_spokes(self, hub, ports):
        """The four R-P spokes of one column -- the quarter-turn of l_spokes.
        The hub sits below its column and all four ports share its x. Row 3 is
        nearest and runs straight up the column's own centre line, face to
        face. The other three leave the hub's left face a lattice point apart,
        climb their own lane beside the column, turn in under their port and
        rise into its bottom-left corner; again the furthest (row 0) takes the
        outermost lane."""
        U = self.U
        hx, hy = self.positions[hub]
        ports = sorted(ports, key=lambda p: self.positions[p][1])
        out = []
        for i, port in enumerate(ports):
            px, py = self.positions[port]
            if LANE_R[i] is None:
                pts = [(hx, hy - U), (hx, py + U)]
            else:
                lane = hx + LANE_R[i] * U
                sy = hy + (1 - i) * U
                turn = py + R_TURN * U
                pts = [
                    (hx - U, sy),
                    (lane, sy),
                    (lane, turn),
                    (px - U, turn),
                    (px - U, py + U),
                ]
            out.append((hub, port, pts))
        return out

    def port_conn_pts(self, e, kind, lane_x, cd):
        """One port-connector edge: out of the port on its own lane, straight
        across to its track in the channel, down (or up) the track, and in
        through the connector's left face. The two port-side exits are the
        whole point of the split (see split_port_exits): the row exit leaves
        the right face and drops onto a lane just under the row; the column exit
        leaves the bottom-right corner and drops further, to a lane in the
        corridor. Each steps clear of the port's own pad first, to its own line
        (see ROW_STEP and COL_STEP). Both lane sets nest outward with
        distance -- the leftmost port has furthest to travel and takes the lane
        furthest from the row -- so a cable's drop only ever crosses lanes that
        have not begun yet at that x, and none of a row's eight outbound cables
        crosses another."""
        U = self.U
        px, py = self.positions[e[1]]
        cx = self.positions[e[0]][0]
        ey = self.exit_y(e, kind)
        if kind == "col":
            sx = px + COL_STEP * U
            pts = [(px + U, py + U), (sx, py + U), (sx, ey)]
        else:
            sx = px + ROW_STEP * U
            pts = [(px + U, py), (sx, py), (sx, ey)]
        cy = self.face_y(e, cd)
        return pts + [(lane_x, ey), (lane_x, cy), (cx - U, cy)]

    def match_pts(self, e, lane_x):
        """A connector-connector match edge: out of each connector's right
        face -- the only edge either of them puts there -- and over a shared
        track."""
        U = self.U
        x1, y1 = self.positions[e[0]]
        x2, y2 = self.positions[e[1]]
        return [(x1 + U, y1), (lane_x, y1), (lane_x, y2), (x2 + U, y2)]

    # --- page ------------------------------------------------------------

    def _size(self):
        """The four outermost pieces of ink are known in closed form -- the
        leftmost L hub's pad, the first and last connector's pads, and the last
        match lane -- so the page is sized from them and the frame is asserted,
        not measured."""
        ink_l = self.grid_cx - self.hub_gap - self.pad // 2
        ink_r = self.match_bus_x0 + self.match_span
        ink_t = self.conn_y0 - self.pad // 2
        ink_b = self.conn_y0 + self.conn_h + self.pad // 2
        w = ink_r + self.frame
        h = self.margin + self.conn_h + self.margin  # the column is the tallest thing
        assert (ink_l, ink_t, h - ink_b, w - ink_r) == (self.frame,) * 4, (
            "frame not uniform"
        )
        # the height of the page the routing was done on, which is what the
        # quarter-turn in pt() measures back from
        self.flat_h = h
        self.W, self.H = (h, w) if self.rotate else (w, h)

    def pt(self, x, y):
        """A routed point in page coordinates. The quarter-turn is applied here
        and nowhere else: it maps lattice lines to lattice lines and right
        angles to right angles, so every spacing invariant above survives it
        untouched, and text can be laid out afterwards in page coordinates and
        stay upright."""
        return (self.flat_h - y, x) if self.rotate else (x, y)
