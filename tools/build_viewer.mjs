import {build} from "esbuild";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import path from "node:path";

const output = path.resolve(process.argv[2] ?? "assets/asic-puzzle");
await mkdir(output, {recursive: true});

await build({
  absWorkingDir: import.meta.dirname,
  entryPoints: ["viewer-three.js"],
  bundle: true,
  format: "iife",
  minify: true,
  outfile: path.join(output, "viewer-three.js"),
  plugins: [{
    name: "gizmo-disposal-fix",
    setup(build) {
      let applied = false;
      build.onLoad({filter: /[/\\]three-viewport-gizmo\.js$/}, async ({path: modulePath}) => {
        const {version} = JSON.parse(await readFile(
          new URL("node_modules/three-viewport-gizmo/package.json", import.meta.url), "utf8"));
        const source = await readFile(modulePath, "utf8");
        // 2.2.0 removes children while iterating them, skipping half on each theme change.
        // Keep this patch pinned until the dependency fixes disposal upstream.
        const original = "this.detachControls(), this.children.forEach((n) => {";
        if (version !== "2.2.0" || source.split(original).length !== 2) {
          throw new Error("Review the three-viewport-gizmo disposal patch for this dependency version.");
        }
        applied = true;
        return {
          contents: source.replace(original, "this.detachControls(), [...this.children].forEach((n) => {"),
          loader: "js",
        };
      });
      build.onEnd(result => {
        if (!result.errors.length && !applied) {
          throw new Error("The three-viewport-gizmo disposal patch was not applied. Review its module path.");
        }
      });
    },
  }],
});
const licenses = await Promise.all(["three", "three-viewport-gizmo"].map(async name =>
  name + "\n" + await readFile(new URL("node_modules/" + name + "/LICENSE", import.meta.url))));
await writeFile(path.join(output, "viewer-three.LICENSE"), licenses.join("\n\n"));
