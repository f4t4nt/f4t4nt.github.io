#!/usr/bin/env python3
"""End-to-end test for figure 3's pinning, against the rendered /graph page.

    python3 tools/test_pick.py [http://localhost:8000/graph.html]

The ground truth is the edge record, read here directly: a path the page
traces has to be a real walk in that graph, and as short as the record allows.
"""

import asyncio
import collections
import itertools
import pathlib
import sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from generate_graph import parse_edges

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/graph.html"

BOARD = "#fullgraph"
OTHER = ".gdiagram:not(#fullgraph)"


def true_graph():
    adj = collections.defaultdict(set)
    for u, v in parse_edges():
        adj[u].add(v)
        adj[v].add(u)
    return {k: sorted(vs) for k, vs in adj.items()}


def all_distances(adj):
    dist = {}
    for src in adj:
        d = {src: 0}
        queue = collections.deque([src])
        while queue:
            v = queue.popleft()
            for n in adj[v]:
                if n not in d:
                    d[n] = d[v] + 1
                    queue.append(n)
        dist[src] = d
    return dist


async def board_handle(page):
    return await page.evaluate_handle(f"document.querySelector('{BOARD}').__ghDiagram")


async def test_paths(page, adj, dist):
    """Every pair: the page's path is a real walk, and it is a shortest one."""
    paths = await page.evaluate(
        f"""() => {{
          const h = document.querySelector('{BOARD}').__ghDiagram;
          const vs = Object.keys(h.pos).sort();
          const out = [];
          for (let i = 0; i < vs.length; i++)
            for (let j = i + 1; j < vs.length; j++)
              out.push([vs[i], vs[j], h.shortestPath(vs[i], vs[j])]);
          return out;
        }}"""
    )
    failures = []
    for a, b, path in paths:
        if not path:
            failures.append(f"{a}->{b}: no path")
            continue
        if path[0] != a or path[-1] != b:
            failures.append(f"{a}->{b}: path runs {path[0]}..{path[-1]}")
            continue
        broken = [
            (x, y) for x, y in itertools.pairwise(path) if y not in adj.get(x, ())
        ]
        if broken:
            failures.append(f"{a}->{b}: {broken[0]} is not an edge")
            continue
        if len(path) - 1 != dist[a][b]:
            failures.append(f"{a}->{b}: {len(path) - 1} hops, shortest is {dist[a][b]}")
    return (
        f"A. Shortest paths ({len(paths)} pairs, diameter {max(max(d.values()) for d in dist.values())})",
        failures,
    )


async def flags(page, sel=BOARD):
    return await page.evaluate(
        f"""() => {{
          const svg = document.querySelector('{sel}');
          const pick = a => Array.from(svg.querySelectorAll('.gnode[' + a + '="1"]'))
            .map(e => e.getAttribute('data-v')).sort();
          return {{
            pinned: svg.getAttribute('data-pinned'),
            hover: svg.getAttribute('data-hover'),
            near: pick('data-near'),
            active: pick('data-active'),
            pin: pick('data-pin'),
            onpath: svg.querySelectorAll('.gedge[data-onpath="1"]').length,
            edgehover: svg.querySelectorAll('.gedge[data-edgehover="1"]').length,
            ingroup: svg.querySelectorAll('.gedge[data-ingroup="1"]').length,
          }};
        }}"""
    )


async def click(page, v):
    await page.click(f'{BOARD} .ghit[data-v="{v}"]', force=True)


async def hover(page, v):
    await page.hover(f'{BOARD} .ghit[data-v="{v}"]', force=True)


async def test_pin_cycle(page, dist):
    """Click pins, hover traces, clicking the same vertex lets go."""
    failures = []
    a, b, c = "A.L1", "C.R4", "B.P23"

    await click(page, a)
    st = await flags(page)
    if st["pinned"] != "1" or st["pin"] != [a] or st["near"] != [a]:
        failures.append(f"pinning {a} gave {st}")

    await hover(page, b)
    st = await flags(page)
    if st["active"] != sorted([a, b]):
        failures.append(f"hover {b} while pinned: active={st['active']}")
    if st["pin"] != [a]:
        failures.append(f"hover {b} while pinned: pin={st['pin']}")
    if len(st["near"]) != dist[a][b] + 1:
        failures.append(
            f"{a}->{b} lit {len(st['near'])} vertices, path has {dist[a][b] + 1}"
        )

    # a second click moves the source rather than adding one
    await click(page, c)
    st = await flags(page)
    if st["pin"] != [c] or st["near"] != [c]:
        failures.append(f"re-pinning to {c} gave {st}")

    # and clicking it again lets go, back to a plain hover of that vertex
    await click(page, c)
    st = await flags(page)
    if st["pinned"] is not None or st["pin"]:
        failures.append(f"unpinning {c} left {st}")
    if len(st["near"]) != 5:
        failures.append(f"after unpin, hover of {c} lit {len(st['near'])}, want 5")

    await page.keyboard.press("Escape")
    return "B. Pin, trace, re-pin, release", failures


async def test_pin_suppresses(page):
    """While a vertex is held, edges and silkscreen names stay quiet."""
    failures = []
    await click(page, "A.L1")

    label = page.locator(f"{BOARD} .glabel").first
    if await label.count():
        await label.hover(force=True)
        st = await flags(page)
        if st["ingroup"] or st["pin"] != ["A.L1"]:
            failures.append(f"group name answered while pinned: {st}")

    # park the pointer over a cable rather than a pad
    box = await page.locator(f"{BOARD}").bounding_box()
    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    st = await flags(page)
    if st["edgehover"]:
        failures.append(f"edge answered while pinned: {st}")
    if st["pin"] != ["A.L1"]:
        failures.append(f"pin lost to a pointermove: {st}")

    await page.keyboard.press("Escape")
    st = await flags(page)
    if st["pinned"] is not None:
        failures.append(f"Escape did not release: {st}")
    return "C. A held vertex silences edges and names", failures


async def test_other_figures(page):
    """Figures 1 and 2 are hover-only: no pointer, and a click does nothing."""
    failures = []
    n = await page.locator(OTHER).count()
    for i in range(n):
        svg = page.locator(OTHER).nth(i)
        if await svg.get_attribute("data-pick"):
            failures.append(f"figure {i + 1} is marked pickable")
        hit = svg.locator(".ghit").first
        if not await hit.count():
            continue
        cursor = await hit.evaluate("el => getComputedStyle(el).cursor")
        if cursor == "pointer":
            failures.append(f"figure {i + 1} shows a pointer cursor")
        await hit.click(force=True)
        if await svg.get_attribute("data-pinned"):
            failures.append(f"figure {i + 1} pinned on click")
    board_cursor = await page.locator(f"{BOARD} .ghit").first.evaluate(
        "el => getComputedStyle(el).cursor"
    )
    if board_cursor != "pointer":
        failures.append(f"board vertices show cursor {board_cursor!r}, want pointer")
    edge_cursor = await page.locator(f"{BOARD} .gedge").first.evaluate(
        "el => getComputedStyle(el).cursor"
    )
    if edge_cursor == "pointer":
        failures.append("board cables show a pointer cursor")
    return "D. Only the board takes a click", failures


async def main():
    adj = true_graph()
    dist = all_distances(adj)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 1200})
        await page.goto(URL)
        await page.wait_for_timeout(400)
        if not await page.evaluate(
            f"!!(document.querySelector('{BOARD}') || {{}}).__ghDiagram"
        ):
            print("figure 3 never initialized")
            await browser.close()
            return 1

        results = [
            await test_paths(page, adj, dist),
            await test_pin_cycle(page, dist),
            await test_pin_suppresses(page),
            await test_other_figures(page),
        ]
        await browser.close()

    bad = 0
    for name, failures in results:
        if failures:
            bad += 1
            print(f"[FAIL] {name}")
            for line in failures[:8]:
                print("   ", line)
        else:
            print(f"[PASS] {name}")
    print("\n" + ("ALL PASS" if not bad else f"{bad} FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
