/* Loads the app's History data and its real tr()/rel() functions into a Node sandbox, for the dev scripts.
   tr/rel are taken from the /* TR *​/ block of biblia/index.html, so there is no second copy to keep in sync. */
const fs = require("fs"), vm = require("vm"), path = require("path");
const DIR = path.join(__dirname, "biblia");
const leer = f => fs.readFileSync(path.join(DIR, f), "utf8");

function cargar(lang) {
  const ctx = { window: {}, lang }; ctx.window.window = ctx.window; vm.createContext(ctx);
  const run = (src, f) => vm.runInContext(src, ctx, { filename: f });
  run(leer("timeline.js"), "timeline.js"); run(leer("people.js"), "people.js");
  ctx.HI18N = ctx.window.HI18N = {};
  ctx.REL = ctx.window.REL; ctx.PR = ctx.window.PR;
  const es = { TL: ctx.window.TL, PP: ctx.window.PP };
  if (lang !== "es") run(leer(`i18n/${lang}.js`), `i18n/${lang}.js`);
  const m = leer("index.html").match(/\/\* TR \*\/([\s\S]*?)\/\* \/TR \*\//);
  if (!m) throw new Error("index.html: no encuentro el bloque /* TR */");
  run(m[1] + "\nthis.tr=tr;this.rel=rel;", "index.html#TR");
  return { ctx, es, H: ctx.window.HI18N[lang], tr: ctx.tr, rel: ctx.rel };
}

/* Every UI string index.html asks to translate: tr("…") literals, data-tr texts, data-tra labels,
   theme/font names, plus the relation labels from people.js REL. */
function clavesUI() {
  const s = leer("index.html");
  const k = new Set([...s.matchAll(/\btr\("([^"]*)"/g)].map(m => m[1]));
  for (const m of s.matchAll(/data-tr="">([^<]+)</g)) k.add(m[1]);
  for (const m of s.matchAll(/data-tra="([^"]+)"/g)) k.add(m[1]);
  for (const m of s.match(/const THEMES=(\[.*?\]\]);/)[1].matchAll(/\["\w+","([^"]+)"\]/g)) k.add(m[1]);
  for (const m of s.match(/const FONTS=(\[.*?\]\]);/)[1].matchAll(/\["\w+","([^"]+)",/g)) k.add(m[1]);
  const { ctx } = cargar("es");
  for (const l of Object.keys(ctx.REL)) k.add(l);
  k.delete(""); k.delete("Aa");
  return [...k].sort();
}

module.exports = { cargar, clavesUI };
