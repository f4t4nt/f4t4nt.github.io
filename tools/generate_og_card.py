#!/usr/bin/env python3
"""Renders assets/og-card.png (1200x630) via a headless browser, so the card's
type matches the site's actual fonts exactly.
"""

import pathlib

from generate_og_art import H as ART_H
from generate_og_art import W as ART_W
from generate_og_art import build_art
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og-card.png"

KICKER = "NISHANT BHAKAR"
HEADLINE = "Making chips at Etched"
SUBTITLE = "I like competing and I love solving hard problems."
FOOTER = "f4t4nt.github.io"

W, H = 1200, 630
TEXT_MAX_WIDTH = 620  # keep type clear of the art panel that starts around x=680

HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper: #fbfaf8;
    --ink: #101215;
    --muted: #6b7078;
    --rule: #dcd8d2;
    --accent: #c8102e;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    width: {w}px; height: {h}px;
    background: var(--paper);
    color: var(--ink);
    font-family: "IBM Plex Sans", sans-serif;
    position: relative;
    overflow: hidden;
  }}
  .art {{
    position: absolute; right: 0; top: 0; width: 520px; height: {h}px;
    overflow: hidden;
    opacity: 0.85;
  }}
  .art svg {{ width: 100%; height: 100%; display: block; }}
  .content {{
    position: absolute; left: 84px; top: 152px; bottom: 130px; width: 640px;
    display: flex; flex-direction: column; justify-content: center;
    align-items: flex-start;
    gap: 30px;
  }}
  .badge {{
    position: absolute; left: 84px; top: 64px;
    width: 56px; height: 56px; border-radius: 12px;
    background: var(--ink);
    color: var(--paper);
    font-family: "IBM Plex Mono", monospace;
    font-weight: 500;
    font-size: 24px;
    display: flex; align-items: center; justify-content: center;
  }}
  .kicker {{
    font-family: "IBM Plex Mono", monospace;
    font-size: 22px;
    letter-spacing: 0.14em;
    color: var(--muted);
  }}
  .headline {{
    font-size: {headline_size}px;
    font-weight: 700;
    line-height: 1.08;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }}
  .subtitle {{
    font-size: {subtitle_size}px;
    line-height: 1.45;
    color: var(--ink);
    white-space: nowrap;
  }}
  .rule {{
    position: absolute; left: 84px; right: 84px; bottom: 84px;
    height: 1px;
    background: linear-gradient(
      to right, var(--rule) 0%, var(--rule) 45%, transparent 63%
    );
  }}
  .footer {{
    position: absolute; left: 84px; bottom: 40px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 19px;
    color: var(--muted);
  }}
</style>
</head><body>
  <div class="art"><svg viewBox="0 0 {art_w} {art_h}" preserveAspectRatio="xMaxYMid meet" xmlns="http://www.w3.org/2000/svg">{art_markup}</svg></div>
  <div class="badge">nb</div>
  <div class="content">
    <div class="kicker">{kicker}</div>
    <div class="headline">{headline}</div>
    <div class="subtitle">{subtitle}</div>
  </div>
  <div class="rule"></div>
  <div class="footer">{footer}</div>
</body></html>
"""


# the faces the card actually sets, as CSS font shorthand. Measuring type
# before these have arrived silently measures a fallback instead.
FACES = [
    '700 58px "IBM Plex Sans"',
    '400 28px "IBM Plex Sans"',
    '500 24px "IBM Plex Mono"',
    '400 19px "IBM Plex Mono"',
]


def _await_fonts(page):
    """Block until the webfonts are in, and fail loudly if they never come.
    Both the shrink-to-fit measurements and the screenshot depend on the real
    metrics; a fallback face renders a card that looks almost right, so the
    failure has to be raised rather than waited out."""
    page.evaluate(
        "faces => Promise.all(faces.map(f => document.fonts.load(f)))"
        ".then(() => document.fonts.ready)",
        FACES,
    )
    missing = page.evaluate(
        "faces => faces.filter(f => !document.fonts.check(f))", FACES
    )
    assert not missing, f"webfonts unavailable: {missing}"


def _shrink_to_fit(page, selector, size, min_size, max_width):
    box = page.eval_on_selector(selector, "el => el.getBoundingClientRect()")
    while box["width"] > max_width and size > min_size:
        size -= 1
        page.eval_on_selector(selector, f"el => el.style.fontSize = '{size}px'")
        box = page.eval_on_selector(selector, "el => el.getBoundingClientRect()")
    return size, box["width"]


def render(headline_size=58, subtitle_size=28):
    art_markup = build_art()

    html = HTML.format(
        w=W,
        h=H,
        kicker=KICKER,
        headline=HEADLINE,
        subtitle=SUBTITLE,
        footer=FOOTER,
        headline_size=headline_size,
        subtitle_size=subtitle_size,
        art_w=ART_W,
        art_h=ART_H,
        art_markup=art_markup,
    )
    html_path = ROOT / "tools" / "_og_card_preview.html"
    html_path.write_text(html)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": W, "height": H}, device_scale_factor=2
        )
        page.goto(f"file://{html_path}")
        _await_fonts(page)

        # both lines must fit on one row each, clear of the art panel
        headline_size, headline_w = _shrink_to_fit(
            page, ".headline", headline_size, 40, TEXT_MAX_WIDTH
        )
        subtitle_size, subtitle_w = _shrink_to_fit(
            page, ".subtitle", subtitle_size, 16, TEXT_MAX_WIDTH
        )

        page.screenshot(path=str(OUT))
        browser.close()

    from PIL import Image

    img = Image.open(OUT).resize((W, H), Image.LANCZOS)
    img.save(OUT)
    html_path.unlink()
    print(
        f"wrote {OUT} (headline {headline_size}px/{headline_w:.0f}px, "
        f"subtitle {subtitle_size}px/{subtitle_w:.0f}px)"
    )


if __name__ == "__main__":
    render()
