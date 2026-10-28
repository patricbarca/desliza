"""
Pregenera explicaciones (por versículo) y resúmenes (por capítulo) con la Message Batches API de Anthropic.

Requisitos:
  pip install anthropic
  export ANTHROPIC_API_KEY=...        (Windows PowerShell:  $env:ANTHROPIC_API_KEY="...")

Los datos se buscan en ./biblia, junto al script o en la carpeta actual (o indica --dir).

Uso:
  0) Ver cuántas solicitudes se enviarían, sin gastar nada (vale para enviar y traducir):
       python generar_ia.py enviar --lang es --libros 0 --simular
  1) Prueba con un libro y mide el costo real:
       python generar_ia.py enviar --lang es --modelo sonnet --libros 0
  2) Revisa el estado y descarga cuando termine (puede tardar hasta 24 h, normalmente menos):
       python generar_ia.py estado
       python generar_ia.py descargar
  3) Lanza todo el idioma (--solo-faltantes salta lo ya descargado y sirve para reintentar errores):
       python generar_ia.py enviar --lang es --modelo sonnet --solo-faltantes
  4) Los demás idiomas, traduciendo lo generado en español (mucho más barato con Haiku):
       python generar_ia.py traducir --lang en --libros 0
       python generar_ia.py traducir --lang en --solo-faltantes
     Los capítulos cuya numeración de versículos no coincide con el español (sobre todo en
     francés) se generan directamente en ese idioma en vez de traducirse.

Salida: un archivo por libro, para que la app solo descargue lo que se lee:
  <dir>/ia/<lang>/<b>.json  ->  {"exp": {"c:v": "texto"}, "sum": {"c": "texto"}}
Índices desde 0 (b = libro, c = capítulo, v = versículo), igual que la app.
"""
import argparse, json, os, re, sys
import anthropic

MODELOS = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
# Extra request params per model. Haiku 5.5 thinks by default and, in testing, spent the whole
# max_tokens thinking and wrote no text; these short texts don't need it. (Allowed at effort <= high;
# Haiku's default effort is medium.) Sonnet 5.5 answered directly in testing, so it keeps defaults.
EXTRA = {"claude-haiku-5-5": {"thinking": {"type": "disabled"}}}
# Translating needs no reasoning, and Sonnet 5.5 sometimes thought until max_tokens and cut the text off.
# "between_tools" is how Sonnet 5.5 turns thinking off ("disabled" is rejected on that model).
EXTRA_TRAD = {**EXTRA, "claude-sonnet-5-5": {"thinking": {"type": "between_tools"}}}
IDIOMA = {
    "es": ("Reina-Valera 1909", "español sencillo y latinoamericano"),
    "en": ("King James Version", "plain, modern English"),
    "pt": ("Bíblia Livre", "português brasileiro simples"),
    "fr": ("Darby 1885", "français simple et moderne"),
    "de": ("Elberfelder 1905", "einfaches, modernes Deutsch"),
}
LOTE = 20000  # solicitudes por batch (límite de la API: 100.000 o 256 MB)
# max_tokens: Spanish runs ~2.3 tokens/word and the model often writes ~150-175 words; 400 truncated
# ~5% of Genesis. German/French run longer than Spanish. Only tokens actually written are billed.
MAX_EXP, MAX_SUM = 700, 400

SISTEMA = ("You are a warm, clear, non-denominational Christian Bible teacher. "
           "Never invent historical facts; if something is uncertain or interpreted in several ways, say so. "
           "Plain text only, no markdown, no titles.")
SISTEMA_TRAD = ("You are a careful translator of Bible study material for a reading app. "
                "Translate faithfully: keep the meaning, tone, paragraph structure and approximate length. "
                "Never add facts or opinions. Plain text only, no markdown, no titles, no translator notes.")

AQUI = os.path.dirname(os.path.abspath(__file__))


def carpeta_datos(d):
    """Carpeta que contiene es.json, en.json, etc."""
    if d:
        if not os.path.exists(os.path.join(d, "es.json")):
            sys.exit(f"No encuentro es.json en {d}")
        return d
    for c in (os.path.join(AQUI, "biblia"), AQUI, "biblia", "."):
        if os.path.exists(os.path.join(c, "es.json")):
            return c
    sys.exit("No encuentro es.json. Indica la carpeta con --dir")


def ruta_estado(d): return os.path.join(d, "batches.json")
def ruta_ia(d, lang, b): return os.path.join(d, "ia", lang, f"{b}.json")
def vacio(): return {"exp": {}, "sum": {}}


def leer_json(ruta, defecto):
    if not os.path.exists(ruta):
        return defecto
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar_json(ruta, datos, **kw):
    """Escritura atómica: si el proceso se corta, el archivo anterior queda intacto."""
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, **kw)
    os.replace(tmp, ruta)


def cargar_biblia(d, lang):
    B = leer_json(os.path.join(d, f"{lang}.json"), None)
    if B is None:
        sys.exit(f"No existe {lang}.json en {d}")
    return B


def validar_libros(libros, B):
    if libros is not None:
        malos = [b for b in libros if not 0 <= b < len(B)]
        if malos:
            sys.exit(f"Índices de libro fuera de rango (0–{len(B)-1}): {malos}")


# ---------- Prompts ----------

def pedido_explicacion(lang, ref, verso, prev, sig):
    ver, pl = IDIOMA[lang]
    return (f"Explain this verse from the {ver}. Write ONLY in {pl}.\n"
            f'Verse ({ref}): "{verso}"\nPrevious context: "{prev}"\nFollowing context: "{sig}"\n'
            "At most 130 words, three short parts separated by a blank line:\n"
            "1) What it says (clarify archaic words if any).\n2) Context: who is speaking and why.\n"
            "3) For today: one practical application.")


def pedido_resumen(lang, ref, texto):
    ver, pl = IDIOMA[lang]
    return (f"Summarize this Bible chapter ({ref}, {ver}). Write ONLY in {pl}.\n"
            f"Text:\n{texto}\n\n2 to 3 short sentences (max 60 words) on what happens or is taught, "
            "based only on the text above.")


def pedido_trad_explicacion(lang, desde, ref, verso, texto):
    ver, pl = IDIOMA[lang]
    ver_o = IDIOMA[desde][0]
    # Naming the exact words works far better than a general rule: in testing, Haiku still kept
    # ~3.5% of notes like '"Crió" means "created"' with only the general instruction.
    ajenas = [t for t in dict.fromkeys(CITA.findall(texto)) if t.strip().lower() not in verso.lower()]
    lista = ("These quoted words or phrases belong to the source wording and are NOT in your reader's verse: "
             + ", ".join(f'"{t}"' for t in ajenas)
             + ". Never leave them in the source language. If a sentence explains what one of them means "
               "(an old or unusual word), rewrite it for a word of the verse above or delete it; "
               "otherwise just translate the phrase.\n") if ajenas else ""
    return (f"Translate this explanation of {ref} into {pl}.\n"
            f"It was written for readers of the {ver_o}. Your reader sees the {ver}, where the verse reads:\n"
            f'"{verso}"\n'
            f"Your reader never sees the {ver_o}. So where the explanation quotes or comments on its wording "
            "(archaic words, old spellings, quoted phrases), either rewrite that comment for a word that really "
            "appears in the verse above, or delete the sentence. Never quote a source-language word, and never "
            "mention the source language or the original translation.\n"
            + lista +
            # Haiku left ~27% of Portuguese texts in Spanish (the languages look alike); say it plainly.
            (f"The explanation below is in Spanish. Every sentence you write must be in {pl}; "
             "do not copy any Spanish sentence.\n" if desde == "es" else "") +
            "Output only the translated explanation.\n\n"
            f"Explanation:\n{texto}")


CITA = re.compile(r'["“«]([^"”»]{3,40})["”»]')


# How each target language names Spanish, the source we translate from. A translation that names it is
# talking about the source wording ("the Spanish word ...", "the sentence about Spanish words is removed").
NOMBRE_ES = {"en": "spanish", "pt": "espanhol", "fr": "espagnol", "de": "spanisch"}
# Spanish words rare in pt/fr/de/en; 3+ of them means the text was left in Spanish.
# ("está" is left out: it is also common Portuguese.)
# The lookbehind skips Portuguese enclitics like "escrevê-las", "arrancá-los".
SOLO_ES = re.compile(r"(?<![-\w])(los|las|del|pero|él|también|esto|ustedes|qué)\b", re.I)
# German "Los" (lot, as in casting lots) is not Spanish.
SOLO_ES_DE = re.compile(r"(?<![-\w])(las|del|pero|él|también|esto|ustedes|qué)\b", re.I)
# Haiku sometimes answered in English instead of French/German (~120 French texts).
SOLO_EN = re.compile(r"\b(the|and|this|that|with|which|they|from|what|says)\b", re.I)


def fuga(src, dst, verso, lang="en", desde="es"):
    """Why a translation still carries foreign material, or None if it looks clean: leaked model
    reasoning, text in the wrong language, a mention of Spanish, or a quoted source word it kept."""
    v, dl = verso.lower(), dst.lower()
    if "<thinking" in dl or "</thinking" in dl:
        return "razonamiento"
    if lang != "en" and len(SOLO_EN.findall(dst)) >= 4:
        return "en inglés"
    if desde == "es" and lang in NOMBRE_ES:
        if re.search(r"\b" + NOMBRE_ES[lang] + r"\b", dl):
            return f"menciona '{NOMBRE_ES[lang]}'"
        if len((SOLO_ES_DE if lang == "de" else SOLO_ES).findall(dst)) >= 3:
            return "sin traducir"
    for tok in CITA.findall(src):
        t = tok.strip().lower()
        if t not in v and re.search(r'["“«]' + re.escape(t) + r'["”»]', dl):
            return tok
    return None


def pedido_trad_resumen(lang, ref, texto):
    pl = IDIOMA[lang][1]
    return (f"Translate this summary of {ref} into {pl}. Output only the translation.\n\n"
            f"Summary:\n{texto}")


# ---------- Request builders ----------

def peticion(cid, modelo, max_tokens, sistema, contenido, extra=EXTRA):
    return {"custom_id": cid,
            "params": {"model": modelo, "max_tokens": max_tokens, "system": sistema, **extra.get(modelo, {}),
                       "messages": [{"role": "user", "content": contenido}]}}


def req_resumen(lang, modelo, b, c, ref_c, versos, extra=EXTRA):
    texto = "\n".join(f"{i+1} {t}" for i, t in enumerate(versos))[:9000]
    return peticion(f"s-{lang}-{b}-{c}", modelo, MAX_SUM, SISTEMA, pedido_resumen(lang, ref_c, texto), extra)


def req_explicacion(lang, modelo, b, c, v, ref_c, versos, extra=EXTRA):
    prev = " ".join(versos[max(0, v-2):v]); sig = " ".join(versos[v+1:v+3])
    return peticion(f"e-{lang}-{b}-{c}-{v}", modelo, MAX_EXP, SISTEMA,
                    pedido_explicacion(lang, f"{ref_c}:{v+1}", versos[v], prev, sig), extra)


def construir(d, lang, modelo, libros, solo_faltantes, sin_razonamiento=False):
    """Generación directa en `lang`. sin_razonamiento: thinking off, for retrying texts where the model
    reasoned until max_tokens (1.8% of the Spanish Bible with Sonnet)."""
    extra = EXTRA_TRAD if sin_razonamiento else EXTRA
    B = cargar_biblia(d, lang); validar_libros(libros, B)
    reqs = []
    for b, (libro, caps) in enumerate(B):
        if libros is not None and b not in libros:
            continue
        hecho = leer_json(ruta_ia(d, lang, b), vacio()) if solo_faltantes else vacio()
        for c, versos in enumerate(caps):
            ref_c = f"{libro} {c+1}"
            if str(c) not in hecho["sum"]:
                reqs.append(req_resumen(lang, modelo, b, c, ref_c, versos, extra))
            reqs += [req_explicacion(lang, modelo, b, c, v, ref_c, versos, extra)
                     for v in range(len(versos)) if f"{c}:{v}" not in hecho["exp"]]
    return reqs


def construir_traduccion(d, lang, desde, modelo, libros, solo_faltantes):
    """Traduce a `lang` lo ya generado en `desde`. Donde la numeración no coincide, genera directo."""
    if lang == desde:
        sys.exit("--lang y --desde deben ser idiomas distintos")
    O, X = cargar_biblia(d, desde), cargar_biblia(d, lang)
    validar_libros(libros, X)
    reqs, cuenta = [], {"traducir": 0, "generar": 0, "sin_origen": 0, "fugas": 0}
    for b, (libro, caps) in enumerate(X):
        if libros is not None and b not in libros:
            continue
        hecho = leer_json(ruta_ia(d, lang, b), vacio()) if solo_faltantes else vacio()
        fuente = leer_json(ruta_ia(d, desde, b), vacio())
        mismo_libro = len(O[b][1]) == len(caps)
        for c, versos in enumerate(caps):
            ref_c = f"{libro} {c+1}"
            # Same verse count is how we know index c:v points at the same verse in both Bibles.
            alineado = mismo_libro and len(O[b][1][c]) == len(versos)
            pend_sum = str(c) not in hecho["sum"]
            pend_exp = [v for v in range(len(versos)) if f"{c}:{v}" not in hecho["exp"]]
            if alineado and solo_faltantes:
                # Re-translate earlier translations that still carry notes about source-language words.
                malos = [v for v in range(len(versos)) if f"{c}:{v}" in hecho["exp"] and f"{c}:{v}" in fuente["exp"]
                         and fuga(fuente["exp"][f"{c}:{v}"], hecho["exp"][f"{c}:{v}"], versos[v], lang, desde)]
                cuenta["fugas"] += len(malos)
                pend_exp = sorted(pend_exp + malos)
            if not alineado:
                if pend_sum: reqs.append(req_resumen(lang, modelo, b, c, ref_c, versos))
                reqs += [req_explicacion(lang, modelo, b, c, v, ref_c, versos) for v in pend_exp]
                cuenta["generar"] += pend_sum + len(pend_exp)
                continue
            if pend_sum:
                if str(c) in fuente["sum"]:
                    reqs.append(peticion(f"s-{lang}-{b}-{c}", modelo, MAX_SUM, SISTEMA_TRAD,
                                         pedido_trad_resumen(lang, ref_c, fuente["sum"][str(c)]), EXTRA_TRAD))
                    cuenta["traducir"] += 1
                else:
                    cuenta["sin_origen"] += 1
            for v in pend_exp:
                src = fuente["exp"].get(f"{c}:{v}")
                if src is None:
                    cuenta["sin_origen"] += 1; continue
                reqs.append(peticion(f"e-{lang}-{b}-{c}-{v}", modelo, MAX_EXP, SISTEMA_TRAD,
                                     pedido_trad_explicacion(lang, desde, f"{ref_c}:{v+1}", versos[v], src), EXTRA_TRAD))
                cuenta["traducir"] += 1
    return reqs, cuenta


# ---------- Commands ----------

def mandar(d, lang, reqs):
    cli, ruta = anthropic.Anthropic(), ruta_estado(d)
    for i in range(0, len(reqs), LOTE):
        bt = cli.messages.batches.create(requests=reqs[i:i+LOTE])
        # Se guarda tras cada lote: si uno falla, los ya enviados (y cobrados) no se pierden.
        est = leer_json(ruta, [])
        est.append({"id": bt.id, "lang": lang})
        guardar_json(ruta, est, indent=1)
        print("Enviado:", bt.id)


def libros_arg(a): return [int(x) for x in a.libros.split(",")] if a.libros else None


def enviar(a, d):
    reqs = construir(d, a.lang, MODELOS[a.modelo], libros_arg(a), a.solo_faltantes, a.sin_razonamiento)
    print(f"{len(reqs)} solicitudes ({a.lang}, {a.modelo})")
    if not a.simular and reqs:
        mandar(d, a.lang, reqs)


def traducir(a, d):
    reqs, n = construir_traduccion(d, a.lang, a.desde, MODELOS[a.modelo], libros_arg(a), a.solo_faltantes)
    print(f"{len(reqs)} solicitudes ({a.desde}→{a.lang}, {a.modelo}): "
          f"{n['traducir']} traducciones, {n['generar']} generadas directo (numeración distinta)"
          + (f", de ellas {n['fugas']} re-traducciones por notas de palabras en {a.desde}" if n["fugas"] else ""))
    if n["sin_origen"]:
        print(f"Aviso: {n['sin_origen']} textos no existen aún en '{a.desde}' y se omiten. "
              f"Genéralos primero y vuelve a correr con --solo-faltantes.")
    if not a.simular and reqs:
        mandar(d, a.lang, reqs)


def estado(a, d):
    est = leer_json(ruta_estado(d), [])
    if not est:
        print("No hay batches pendientes.")
    cli = anthropic.Anthropic()
    for e in est:
        bt = cli.messages.batches.retrieve(e["id"])
        rc = bt.request_counts
        print(e["id"], e["lang"], bt.processing_status,
              f"ok={rc.succeeded} procesando={rc.processing} error={rc.errored} "
              f"cancelado={rc.canceled} expirado={rc.expired}")


def descargar(a, d):
    cli, ruta_est = anthropic.Anthropic(), ruta_estado(d)
    tok_in = tok_out = fallos = 0
    for e in leer_json(ruta_est, []):
        bt = cli.messages.batches.retrieve(e["id"])
        if bt.processing_status != "ended":
            print("Aún procesando:", e["id"]); continue
        libros, nuevos = {}, 0  # (lang, b) -> datos del libro
        for r in cli.messages.batches.results(e["id"]):
            if r.result.type != "succeeded":
                fallos += 1; continue
            msg = r.result.message
            tok_in += msg.usage.input_tokens; tok_out += msg.usage.output_tokens
            txt = "".join(x.text for x in msg.content if x.type == "text").strip()
            if not txt or msg.stop_reason == "max_tokens":
                fallos += 1; continue  # vacío o cortado: mejor reintentarlo que mostrarlo a medias
            p = r.custom_id.split("-")
            lang, b = p[1], int(p[2])
            libro = libros.get((lang, b))
            if libro is None:
                libro = libros[(lang, b)] = leer_json(ruta_ia(d, lang, b), vacio())
            if p[0] == "s": libro["sum"][p[3]] = txt
            else:           libro["exp"][f"{p[3]}:{p[4]}"] = txt
            nuevos += 1
        for (lang, b), libro in libros.items():
            guardar_json(ruta_ia(d, lang, b), libro, separators=(",", ":"))
        # Quitar el batch del estado solo después de guardar sus resultados.
        guardar_json(ruta_est, [x for x in leer_json(ruta_est, []) if x["id"] != e["id"]], indent=1)
        print(f"{e['id']}: {nuevos} textos guardados en {len(libros)} libro(s) de ia/{e['lang']}/")
    print(f"Tokens usados: entrada {tok_in:,} · salida {tok_out:,}")
    if fallos:
        print(f"{fallos} solicitudes fallaron o salieron cortadas. Reintenta con el mismo comando "
              f"(enviar o traducir) y --solo-faltantes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="carpeta con es.json, en.json… (por defecto ./biblia)")
    sp = ap.add_subparsers(dest="cmd", required=True)

    def comunes(p, modelo):
        p.add_argument("--lang", default="es", choices=IDIOMA)
        p.add_argument("--modelo", default=modelo, choices=MODELOS)
        p.add_argument("--libros", help="ej: 0  o  0,1,2  (0 = Génesis)")
        p.add_argument("--solo-faltantes", action="store_true", help="omite lo que ya está en ia/<lang>/")
        p.add_argument("--simular", action="store_true", help="solo cuenta las solicitudes, no envía nada")

    e = sp.add_parser("enviar", help="genera directamente en un idioma")
    comunes(e, "sonnet")
    e.add_argument("--sin-razonamiento", action="store_true",
                   help="desactiva el razonamiento previo; útil para reintentar textos que salieron cortados")
    t = sp.add_parser("traducir", help="traduce lo generado en otro idioma")
    comunes(t, "haiku")
    t.add_argument("--desde", default="es", choices=IDIOMA, help="idioma de origen (por defecto es)")
    sp.add_parser("estado"); sp.add_parser("descargar")
    a = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY") and not getattr(a, "simular", False):
        sys.exit("Falta la API key. En esta misma ventana de PowerShell ejecuta:\n"
                 '  $env:ANTHROPIC_API_KEY="tu-clave"\n'
                 "y vuelve a lanzar el comando. (setx solo afecta a ventanas que abras después.)")
    {"enviar": enviar, "traducir": traducir, "estado": estado, "descargar": descargar}[a.cmd](a, carpeta_datos(a.dir))
