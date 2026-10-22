const katex = require("katex");
let buf = ""; process.stdin.on("data", d => buf += d).on("end", () => {
  const items = JSON.parse(buf);
  const out = items.map(({tex, display}) => {
    try { return katex.renderToString(tex, {displayMode: display, throwOnError: true, strict: "ignore",
        macros: {"\\ite": "\\operatorname{ite}"}}); }
    catch (e) { return "KATEX_ERROR:" + e.message.replace(/\n/g, " "); }
  });
  process.stdout.write(JSON.stringify(out));
});
