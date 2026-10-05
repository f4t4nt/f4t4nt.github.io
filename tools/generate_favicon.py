#!/usr/bin/env python3
"""Generate favicon.svg from Lora's variable TTF (requires fonttools).

Usage: python tools/generate_favicon.py /path/to/Lora.ttf
Font source: https://github.com/google/fonts/tree/main/ofl/lora
Outlines keep the tab icon independent of installed or downloaded webfonts.
"""

import argparse
import pathlib

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = pathlib.Path(__file__).resolve().parent.parent


def render(font_path):
    font = instantiateVariableFont(TTFont(font_path), {"wght": 500})
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    bounds = BoundsPen(glyphs)
    offset = 0
    placements = []
    for letter in "nb":
        glyph = glyphs[cmap[ord(letter)]]
        glyph.draw(TransformPen(bounds, (1, 0, 0, 1, offset, 0)))
        placements.append((glyph, offset))
        offset += glyph.width
    x0, y0, x1, y1 = bounds.bounds
    scale = min(50 / (x1 - x0), 42 / (y1 - y0))
    tx = 32 - scale * (x0 + x1) / 2
    ty = 32 + scale * (y0 + y1) / 2
    pen = SVGPathPen(glyphs)
    for glyph, offset in placements:
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, tx + offset * scale, ty)))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n'
        '  <rect width="64" height="64" rx="6" fill="#f6f9fd"/>\n'
        f'  <path fill="#2259cf" d="{pen.getCommands()}"/>\n'
        '</svg>\n'
    )
    (ROOT / "favicon.svg").write_text(svg)
    font.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=pathlib.Path)
    render(parser.parse_args().font)
