#!/usr/bin/env python3
"""End-to-end hover test for assets/graph-interactive.js, against the live
page in a headless browser. Hovers all 104 vertices and 208 edges and
checks the exact DOM result, computed independently of the JS under test.

Usage:
    python3 -m http.server 8000 &      # serve the repo root
    python3 tools/test_hover.py [http://localhost:8000/index.html]
"""

import asyncio
import math
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from generate_graph import (
    BLOCKS,
    block_positions,
    connector_positions,
    is_conn,
    parse_edges,
)
from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/index.html"


# ground truth: the real graph, independent of the SVG entirely


def build_adjacency():
    edges = parse_edges()
    adj = {}
    for u, v in edges:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)
    return edges, adj


# a few port<->connector edges are unreachable: their hit-segment always
# loses resolveEdgeAt's tie-breaks to another edge at the same node. Modeled
# here from position/order data alone, never by importing graph-interactive.js,
# so test D stays an honest check.


def known_unreachable_edges(edges):
    positions = {}
    for b in BLOCKS:
        positions.update(block_positions(b))
    conn_pos = connector_positions(edges)
    positions.update(conn_pos)

    port_edges = []
    for u, v in edges:
        cu, cv = is_conn(u), is_conn(v)
        if cu != cv:
            conn, port = (u, v) if cu else (v, u)
            port_edges.append((conn, port))

    def dist(port, conn):
        ax, ay = positions[port]
        bx, by = positions[conn]
        return math.hypot(ax - bx, ay - by)

    port_conns = defaultdict(list)
    for conn, port in port_edges:
        port_conns[port].append(conn)
    port_reachable = set()
    for port, conns in port_conns.items():
        nearest = min(conns, key=lambda c: dist(port, c))
        port_reachable.add((nearest, port))

    conn_first = {}
    for conn, port in port_edges:
        if conn not in conn_first:
            conn_first[conn] = port
    conn_reachable = set(conn_first.items())

    unreachable = set()
    for conn, port in port_edges:
        if (conn, port) not in port_reachable and (conn, port) not in conn_reachable:
            unreachable.add(frozenset((conn, port)))
    return unreachable


# ground truth: per-element expectations computed from each element's own
# data-* attributes, independent of graph-interactive.js's implementation


def onpath_expected(el, label):
    """Expected onpath when `label` is hovered -- an independent
    reimplementation of highlight()'s branching in graph-interactive.js."""
    if el["hub"] or el["ids"] is not None:
        onpath = False
        if el["hub"] and (label == el["hub"] or label in el["far"]):
            onpath = True
        if el["ids"] is not None and label in el["ids"]:
            onpath = True
        return onpath
    return label == el["u"] or label == el["w"]


def edgehover_expected(el, a, b):
    """Expected edgehover for hovered edge (a, b) -- an independent
    reimplementation of edgeConnects()."""
    if el["hub"] and (
        (el["hub"] == a and b in el["far"]) or (el["hub"] == b and a in el["far"])
    ):
        return True
    if el["ids"] is not None and a in el["ids"] and b in el["ids"]:
        return True
    return (
        not el["hub"]
        and el["ids"] is None
        and ((el["u"] == a and el["w"] == b) or (el["u"] == b and el["w"] == a))
    )


# browser plumbing

DUMP_JS = """
() => {
    const svg = document.querySelector('svg.gdiagram');
    const els = Array.from(svg.querySelectorAll('.gedge'));
    return els.map(el => ({
        hub: el.getAttribute('data-hub'),
        far: (el.getAttribute('data-far') || '').split(',').filter(Boolean),
        ids: el.hasAttribute('data-ids') ? el.getAttribute('data-ids').split(',').filter(Boolean) : null,
        u: el.getAttribute('data-u'),
        w: el.getAttribute('data-w'),
    }));
}
"""


async def get_page(playwright):
    browser = await playwright.chromium.launch()
    page = await browser.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.goto(URL)
    await page.wait_for_timeout(150)
    handle_ok = await page.evaluate(
        "() => !!(document.querySelector('svg.gdiagram') && document.querySelector('svg.gdiagram').__ghDiagram)"
    )
    if not handle_ok:
        raise RuntimeError(
            "svg.gdiagram.__ghDiagram not found -- graph-interactive.js didn't initialize"
        )
    return browser, page, errs


# tests


async def test_structural(page, edges, adj):
    """A: DOM's vertex set and reconstructed adjacency match the real graph exactly."""
    failures = []
    dom_vertices = await page.evaluate(
        "() => Array.from(document.querySelectorAll('svg.gdiagram .ghit')).map(e => e.getAttribute('data-v'))"
    )
    if set(dom_vertices) != set(adj.keys()):
        missing = set(adj.keys()) - set(dom_vertices)
        extra = set(dom_vertices) - set(adj.keys())
        failures.append(
            f"vertex set mismatch: missing={sorted(missing)[:5]} extra={sorted(extra)[:5]}"
        )
    if len(dom_vertices) != len(set(dom_vertices)):
        failures.append("duplicate .ghit data-v labels in DOM")

    els = await page.evaluate(DUMP_JS)
    recon = {}
    for el in els:
        if el["hub"]:
            for far in el["far"]:
                recon.setdefault(el["hub"], set()).add(far)
                recon.setdefault(far, set()).add(el["hub"])
        elif el["ids"] is None and el["u"] and el["w"]:
            recon.setdefault(el["u"], set()).add(el["w"])
            recon.setdefault(el["w"], set()).add(el["u"])
    if recon != adj:
        bad = [v for v in adj if recon.get(v) != adj[v]][:5]
        failures.append(f"reconstructed adjacency mismatch at: {bad}")

    return "A. DOM structure matches real graph", failures


async def test_node_hover(page, adj):
    """B: hovering every vertex sets exactly the right data-near set and
    onpath flags."""
    els = await page.evaluate(DUMP_JS)
    labels = sorted(adj.keys())

    actual = await page.evaluate(
        """(labels) => {
            const svg = document.querySelector('svg.gdiagram');
            const h = svg.__ghDiagram;
            const gedges = Array.from(svg.querySelectorAll('.gedge'));
            const out = {};
            for (const label of labels) {
                const hit = svg.querySelector(`.ghit[data-v="${CSS.escape(label)}"]`);
                h.highlight(label, hit.getAttribute('cx'), hit.getAttribute('cy'));
                const near = Array.from(svg.querySelectorAll('.gnode[data-near="1"]')).map(n => n.getAttribute('data-v'));
                const flags = gedges.map(el => el.hasAttribute('data-onpath'));
                out[label] = { near, flags };
                h.clear();
            }
            return out;
        }""",
        labels,
    )

    failures = []
    for label in labels:
        expect_near = {label} | adj[label]
        got_near = set(actual[label]["near"])
        if got_near != expect_near:
            failures.append(
                f"{label}: near mismatch, expected {sorted(expect_near)} got {sorted(got_near)}"
            )
            continue
        flags = actual[label]["flags"]
        for i, el in enumerate(els):
            exp_onpath = onpath_expected(el, label)
            got_onpath = flags[i]
            if exp_onpath != got_onpath:
                failures.append(
                    f"{label}: element#{i} (hub={el['hub']} ids={el['ids']} "
                    f"u={el['u']} w={el['w']}) expected onpath={exp_onpath} "
                    f"got onpath={got_onpath}"
                )
            if len(failures) > 30:
                return "B. Node hover (104 vertices)", failures + ["... truncated"]

    return "B. Node hover (104 vertices)", failures


async def test_edge_hover(page, edges):
    """C: hovering every real edge (via highlightEdge, bypassing pointer
    geometry) sets exactly the right data-edgehover flags."""
    els = await page.evaluate(DUMP_JS)
    pair_list = [[u, v] for u, v in edges]

    actual = await page.evaluate(
        """(pairs) => {
            const svg = document.querySelector('svg.gdiagram');
            const h = svg.__ghDiagram;
            const gedges = Array.from(svg.querySelectorAll('.gedge'));
            const out = [];
            for (const [a, b] of pairs) {
                h.highlightEdge(a, b);
                out.push(gedges.map(el => el.hasAttribute('data-edgehover')));
                h.clear();
            }
            return out;
        }""",
        pair_list,
    )

    failures = []
    for idx, (u, v) in enumerate(edges):
        flags = actual[idx]
        for i, el in enumerate(els):
            exp_hit = edgehover_expected(el, u, v)
            got_hit = flags[i]
            if exp_hit != got_hit:
                failures.append(
                    f"edge {u}-{v}: element#{i} (hub={el['hub']} ids={el['ids']} "
                    f"u={el['u']} w={el['w']}) expected edgehover={exp_hit} "
                    f"got edgehover={got_hit}"
                )
            if len(failures) > 30:
                return "C. Edge hover (208 edges, direct)", failures + ["... truncated"]

    return "C. Edge hover (208 edges, direct)", failures


async def test_edge_geometry(page, edges):
    """D: every real edge must be hoverable from an actual cursor position
    near at least one endpoint's own geometry. Hovering exactly at a shared
    hub is expected to be ambiguous among its spokes, so only one endpoint
    needs to resolve correctly; segment choice is anchored on whichever
    endpoint docks nearest the owner's own node, not shortest segment
    length. Anything unreachable beyond known_unreachable_edges() fails.
    """
    known = known_unreachable_edges(edges)
    pair_list = [[u, v] for u, v in edges]

    results = await page.evaluate(
        """(pairs) => {
            const svg = document.querySelector('svg.gdiagram');
            const h = svg.__ghDiagram;
            const OFFSET = 6.5; // just past the 5.5px .ghit hit-circle radius

            function tryFrom(owner, other) {
                const op = h.pos[owner];
                if (!op) return false;
                const ox = parseFloat(op.cx), oy = parseFloat(op.cy);
                let best = null, bestDock = Infinity;
                for (const seg of h.hitSegments) {
                    if (!seg.labels.includes(owner)) continue;
                    const hasPair = seg.pairs.some(p => (p[0] === owner && p[1] === other) || (p[0] === other && p[1] === owner));
                    if (!hasPair) continue;
                    const d1 = (seg.x1 - ox) ** 2 + (seg.y1 - oy) ** 2;
                    const d2 = (seg.x2 - ox) ** 2 + (seg.y2 - oy) ** 2;
                    const [dock, nx, ny, fx, fy] = d1 <= d2
                        ? [d1, seg.x1, seg.y1, seg.x2, seg.y2]
                        : [d2, seg.x2, seg.y2, seg.x1, seg.y1];
                    if (dock < bestDock) { bestDock = dock; best = { nx, ny, fx, fy }; }
                }
                if (!best) return false;
                const len = Math.hypot(best.fx - best.nx, best.fy - best.ny);
                const t = len > 0 ? Math.min(OFFSET / len, 0.9) : 0;
                const x = best.nx + (best.fx - best.nx) * t;
                const y = best.ny + (best.fy - best.ny) * t;
                const r = h.resolveEdgeAt(x, y);
                return !!r && ((r.a === owner && r.b === other) || (r.a === other && r.b === owner));
            }

            return pairs.map(([a, b]) => ({ a, b, fromA: tryFrom(a, b), fromB: tryFrom(b, a) }));
        }""",
        pair_list,
    )

    found_unreachable = {
        frozenset((r["a"], r["b"]))
        for r in results
        if not r["fromA"] and not r["fromB"]
    }
    unexpected = found_unreachable - known
    now_reachable = known - found_unreachable

    failures = [
        f"edge {sorted(pair)}: unreachable from EITHER endpoint (new/unexpected)"
        for pair in unexpected
    ]
    failures += [
        f"edge {sorted(pair)}: expected to stay unreachable (known geometric-tie limitation) but is now reachable "
        "-- update known_unreachable_edges if this was an intentional fix"
        for pair in now_reachable
    ]
    note = (
        f"({len(known)} edges accepted as unreachable due to the port/connector-jog geometric tie documented above)"
        if not failures
        else ""
    )
    return (
        "D. Edge hover geometry (every edge hoverable from at least one end)",
        failures,
        note,
    )


async def test_clear_state(page):
    """E: clear() leaves no hover residue."""
    residue = await page.evaluate(
        """() => {
            const svg = document.querySelector('svg.gdiagram');
            const h = svg.__ghDiagram;
            h.highlight('C072', 0, 0);
            h.clear();
            const bad = [];
            if (svg.hasAttribute('data-hover')) bad.push('svg still has data-hover');
            svg.querySelectorAll('[data-near],[data-onpath],[data-edgehover]')
                .forEach(el => bad.push('residual attr on ' + (el.getAttribute('data-v') || el.className.baseVal)));
            return bad;
        }"""
    )
    return "E. clear() leaves no residue", residue


async def main():
    edges, adj = build_adjacency()
    assert len(edges) == 208 and len(adj) == 104

    async with async_playwright() as p:
        browser, page, page_errs = await get_page(p)
        try:
            results = []
            results.append(await test_structural(page, edges, adj))
            results.append(await test_node_hover(page, adj))
            results.append(await test_edge_hover(page, edges))
            results.append(await test_edge_geometry(page, edges))
            results.append(await test_clear_state(page))
        finally:
            await browser.close()

    ok = True
    for result in results:
        name, failures = result[0], result[1]
        note = result[2] if len(result) > 2 else ""
        status = "PASS" if not failures else f"FAIL ({len(failures)})"
        print(f"[{status}] {name}" + (f" {note}" if note else ""))
        for f in failures[:15]:
            print(f"    - {f}")
        if failures:
            ok = False
    if page_errs:
        print(f"[FAIL] page errors: {page_errs}")
        ok = False

    print()
    print("ALL PASS" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
