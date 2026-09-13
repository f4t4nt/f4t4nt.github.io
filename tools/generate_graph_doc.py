#!/usr/bin/env python3
"""Regenerates the /graph page.

Everything on the page -- the prose's counts, the port table, all three
figures -- is derived from data/deg4-dia4-n104.edges at build time, so the
page cannot drift from the record. The claims it makes about the graph
(4-regular, diameter 4, one port per block per connector) are recomputed and
asserted here rather than written down, which is why editing the record is
enough to keep the page honest.

The full figure at the bottom is the same routed drawing as the card's art,
from pcb_layout.Layout, quarter-turned and with the spacing knobs set for
reading rather than for the card's composition.

The page is written to graph/index.html and carries no frontmatter: /graph
resolves by the directory-index convention every static host already follows,
so nothing here needs Jekyll and what `python3 -m http.server` serves is
exactly what GitHub Pages serves.

Each figure is also written to assets/ as a standalone .svg, the way
generate_graph.py writes the rail. The page carries them inline so they paint
with it and the hover code can reach them; the assets are the same bytes, for
anything that wants one figure on its own.
"""

import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "graph" / "index.html"
ASSETS = ROOT / "assets"

sys.path.insert(0, str(ROOT / "tools"))
from generate_graph import f, is_conn, parse_edges
from pcb_layout import BLOCKS, Layout

# --- facts, recomputed from the record ------------------------------------


def adjacency(edges):
    adj = collections.defaultdict(set)
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    return adj


def graph_facts(edges):
    """The numbers the prose quotes. Computed, then asserted against the
    claims the page makes, so a change to the record either flows through or
    stops the build."""
    adj = adjacency(edges)
    ecc = {}
    for src in adj:
        dist = {src: 0}
        queue = collections.deque([src])
        while queue:
            x = queue.popleft()
            for y in adj[x]:
                if y not in dist:
                    dist[y] = dist[x] + 1
                    queue.append(y)
        assert len(dist) == len(adj), f"{src} cannot reach the whole graph"
        ecc[src] = max(dist.values())

    facts = {
        "n": len(adj),
        "m": len(edges),
        "degree": sorted({len(a) for a in adj.values()}),
        "diameter": max(ecc.values()),
        "min_ecc": min(ecc.values()),
    }
    assert facts["n"] == 104 and facts["m"] == 208, facts
    assert facts["degree"] == [4], facts["degree"]
    assert facts["diameter"] == 4 and facts["min_ecc"] == 4, facts
    return facts


def connector_ports(edges):
    """{connector: {block: port}} -- and the assertion that this shape is the
    whole story: every connector reaches exactly one port in every block, so
    the page never has to describe an exception."""
    ports = collections.defaultdict(dict)
    partner = {}
    for u, v in edges:
        cu, cv = is_conn(u), is_conn(v)
        if cu and cv:
            partner[u], partner[v] = v, u
        elif cu or cv:
            conn, port = (u, v) if cu else (v, u)
            block = port.split(".", 1)[0]
            assert block not in ports[conn], f"{conn} reaches {block} twice"
            ports[conn][block] = port
    for conn, byblock in ports.items():
        assert sorted(byblock) == BLOCKS, f"{conn} misses a block: {sorted(byblock)}"
    assert len(ports) == 32 and len(partner) == 32
    return dict(ports)


# --- one scale, for all three figures --------------------------------------
#
# Every figure on the page is drawn on the board's own lattice -- pitch U, pads
# of side 2U -- and rendered at SCALE pixels per lattice unit. So a pad, a
# label and a cable come out the same size on the page in all three, and the
# only thing that differs between them is how much of the graph each shows.
# The alternative, letting each figure pick its own units and then sizing it by
# eye in CSS, is what made the three disagree about how big a vertex is.
# fmt: off
U = 8                  # the lattice pitch, the same one pcb_layout works on
SCALE = 0.45           # lattice units to CSS pixels, page-wide
TYPE = 4 * U           # a vertex label
STROKE = 0.375 * U     # a cable
AIR = U                # between the outermost ink and the edge of the box
EM = 0.6               # the mono face's advance width, for measuring labels
# fmt: on

MONO = "IBM Plex Mono, ui-monospace, monospace"


def box(x0, y0, x1, y1):
    """The viewBox and the on-page size of a figure, from the extent of its
    ink. The pixel size is written onto the element rather than left to the
    stylesheet, which is what holds every figure to the one scale; the
    stylesheet's max-width is only there to let a narrow window shrink them."""
    x0, y0 = x0 - AIR, y0 - AIR
    w, h = x1 + AIR - x0, y1 + AIR - y0
    return (
        f' viewBox="{f(x0)} {f(y0)} {f(w)} {f(h)}"'
        f' width="{f(w * SCALE)}" height="{f(h * SCALE)}"'
    )


def named(members):
    """The set of vertices a silkscreen name stands for -- a pad's own name one
    vertex, an L or R name the line of the grid it heads, a block letter the
    whole block, a pair number the two connectors it sits between. The hover
    code reads the list and decides what to do with it."""
    return f' class="glabel" data-group="{",".join(members)}"'


def hub_group(block, side, i):
    """An L or R name's set: the hub and the four ports on its line, which are
    exactly the vertices the hub's original K4,4 edges touch."""
    ports = (
        [f"{block}.P{i}{j}" for j in range(1, 5)]
        if side == "L"
        else [f"{block}.P{j}{i}" for j in range(1, 5)]
    )
    return [f"{block}.{side}{i}"] + ports


def silk(x, y, text, anchor="middle", members=()):
    """A label, vertically centred on y rather than sitting on it, so a name
    reads as belonging to the thing beside it."""
    return (
        f'<text{named(members)} x="{f(x)}" y="{f(y + 0.36 * TYPE)}"'
        f' font-size="{f(TYPE)}" text-anchor="{anchor}">{text}</text>'
    )


def pad(label, x, y, side):
    """A node, drawn the way the board draws one: a square pad centred on its
    own point. Nothing in this site's drawings is round."""
    return (
        f'<rect class="gnode" data-v="{label}" x="{f(x - side / 2)}"'
        f' y="{f(y - side / 2)}" width="{f(side)}" height="{f(side)}"/>'
    )


# --- figure 1: one block ---------------------------------------------------

BF_GAP = 2.5 * U  # from a pad to its name, above an L, left of an R
BF_BLOCK = "A"  # the block figure 1 is cut from


def block_figure(L):
    """Block A lifted straight off figure 3: the same 24 pads at the same
    spacing, joined by the same 32 routed cables, with the channel and the other
    two blocks cut away. Nothing here is a second opinion about how a block is
    arranged -- it is one block at the size a reader will meet three of, and the
    only thing the figure adds is the room the names need.

    So it comes turned as the board turns it, L along the top and R down the
    left, and it inherits the routing with everything that follows from it: the
    hubs standing half a port pitch off the grid, each of a hub's four spokes on
    its own lane, and each of the four leaving its pad by its own point rather
    than all four from the centre."""
    pre = f"{BF_BLOCK}."
    pos = {v: L.pt(*L.positions[v]) for v in L.positions if v.startswith(pre)}
    wires = [
        (u, w, [L.pt(*p) for p in pts])
        for u, w, pts in L.wires
        if u.startswith(pre) and w.startswith(pre)
    ]
    assert len(pos) == 24 and len(wires) == 32, (len(pos), len(wires))

    # The block's own ink, pads included, moved so its top-left corner is the
    # origin -- the coordinates it had were positions on a board this figure no
    # longer shows.
    xs = [x for _, _, pts in wires for x, _ in pts] + [
        x + s * L.pad / 2 for x, _ in pos.values() for s in (-1, 1)
    ]
    ys = [y for _, _, pts in wires for _, y in pts] + [
        y + s * L.pad / 2 for _, y in pos.values() for s in (-1, 1)
    ]
    ox, oy, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    pos = {v: (x - ox, y - oy) for v, (x, y) in pos.items()}
    wires = [(u, v, [(x - ox, y - oy) for x, y in pts]) for u, v, pts in wires]

    # Tight to the ink on all four sides, names included. Centring the box on
    # the 4x4 instead would pad the two sides the hubs do not hang off, for a
    # band of blank the height of a hub arm; the grid reads as the middle of the
    # picture anyway, since what sits opposite it is two thin arms and faint type.
    l_y = min(y for v, (_, y) in pos.items() if ".L" in v)
    r_x = min(x for v, (x, _) in pos.items() if ".R" in v)
    vb = box(r_x - BF_GAP - 2 * EM * TYPE, l_y - BF_GAP - 0.72 * TYPE, w, h)
    out = []
    out.append(
        f'<svg class="gdiagram"{vb}'
        f' xmlns="http://www.w3.org/2000/svg" role="img"'
        f' aria-label="Block {BF_BLOCK}: a subdivided K4,4. Four L'
        f" vertices along the top, four R vertices down the left,"
        f" sixteen P vertices at the grid intersections where each"
        f" Li-Rj edge is split. Hover a vertex to highlight its"
        f' neighbors.">'
    )

    out.append(
        f'<g stroke="currentColor" fill="none"'
        f' stroke-width="{f(STROKE)}" stroke-linejoin="round">'
    )
    for u, v, pts in wires:
        d = f"M {f(pts[0][0])} {f(pts[0][1])}" + "".join(
            f" L {f(x)} {f(y)}" for x, y in pts[1:]
        )
        out.append(
            f'<path class="gedge" data-u="{u}" data-w="{v}" opacity="0.7" d="{d}"/>'
        )
    out.append("</g>")

    # every vertex is the same pad: one size, one fill, the way the rail draws
    # them. Which vertices the subdivision added is something the drawing says
    # by where they sit, not by giving them a second appearance
    out.append('<g fill="currentColor" stroke="none">')
    for label in pos:
        out.append(pad(label, *pos[label], side=L.pad))
    out.append("</g>")

    out.append(f'<g fill="currentColor" fill-opacity="0.6" font-family="{MONO}">')
    # the same two placements the board uses: an L name sits on its own column
    # above the hub, so it is set by its baseline rather than centred like every
    # other label; an R name is centred beside its hub, out to the left
    for i in range(1, 5):
        x, y = pos[f"{pre}L{i}"]
        out.append(
            f'<text{named(hub_group(BF_BLOCK, "L", i))} x="{f(x)}"'
            f' y="{f(y - BF_GAP)}"'
            f' font-size="{f(TYPE)}" text-anchor="middle">L{i}</text>'
        )
    for j in range(1, 5):
        x, y = pos[f"{pre}R{j}"]
        out.append(
            silk(
                x - BF_GAP,
                y,
                f"R{j}",
                anchor="end",
                members=hub_group(BF_BLOCK, "R", j),
            )
        )
    out.append("</g>")

    out.append('<g class="ghit-layer">')
    for label, (x, y) in pos.items():
        out.append(
            f'<circle class="ghit" data-v="{label}"'
            f' cx="{f(x)}" cy="{f(y)}" r="{f(2.5 * U)}"/>'
        )
    out.append("</g></svg>")
    return "".join(out)


# --- figure 2: one connector ----------------------------------------------

CF_GAP = 2.5 * U  # from a pad to its name
CF_CAP = 8 * U  # the longest empty stretch the figure keeps, per axis


def squeeze(vals, cap):
    """An axis of the drawing, shortened. Every coordinate the ink actually uses
    keeps its place in the order and its distance from its neighbour, up to cap;
    anything further apart than that comes back to cap. So the fine structure
    survives exactly -- the jogs where four cables leave one pad by four
    different points, the pitch between a connector and its partner -- and what
    is spent is the empty middle of a long run."""
    out, acc, prev = {}, 0, None
    for v in vals:
        if prev is not None:
            acc += min(v - prev, cap)
        out[v], prev = acc, v
    return out


def connector_figure(L, conn):
    """One connector lifted off figure 3 the way figure 1 lifts a block: the
    four cables the board actually runs out of this pad, with the other 204
    taken away. The four are the same four at every connector -- one to the
    partner it shares a number with, one into each block -- and the record's
    names already say which is which.

    Unlike figure 1 this one is not at the board's scale across, because at the
    board's scale it is mostly the blank the other 204 cables were filling. The
    pads and the type stay the size they are everywhere else on the page and the
    routing keeps every turn it has; it is only the empty runs between the turns
    that are brought in, by squeeze() above."""
    wires = [(u, w, [L.pt(*p) for p in pts]) for u, w, pts in L.wires if conn in (u, w)]
    assert len(wires) == 4, len(wires)
    far = [w if u == conn else u for u, w, _ in wires]
    pos = {v: L.pt(*L.positions[v]) for v in [conn] + far}

    pts = [p for _, _, ps in wires for p in ps] + list(pos.values())
    sx = squeeze(sorted({x for x, _ in pts}), CF_CAP)
    sy = squeeze(sorted({y for _, y in pts}), CF_CAP)
    pos = {v: (sx[x], sy[y]) for v, (x, y) in pos.items()}
    wires = [(u, v, [(sx[x], sy[y]) for x, y in ps]) for u, v, ps in wires]

    # A name goes wherever its pad has room, which is the board's own habit. A
    # port is the top of a cable with nothing above it, so its name sits over
    # it; the connector and its partner are one pitch apart in the bottom row,
    # which is not room for two names side by side, so those two hang off the
    # ends of the pair instead, one each way.
    side = {conn: -1, far[[is_conn(v) for v in far].index(True)]: 1}
    nw = {v: len(v) * EM * TYPE for v in pos}

    # the box takes cables, pads and names together: the names reach further
    # than the ink they belong to on three sides of this drawing
    xs = [x for _, _, ps in wires for x, _ in ps]
    ys = [y for _, _, ps in wires for _, y in ps]
    for v, (x, y) in pos.items():
        xs += [x - L.pad / 2, x + L.pad / 2]
        ys += [y - L.pad / 2, y + L.pad / 2]
        if v in side:
            xs.append(x + side[v] * (CF_GAP + nw[v]))
            ys += [y - 0.72 * TYPE, y + 0.28 * TYPE]
        else:
            xs += [x - nw[v] / 2, x + nw[v] / 2]
            ys.append(y - CF_GAP - 0.72 * TYPE)
    vb = box(min(xs), min(ys), max(xs), max(ys))
    out = []
    out.append(
        f'<svg class="gdiagram"{vb}'
        ' xmlns="http://www.w3.org/2000/svg" role="img"'
        ' aria-label="One connector and its four edges, drawn where the'
        " board runs them: one to its partner alongside it, one up into"
        " each of the three blocks. Hover a vertex to highlight its"
        ' neighbors.">'
    )

    out.append(
        f'<g stroke="currentColor" fill="none"'
        f' stroke-width="{f(STROKE)}" stroke-linejoin="round">'
    )
    for u, v, pts in wires:
        d = f"M {f(pts[0][0])} {f(pts[0][1])}" + "".join(
            f" L {f(x)} {f(y)}" for x, y in pts[1:]
        )
        out.append(
            f'<path class="gedge" data-u="{u}" data-w="{v}" opacity="0.7" d="{d}"/>'
        )
    out.append("</g>")

    # one pad for every vertex, as in the block figure and on the board
    out.append('<g fill="currentColor" stroke="none">')
    for v, (x, y) in pos.items():
        out.append(pad(v, x, y, side=L.pad))
    out.append("</g>")

    out.append(f'<g fill="currentColor" fill-opacity="0.6" font-family="{MONO}">')
    for v, (x, y) in pos.items():
        if v in side:
            out.append(
                silk(
                    x + side[v] * CF_GAP,
                    y,
                    v,
                    members=[v],
                    anchor="end" if side[v] < 0 else "start",
                )
            )
        else:
            out.append(
                f'<text{named([v])} x="{f(x)}" y="{f(y - CF_GAP)}"'
                f' font-size="{f(TYPE)}" text-anchor="middle">{v}</text>'
            )
    out.append("</g>")

    out.append('<g class="ghit-layer">')
    for v, (x, y) in pos.items():
        out.append(
            f'<circle class="ghit" data-v="{v}" cx="{f(x)}"'
            f' cy="{f(y)}" r="{f(2.5 * U)}"/>'
        )
    out.append("</g></svg>")
    return "".join(out)


# --- figure 3: the whole graph, routed ------------------------------------

# The block letter: how far above its block's L row the baseline sits, in
# lattice pitches, and the size of the type. It is the one thing on the page
# set larger than TYPE, because it names a whole block rather than a vertex.
LETTER_UP = 9 * U
LETTER_SIZE = 1.5 * TYPE

# From an R pad to the right-hand end of its name.
R_GAP = 2.5 * U


def staple_bottom(L):
    """How far below the connector row a match staple reaches, in page
    coordinates. Turned, the match bus that ran down the flat page's right-hand
    side is the row of staples under the connectors, and match_out is measured
    from the pads' faces -- so the two together are the depth a reader sees."""
    conn_y = L.pt(*L.positions[L.conn_labels[0]])[1]
    return conn_y + L.pad / 2 + L.match_out


def full_figure(L):
    """The 104 vertices and 208 edges as one board. pcb_layout has already
    done the work; this only paints it, labels the landmarks, and lays the
    hover targets over the top.

    Quarter-turned, the drawing reads down the page: the three blocks side by
    side along the top, the channel carrying all 96 port-connector cables
    below them, the 32 connectors in a single row, and the matching underneath
    as sixteen staples of one depth."""
    assert L.U == U, "the board is drawn on a different lattice from the page"
    # Layout sizes its page from the cables and the pads; the block letters and
    # the pair numbers are this page's own addition, and stand outside both. So
    # the box is opened by however much of that type would otherwise fall off
    # an edge. Paying for it here rather than by widening the frame keeps the
    # frame meaning what it says -- air on all four sides -- instead of being
    # set by one row of type.
    l_row = min(L.pt(*L.positions[f"{b}.L1"])[1] for b in BLOCKS)
    head = max(0.0, LETTER_UP + 0.72 * LETTER_SIZE + AIR - l_row)
    pair_y = staple_bottom(L) + 1.2 * TYPE
    tail = max(0.0, pair_y + AIR - L.H)
    # The R names hang off the left of their block, and the left-most block
    # stands at the frame, so they are the one piece of silkscreen that runs
    # into the page's own edge.
    r_ink = (
        min(L.pt(*L.positions[f"{b}.R{j}"])[0] for b in BLOCKS for j in range(1, 5))
        - R_GAP
        - 2 * EM * TYPE
    )
    left = max(0.0, AIR - r_ink)

    out = []
    out.append(
        f'<svg id="fullgraph" class="gdiagram"'
        f' viewBox="{f(-left)} {f(-head)} {f(L.W + left)}'
        f' {f(L.H + head + tail)}"'
        f' width="{f((L.W + left) * SCALE)}"'
        f' height="{f((L.H + head + tail) * SCALE)}"'
        f' xmlns="http://www.w3.org/2000/svg"'
        f' role="img" aria-label="The whole 104-vertex graph drawn as a'
        f" circuit board: three blocks along the top, a routing channel"
        f" of 96 cables below them, the 32 connectors in a row, and the"
        f" 16 matching edges as staples at the bottom. Hover any vertex"
        f' to highlight its four neighbors.">'
    )

    out.append(
        '<g stroke="currentColor" fill="none"'
        f' stroke-width="{f(STROKE)}" stroke-linejoin="round">'
    )
    for u, w, pts in L.wires:
        p = [L.pt(x, y) for x, y in pts]
        d = f"M {f(p[0][0])} {f(p[0][1])}" + "".join(
            f" L {f(x)} {f(y)}" for x, y in p[1:]
        )
        out.append(
            f'<path class="gedge" data-u="{u}" data-w="{w}" opacity="0.55" d="{d}"/>'
        )
    out.append("</g>")

    out.append('<g fill="currentColor" stroke="none">')
    for label, (x, y) in L.positions.items():
        cx, cy = L.pt(x, y)
        out.append(
            f'<rect class="gnode" data-v="{label}"'
            f' x="{f(cx - L.U)}" y="{f(cy - L.U)}"'
            f' width="{f(L.pad)}" height="{f(L.pad)}"/>'
        )
    out.append("</g>")

    # Silkscreen: paint-order puts a paper-coloured stroke behind every glyph,
    # so a label stays legible wherever it has to sit -- which matters for the
    # R labels, whose only room is over the corridor lanes beside the block.
    out.append(
        '<g fill="currentColor" fill-opacity="0.6" stroke="var(--paper)"'
        f' stroke-width="{f(0.6 * L.U)}" stroke-linejoin="round"'
        ' paint-order="stroke fill"'
        f' font-family="{MONO}">'
    )
    for b in BLOCKS:
        # turned, a block's L hubs run along its top edge and its R hubs down
        # its left, so the letter goes above the block, clear of the L labels
        block = [v for v in L.positions if v.startswith(f"{b}.")]
        xs = [L.pt(*L.positions[v])[0] for v in block]
        top = L.pt(*L.positions[f"{b}.L1"])[1]
        out.append(
            f'<text{named(block)} x="{f((min(xs) + max(xs)) / 2)}"'
            f' y="{f(top - LETTER_UP)}"'
            f' font-size="{f(LETTER_SIZE)}"'
            f' font-weight="600" fill-opacity="0.8"'
            f' text-anchor="middle">{b}</text>'
        )
        for i in range(1, 5):
            x, y = L.pt(*L.positions[f"{b}.L{i}"])
            out.append(
                f'<text{named(hub_group(b, "L", i))} x="{f(x)}"'
                f' y="{f(y - 2.5 * U)}"'
                f' font-size="{f(TYPE)}"'
                f' text-anchor="middle">L{i}</text>'
            )
        for j in range(1, 5):
            x, y = L.pt(*L.positions[f"{b}.R{j}"])
            out.append(
                silk(x - R_GAP, y, f"R{j}", anchor="end", members=hub_group(b, "R", j))
            )

    # A pair's two connectors are adjacent in the row and its staple joins
    # them, so the number goes under the staple, centred on the span it names.
    # Above the row is where the 96 channel cables come in, and a number set in
    # among them had to be read off the one clear gap it happened to sit in.
    for lo, hi in zip(L.conn_labels[::2], L.conn_labels[1::2]):
        assert lo[:-1] == hi[:-1], f"{lo} and {hi} are not a pair"
        a, b = L.pt(*L.positions[lo]), L.pt(*L.positions[hi])
        out.append(
            f'<text{named([lo, hi])} x="{f((a[0] + b[0]) / 2)}"'
            f' y="{f(pair_y)}"'
            f' font-size="{f(TYPE)}" text-anchor="middle">'
            f"{lo[:-1]}</text>"
        )
    out.append("</g>")

    out.append('<g class="ghit-layer">')
    for label, (x, y) in L.positions.items():
        cx, cy = L.pt(x, y)
        out.append(
            f'<circle class="ghit" data-v="{label}" cx="{f(cx)}"'
            f' cy="{f(cy)}" r="{f(2.5 * U)}"/>'
        )
    out.append("</g></svg>")
    return "".join(out)


# --- the port table --------------------------------------------------------

RECORD = (
    "https://github.com/f4t4nt/f4t4nt.github.io/blob/main/data/deg4-dia4-n104.edges"
)


def port_table(ports):
    """One row per pair rather than per connector: a and b side by side, six
    ports across. A pair is the unit the wiring is chosen in, so the two halves
    belong on one line where they can be compared."""
    # the rule that opens each half of the row, so the six ports read as two
    # groups of three rather than one run of six
    half = ' class="half"'
    conns = sorted(ports)
    rows = []
    for a, b in zip(conns[::2], conns[1::2]):
        assert a[:-1] == b[:-1] and (a[-1], b[-1]) == ("a", "b"), f"{a}/{b}"
        cells = "".join(
            f"<td{half if k == 0 else ''}>{ports[c][blk].split('.', 1)[1]}</td>"
            for c in (a, b)
            for k, blk in enumerate(BLOCKS)
        )
        rows.append(f'<tr><th scope="row">{a[:-1]}</th>{cells}</tr>')
    heads = "".join(
        f'<th scope="col"{half if k == 0 else ""}>{blk}</th>'
        for _ in range(2)
        for k, blk in enumerate(BLOCKS)
    )
    return (
        '<table class="ports">\n'
        f'<caption>Complete graph listed <a href="{RECORD}">here</a>.</caption>\n'
        '<colgroup><col class="pair">'
        '<col class="block" span="6"></colgroup>\n'
        "<thead>\n"
        '<tr><th rowspan="2" scope="col">pair</th>'
        '<th colspan="3" scope="colgroup" class="half">a</th>'
        '<th colspan="3" scope="colgroup" class="half">b</th></tr>\n'
        f"<tr>{heads}</tr>\n</thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"
    )


# --- the page --------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Largest known (4,4)-graph &mdash; Nishant Bhakar</title>
<meta name="description" content="How the largest known degree-4, diameter-4 graph &mdash; 104 vertices &mdash; is built, and the exact port each connector wires into.">
<link rel="canonical" href="https://f4t4nt.github.io/graph">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles.css">
<style>
  .doc {{ max-width: 45rem; margin: 0 auto; padding: 4.5rem 1.5rem 6rem; }}
  .doc h1 {{ font-size: 1.5rem; margin: 0 0 0.3rem; }}
  .doc .sub {{ color: var(--muted); margin: 0 0 2.5rem; }}
  .doc h2 {{ margin-top: 2.75rem; }}
  /* Let the browser look ahead before it breaks a line. Most of the bad ones
     here came from a mono symbol landing at the margin, so symbols are kept
     whole as well -- a name like Pij or Li-Rj reads as one word and should
     break like one.

     The site's stylesheet holds a paragraph to a 34rem measure, which is right
     for the home page, where nothing else on it is any wider. Here the rules
     and the port table run the full column, and a paragraph stopping short of
     them reads as a ragged second margin down the page. So the prose takes the
     column too, and there is one left edge and one right edge throughout. */
  .doc p {{ max-width: none; text-wrap: pretty; }}
  .doc .back {{
    display: inline-block;
    margin-top: 3rem;
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85rem;
  }}
  .doc figure {{ margin: 2rem 0; text-align: center; }}
  /* Every figure arrives with its own width and height in pixels, set from the
     one scale the generator draws all three at, so nothing here picks a size.
     All the stylesheet does is let a window narrower than a figure shrink it,
     which is the only case where the shared scale has to give. */
  .gdiagram {{ max-width: 100%; height: auto; color: var(--ink); }}
  /* Vertex names are set in the same mono the drawings label them in, and are
     spelled the way the edge record spells them -- L1, P34, X02a -- so there
     is nothing to translate between the prose, the figures and the file. */
  .sym {{
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.92em;
    white-space: nowrap;
  }}
  .sym sub, .sym sup {{ font-size: 0.75em; }}

  /* The board is wider than the prose's measure, so it breaks out of the
     column -- but it is not stretched to any particular width: it takes the
     size the shared scale gives it, the same as the other two figures, and
     this only centres it. */
  .board {{
    width: fit-content;
    max-width: calc(100vw - 3rem);
    margin: 1.5rem auto 0;
  }}
  /* The board sits between two .doc columns, so its air is theirs: the tail
     the page ends with would otherwise open up between the board and the
     paragraph introducing it. */
  .doc.lead {{ padding-bottom: 0; }}
  .doc.tail {{ padding-top: 0; }}
  /* The table is a picture of the wiring, not text to quote: dragging across
     it should no more select "P13 P42 P34" than dragging across a figure
     picks out its labels. */
  .doc table.ports {{
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    user-select: none;
    -webkit-user-select: none;
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.8rem;
    font-variant-numeric: tabular-nums;
  }}
  .doc table.ports col.pair {{ width: 16%; }}
  .doc table.ports col.block {{ width: 14%; }}
  .doc table.ports th, .doc table.ports td {{
    padding: 0.32rem 0.6rem;
    text-align: left;
    border-bottom: 1px solid var(--rule);
  }}
  .doc table.ports thead th {{
    font-family: "IBM Plex Sans", ui-sans-serif, sans-serif;
    font-weight: 600;
    font-size: 0.72rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--ink);
    overflow-wrap: break-word;
  }}
  .doc table.ports thead th[colspan] {{ text-transform: none; }}
  /* the one line the table carries, set under it as a note rather than over it
     as a title -- it points somewhere rather than saying what the table is */
  .doc table.ports caption {{
    caption-side: bottom;
    padding-top: 0.7rem;
    font-family: "IBM Plex Sans", ui-sans-serif, sans-serif;
    font-size: 0.85rem;
    color: var(--muted);
    text-align: right;
    user-select: text;
    -webkit-user-select: text;
  }}
  .doc table.ports tbody th {{ font-weight: 500; }}
  /* a and b are the two halves of one row, so the rule that separates them is
     the only vertical one in the table */
  .doc table.ports .half {{ border-left: 1px solid var(--rule); }}
  /* the same faint tint the homepage list uses, for the same reason: a row is
     seven cells wide and the eye needs to be told which seven */
  .doc table.ports tbody tr {{ transition: background-color 0.25s ease-out; }}
  .doc table.ports tbody tr:hover {{
    background: color-mix(in srgb, var(--rule) 16%, var(--paper));
  }}
</style>
</head>
<body>
<div class="doc lead">

<h1>The largest known degree-4, diameter-4 graph</h1>

<p>{n} vertices and {m} edges, with every vertex at degree 4 and any two at
most 4 steps apart, built from three identical blocks and a set of connectors
between them.</p>

<p>The building block is a subdivided <span class="sym">K<sub>4,4</sub></span>:
a complete bipartite graph between four &ldquo;L&rdquo; and four
&ldquo;R&rdquo; vertices, each of its 16 edges split by a vertex in the
middle. The vertex splitting <span class="sym">Li</span>&ndash;<span
class="sym">Rj</span> is port <span class="sym">Pij</span>. That is 4 + 4 + 16
= 24 vertices and 32 edges per block.</p>

<figure>
{block_svg}
</figure>

<p>Three copies &mdash; A, B and C &mdash; account for 72 vertices and 96
edges. An <span class="sym">Li</span> or <span class="sym">Rj</span> is already
at degree 4; a port is at 2, short two edges.</p>

<p>The remaining 32 vertices are connectors, in 16 matched pairs: X01a/X01b
through X16a/X16b. Each runs one edge to its partner and one into each block,
so it too sits at degree 4, and each port takes two of those, which brings the
ports up as well. That is 16 matching edges and 96 connector&ndash;port edges,
for {n} vertices and {m} in total.</p>

<figure>
{conn_svg}
</figure>

<p>The one thing none of that determines is <em>which</em> port in each block a
given connector reaches. It is the construction's free parameter, and it is
what the diameter turns on. The assignment used here is below.</p>

{table}

<h2>The whole thing</h2>
<p>Laid out as a board: the three blocks along the top, each with its L
branches on its top edge and its R branches down its left; the channel
underneath carrying all 96 connector&ndash;port cables; the 32 connectors in
a single row; and the matching below them as sixteen staples, each joining the
two connectors of one pair.</p>

</div>

<figure class="board">
{full_svg}
</figure>

<div class="doc tail">
<a class="back" href="/">&larr; back</a>
</div>

<script src="/assets/graph-interactive.js"></script>
<script>
  document.querySelectorAll(".gdiagram").forEach(window.initGraphDiagram);
</script>
</body>
</html>
"""


def build_page():
    edges = parse_edges()
    facts = graph_facts(edges)
    ports = connector_ports(edges)
    # Every connector has the same four-edge shape, so which one the figure
    # shows is only a question of which draws well: X08a is halfway along the
    # row, so its three port cables leave in both directions and the picture
    # comes out about as tall as it is wide rather than a strip. The assert is
    # the part that matters -- a connector landing on the same port number in
    # all three blocks would suggest more regularity than the assignment has.
    conn = "X08a"
    assert len({ports[conn][b].split(".", 1)[1] for b in BLOCKS}) == 3, (
        f"{conn} reaches the same port twice"
    )

    # The page reads the board for the graph rather than admiring it as a
    # board, so anything whose size carries no information is taken back: the
    # matching collapses onto one track (match_step=0) instead of fanning into
    # the card's staircase, the channel keeps a pitch of air each side, the
    # staples go no deeper than clears the pads, and the frame is a pitch rather
    # than two -- the page's own margins already stand the figure off.
    #
    # What the blocks want instead is space between them: three blocks with a
    # clear lane between each pair read as three things, and the letter over
    # each one then has something to sit on. The registration fixes
    # 3*block_h + 2*gap_row + head_row + tail_row at the column's 31 pitches, so
    # gap_row 2 -> 3 is bought from the blocks -- the hubs stand one pitch off
    # their port grid rather than two. That also leaves the end rooms equal at 2
    # and 2, centring the stack exactly on the connector column. Nothing finer
    # is available: a block row has to land on a connector row for the lane
    # plan's residues to hold, and a whole pitch further down is more than
    # head_row can give, since block A's L spokes need nine lattice lines of
    # standoff and a pitch is eight.
    board = Layout(
        hub_gap=1,
        gap_row=3,
        head_row=2,
        tail_row=2,
        channel_gap=1,
        frame=1,
        match_out=2,
        match_step=0,
        rotate=True,
    )

    figures = {
        "graph-block": block_figure(board),
        "graph-connector": connector_figure(board, conn),
        "graph-board": full_figure(board),
    }
    html = PAGE.format(
        n=facts["n"],
        m=facts["m"],
        block_svg=figures["graph-block"],
        conn_svg=figures["graph-connector"],
        table=port_table(ports),
        full_svg=figures["graph-board"],
    )
    return html, figures


if __name__ == "__main__":
    html, figures = build_page()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print("wrote", OUT, f"({len(html)} bytes)")
    for name, svg in figures.items():
        path = ASSETS / f"{name}.svg"
        path.write_text(svg)
        print("wrote", path, f"({len(svg)} bytes)")
