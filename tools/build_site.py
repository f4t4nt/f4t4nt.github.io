"""Stage the static site with a deployment-supplied script."""

import argparse
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parent.parent


def build(output, script):
    source = script.read_text()
    if not source.strip():
        raise ValueError("The site script must not be empty")
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("assets", "graph", "asic-puzzle"):
        shutil.copytree(ROOT / directory, output / directory)
    for pattern in ("*.html", "*.css", "favicon.svg", "robots.txt", "sitemap.xml"):
        for path in ROOT.glob(pattern):
            shutil.copy2(path, output / path.name)
    (output / "assets/site.js").write_text(source)
    for path in output.rglob("*.html"):
        if path.relative_to(output).parts[0] == "assets":
            continue
        html = path.read_text()
        if html.count("</head>") != 1:
            raise ValueError(f"Expected one closing head tag: {path}")
        path.write_text(html.replace("</head>", '<script defer src="/assets/site.js"></script>\n</head>'))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--script", type=pathlib.Path, required=True)
    args = parser.parse_args()
    build(args.output, args.script)
