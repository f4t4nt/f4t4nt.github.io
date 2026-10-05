#!/usr/bin/env python3
"""Render the shared 1200x630 social card using the site's fonts and graph.

Requires Playwright and its Chromium browser. An existing Chromium installation
can be selected with --browser-path.
"""

import argparse
import pathlib

from generate_og_art import H as ART_H
from generate_og_art import W as ART_W
from generate_og_art import build_art
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og-card.png"
W, H = 1200, 630

HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@500&family=Source+Sans+3:wght@400;500&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; width: 1200px; height: 630px; overflow: hidden;
    background: #f6f9fd; color: #192b46;
    font-family: "Source Sans 3", sans-serif; position: relative;
  }
  h1, p { margin: 0; }
  .content { position: absolute; left: 72px; top: 201px; width: 800px; }
  h1 {
    font-family: Lora, Georgia, serif; font-weight: 500; font-size: 92px;
    line-height: 1.12; color: #2259cf; letter-spacing: -0.045em;
  }
  .content p { margin-top: 22px; font-size: 32px; line-height: 1.4; white-space: nowrap; }
  .content .role { margin-top: 10px; font-size: 24px; color: #536781; }
  .footer { position: absolute; bottom: 56px; left: 72px; font-size: 21px; color: #536781; }
  .art { position: absolute; top: 38px; right: 42px; width: 345px; height: 554px; }
  .art svg { width: 100%; height: 100%; }
</style>
</head><body>
  <div class="art">__ART__</div>
  <div class="content">
    <h1>Nishant Bhakar</h1>
    <p>I like competing and I love solving hard problems.</p>
    <p class="role">Making chips at Etched in San Jose, CA.</p>
  </div>
  <div class="footer">f4t4nt.github.io</div>
</body></html>
"""

FACES = ['500 92px "Lora"', '400 32px "Source Sans 3"']


def render(browser_path=None):
    art = (
        f'<svg viewBox="0 0 {ART_W} {ART_H}" xmlns="http://www.w3.org/2000/svg">'
        f'{build_art()}</svg>'
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=browser_path)
        try:
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            page.set_content(HTML.replace("__ART__", art), wait_until="networkidle")
            loaded = page.evaluate(
                "faces => Promise.all(faces.map(f => document.fonts.load(f).then(fonts => fonts.length)))",
                FACES,
            )
            assert all(loaded), f"webfonts unavailable: {loaded}"
            page.evaluate("document.fonts.ready")
            # Measure actual text rather than full-width paragraph boxes.
            fits = page.evaluate("""() => {
              const art = document.querySelector('.art').getBoundingClientRect();
              return [...document.querySelectorAll('.content h1, .content p')].every(el => {
                const range = document.createRange();
                range.selectNodeContents(el);
                const rects = [...range.getClientRects()];
                return rects.length === 1 && rects[0].right < art.left;
              });
            }""")
            assert fits, "Card text wraps or overlaps the graph"
            page.screenshot(path=str(OUT))
        finally:
            browser.close()
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-path", help="Path to an existing Chromium executable")
    args = parser.parse_args()
    render(args.browser_path)
