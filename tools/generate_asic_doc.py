# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4==4.14.3", "Pygments==2.19.2"]
# ///
"""Build both ASIC article URLs from the paper, canonical notebook and figures.

The paper supplies the narrative; selected notebook figures extend its explanations.
All notebook cells are paired with the corresponding sections in the code column.
"""
import argparse
import gzip
import html
import json
import pathlib
import re
import subprocess
import struct
import xml.etree.ElementTree as ET
import bs4
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer, VerilogLexer

FMT = HtmlFormatter(nowrap=True)


def hl(code, lang="python"):
    return highlight(code, VerilogLexer() if lang == "verilog" else PythonLexer(), FMT)


def image_dimensions(path):
    if path.suffix == ".png":
        return struct.unpack(">II", path.read_bytes()[16:24])
    root = ET.parse(path).getroot()
    dimensions = []
    for key in ("width", "height"):
        match = re.fullmatch(r"([\d.]+)(pt|px)?", root.attrib[key])
        dimensions.append(float(match[1]) * (4 / 3 if match[2] == "pt" else 1))
    return dimensions

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE.parent
TEX = SITE / "asic-puzzle/source/main.tex"
ASSETS = SITE / "assets/asic-puzzle"
EN_DASH = "\u2013"

unknown = set()
FIGNUM = {}

NB_CAPTIONS = {
    "ff-dependencies": "The 92 flip-flops and their dependencies, arranged by position on the die; the highlighted paths lead to success.",
}
VIEWER_CAPTIONS = {
    "die_layers": "The puzzle GDS seen from above, every layer at once. Hover a polygon or legend entry to isolate its layer.",
    "mux3d": "The mux's conducting and contact layers. Select a layer to isolate its polygons; the cube's Top face gives the corresponding plan view.",
    "puzzle3d": "The whole puzzle die. Conductors view assigns a color to each recovered net, with power and ground in gray. Hover a wire to isolate it; click to center it.",
    "puzzle_zoom3d": "A 30 by 24 micron zoom into the puzzle, full stack, with the cell footprints below.",
    "warmup_replay": "The warm-up circuit with editable 8-bit inputs. Highlighted digits mark the bits applied on the selected clock edge; the flip-flops light as their stored bits change.",
    "winning_run": "The winning run on the die: the unique input shifted in, then success and (* TWO STARS *).",
}
FIGURE_LEADS = {
    "mux3d": "We can inspect the conducting polygons and contacts either separately or as a stack. The contacts join conductors on adjacent layers; these vertical connections are as important as intersections within a layer.",
    "puzzle_zoom3d": "A close-up separates the routing layers from the cells beneath them. We retain this geometry when recovering connectivity, rather than treating intersections in a top-down projection as electrical connections.",
    "puzzle3d": "The recovered nets can also be inspected in the original geometry. The conductor view includes pin shapes as well as drawing polygons; the full stack supplies their physical context.",
    "warmup_replay": "We can now replay the sample tests on the recovered warm-up circuit. The flip-flop states change at the clock edges, while the combinational wires follow the current inputs and stored state.",
}
MATH = []   # (tex, display) rendered by KaTeX in one node call at the end


def queue_math(tex, display=False):
    MATH.append((tex, display))
    return f"\u0003{len(MATH) - 1}\u0004"

SYMBOLS = {r"\times": "\u00d7", r"\land": "\u2227", r"\lor": "\u2228", r"\neg": "\u00ac", r"\lnot": "\u00ac",
           r"\oplus": "\u2295", r"\to": "\u2192", r"\rightarrow": "\u2192", r"\Rightarrow": "\u21d2",
           r"\longmapsto": "\u27fc", r"\mapsto": "\u21a6", r"\iff": "\u27fa", r"\leq": "\u2264", r"\le": "\u2264",
           r"\geq": "\u2265", r"\ge": "\u2265", r"\neq": "\u2260", r"\ne": "\u2260", r"\ldots": "\u2026",
           r"\cdots": "\u22ef", r"\dots": "\u2026", r"\cdot": "\u00b7", r"\pm": "\u00b1", r"\in": "\u2208",
           r"\mid": "|", r"\wedge": "\u2227", r"\vee": "\u2228", r"\equiv": "\u2261", r"\colon": ":",
           r"\,": " ", r"\;": " ", r"\!": "", r"\quad": "  ", r"\qquad": "   ", r"\ ": " ", r"\%": "%",
           r"\&": "&amp;", r"\#": "#", r"\_": "_", r"\{": "{", r"\}": "}", r"\$": "$"}


def inline(s):
    """Inline LaTeX (text mode) to HTML."""
    s = re.sub(r"(?<!\\)%.*", "", s)
    while r"\footnote{" in s:
        i = s.index(r"\footnote{")
        j, depth = i + len(r"\footnote{"), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        s = s[:i] + s[j:]
    out, i = [], 0
    while i < len(s):
        if s[i] == "$":
            j = s.index("$", i + 1)
            out.append(("math", s[i + 1:j]))
            i = j + 1
        else:
            j = s.find("$", i)
            j = len(s) if j < 0 else j
            out.append(("text", s[i:j]))
            i = j
    parts = []
    for kind, t in out:
        if kind == "math":
            parts.append(queue_math(t))
            continue
        t = html.escape(t, quote=False)
        t = re.sub(r"Figure~?\\ref\{fig:([a-z-]+)\}", lambda m: f'<a href="#fig-{m.group(1)}">Figure {FIGNUM.get(m.group(1), "?")}</a>', t)
        t = t.replace("``", "\u201c").replace("''", "\u201d").replace("--", EN_DASH).replace("~", "&nbsp;")
        t = re.sub(r"\\texttt\{((?:[^{}]|\{[^{}]*\})*)\}", r"<code>\1</code>", t)
        t = re.sub(r"\\emph\{([^{}]*)\}", r"<em>\1</em>", t)
        t = re.sub(r"\\textit\{([^{}]*)\}", r"<em>\1</em>", t)
        t = re.sub(r"\\textbf\{([^{}]*)\}", r"<strong>\1</strong>", t)
        t = re.sub(r"\\href\{([^{}]*)\}\{([^{}]*)\}", lambda m: f'<a href="{m.group(1).replace(chr(92), "")}">{m.group(2)}</a>', t)
        t = re.sub(r"\\url\{([^{}]*)\}", r'<a href="\1">\1</a>', t)
        t = re.sub(r"\\(?:label|ref|cite|vspace)\{[^{}]*\}", "", t)
        for k, v in SYMBOLS.items():
            t = t.replace(html.escape(k, quote=False), v)
        for cmd in re.findall(r"\\[a-zA-Z]+", t):
            unknown.add("text:" + cmd)
        parts.append(t)
    return "".join(parts).strip()


def display_math(s):
    """A display-math block to KaTeX, keeping the LaTeX; the one @{} column spec becomes an explicit column."""
    s = s.strip()
    if r"@{\;\longmapsto\;}" in s:
        s = s.replace(r"\begin{array}{c@{\;\longmapsto\;}c}", r"\begin{array}{ccc}").replace("&", r"& \longmapsto &")
    return f'<div class="math">{queue_math(s, True)}</div>'


def parse_tex():
    full = TEX.read_text()
    body = full[full.index(r"\begin{document}") + len(r"\begin{document}"):full.index(r"\end{document}")]
    body = re.sub(r"\bn7(?![A-Za-z0-9])", "n237", body)
    bits = re.search(r"\\newcommand\{\\bits\}\{\\texttt\{\\seqsplit\{([01]+)\}\}\}", full).group(1)
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.S).group(1).strip()
    body = body[body.index(r"\end{abstract}") + len(r"\end{abstract}"):]
    items, pos = [], 0
    pattern = re.compile(
        r"\\(section|subsection)\{([^{}]*)\}|\\begin\{figure\}.*?\\end\{figure\}|\\begin\{(itemize|enumerate)\}.*?\\end\{\3\}|"
        r"\\begin\{lstlisting\}.*?\\end\{lstlisting\}|\\\[.*?\\\]|\\begin\{center\}.*?\\end\{center\}", re.S)

    def paras(chunk):
        for para in re.split(r"\n\s*\n", chunk):
            if para.strip():
                items.append(("p", para.strip()))

    for m in pattern.finditer(body):
        paras(body[pos:m.start()])
        tok = m.group(0)
        if m.group(1):
            items.append((m.group(1), m.group(2)))
        elif tok.startswith(r"\begin{figure}"):
            src = re.search(r"\\(?:input|includegraphics(?:\[[^\]]*\])?)\{figures/([^{}]*?)(?:\.tikz|\.pdf)?\}", tok).group(1)
            cap = re.search(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", tok).group(1)
            lab = re.search(r"\\label\{fig:([a-z-]+)\}", tok).group(1)
            FIGNUM.setdefault(lab, len(FIGNUM) + 1)
            items.append(("figure", (src, cap, lab)))
        elif tok.startswith(r"\begin{lstlisting}"):
            cap = re.search(r"caption=\{((?:[^{}]|\{[^{}]*\})*)\}", tok)
            code = re.sub(r"\\begin\{lstlisting\}(\[(?:[^\[\]]|\[[^\]]*\])*\])?|\\end\{lstlisting\}", "", tok).strip("\n")
            items.append(("listing", (code, cap.group(1) if cap else "")))
        elif tok.startswith(r"\["):
            items.append(("math", tok[2:-2]))
        elif tok.startswith(r"\begin{center}"):
            inner = re.sub(r"\\begin\{center\}|\\end\{center\}", "", tok).strip()
            if r"\begin{tabular}" in inner:
                rows = re.search(r"\\begin\{tabular\}\{(?:[^{}]|\{[^{}]*\})*\}(.*?)\\end\{tabular\}", inner, re.S).group(1)
                rows = [r for r in re.split(r"\\\\", re.sub(r"\\(toprule|midrule|bottomrule)", "", rows)) if r.strip()]
                items.append(("table", [[c.strip() for c in r.split("&")] for r in rows]))
            else:
                items.append(("center", inner))
        else:
            kind = m.group(3)
            inner = re.sub(r"\\begin\{%s\}(\[[^\]]*\])?|\\end\{%s\}" % (kind, kind), "", tok)
            items.append((kind, [x.strip() for x in re.split(r"\\item\s*", inner) if x.strip()]))
        pos = m.end()
    paras(body[pos:])
    return abstract, items, bits


NB_MAP = {
    "The warm-up as a running example": "The warm-up as a running example",
    "The puzzle": "What the file describes",
    "From GDS geometry to wires": "What the DSU represents logically",
    "Attaching names to components": "Attaching names to components",
    "From named cells to Boolean equations": "Translating the remaining cells",
    "Simulation": "Adding memory and the clock",
    "The example VCD": "Adding memory and the clock",
    "Turning the clocked circuit into one finite formula": "Turning a clocked circuit into one finite formula",
    "Star Battle": "Recovering the regions",
}


def md_inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]*)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def notebook_blocks(path):
    nb = json.loads(path.read_text())
    groups, code_groups, current = {}, {}, "Setup"
    seen_ids = set()
    for cell in nb["cells"]:
        cell_id = cell["id"]
        if cell_id in seen_ids:
            raise ValueError(f"Duplicate notebook cell ID: {cell_id}")
        seen_ids.add(cell_id)
        src = "".join(cell["source"])
        if cell["cell_type"] == "markdown":
            heads = [line for line in src.splitlines() if line.startswith("#")]
            if heads:
                title = heads[0].lstrip("#").strip()
                current = "Setup" if title.startswith("Jane Street") else NB_MAP.get(title, title)
            destination = cell["metadata"].get("article_section", current)
            rest = "\n".join(line for line in src.splitlines() if not line.startswith("#")).strip()
            if rest:
                code_groups.setdefault(destination, []).append(
                    f'<div class="source-cell" data-cell="{cell_id}">' +
                    "".join(f'<p>{md_inline(p.strip())}</p>' for p in re.split(r"\n\s*\n", rest) if p.strip()) + '</div>')
            continue
        if cell["cell_type"] != "code":
            raise ValueError(f"Unsupported notebook cell: {cell_id}")
        if not src.strip():
            raise ValueError(f"Empty notebook code cell: {cell_id}")
        destination = cell["metadata"].get("article_section", current)
        block = [f'<div class="source-cell" data-cell="{cell_id}"><pre><code>{hl(src.rstrip())}</code></pre>']
        texts = []
        for output in cell.get("outputs", []):
            if output["output_type"] == "error":
                raise ValueError(f"Notebook execution failed in {cell_id}")
            data = output.get("data", {})
            if "image/svg+xml" in data:
                caption = NB_CAPTIONS[cell_id]
                image = f"/assets/asic-puzzle/img/{cell_id}.svg"
                if not (SITE / image.lstrip("/")).exists():
                    raise FileNotFoundError(image)
                groups.setdefault(destination, []).append(
                    f'<figure class="nbfig wide"><img src="{image}" alt="{html.escape(caption)}" loading="lazy">'
                    f'<figcaption>{caption}</figcaption></figure>')
            elif "image/png" in data:
                raise ValueError(f"Unexpected raster plot in {cell_id}")
            elif output["output_type"] == "stream":
                texts.append("".join(output.get("text", [])))
            elif "text/plain" in data and "text/html" not in data:
                texts.append("".join(data["text/plain"]))
            if "text/html" in data:
                document = bs4.BeautifulSoup("".join(data["text/html"]), "html.parser")
                for frame in document.select("iframe[src]"):
                    name = pathlib.PurePosixPath(frame["src"]).stem
                    if frame["src"] != f"figs/{name}.html" or name not in VIEWER_CAPTIONS:
                        raise ValueError(f"Unexpected notebook viewer: {frame['src']}")
                    caption = VIEWER_CAPTIONS[name]
                    if name in FIGURE_LEADS:
                        groups.setdefault(destination, []).append(f'<p>{FIGURE_LEADS[name]}</p>')
                    groups.setdefault(destination, []).append(
                        f'<figure class="viewer wide" data-view="{name}"><iframe src="/assets/asic-puzzle/{name}.html" '
                        f'title="{html.escape(caption)}"></iframe><figcaption>{caption}</figcaption></figure>')
        if texts:
            block.append(f'<pre class="out"><code>{html.escape("".join(texts).rstrip())}</code></pre>')
        block.append("</div>")
        code_groups.setdefault(destination, []).append("".join(block))
    for heading, blocks in code_groups.items():
        if heading == "Attaching names to components":
            groups.setdefault(heading, []).append(
                '<p class="bridge">Net IDs are assigned during extraction and can differ between executions. '
                'The wire from <code>sr_a/_11_.X</code> to <code>sr_a/_19_.D</code> is labeled '
                '<code>n237</code> in the write-up; its endpoints identify the same wire in the notebook.</p>')
        groups.setdefault(heading, []).append(
            '<details class="code"><summary>Notebook</summary>' + "".join(blocks) + "</details>")
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("solution", type=pathlib.Path, help="Canonical solution checkout")
    args = parser.parse_args()
    notebook = args.solution / "solution.ipynb"
    if notebook.read_bytes() != (SITE / "asic-puzzle/solution.ipynb").read_bytes():
        raise ValueError("Notebook changed; run execute_asic_notebook.py before generating the article")
    abstract, items, bits = parse_tex()
    groups = notebook_blocks(notebook)
    parts = []
    pending = None
    excluded = False
    for kind, payload in items:
        if kind == "section":
            excluded = payload == "AI policy"
        if excluded:
            continue
        if kind in ("section", "subsection"):
            if pending in groups:
                parts.extend(groups.pop(pending))
            pending = payload
            tag = "h2" if kind == "section" else "h3"
            parts.append(f"<{tag}>{inline(payload)}</{tag}>")
        elif kind == "p":
            parts.append(f"<p>{inline(payload)}</p>")
        elif kind == "figure":
            src, caption, label = payload
            if src == "recovered-board" and pending in groups:
                parts.extend(groups.pop(pending))
            parts.append(f'<figure class="paper-figure" id="fig-{label}"><img src="/assets/asic-puzzle/fig/{src}.svg" alt="{html.escape(caption)}"><figcaption>{inline(caption)}</figcaption></figure>')
        elif kind == "listing":
            code, caption = payload
            language = "verilog" if "always @" in code else "python"
            parts.append(f'<figure class="listing"><figcaption>{inline(caption)}</figcaption><pre><code>{hl(code, language)}</code></pre></figure>')
        elif kind == "math":
            parts.append(display_math(payload))
        elif kind == "table":
            head, *rows = payload
            parts.append('<table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                         + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows) + "</tbody></table>")
        elif kind == "center":
            if r"\bits" in payload:
                parts.append(f'<p class="bits">{bits}</p>')
            else:
                value = inline(re.sub(r"\\(parbox|Large|small)\{[^{}]*\}|\\(Large|small)", "", payload))
                parts.append(f'<p class="center">{value}</p>')
        else:
            tag = "ul" if kind == "itemize" else "ol"
            parts.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in payload) + f"</{tag}>")
    if pending in groups:
        parts.extend(groups.pop(pending))
    setup = "".join(groups.pop("Setup", []))
    if groups:
        raise ValueError(f"Unplaced notebook groups: {list(groups)}")
    body = bs4.BeautifulSoup("\n".join(parts), "html.parser")
    contents = []
    for index, heading in enumerate(body.select("h2"), 1):
        heading["id"] = f"section-{index}"
        contents.append(f'<li><a href="#section-{index}">{heading.get_text()}</a></li>')
    dependencies = body.select_one('img[src$="/ff-dependencies.svg"]').find_parent("figure")
    audit = next(p for p in body.select("p") if "backward fan-in audit" in p.get_text())
    audit.insert_after(dependencies.extract())
    figure_number = 0
    for figure in body.select("figure:not(.listing)"):
        img = figure.find("img")
        if img:
            img["draggable"] = "false"
            path = pathlib.PurePosixPath(img["src"])
            width, height = image_dimensions(SITE / str(path).lstrip("/"))
            img["width"], img["height"] = str(round(width)), str(round(height))
            img["style"] = f"--image-width: {width}px; aspect-ratio: {width} / {height}"
            dark = path.with_name(path.stem + "-dark" + path.suffix)
            if not (SITE / str(dark).lstrip("/")).exists():
                raise ValueError(f"Missing dark figure: {dark}; re-run the notebook or paper renderer")
            img["data-light-src"] = str(path)
            img["data-dark-src"] = str(dark)
            figure["data-plot"] = path.stem
        caption = figure.find("figcaption")
        if not caption:
            raise ValueError("Figure without a caption")
        figure_number += 1
        caption.insert(0, f"Figure {figure_number}. ")
        if "paper-figure" in figure.get("class", []):
            for link in body.select(f'a[href="#{figure["id"]}"]'):
                link.string = f"Figure {figure_number}"
        else:
            caption["class"] = ["bridge"]
        frame = figure.find("iframe")
        if frame:
            frame["height"] = "620"
            name = pathlib.PurePosixPath(frame["src"]).stem
            if name in ("winning_run", "die_layers"):
                figure["data-canvas-ratio"] = ""
                if name == "die_layers":
                    scene = json.loads(gzip.decompress((ASSETS / f"{name}.scene.json.gz").read_bytes()))
                    x0, y0, x1, y1 = scene["bounds"]
                    figure["style"] = f"--canvas-ratio: {(x1 - x0) / (y1 - y0)}; --viewer-extra-height: 78px"
                else:
                    document = (ASSETS / f"{name}.html").read_text().split("<script>", 1)[0]
                    canvas = bs4.BeautifulSoup(document, "html.parser").find("canvas")
                    width, height = int(canvas["width"]) / 2, int(canvas["height"]) / 2
                    figure["style"] = f"--canvas-width: {width}px; --canvas-ratio: {height / width}; --viewer-extra-height: 153px"
            frame["data-src"] = frame["src"]
            del frame["src"]
    # Pair each explanation with its own notebook cells, keeping document order
    # and anchors identical in both reading modes.
    section = narrative = None
    for element in list(body.contents):
        if isinstance(element, bs4.Tag) and element.name in ("h2", "h3"):
            section = body.new_tag("section", attrs={"class": "article-section"})
            element.insert_before(section)
            section.append(element.extract())
            narrative = body.new_tag("div", attrs={"class": "section-narrative"})
            section.append(narrative)
        elif section is not None:
            if isinstance(element, bs4.Tag) and "code" in element.get("class", []):
                rail = body.new_tag("aside", attrs={"class": "section-notebook", "aria-label": "Notebook implementation"})
                rail.append(element.extract())
                section.append(rail)
                section["class"].append("has-notebook")
            else:
                narrative.append(element.extract())
    for section in body.select(".article-section"):
        narrative = section.select_one(".section-narrative")
        if not narrative.get_text(strip=True) and not narrative.find():
            narrative.decompose()
            section["class"].append("section-heading")
    first_section = body.select_one(".article-section")
    setup_rail = body.new_tag("aside", attrs={"class": "section-notebook", "aria-label": "Notebook setup"})
    setup_content = bs4.BeautifulSoup(setup, "html.parser")
    setup_content.select_one("details.code summary").string = "Setup"
    setup_rail.append(setup_content)
    first_section.append(setup_rail)
    first_section["class"].append("has-notebook")
    for detail in body.select("details.code"):
        subject = "setup" if detail.find_parent("aside").get("aria-label") == "Notebook setup" else "code"
        detail.summary.clear()
        label = body.new_tag("span", attrs={"class": "code-label", "data-subject": subject})
        label.string = f"View {subject}"
        count = body.new_tag("span", attrs={"class": "code-count"})
        count.string = f'{len(detail.select(".source-cell"))} cells'
        detail.summary.extend([label, count])
        group = body.new_tag("div", attrs={"class": "code-group"})
        detail.wrap(group)
        control = body.new_tag("button", attrs={"class": "expand-code", "type": "button"})
        control.string = "Expand all code"
        group.insert(0, control)
    home = bs4.BeautifulSoup((SITE / "index.html").read_text(), "html.parser")
    theme_button = str(home.select_one(".theme-toggle"))
    page = f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jane Street ASIC Puzzle 2026 · Nishant Bhakar</title>
<meta name="description" content="From GDS geometry to Boolean equations, a unique 121-bit input, and a hidden Star Battle board. The full write-up with interactive figures and notebook code.">
<link rel="canonical" href="https://f4t4nt.github.io/asic-puzzle"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<script src="/assets/theme.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Lora:ital,wght@0,500;1,400&family=Source+Sans+3:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/assets/asic-puzzle/article.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.css" crossorigin="anonymous">
<script defer src="/assets/asic-puzzle/article.js"></script></head>
<body class="asic-page read-with-code"><a class="skip-link" href="#article">Skip to write-up</a><div class="article-shell">
<header class="article-top"><a href="/">Nishant Bhakar</a><div><a href="/assets/asic-puzzle/writeup.pdf">PDF</a><a href="https://github.com/f4t4nt/jane-street-asic-puzzle-2026">Source</a>{theme_button}</div></header>
<div class="article-layout"><aside class="contents"><nav aria-label="Contents"><a class="contents-title" href="#top">Contents</a><ol>{''.join(contents)}</ol></nav></aside>
<main id="article"><header class="article-heading" id="top"><p class="article-date">August 7th, 2026</p><hgroup><h1>Jane Street ASIC Puzzle 2026</h1><p class="article-subtitle">My solution to <a href="https://blog.janestreet.com/can-you-reverse-engineer-an-asic/">Jane Street’s ASIC reverse-engineering puzzle</a>.</p></hgroup><p class="abstract">{inline(abstract)}</p>
</header>
<article class="paper">{body}</article>
<a class="back" href="/">← Back to home</a></main></div></div></body></html>'''
    rendered = json.loads(subprocess.run(
        ["node", str(HERE / "render_math.js")],
        input=json.dumps([{"tex": tex, "display": display} for tex, display in MATH]),
        capture_output=True, text=True, check=True,
    ).stdout)
    if any(value.startswith("KATEX_ERROR") for value in rendered):
        raise ValueError([value for value in rendered if value.startswith("KATEX_ERROR")])
    page = re.sub("\u0003(\\d+)\u0004", lambda match: rendered[int(match[1])], page)
    if unknown:
        raise ValueError(f"Unrecognized LaTeX: {sorted(unknown)}")
    for path in (SITE / "asic-puzzle.html", SITE / "asic-puzzle/index.html"):
        path.write_text(page)
    print(f"Generated both URLs: {figure_number} figures, {len(MATH)} math expressions.")


if __name__ == "__main__":
    main()
