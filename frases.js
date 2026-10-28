/* Prints one relationship sentence per distinct label, as the app shows them, for a language.
   Usage: node frases.js <lang>   (es uses the inline Spanish overrides from index.html) */
const fs = require("fs"), vm = require("vm"), path = require("path");
const lang = process.argv[2], dir = path.join(__dirname, "biblia");
const ctx = { window: {} }; ctx.window.window = ctx.window; vm.createContext(ctx);
const run = (src, f) => vm.runInContext(src, ctx, { filename: f });
run(fs.readFileSync(path.join(dir, "timeline.js"), "utf8"), "timeline.js");
run(fs.readFileSync(path.join(dir, "people.js"), "utf8"), "people.js");
ctx.window.HI18N = {}; ctx.HI18N = ctx.window.HI18N;
// Spanish overrides live inline in index.html between these markers.
const html = fs.readFileSync(path.join(dir, "index.html"), "utf8");
const m = html.match(/\/\* ES-UI \*\/([\s\S]*?)\/\* \/ES-UI \*\//); if (m) run(m[1], "es-ui");
if (lang !== "es") run(fs.readFileSync(path.join(dir, "i18n", lang + ".js"), "utf8"), lang);
const H = ctx.window.HI18N[lang] || {}, ui = H.ui || {}, PP = ctx.window.PP;
const tr = (k, ...a) => { const t = ui[k] ?? k; const r = t.replace(/\{(\d)\}/g, (_, i) => a[i]);
  if (lang === "fr") return r.replace(/\b([dD])e ([AEIOUYÉÈÊÎÔaeiouyéèêîô])/g, "$1’$2");
  if (lang === "de") return r.replace(/\b(von|mit) (\S+) der Täufer\b/g, "$1 $2 dem Täufer");
  return r };  // keep in sync with tr() in biblia/index.html
const name = id => (H.PP?.[id]?.n) || PP[id].n, seen = new Set();
for (const [a, b, l] of ctx.window.PR) { if (seen.has(l)) continue; seen.add(l);
  console.log(tr("{0} es {1} {2}", name(a), tr(l), name(b))) }
