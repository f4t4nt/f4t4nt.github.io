import pathlib
import tempfile
import unittest

import build_site
import test_site


class BuildTest(unittest.TestCase):
    def test_stages_pages_without_changing_sources_or_viewers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            script = root / "script.js"
            script.write_text('window.siteReady = true;\n')
            output = root / "output"
            pages = [p for p in build_site.ROOT.rglob("*.html")
                     if p.relative_to(build_site.ROOT).parts[0] not in ("assets", "tools")]
            before = {p: p.read_bytes() for p in pages}
            build_site.build(output, script)
            self.assertEqual((output / "assets/site.js").read_bytes(), script.read_bytes())
            for path in pages:
                with self.subTest(page=path.name):
                    document = test_site.Document(output / path.relative_to(build_site.ROOT))
                    scripts = [attrs for tag, attrs in document.elements
                               if tag == "script" and attrs.get("src") == "/assets/site.js"]
                    self.assertEqual(len(scripts), 1)
                    self.assertIn("defer", scripts[0])
                    self.assertEqual(path.read_bytes(), before[path])
            for path in (build_site.ROOT / "assets").rglob("*"):
                if path.is_file():
                    with self.subTest(asset=path.name):
                        self.assertEqual(path.read_bytes(), (output / path.relative_to(build_site.ROOT)).read_bytes())
            self.assertFalse((output / ".git").exists())
            self.assertFalse((output / "tools").exists())

    def test_rejects_missing_or_empty_script_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            output = root / "output"
            script = root / "script.js"
            with self.assertRaises(FileNotFoundError):
                build_site.build(output, script)
            self.assertFalse(output.exists())
            script.write_text("\n")
            with self.assertRaises(ValueError):
                build_site.build(output, script)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
