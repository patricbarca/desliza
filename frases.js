/* Prints one relationship sentence per distinct label, exactly as the app shows it.
   Usage: node frases.js <lang> */
const { cargar } = require("./i18n_ctx");
const lang = process.argv[2] || "es";
const { ctx, H, rel } = cargar(lang);
const name = id => H?.PP?.[id]?.n || ctx.window.PP[id].n, seen = new Set();
for (const [a, b, l] of ctx.PR) { if (seen.has(l)) continue; seen.add(l); console.log(rel(l, name(a), name(b))) }
