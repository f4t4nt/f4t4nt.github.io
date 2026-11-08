"""Check published pages and local links: python3 -m unittest discover -s tools -p test_site.py."""

import html.parser
import pathlib
import unittest
import urllib.parse
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parent.parent
ORIGIN = "https://f4t4nt.github.io"


class Document(html.parser.HTMLParser):
    """Collect actual HTML elements, excluding escaped notebook source code."""

    def __init__(self, path):
        super().__init__()
        self.elements = []
        self.ids = set()
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if "id" in attrs:
            self.ids.add(attrs["id"])


def resolve(url):
    path = ROOT / urllib.parse.unquote(urllib.parse.urlsplit(url).path).lstrip("/")
    if path.is_dir():
        return path / "index.html"
    if not path.suffix:
        return path.with_suffix(".html")
    return path


class SiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sitemap = ET.parse(ROOT / "sitemap.xml")
        cls.urls = [node.text for node in sitemap.findall(".//{*}loc")]
        cls.pages = {url: Document(resolve(url)) for url in cls.urls}

    def test_page_metadata(self):
        self.assertTrue(self.urls)
        for url, page in self.pages.items():
            with self.subTest(url=url):
                canonical = [a["href"] for t, a in page.elements
                             if t == "link" and a.get("rel") == "canonical"]
                self.assertEqual(canonical, [url])

    def test_article_aliases_are_identical(self):
        for url in self.urls:
            if url == ORIGIN + "/":
                continue
            path = urllib.parse.urlsplit(url).path.lstrip("/")
            with self.subTest(url=url):
                self.assertEqual((ROOT / f"{path}.html").read_bytes(),
                                 (ROOT / path / "index.html").read_bytes())

    def test_local_links_assets_and_fragments(self):
        documents = dict(self.pages)
        for url, page in self.pages.items():
            for tag, attrs in page.elements:
                for key in ("href", "src", "data-src"):
                    if key not in attrs:
                        continue
                    target = urllib.parse.urljoin(url, attrs[key])
                    parts = urllib.parse.urlsplit(target)
                    if parts.scheme not in ("http", "https") or parts.netloc != "f4t4nt.github.io":
                        continue
                    with self.subTest(page=url, target=target):
                        path = resolve(target)
                        self.assertTrue(path.is_file(), f"Missing local target: {target}")
                        if parts.fragment and path.suffix == ".html":
                            base = urllib.parse.urlunsplit(parts._replace(fragment="", query=""))
                            if base not in documents:
                                documents[base] = Document(path)
                            self.assertIn(urllib.parse.unquote(parts.fragment), documents[base].ids)
                if tag == "iframe":
                    self.assertTrue(attrs.get("title"), f"Untitled viewer on {url}")

if __name__ == "__main__":
    unittest.main()
