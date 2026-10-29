"""Finds AI texts where the model wrote about its task instead of (or besides) the content:
"Here is the corrected translation:", "Translating the rest:", "Die Zusammenfassung ist auf Spanisch"…
With --borrar it deletes those entries, so `generar_ia.py traducir/adaptar --solo-faltantes` regenerates them.
Usage: python revisar_meta.py [--borrar] [lang …]     (default: en bsb pt fr de)
"""
import json, os, re, sys

META = re.compile(
    r"here is the (corrected |revised )?(translation|explanation|summary)|translating the rest|"
    r"rewriting (correctly|it)|let me (give|rewrite|translate|redo)|\bhmm\b|must be translated|"
    r"\bsource (is|text|language|wording)\b|the original spanish|"
    r"self-correction|\b(ist|is) auf spanisch|die aufgabe (lautet|ist), (sie|es)|zielsprache|ich übersetze|übersetzung soll|"
    r"português brasileiro simples|plain, modern english|einfaches, modernes deutsch|français simple et moderne|"
    r"translator'?s? note|note du traducteur|nota do tradutor|anmerkung des übersetzers|<thinking", re.I)

borrar = "--borrar" in sys.argv
langs = [a for a in sys.argv[1:] if not a.startswith("--")] or ["en", "bsb", "pt", "fr", "de"]
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "biblia", "app", "ia")
for lang in langs:
    n = 0
    for b in range(66):
        ruta = os.path.join(d, lang, f"{b}.json")
        h = json.load(open(ruta, encoding="utf-8"))
        malos = [(kind, k) for kind in ("exp", "sum") for k, t in h[kind].items() if META.search(t)]
        for kind, k in malos:
            n += 1
            if not borrar and n <= 3:
                t = h[kind][k]; m = META.search(t)
                print(f"  {lang} {b} {kind} {k}: …{t[max(0, m.start()-50):m.end()+50]!r}…")
            if borrar:
                del h[kind][k]
        if borrar and malos:
            with open(ruta + ".tmp", "w", encoding="utf-8") as f:
                json.dump(h, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(ruta + ".tmp", ruta)
    print(f"{lang}: {n} textos con notas del modelo" + (" (borrados para regenerar)" if borrar else ""))
