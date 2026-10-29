"""Converts the official Berean Standard Bible text (bereanbible.com/bsb.txt, public domain since 2023-04-30)
into the app's Bible format: [[book name, [[verse, …] per chapter]] …], same book order as en.json.

The file is "Book C:V<TAB>text", one verse per line, after 3 header lines. Verses the BSB leaves out
(it follows the oldest manuscripts) are filled with a short bracketed note, so verse indices stay aligned
with the other Bibles and the AI texts keyed by "c:v".
Usage: python convertir_bsb.py <bsb.txt> <salida.json> <en.json de referencia>
"""
import json, re, sys
from collections import OrderedDict

src, out, ref = sys.argv[1:4]
LINEA = re.compile(r"^(.+?) (\d+):(\d+)\t(.*)$")
libros = OrderedDict()
for raw in open(src, encoding="utf-8-sig"):
    m = LINEA.match(raw.rstrip("\r\n"))
    if not m:
        continue  # header lines
    libro, c, v, t = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).strip()
    libros.setdefault(libro, {}).setdefault(c, {})[v] = t

KJV = json.load(open(ref, encoding="utf-8"))
if len(libros) != len(KJV):
    sys.exit(f"{len(libros)} libros, se esperaban {len(KJV)}")
NOTA = "[This verse is not included in the earliest manuscripts.]"
B, rellenos, extra = [], [], []
for (libro, caps), (_, kcaps) in zip(libros.items(), KJV):
    if len(caps) != len(kcaps):
        sys.exit(f"{libro}: {len(caps)} capítulos, KJV tiene {len(kcaps)}")
    capitulos = []
    for c in range(1, len(kcaps) + 1):
        vs, n = caps[c], len(kcaps[c - 1])
        if max(vs) > n:
            extra.append(f"{libro} {c}: BSB llega a {max(vs)}, KJV a {n}")
        fila = []
        for v in range(1, n + 1):
            if v in vs and vs[v]:
                fila.append(vs[v])
            else:
                fila.append(NOTA); rellenos.append(f"{libro} {c}:{v}")
        capitulos.append(fila)
    B.append([libro.replace("Psalm", "Psalms") if libro == "Psalm" else libro, capitulos])
json.dump(B, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"{len(B)} libros, {sum(len(v) for _, cs in B for v in cs)} versículos")
print("versículos sin texto en la BSB (con nota):", len(rellenos), rellenos)
print("capítulos donde la BSB tiene más versículos que la KJV:", extra or "ninguno")
