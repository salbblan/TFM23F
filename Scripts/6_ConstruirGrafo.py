"""
6_ConstruirGrafo.py — Construcción del grafo de relaciones del 23-F
─────────────────────────────────────────────────────────────────────
Entrada : data/relaciones_extraidas.csv      (de 5_ExtraerRelaciones.py)
          data/rtve_23f_corpus_final.json    (de 3_ValidarDatos.py)
Salida  : data/grafo_23f.graphml             (para Gephi / Cytoscape / networkx)
          data/grafo_23f.json                (formato node-link, para D3.js / front-end)
 
Nodos (4 tipos):
    Persona, Institución, Lugar, Documento
 
Aristas (12 tipos):
    CONOCE, INFORMA, PERTENECE, LLAMA, ASISTE, ORDENA, MENCIONA,
    PROPONE, SOLICITA, COLABORA, AUTORIZA, NIEGA
 
Mapeo aplicado desde las relaciones detalladas de 5_ExtraerRelaciones.py:
    INFORMA_A      -> INFORMA
    PERTENECE_A    -> PERTENECE
    LLAMA_A        -> LLAMA
    VISITA         -> ASISTE
    SE_REUNE_CON   -> ASISTE
    RECIBE_ORDEN   -> ORDENA
    MENCIONA       -> MENCIONA   (sin cambio)
    CONOCE         -> CONOCE     (sin cambio)
    PROPONE, SOLICITA, COLABORA, AUTORIZA, NIEGA -> sin cambio (se añaden tal cual)
 
Además, se añade una arista MENCIONA desde cada nodo Documento hacia cada
entidad que aparece en alguna relación extraída de ese documento — así los
nodos Documento quedan conectados al grafo (trazabilidad: qué documento
habla de qué persona/institución/lugar).
 
Clasificación de entidades en Persona / Institución / Lugar:
    1. Si el nombre contiene una palabra clave de institución (Consejo,
       Tribunal, CESID, Guardia Civil, Ministerio, PSOE...) -> Institución.
    2. Si no, y el nombre aparece en el campo 'lugares' del corpus -> Lugar.
    3. En cualquier otro caso -> Persona (incluye los términos genéricos
       no resueltos, que quedan como Persona por defecto).
 
No se usa el tipo Evento en esta versión (decisión acordada).
 
Uso:
    python scripts/6_ConstruirGrafo.py
"""
 
import argparse
import csv
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path
 
try:
    import networkx as nx
except ImportError:
    nx = None
 
DEFAULT_RELACIONES = Path(__file__).resolve().parent.parent / "data" / "relaciones_extraidas.csv"
DEFAULT_CORPUS     = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus_final.json"  # de 3_ValidarDatos.py — ya incluye entidades faltantes
DEFAULT_CSV_FUSION = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates_revisado.csv"
DEFAULT_GRAPHML    = Path(__file__).resolve().parent.parent / "data" / "grafo_23f.graphml"
DEFAULT_JSON        = Path(__file__).resolve().parent.parent / "data" / "grafo_23f.json"
 
# ── Mapeo de relaciones detalladas -> aristas del grafo ──────────────────────
MAPEO_RELACIONES = {
    "INFORMA_A": "INFORMA",
    "PERTENECE_A": "PERTENECE",
    "LLAMA_A": "LLAMA",
    "VISITA": "ASISTE",
    "SE_REUNE_CON": "ASISTE",
    "RECIBE_ORDEN": "ORDENA",
    "MENCIONA": "MENCIONA",
    "CONOCE": "CONOCE",
    "PROPONE": "PROPONE",
    "SOLICITA": "SOLICITA",
    "COLABORA": "COLABORA",
    "AUTORIZA": "AUTORIZA",
    "NIEGA": "NIEGA",
}
 
# ── Palabras clave para detectar Instituciones ───────────────────────────────
PALABRAS_INSTITUCION = [
    "consejo", "tribunal", "cesid", "ejercito", "ejército", "gobierno",
    "psoe", "guardia civil", "ministerio", "junta", "partido", "iglesia",
    "embajada", "prensa", "diario", "periodico", "periódico", "policia",
    "policía", "fas", "ucd", "pce", "onu", "otan", "rtve", "confederacion",
    "confederación", "comite", "comité", "asociacion", "asociación",
    "movimiento", "fiscalia", "fiscalía", "fiscal", "sala", "estado mayor",
    "capitania", "capitanía", "division", "división", "regimiento",
    "ejecutivo", "congreso", "senado", "audiencia", "juzgado", "brigada",
    "comandancia", "direccion general", "dirección general", "casa real",
]
PATRON_INSTITUCION = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in PALABRAS_INSTITUCION) + r")\b",
    re.IGNORECASE,
)
 
# Palabras de rango/cargo/partícula a ignorar al buscar si queda un nombre
# propio distintivo tras quitar la parte institucional. Reutiliza la misma
# idea que 2_RevisarCandidatos.py: si no queda nada relevante, es un
# término puramente genérico/institucional; si queda algo, es una persona
# concreta (p.ej. "Capitán De La Guardia Civil Muñecas" -> queda "Muñecas").
PALABRAS_IGNORABLES = set(PALABRAS_INSTITUCION) | {
    "el", "la", "los", "las", "de", "del", "don", "dona", "doña", "sr", "sra",
    "señor", "señora", "excmo", "excma", "ilmo", "ilma", "general", "teniente",
    "coronel", "capitan", "capitán", "comandante", "sargento", "cabo", "soldado",
    "militar", "consejero", "togado", "juez", "especial", "presidente",
    "vicepresidente", "secretario", "fiscal", "defensor", "defensores",
    "letrado", "letrados", "abogado", "abogados", "ministro", "director",
    "directora", "divis", "cuerpo", "y", "e", "o", "su", "majestad", "rey",
    "reina", "vuestra", "excelencia", "d", "dr", "testigo", "testigos",
    "regimiento", "zona", "region", "región", "oficial", "jefe", "jefatura",
    "mando", "mandos", "cuadro", "cuadros",
}
MIN_LEN_NOMBRE_PROPIO = 3
 
# ── Corrección manual: personas reales que RTVE etiquetó por error SOLO en
# el campo 'lugares' en algún documento (nunca como 'persona' en ninguno),
# así que la priorización personas > lugares no las detecta por sí sola.
# Se fuerza su tipo a Persona, con prioridad sobre cualquier otra regla.
# Encontradas mediante revisión manual de los nodos Lugar.
PERSONAS_MAL_ETIQUETADAS_COMO_LUGAR = {
    "Coronel San Martin",
    "General Caruana",
    "General Prieto",
    "Generales Aramburu",
    "Generales Armada",
    "Generales Miláns Del Bosch",
    "Teniente - General Gutiérrez Mellado",
}
 
 
def queda_nombre_propio(nombre: str) -> bool:
    """True si, tras quitar palabras de rango/institución/partículas, queda
    alguna palabra (probable apellido o nombre propio de una persona)."""
    n = nombre.lower()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"[^a-záéíóúñü\s]", " ", n)
    palabras = [w for w in n.split() if len(w) > MIN_LEN_NOMBRE_PROPIO]
    return any(w not in PALABRAS_IGNORABLES for w in palabras)
 
 
# ── Detección de términos genéricos a excluir del grafo (misma heurística
# que 2_RevisarCandidatos.py: nombres que aparecen emparejados con MUCHAS
# entidades distintas y heterogéneas entre sí — señal de que son cargos o
# colectivos genéricos, no una persona/institución concreta) ────────────────
STOPWORDS_GENERICOS = set("""
    el la los las de del don dona doña sr sra señor señora excmo excma ilmo ilma
    general teniente coronel capitan capitán comandante sargento cabo soldado
    guardia civil militar consejero togado juez especial presidente vicepresidente
    secretario fiscal defensor defensores letrado letrados abogado abogados ministro
    ministerio gobierno estado director directora division divis cuerpo y e o
    su majestad rey reina vuestra excelencia ve vi excmo sr sra d dr
    testigo testigos consejo supremo justicia militar sala tribunal regimiento
    zona region militar division cuerpo armada ejercito ejército fuerzas armadas
    comandancia jefe jefatura oficial mando mandos cuadro cuadros
""".split())
MIN_WORD_LEN_GENERICO = 4
HUB_MIN_DEGREE = 5
HUB_MAX_AVGSIM = 0.15
 
 
def _palabras_significativas_generico(nombre: str) -> set:
    n = nombre.lower()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"[^a-záéíóúñü\s]", " ", n)
    return {w for w in n.split() if len(w) > MIN_WORD_LEN_GENERICO and w not in STOPWORDS_GENERICOS}
 
 
def detectar_terminos_genericos_a_excluir(csv_fusion_path: Path) -> set:
    """
    Reutiliza la heurística de 2_RevisarCandidatos.py: un nombre que aparece
    emparejado con >= HUB_MIN_DEGREE entidades distintas, cuyos compañeros
    son heterogéneos entre sí (poca similitud de palabras), es un término
    genérico (cargo, colectivo...) y no representa una entidad concreta.
    Estos se EXCLUYEN del grafo final (no solo de la fusión).
    """
    if not csv_fusion_path.exists():
        print(f"(Aviso: no se encontró {csv_fusion_path} — no se excluye ningún término genérico)")
        return set()
 
    rows = list(csv.DictReader(open(csv_fusion_path, encoding="utf-8")))
    partners: dict[str, set] = defaultdict(set)
    for r in rows:
        a, b = r["nombre_a"].strip(), r["nombre_b"].strip()
        partners[a].add(b)
        partners[b].add(a)
 
    genericos = set()
    for nombre, companeros in partners.items():
        if len(companeros) < HUB_MIN_DEGREE:
            continue
        companeros = list(companeros)
        sw = {c: _palabras_significativas_generico(c) for c in companeros}
        similitudes = []
        for c1, c2 in combinations(companeros, 2):
            s1, s2 = sw[c1], sw[c2]
            if not s1 and not s2:
                continue
            union_ = s1 | s2
            inter = s1 & s2
            similitudes.append(len(inter) / len(union_) if union_ else 0.0)
        avg_sim = sum(similitudes) / len(similitudes) if similitudes else 0.0
        if avg_sim < HUB_MAX_AVGSIM:
            genericos.add(nombre)
    return genericos
 
 
def cargar_categorias_corpus(corpus_path: Path):
    """Devuelve (set_personas, set_lugares) con los nombres canónicos tal
    como aparecen en los campos 'personas' y 'lugares' del corpus final."""
    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)
    personas, lugares = set(), set()
    for doc in corpus:
        personas.update(p.strip() for p in doc.get("personas", []))
        lugares.update(l.strip() for l in doc.get("lugares", []))
    return personas, lugares
 
 
def clasificar_entidad(nombre: str, personas: set, lugares: set) -> str:
    # Corrección manual con prioridad máxima (ver PERSONAS_MAL_ETIQUETADAS_COMO_LUGAR)
    if nombre in PERSONAS_MAL_ETIQUETADAS_COMO_LUGAR:
        return "Persona"
 
    coincide_institucion = bool(PATRON_INSTITUCION.search(nombre))
    if coincide_institucion:
        # Si tras quitar la parte institucional/rango queda un apellido o
        # nombre propio (p.ej. "Muñecas" en "Capitán De La Guardia Civil
        # Muñecas"), es una PERSONA con cargo, no una institución genérica.
        if not queda_nombre_propio(nombre):
            return "Institución"
        # Si queda nombre propio, cae al resto de comprobaciones (Persona/Lugar)
 
    # IMPORTANTE: se comprueba 'personas' ANTES que 'lugares'. El propio
    # etiquetado automático de RTVE mete a veces nombres de personas reales
    # en el campo 'lugares' de algún documento por error (falso positivo de
    # su NER) — p.ej. "Comandante Cortina" o "Teniente General Miláns Del
    # Bosch" aparecían así. Si no priorizáramos 'personas', estas figuras
    # acabarían mal clasificadas como Lugar en el grafo.
    if nombre in personas:
        return "Persona"
    if nombre in lugares:
        return "Lugar"
    # 'Persona' por defecto, incluso si no aparece literalmente en ningún
    # set (puede ser una variante ya fusionada a un canónico que sí está
    # en el set, o un término genérico no resuelto).
    return "Persona"
 
 
def main():
    parser = argparse.ArgumentParser(description="Construye el grafo de relaciones del 23-F")
    parser.add_argument("--relaciones", type=Path, default=DEFAULT_RELACIONES)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--csv-fusion", type=Path, default=DEFAULT_CSV_FUSION)
    parser.add_argument("--out-graphml", type=Path, default=DEFAULT_GRAPHML)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument(
        "--excluir-genericos", dest="excluir_genericos", action="store_true", default=False,
        help="Excluye del grafo los nodos puramente genéricos (cargos/colectivos sin "
             "identidad concreta, p.ej. 'Capitán', 'Procesados', 'Tenientes'). "
             "Desactivado por defecto: la heurística automática es poco precisa para "
             "esto (ver discusión en el chat) — se recomienda una lista manual curada "
             "en su lugar, si se quiere retomar esta exclusión.",
    )
    parser.add_argument(
        "--no-excluir-genericos", dest="excluir_genericos", action="store_false",
        help="(Comportamiento por defecto) No excluye ningún nodo genérico.",
    )
    args = parser.parse_args()
 
    if not args.relaciones.exists():
        raise SystemExit(f"No se encontró: {args.relaciones} — ejecuta antes 5_ExtraerRelaciones.py")
    if not args.corpus.exists():
        raise SystemExit(f"No se encontró: {args.corpus} — ejecuta antes 3_ValidarDatos.py")
 
    personas, lugares = cargar_categorias_corpus(args.corpus)
    print(f"Personas conocidas en el corpus : {len(personas)}")
    print(f"Lugares conocidos en el corpus  : {len(lugares)}")
 
    genericos_a_excluir = set()
    if args.excluir_genericos:
        genericos_a_excluir = detectar_terminos_genericos_a_excluir(args.csv_fusion)
        print(f"Términos genéricos a excluir del grafo : {len(genericos_a_excluir)}")
 
    with open(args.relaciones, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    print(f"Relaciones cargadas             : {len(filas)}")
 
    # ── Construir nodos ───────────────────────────────────────────────────
    nodos: dict[str, dict] = {}  # node_id -> atributos
    aristas: list[dict] = []
 
    def asegurar_nodo_entidad(nombre: str):
        if nombre not in nodos:
            tipo = clasificar_entidad(nombre, personas, lugares)
            nodos[nombre] = {"label": nombre, "tipo": tipo}
        return nombre
 
    def asegurar_nodo_documento(doc_id, titulo, url, fecha):
        node_id = f"DOC_{doc_id}"
        if node_id not in nodos:
            nodos[node_id] = {
                "label": titulo or node_id,
                "tipo": "Documento",
                "documento_id": doc_id,
                "url": url,
                "fecha": fecha,
            }
        return node_id
 
    docs_entidades_vistas: set[tuple] = set()  # (doc_node_id, entidad) ya conectados
 
    for fila in filas:
        e1 = asegurar_nodo_entidad(fila["entidad_1"].strip())
        e2 = asegurar_nodo_entidad(fila["entidad_2"].strip())
        relacion_original = fila["relacion"].strip()
        relacion_grafo = MAPEO_RELACIONES.get(relacion_original, relacion_original)
        negada = fila.get("negada", "").strip().lower() in ("true", "si", "sí", "1")
 
        aristas.append({
            "origen": e1,
            "destino": e2,
            "tipo": relacion_grafo,
            "relacion_original": relacion_original,
            "negada": negada,
            "documento_id": fila["documento_id"],
            "documento_fecha": fila.get("documento_fecha", ""),
            "frase_evidencia": fila["frase_evidencia"],
        })
 
        doc_node = asegurar_nodo_documento(
            fila["documento_id"], fila.get("documento_titulo", ""),
            fila.get("documento_url", ""), fila.get("documento_fecha", ""),
        )
        for entidad in (e1, e2):
            clave = (doc_node, entidad)
            if clave not in docs_entidades_vistas:
                docs_entidades_vistas.add(clave)
                aristas.append({
                    "origen": doc_node,
                    "destino": entidad,
                    "tipo": "MENCIONA",
                    "relacion_original": "MENCIONA_DOCUMENTO",
                    "negada": False,
                    "documento_id": fila["documento_id"],
                    "documento_fecha": fila.get("documento_fecha", ""),
                    "frase_evidencia": "",
                })
 
    # ── Filtrar nodos puramente genéricos (y sus aristas) si se ha pedido ──
    if genericos_a_excluir:
        nodos_excluidos = {n for n in nodos if n in genericos_a_excluir}
        n_nodos_antes, n_aristas_antes = len(nodos), len(aristas)
        for n in nodos_excluidos:
            del nodos[n]
        aristas = [
            a for a in aristas
            if a["origen"] not in nodos_excluidos and a["destino"] not in nodos_excluidos
        ]
        print(f"Nodos excluidos (genéricos)     : {len(nodos_excluidos)} "
              f"({n_nodos_antes} -> {len(nodos)})")
        print(f"Aristas excluidas (por arrastre) : {n_aristas_antes - len(aristas)} "
              f"({n_aristas_antes} -> {len(aristas)})")
 
    print(f"{'─' * 50}")
    print(f"Nodos totales   : {len(nodos)}")
    from collections import Counter
    print("  por tipo      :", dict(Counter(n["tipo"] for n in nodos.values())))
    print(f"Aristas totales : {len(aristas)}")
    print("  por tipo      :", dict(Counter(a["tipo"] for a in aristas)))
 
    # ── Guardar como JSON node-link (no depende de networkx) ──────────────
    grafo_json = {
        "nodes": [{"id": node_id, **attrs} for node_id, attrs in nodos.items()],
        "edges": aristas,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(grafo_json, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado JSON (node-link) en : {args.out_json}")
 
    # ── Guardar como GraphML si networkx está disponible ───────────────────
    if nx is None:
        print("\n(networkx no está instalado — se omite la exportación a .graphml;")
        print(" instala con: pip install networkx)")
        return
 
    G = nx.MultiDiGraph()
    for node_id, attrs in nodos.items():
        G.add_node(node_id, **{k: ("" if v is None else v) for k, v in attrs.items()})
    for arista in aristas:
        G.add_edge(
            arista["origen"], arista["destino"],
            tipo=arista["tipo"],
            relacion_original=arista["relacion_original"],
            negada=arista["negada"],
            documento_id=str(arista["documento_id"]),
            frase_evidencia=arista["frase_evidencia"],
        )
 
    nx.write_graphml(G, args.out_graphml)
    print(f"Guardado GraphML en          : {args.out_graphml}")
 
 
if __name__ == "__main__":
    main()
 