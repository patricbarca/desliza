/* Checks biblia/i18n/<lang>.js against the Spanish source (timeline.js, people.js, UI keys).
   Usage: node validar_i18n.js <lang> [ui_keys.json]
   Exits 1 and lists problems if anything is missing or the structure differs. */
const fs = require("fs"), vm = require("vm"), path = require("path");
const lang = process.argv[2], dir = path.join(__dirname, "biblia");
const keysFile = process.argv[3];
const ctx = { window: {} }; ctx.window.window = ctx.window; vm.createContext(ctx);
const run = f => vm.runInContext(fs.readFileSync(path.join(dir, f), "utf8"), ctx, { filename: f });
run("timeline.js"); run("people.js");
const TL = ctx.window.TL, PP = ctx.window.PP;
ctx.HI18N = ctx.window.HI18N = {};
try { run(`i18n/${lang}.js`) } catch (e) { console.log("No carga:", e.message); process.exit(1) }
const H = ctx.window.HI18N[lang], err = [];
const str = (v, w) => { if (typeof v !== "string" || !v.trim()) err.push(`vacío o no texto: ${w}`) };
if (!H) { console.log(`HI18N.${lang} no existe`); process.exit(1) }
// Timeline: same eras, same events, same references, same list lengths.
if (!Array.isArray(H.TL) || H.TL.length !== TL.length) err.push(`TL: ${H.TL?.length} épocas, deberían ser ${TL.length}`);
else TL.forEach((era, i) => {
  const x = H.TL[i]; ["t", "d", "s"].forEach(f => str(x[f], `TL[${i}].${f}`));
  if (!x.e || x.e.length !== era.e.length) { err.push(`TL[${i}].e: ${x.e?.length} eventos, deberían ser ${era.e.length}`); return }
  era.e.forEach((ev, j) => {
    const y = x.e[j], w = `TL[${i}].e[${j}]`;
    ["t", "d", "s"].forEach(f => str(y[f], `${w}.${f}`));
    if (JSON.stringify(y.r) !== JSON.stringify(ev.r)) err.push(`${w}.r cambió: ${JSON.stringify(y.r)} ≠ ${JSON.stringify(ev.r)}`);
    ["p", "k"].forEach(f => { if (!Array.isArray(y[f]) || y[f].length !== ev[f].length) err.push(`${w}.${f}: largo ${y[f]?.length} ≠ ${ev[f].length}`); else y[f].forEach((z, n) => str(z, `${w}.${f}[${n}]`)) });
  });
});
// Characters: every id with a name and a description, no extra ids.
for (const id of Object.keys(PP)) { const p = H.PP?.[id]; if (!p) { err.push(`PP.${id} falta`); continue } str(p.n, `PP.${id}.n`); str(p.d, `PP.${id}.d`) }
for (const id of Object.keys(H.PP || {})) if (!PP[id]) err.push(`PP.${id} no existe en español`);
// UI: every key translated, same {n} placeholders.
if (keysFile) {
  const keys = JSON.parse(fs.readFileSync(keysFile, "utf8"));
  for (const k of keys) {
    const v = H.ui?.[k]; if (v === undefined) { err.push(`ui falta: ${JSON.stringify(k)}`); continue } str(v, `ui[${JSON.stringify(k)}]`);
    const ph = s => (s.match(/\{\d\}/g) || []).sort().join();
    if (ph(k) !== ph(v || "")) err.push(`ui placeholders distintos: ${JSON.stringify(k)} → ${JSON.stringify(v)}`);
  }
}
if (err.length) { console.log(`${lang}: ${err.length} problemas`); err.slice(0, 60).forEach(e => console.log(" -", e)); process.exit(1) }
console.log(`${lang}: OK (${TL.length} épocas, ${Object.keys(PP).length} personajes${keysFile ? ", ui completa" : ""})`);
