/* Checks biblia/app/i18n/<lang>.js against the Spanish source: same timeline shape, every character,
   every UI string index.html uses (collected automatically), and every relation as a "{0} … {1}" sentence.
   Usage: node validar_i18n.js <lang> [<lang>…]   (no args: en pt fr de). Exits 1 if anything is wrong. */
const { cargar, clavesUI } = require("./i18n_ctx");
const langs = process.argv.slice(2).length ? process.argv.slice(2) : ["en", "pt", "fr", "de"];
const keys = clavesUI();
let mal = false;
for (const lang of langs) {
  let r; try { r = cargar(lang) } catch (e) { console.log(`${lang}: no carga: ${e.message}`); mal = true; continue }
  const { es: { TL, PP }, H, ctx } = r, err = [];
  const str = (v, w) => { if (typeof v !== "string" || !v.trim()) err.push(`vacío o no texto: ${w}`) };
  if (!H) { console.log(`${lang}: HI18N.${lang} no existe`); mal = true; continue }
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
  // UI: every key translated with the same {n} placeholders; relations are full two-person sentences.
  const ph = s => (s.match(/\{\d\}/g) || []).sort().join();
  for (const k of keys) {
    const v = H.ui?.[k]; if (v === undefined) { err.push(`ui falta: ${JSON.stringify(k)}`); continue } str(v, `ui[${JSON.stringify(k)}]`);
    const want = ctx.REL[k] ? "{0},{1}" : ph(k);
    if (ph(v || "") !== want) err.push(`ui marcadores: ${JSON.stringify(k)} → ${JSON.stringify(v)} (se esperaba ${want || "ninguno"})`);
  }
  for (const k of Object.keys(H.ui || {})) if (!keys.includes(k)) err.push(`ui sobra (ya no se usa): ${JSON.stringify(k)}`);
  if (err.length) { mal = true; console.log(`${lang}: ${err.length} problemas`); err.slice(0, 60).forEach(e => console.log(" -", e)) }
  else console.log(`${lang}: OK (${TL.length} épocas, ${Object.keys(PP).length} personajes, ${keys.length} textos de interfaz)`);
}
process.exit(mal ? 1 : 0);
