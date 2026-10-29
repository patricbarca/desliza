"""Free text fixes for a pattern the translation passes left: Spanish "Dice que…" ("It says that…") came out as
"The explanation says that…", which reads as if the text were talking about itself. Rewrites it to talk about
the verse. Deterministic, no AI. Usage: python pulir_explicaciones.py [--aplicar] [lang …]  (default en bsb)
"""
import json, os, re, sys

REGLAS = {
    "en": [
        (r"\bThe explanation says that\b", "This verse says that"),
        (r"\bThe explanation says\b", "This verse says"),
        (r"\bthe explanation says\b", "the verse says"),
        (r"\b[Tt]he explanation also (notes|mentions|explains|points out|says)\b", r"It also \1"),
        (r"\b(the|this) (original )?explanation (refers|speaks|talks|points) (to|about|of)\b", r"the verse \3 \4"),
        (r"\bThe (original )?explanation\b", "The verse"),
        (r"\bthe (original )?explanation\b", "the verse"),
    ],
}
REGLAS["bsb"] = REGLAS["en"]
REGLAS["de"] = [(r"\bDie Erklärung (sagt|besagt)\b", r"Der Vers \1"), (r"\bdie Erklärung (sagt|besagt)\b", r"der Vers \1")]
REGLAS["pt"] = [(r"\bA explicação (diz|afirma)\b", r"O versículo \1"), (r"\ba explicação (diz|afirma)\b", r"o versículo \1")]
REGLAS["fr"] = [(r"\bL['’]explication (dit|affirme)\b", r"Le verset \1"), (r"\bl['’]explication (dit|affirme)\b", r"le verset \1")]

aplicar = "--aplicar" in sys.argv
langs = [a for a in sys.argv[1:] if not a.startswith("--")] or ["en", "bsb"]
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "biblia", "app", "ia")
for lang in langs:
    reglas = [(re.compile(p), r) for p, r in REGLAS[lang]]
    cambios = textos = 0
    ejemplo = None
    for b in range(66):
        ruta = os.path.join(d, lang, f"{b}.json")
        h = json.load(open(ruta, encoding="utf-8"))
        tocado = False
        for k, t in h["exp"].items():
            n = t
            for p, r in reglas:
                n = p.sub(r, n)
            if n != t:
                textos += 1; cambios += 1; tocado = True
                ejemplo = ejemplo or (t[:90], n[:90])
                h["exp"][k] = n
        if aplicar and tocado:
            with open(ruta + ".tmp", "w", encoding="utf-8") as f:
                json.dump(h, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(ruta + ".tmp", ruta)
    print(f"{lang}: {textos} textos {'corregidos' if aplicar else 'a corregir'}; ej.: {ejemplo}")
