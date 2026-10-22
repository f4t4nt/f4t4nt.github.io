# /// script
# requires-python = ">=3.11"
# dependencies = ["nbclient", "nbformat", "jupyter-client", "ipykernel", "matplotlib", "gdstk", "shapely", "mapbox-earcut", "z3-solver", "k3d"]
# ///
"""Execute the solution repository's notebook and import its article assets.

Usage: uv run tools/execute_asic_notebook.py SOLUTION_CHECKOUT BUILD_DIRECTORY
"""
import argparse
import pathlib
import shutil
import sys
import tempfile

import jupyter_client
import nbclient
import nbformat

SITE = pathlib.Path(__file__).resolve().parent.parent
VIEWER_FILES = ("viewer.js", "viewer.css", "viewer-layers.js", "viewer-three.js", "viewer-three.LICENSE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("solution", type=pathlib.Path)
    parser.add_argument("build", type=pathlib.Path)
    args = parser.parse_args()
    source = args.solution.resolve()
    if not (source / "repo/puzzle.gds").is_file():
        raise FileNotFoundError(f"{source}/repo must contain the original puzzle submodule")
    args.build.mkdir(parents=True, exist_ok=True)
    path = source / "solution.ipynb"
    notebook = nbformat.read(path, as_version=4)
    # A fresh export directory cannot reintroduce figures removed from the notebook.
    with tempfile.TemporaryDirectory(prefix="notebook-", dir=args.build.resolve()) as directory:
        work = pathlib.Path(directory)
        (work / "repo").symlink_to(source / "repo", target_is_directory=True)
        figures = work / "figs"
        figures.mkdir()
        shutil.copyfile(source / "figs/viewer.html", figures / "viewer.html")
        for name in ("scene_export.py", *VIEWER_FILES):
            shutil.copyfile(source / name, work / name)
        kernel = jupyter_client.KernelManager(kernel_name="python3")
        kernel.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        client = nbclient.NotebookClient(
            notebook, km=kernel, timeout=1200, store_widget_state=False,
            resources={"metadata": {"path": str(work)}},
            on_cell_start=lambda cell, cell_index: print(f"Executing cell {cell_index}: {cell.id}", flush=True),
        )
        try:
            client.execute()
        finally:
            if kernel.has_kernel:
                kernel.shutdown_kernel(now=True)
            kernel.cleanup_resources()
        notebook.metadata.pop("widgets", None)
        for cell in notebook.cells:
            cell.metadata.pop("execution", None)
        assets = SITE / "assets/asic-puzzle"
        images = assets / "img"
        images.mkdir(exist_ok=True)
        exported = set()
        source_exports = set()
        for file in figures.iterdir():
            if file.suffix in (".svg", ".png"):
                destination = images / file.name
            elif file.name.endswith(".scene.json.gz") or (file.suffix == ".html" and file.name != "viewer.html"):
                destination = assets / file.name
            else:
                continue
            shutil.copyfile(file, destination)
            exported.add(destination)
            source_destination = source / "figs" / file.name
            shutil.copyfile(file, source_destination)
            source_exports.add(source_destination)
        # Only notebook exports live in img/ and these root-level asset formats.
        previous = [*images.glob("*.svg"), *images.glob("*.png"),
                    *assets.glob("*.scene.json.gz"), *assets.glob("*.html")]
        for file in previous:
            if file not in exported and file.name != "viewer.html":
                file.unlink()
        for file in (source / "figs").iterdir():
            if (
                (file.suffix in (".svg", ".png", ".html") or file.name.endswith(".scene.json.gz"))
                and file.name != "viewer.html"
                and file not in source_exports
            ):
                file.unlink()
        for name in VIEWER_FILES:
            shutil.copyfile(source / name, assets / name)
            shutil.copyfile(source / name, source / "figs" / name)
        shutil.copyfile(source / "figs/viewer.html", assets / "viewer.html")
        shutil.copyfile(source / "scene_export.py", SITE / "asic-puzzle/scene_export.py")
        for name in ("viewer-three.js", "build_viewer.mjs"):
            shutil.copyfile(source / "tools" / name, SITE / "tools" / name)
        nbformat.write(notebook, path)
        shutil.copyfile(path, SITE / "asic-puzzle/solution.ipynb")
        print(f"Executed {len(notebook.cells)} cells; imported {len(exported)} figure assets.")


if __name__ == "__main__":
    main()
