"""
Genera las historias de cada capítulo de la historia de la humanidad con la Message Batches API (50 % más barato).

Lee los capítulos de biblia/prototipo/estructura.json y escribe un JSON por capítulo en
biblia/prototipo/historias/<capitulo>.json, más historias/indice.json ({capitulo: nº de historias}).

Requisitos:
  pip install anthropic
  ANTHROPIC_API_KEY en el entorno (Windows PowerShell:  $env:ANTHROPIC_API_KEY="...")

Uso:
  python generar_historia.py simular  --era media          # cuenta tokens de entrada, no gasta en generar
  python generar_historia.py enviar   --era media          # lanza el lote (Opus 5.5 por defecto)
  python generar_historia.py estado                        # ¿terminó el lote?
  python generar_historia.py descargar                     # guarda capítulos + informe de coste real
Opciones: --modelo opus|sonnet, --esfuerzo low|medium|high, --caps id1,id2 (solo esos capítulos),
          --salida carpeta (dentro de biblia/prototipo; por defecto "historias")
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

AQUI = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(AQUI, "biblia", "prototipo")
ESTRUCTURA = os.path.join(PROTO, "estructura.json")
SALIDA = os.path.join(PROTO, "historias")
LOTES = os.path.join(SALIDA, "_lotes.json")

MODELOS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"}
# USD por millón de tokens (entrada, salida), precio estándar. El lote cobra la mitad.
PRECIOS = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00)}
DESCUENTO_LOTE = 0.5
MAX_TOKENS = 32000  # incluye el razonamiento; un capítulo de texto ocupa ~5.000

SISTEMA = """Eres un divulgador de historia riguroso y cercano. Escribes los capítulos de una app de historia de la humanidad que se lee en el móvil deslizando tarjetas, como en Instagram. El público son adultos curiosos sin formación histórica, de cualquier país y creencia.

Cada capítulo tiene entre 8 y 12 historias en orden cronológico. Cada historia cuenta UNA idea concreta y memorable: una persona, un lugar, un objeto o un momento. Juntas deben cubrir lo esencial del capítulo según el encargo.

Estilo:
- Español neutro y sencillo, frases cortas, sin tecnicismos sin explicar. Sin listas ni markdown.
- titulo: corto (máximo 8 palabras), atractivo pero sin sensacionalismo.
- texto: entre 60 y 110 palabras.

Neutralidad y mirada global (tan importante como el rigor):
- Narra como un observador neutral que no escribe desde ningún país, religión ni bando. La historia de la app es la de toda la humanidad.
- Cuando un hecho se recuerda o se interpreta de forma distinta según el pueblo, la región o la tradición, dilo dentro del propio texto y atribuye cada versión a quien la sostiene ("para los cronistas cruzados…, mientras que las crónicas árabes…"), sin dar por buena ninguna.
- Da voz a los protagonistas de todos los lados, también a los vencidos, a las mujeres y a la gente común, no solo a reyes y ejércitos.
- Usa palabras descriptivas, no valorativas: evita "descubrimiento" cuando ya había gente, "bárbaros", "salvajes", "infieles", "primitivos" o "civilizar", salvo citando a quien las usó.
- Respeta todas las culturas y creencias. Usa los nombres locales cuando ayuden.

Rigor (lo más importante):
- No inventes datos, cifras, nombres ni citas textuales. Si un dato es incierto, aproximado o discutido, dilo ("se calcula", "según la tradición", "los historiadores no se ponen de acuerdo").
- Distingue siempre leyenda de hecho documentado.
- Las fechas aproximadas llevan "c." (circa).

Campos especiales:
- profundizar: en más o menos una de cada tres historias, la que más lo merezca. Entre 3 y 4 párrafos de 40 a 80 palabras que aporten pruebas concretas (excavaciones, documentos, crónicas) o explicaciones. Si las fuentes de cada lado cuentan cosas distintas, este es el lugar para mostrarlas con calma. En las demás, null.
- conecta_con: cuando la historia lleva de forma natural a otro capítulo de la app (un antecedente, una consecuencia). Entre 0 y 3 por capítulo; si no, null. texto: una frase corta de invitación, por ejemplo "Sigue con los mongoles →".
- imagen_wikipedia: título EXACTO de un artículo que exista en la Wikipedia en inglés y cuya imagen principal ilustre la historia. Prefiere artículos de lugares, edificios, objetos, obras de arte o personas; evita conceptos abstractos (su imagen suele ser un mapa). No repitas la misma imagen en el capítulo.
- lugar: dónde ocurre, con coordenadas decimales reales (servirán para un mapa).
- anio: un año representativo (negativo para antes de Cristo).
- notas_revision: datos concretos que un revisor humano debería comprobar (cifras, fechas dudosas, atribuciones). Puede ir vacío."""


def esquema(destinos):
    """JSON schema del capítulo. `destinos` = ids válidos "era/capitulo" para conecta_con."""
    lugar = {"type": "object", "additionalProperties": False, "required": ["nombre", "lat", "lon"],
             "properties": {"nombre": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}}}
    historia = {
        "type": "object", "additionalProperties": False,
        "required": ["titulo", "fecha", "anio", "lugar", "texto", "imagen_wikipedia",
                     "profundizar", "conecta_con"],
        "properties": {
            "titulo": {"type": "string"}, "fecha": {"type": "string"}, "anio": {"type": "integer"},
            "lugar": lugar, "texto": {"type": "string"}, "imagen_wikipedia": {"type": "string"},
            "profundizar": {"anyOf": [{"type": "null"}, {
                "type": "object", "additionalProperties": False, "required": ["titulo", "parrafos"],
                "properties": {"titulo": {"type": "string"}, "parrafos": {"type": "array", "items": {"type": "string"}}}}]},
            "conecta_con": {"anyOf": [{"type": "null"}, {
                "type": "object", "additionalProperties": False, "required": ["capitulo", "texto"],
                "properties": {"capitulo": {"type": "string", "enum": destinos}, "texto": {"type": "string"}}}]},
        },
    }
    return {"type": "object", "additionalProperties": False, "required": ["resumen", "historias", "notas_revision"],
            "properties": {"resumen": {"type": "string"},
                           "historias": {"type": "array", "items": historia},
                           "notas_revision": {"type": "array", "items": {"type": "string"}}}}


def cargar_estructura():
    with open(ESTRUCTURA, encoding="utf-8") as f:
        return json.load(f)


def pedido(era, cap, eras):
    hermanos = "\n".join(f"- {c['n']} ({c['y']})" for c in era["caps"] if c["id"] != cap["id"])
    lugar = (cap.get("lugar") or {}).get("nombre", "—")  # el prólogo no tiene lugar
    return (f"ERA: {era['n']} ({era['y']})\n{era['d']}\n\n"
            f"CAPÍTULO QUE DEBES ESCRIBIR: {cap['n']} ({cap['y']}), lugar principal: {lugar}\n"
            f"Encargo: {cap.get('brief') or 'Cubre lo esencial de este tema.'}\n\n"
            f"Otros capítulos de esta era (no los repitas, como mucho enlázalos):\n{hermanos}\n\n"
            "Escribe el capítulo completo.")


def construir(eras, era_id, modelo, esfuerzo, solo):
    era = next((e for e in eras if e["id"] == era_id), None)
    if not era:
        sys.exit(f"No existe la era '{era_id}'. Eras: {', '.join(e['id'] for e in eras)}")
    destinos = sorted(f"{e['id']}/{c['id']}" for e in eras for c in e["caps"])
    caps = [c for c in era["caps"] if not solo or c["id"] in solo]
    if not caps:
        sys.exit("Ningún capítulo coincide con --caps")
    reqs = [Request(custom_id=f"{era['id']}--{c['id']}", params=MessageCreateParamsNonStreaming(
        model=modelo, max_tokens=MAX_TOKENS, system=SISTEMA,
        output_config={"effort": esfuerzo, "format": {"type": "json_schema", "schema": esquema(destinos)}},
        messages=[{"role": "user", "content": pedido(era, c, eras)}],
    )) for c in caps]
    return reqs


def leer_lotes():
    if os.path.exists(LOTES):
        with open(LOTES, encoding="utf-8") as f:
            return json.load(f)
    return []


def guardar_json(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)  # escritura atómica: nunca deja un JSON a medias


def coste(modelo, u):
    pin, pout = PRECIOS[modelo]
    entrada = (u["input_tokens"] + 1.25 * u["cache_creation_input_tokens"] + 0.1 * u["cache_read_input_tokens"])
    return (entrada * pin + u["output_tokens"] * pout) / 1e6 * DESCUENTO_LOTE


def imagenes_faltantes(titulos):
    """Títulos de Wikipedia sin imagen principal (o inexistentes). Devuelve None si no hay red."""
    faltan = []
    titulos = sorted(set(titulos))
    for i in range(0, len(titulos), 50):
        lote = titulos[i:i + 50]
        url = ("https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages"
               "&piprop=thumbnail&pithumbsize=100&titles=" + urllib.parse.quote("|".join(lote)))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cronica-generador/1.0 (prototipo educativo)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                q = json.load(r).get("query", {})
        except Exception as e:  # sin red o Wikipedia caída: no bloquea la descarga
            print(f"  (no se pudieron comprobar imágenes: {e})")
            return None
        final = {t: t for t in lote}
        for paso in (q.get("normalized", []), q.get("redirects", [])):
            for p in paso:
                for k, v in final.items():
                    if v == p["from"]:
                        final[k] = p["to"]
        con_imagen = {p["title"] for p in q.get("pages", {}).values() if "thumbnail" in p}
        faltan += [t for t in lote if final[t] not in con_imagen]
    return faltan


def cmd_simular(a):
    eras = cargar_estructura()
    modelo = MODELOS[a.modelo]
    reqs = construir(eras, a.era, modelo, a.esfuerzo, a.caps)
    cli = anthropic.Anthropic()
    total = 0
    for r in reqs:
        p = r["params"]
        n = cli.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"],
                                      output_config=p["output_config"]).input_tokens
        total += n
    pin, _ = PRECIOS[modelo]
    print(f"{len(reqs)} capítulos, {total:,} tokens de entrada "
          f"(≈ {total * pin / 1e6 * DESCUENTO_LOTE:.3f} USD en lote). La salida se paga aparte y es la mayor parte.")


def cmd_enviar(a):
    eras = cargar_estructura()
    modelo = MODELOS[a.modelo]
    reqs = construir(eras, a.era, modelo, a.esfuerzo, a.caps)
    lote = anthropic.Anthropic().messages.batches.create(requests=reqs)
    lotes = leer_lotes()
    lotes.append({"id": lote.id, "era": a.era, "modelo": modelo, "esfuerzo": a.esfuerzo,
                  "capitulos": len(reqs), "creado": datetime.now(timezone.utc).isoformat(), "descargado": False})
    guardar_json(LOTES, lotes)
    print(f"Lote {lote.id} enviado: {len(reqs)} capítulos de '{a.era}' con {modelo}.")


def cmd_estado(a):
    cli = anthropic.Anthropic()
    pend = [l for l in leer_lotes() if not l["descargado"]]
    if not pend:
        print("No hay lotes pendientes.")
    for l in pend:
        b = cli.messages.batches.retrieve(l["id"])
        c = b.request_counts
        print(f"{l['id']} ({l['era']}): {b.processing_status} — en curso {c.processing}, "
              f"ok {c.succeeded}, error {c.errored}, expirados {c.expired}")
    # Para esperar desde un script: sale con 0 solo si todos terminaron
    if a.esperar:
        while any(cli.messages.batches.retrieve(l["id"]).processing_status != "ended" for l in pend):
            time.sleep(60)
        print("Todos los lotes terminaron.")


def cmd_descargar(a):
    cli = anthropic.Anthropic()
    eras = cargar_estructura()
    era_de = {c["id"]: e for e in eras for c in e["caps"]}
    indice_ruta = os.path.join(SALIDA, "indice.json")
    indice = json.load(open(indice_ruta, encoding="utf-8")) if os.path.exists(indice_ruta) else {}
    lotes = leer_lotes()
    for l in lotes:
        if l["descargado"]:
            continue
        b = cli.messages.batches.retrieve(l["id"])
        if b.processing_status != "ended":
            print(f"{l['id']} aún no terminó ({b.processing_status}).")
            continue
        informe = {"lote": l["id"], "era": l["era"], "modelo": l["modelo"], "esfuerzo": l.get("esfuerzo"),
                   "capitulos": {}, "fallos": {}}
        tot = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        for r in cli.messages.batches.results(l["id"]):
            cap_id = r.custom_id.split("--", 1)[1]
            if r.result.type != "succeeded":
                informe["fallos"][cap_id] = r.result.type
                continue
            msg = r.result.message
            u = {k: getattr(msg.usage, k, 0) or 0 for k in tot}
            for k in tot:
                tot[k] += u[k]
            if msg.stop_reason != "end_turn":  # refusal o max_tokens: el JSON puede no valer
                informe["fallos"][cap_id] = f"stop_reason={msg.stop_reason}"
                continue
            texto = next((bl.text for bl in msg.content if bl.type == "text"), "")
            try:
                datos = json.loads(texto)
            except json.JSONDecodeError as e:
                informe["fallos"][cap_id] = f"JSON inválido: {e}"
                continue
            historias = datos.get("historias", [])
            palabras = sum(len(h["texto"].split()) for h in historias)
            datos["meta"] = {"era": era_de[cap_id]["id"], "capitulo": cap_id, "modelo": msg.model,
                             "generado": datetime.now(timezone.utc).isoformat(), "uso": u,
                             "coste_usd": round(coste(l["modelo"], u), 4)}
            guardar_json(os.path.join(SALIDA, f"{cap_id}.json"), datos)
            indice[cap_id] = len(historias)
            informe["capitulos"][cap_id] = {
                "historias": len(historias), "palabras_texto": palabras,
                "profundizar": sum(1 for h in historias if h["profundizar"]),
                "enlaces": sum(1 for h in historias if h["conecta_con"]),
                "notas_revision": len(datos.get("notas_revision", [])),
                "tokens_salida": u["output_tokens"], "coste_usd": datos["meta"]["coste_usd"]}
        guardar_json(indice_ruta, indice)
        # Imágenes sin foto en Wikipedia: el prototipo muestra un degradado en su lugar
        titulos = []
        for cap_id in informe["capitulos"]:
            with open(os.path.join(SALIDA, f"{cap_id}.json"), encoding="utf-8") as f:
                titulos += [h["imagen_wikipedia"] for h in json.load(f)["historias"]]
        informe["imagenes_sin_foto"] = imagenes_faltantes(titulos)
        informe["imagenes_total"] = len(titulos)
        informe["uso_total"] = tot
        informe["coste_total_usd"] = round(coste(l["modelo"], tot), 4)
        guardar_json(os.path.join(SALIDA, f"_informe_{l['era']}.json"), informe)
        l["descargado"] = True
        guardar_json(LOTES, lotes)
        n = len(informe["capitulos"])
        print(f"{l['era']}: {n} capítulos guardados, {len(informe['fallos'])} fallos, "
              f"coste real {informe['coste_total_usd']:.2f} USD "
              f"({tot['input_tokens']:,} tokens entrada, {tot['output_tokens']:,} salida).")
        if informe["fallos"]:
            print("  Fallos:", informe["fallos"])
        if informe["imagenes_sin_foto"]:
            print(f"  Sin imagen en Wikipedia: {informe['imagenes_sin_foto']}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("simular", "enviar"):
        s = sub.add_parser(nombre)
        s.add_argument("--era", required=True)
        s.add_argument("--modelo", choices=MODELOS, default="opus")
        s.add_argument("--esfuerzo", choices=["low", "medium", "high"], default="high")
        s.add_argument("--caps", type=lambda s: set(s.split(",")), default=None)
    e = sub.add_parser("estado")
    e.add_argument("--esperar", action="store_true", help="espera hasta que terminen todos los lotes")
    d = sub.add_parser("descargar")
    for s in sub.choices.values():
        s.add_argument("--salida", default="historias",
                       help="carpeta dentro de biblia/prototipo (p. ej. historias_sonnet para comparar modelos)")
    a = p.parse_args()
    # La carpeta de salida guarda también su propio registro de lotes
    global SALIDA, LOTES
    SALIDA = os.path.join(PROTO, a.salida)
    LOTES = os.path.join(SALIDA, "_lotes.json")
    try:
        {"simular": cmd_simular, "enviar": cmd_enviar, "estado": cmd_estado, "descargar": cmd_descargar}[a.cmd](a)
    except anthropic.AuthenticationError:
        sys.exit("Clave de API no válida. Revisa ANTHROPIC_API_KEY.")
    except anthropic.BadRequestError as e:
        sys.exit(f"Petición rechazada por la API: {e.message}")
    except anthropic.APIConnectionError:
        sys.exit("Sin conexión con la API de Anthropic.")


if __name__ == "__main__":
    main()
