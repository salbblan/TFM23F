"""
5_ExtraerRelaciones.py
----------------------
Extrae relaciones tipadas entre entidades (personas/lugares) a partir del corpus del 23-F, usando:
  1) El mapeo de fusión de entidades ya revisado (CSV) para normalizar
     variantes de nombre a un nombre canónico.
  2) Un diccionario de patrones léxicos (verbos/expresiones) para detectar
     13 tipos de relación dentro de cada frase.
 
Reglas aplicadas (decisiones acordadas):
  - Si dos entidades coinciden en una frase pero ningún verbo de la lista coincide -> se descarta la frase (no se genera relación genérica).
  - No se infiere dirección sujeto - objeto: la relación se guarda como no dirigida (par de entidades sin importar el orden), aunque ambos
    nombres se conservan en columnas separadas tal y como aparecen.
 
Salida: CSV con columnas:
    documento_id, documento_titulo, documento_url,
    entidad_1, relacion, entidad_2, frase_evidencia
"""
 
import csv
import json
import re
import unicodedata
from collections import defaultdict
from itertools import combinations
from pathlib import Path
 

# Rutas 

CSV_FUSION_PATH = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates_revisado.csv"
CORPUS_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus_final.json"  # de 3_ValidarDatos.py - ya incluye entidades faltantes
ALIAS_LOCALES_PATH = Path(__file__).resolve().parent.parent / "data" / "alias_locales_por_documento.json"  # de 4_ResolverGenericosLocal.py
OVERRIDES_MANUALES_PATH = Path(__file__).resolve().parent.parent / "data" / "overrides_manuales.json"  # solo 'alias'/'secciones' (revisión manual)
OUTPUT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "relaciones_extraidas.csv"
OUTPUT_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "relaciones_extraidas.json"
CANONICAL_MAP_PATH = Path(__file__).resolve().parent.parent / "data" / "entity_canonical_map.json" 

# Longitud mínima de un alias para considerarlo válido como mención deentidad (evita falsos positivos con nombres de pila sueltos muy cortos).
MIN_ALIAS_LEN = 4
 
 

# 1. Diccionario de relaciones, patrones regex (sin acentos, minúsculas)

RELATION_PATTERNS = {
    "SE_REUNE_CON": [
        r"se reun\w* con", r"reunion\w* con", r"se entrevist\w* con",
        r"se vio con", r"se vieron",
    ],
    "INFORMA_A": [
        r"inform\w* a\b", r"dio cuenta a", r"puso al corriente a",
    ],
    "PERTENECE_A": [
        r"pertenec\w* a", r"miembro de", r"forma(?:ba)? parte de",
        r"integrante de",
    ],
    "LLAMA_A": [
        r"llam\w* a\b", r"telefone\w*", r"llamada telefonica a",
    ],
    "VISITA": [
        r"visit\w*",
    ],
    "RECIBE_ORDEN": [
        r"recib\w* (?:la )?orden", r"dio la orden a", r"orden\w* a\b",
        r"a las ordenes de",
    ],
    "PROPONE": [
        r"propon\w*", r"propuso",
    ],
    "SOLICITA": [
        r"solicit\w*", r"pid(?:e|io|ieron|io)\b", r"peticion de",
    ],
    "COLABORA": [
        r"colabor\w*",
    ],
    "CONOCE": [
        r"conoc\w*",
    ],
    "NIEGA": [
        r"nieg\w*", r"neg(?:o|aron)\b", r"desminti\w*",
    ],
    "AUTORIZA": [
        r"autoriz\w*",
    ],
    "MENCIONA": [
        r"mencion\w*", r"cit(?:o|aron|ado|ada)\b",
    ],
}
 
# Compilar todos los patrones una sola vez (sobre texto ya sin acentos)
COMPILED_PATTERNS = {
    relation: [re.compile(p, re.IGNORECASE) for p in patterns]
    for relation, patterns in RELATION_PATTERNS.items()
}
 
 
MESES_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}
 
 
def extraer_fecha(*textos: str):
    """
    Intento best-effort de extraer una fecha en formato YYYY-MM-DD a partir
    del título o el texto de un documento. Busca, por orden de prioridad:
        1. "18 de febrero de 1981"           (fecha completa con nombre de mes)
        2. "18-02-1981" / "18/02/1981"        (fecha con año de 4 cifras)
        3. "18-02-81" / "FECHA:18-02-81"      (fecha corta en cabecera/membrete, muy común en los documentos militares de este corpus: códigos de referencia tipo "C/SG/2820/20-02-82")
    Si no encuentra nada reconocible, devuelve None (no se inventa fecha).
 
    NOTA: para años de 2 cifras se asume el prefijo "19" (válido para este corpus, que cubre 1981-1982). Si se reutiliza este script con documentos de otra época, ese supuesto habría que revisarlo.
 
    NOTA 2: fechas que solo dan mes y año ("diciembre de 1981", sin día) se descartan a propósito - devolver "1981-12-01" inventaría un día que el documento no especifica.
    """
    for texto in textos:
        if not texto:
            continue
        texto_lower = texto.lower()
 
        m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", texto_lower)
        if m:
            dia, mes_nombre, anio = m.groups()
            mes = MESES_ES.get(mes_nombre)
            if mes:
                return f"{anio}-{mes}-{int(dia):02d}"
 
        # Año de 2 O 4 cifras (cubre tanto "18/02/1981" como "20-02-82")
        m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", texto_lower)
        if m:
            dia, mes, anio = m.groups()
            if len(anio) == 2:
                anio = "19" + anio
            return f"{anio}-{int(mes):02d}-{int(dia):02d}"
 
        m = re.search(r"\b(19\d{2})-(\d{2})-(\d{2})\b", texto_lower)
        if m:
            return m.group(0)
 
    return None
 
 
def quitar_acentos(texto: str) -> str:
    """Normaliza acentos para que el matching de patrones sea robusto independientemente de tildes (informó / informo, etc.)."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
 
 
def dividir_en_frases(texto: str):
    """División simple de un texto en frases usando puntuación básica."""
    if not texto:
        return []
    # Normaliza saltos de línea a espacios para no cortar frases a medias
    texto = texto.replace("\n", " ")
    frases = re.split(r"(?<=[\.\!\?])\s+", texto)
    return [f.strip() for f in frases if f.strip()]
 
 
# 2. Construir el diccionario de alias 

def cargar_mapeo_canonico(path: Path) -> dict:
    """
    Carga el mapeo alias -> nombre canónico generado por 3_ValidarDatos.py. Así se evita recalcular las fusiones y se garantiza que todo el pipeline usa exactamente los mismos nombres canónicos.
    """
    if not path.exists():
        raise SystemExit(
            f"No se encontró: {path}\n"
            "Ejecuta antes 3_ValidarDatos.py para generar entity_canonical_map.json"
        )

    with open(path, encoding="utf-8") as f:
        return json.load(f)
 
def construir_diccionario_alias(corpus: list, mapeo_canonico: dict):
    """
    Construye {alias_en_minusculas: nombre_canonico} para todas las entidades (personas/lugares) presentes en el corpus, fusionadas o no. Las que no aparecen en mapeo_canonico se mapean a sí mismas.
    """
    alias_dict = {}
    for doc in corpus:
        for campo in ("personas", "lugares"):
            for nombre in doc.get(campo, []):
                nombre = nombre.strip()
                if len(nombre) < MIN_ALIAS_LEN:
                    continue
                canonico = mapeo_canonico.get(nombre, nombre)
                alias_dict[nombre.lower()] = canonico
    return alias_dict
 
 
def cargar_alias_locales(path: Path) -> dict:
    """
    Carga el JSON generado por 4_ResolverGenericosLocal.py:
        { "id_documento": { "termino_generico": "nombre_canonico" } }
    Si el archivo no existe, devuelve un diccionario vacío (la extracción de relaciones sigue funcionando igual, solo sin resolver genéricos).
    """
    if not path.exists():
        print(f"(Aviso: no se encontró {path} - se continúa sin resolver "
              f"términos genéricos locales por documento)")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
 
 
def cargar_overrides_manuales(path: Path) -> dict:
    """
    Carga el JSON de revisión manual humana (overrides_manuales.json):
        {
          "id_documento": {
            "alias": { "termino": "canonico" }              // caso simple
          }
        }
    o, para documentos donde un mismo término ("Capitán", "A"...) se refiere a personas distintas en distintas partes del documento (p.ej. varias 
      cintas de una transcripción telefónica):
        {
          "id_documento": {
            "secciones": [
              {
                "marcador_inicio": "CINTA - 1, CARA - 1",
                "marcador_fin": "CINTA - 1, CARA - 2",   // null = hasta el final
                "alias": { "Capitán": "Capitán Díaz Sánchez" }
              },
              ...
            ]
          }
        }
    Si el archivo no existe, devuelve {} (no afecta al resto del pipeline).
    """
    if not path.exists():
        print(f"(Aviso: no se encontró {path} - se continúa sin overrides manuales)")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
 
 
def obtener_segmentos_documento(
    texto: str,
    doc_id,
    alias_locales: dict,
    overrides_manuales: dict,
) -> list:
    """
    Devuelve una lista de (texto_segmento, alias_extra_dict) que cubre todo el texto del documento. Para documentos sin overrides o con un override
    'alias' simple (sin secciones), devuelve un único segmento con todo el texto. Para documentos con 'secciones', divide el texto según los
    marcadores literales indicados (p.ej. "CINTA - 1, CARA - 1"), aplicando a cada sección su propio diccionario de alias además de la base.
 
    El texto ANTES del primer marcador (si lo hay) usa solo la base, sin ningún alias de sección - por si hay contenido fuera de las cintas delimitadas (cabeceras, índices, etc.).
    """
    alias_base = dict(alias_locales.get(str(doc_id), {}))
    entry = overrides_manuales.get(str(doc_id))
 
    if not entry:
        return [(texto, alias_base)]
 
    if "secciones" not in entry:
        alias_doc = dict(alias_base)
        alias_doc.update(entry.get("alias", {}))
        return [(texto, alias_doc)]
 
    # Caso con secciones: localizar cada marcador de inicio en el texto
    marcadores = []
    for sec in entry["secciones"]:
        idx = texto.find(sec["marcador_inicio"])
        if idx == -1:
            print(f"  (Aviso: marcador no encontrado en doc {doc_id}: "
                  f"{sec['marcador_inicio']!r} - esa sección se omite)")
            continue
        marcadores.append((idx, sec))
    marcadores.sort(key=lambda par: par[0])
 
    if not marcadores:
        return [(texto, alias_base)]
 
    # Calcular el rango (inicio, fin, alias) de cada sección definida
    rangos_seccion = []
    for i, (idx_inicio, sec) in enumerate(marcadores):
        marcador_fin = sec.get("marcador_fin")
        if marcador_fin:
            idx_fin = texto.find(marcador_fin, idx_inicio)
            idx_fin = idx_fin if idx_fin != -1 else len(texto)
        elif i + 1 < len(marcadores):
            idx_fin = marcadores[i + 1][0]
        else:
            idx_fin = len(texto)
 
        alias_seccion = dict(alias_base)
        alias_seccion.update(sec.get("alias", {}))
        rangos_seccion.append((idx_inicio, idx_fin, alias_seccion))
 
    # Recorrer el texto de principio a fin, rellenando con alias_base cualquier hueco que quede entre secciones (p.ej. el propio marcador_fin 
    # y lo que venga después, si no coincide exactamente con el siguiente marcador_inicio) - así no se pierde ningún fragmento de texto.
    segmentos = []
    cursor = 0
    for idx_inicio, idx_fin, alias_seccion in rangos_seccion:
        if idx_inicio > cursor:
            segmentos.append((texto[cursor:idx_inicio], dict(alias_base)))
        segmentos.append((texto[idx_inicio:idx_fin], alias_seccion))
        cursor = max(cursor, idx_fin)
    if cursor < len(texto):
        segmentos.append((texto[cursor:], dict(alias_base)))
 
    return segmentos
 
 
 
def compilar_detector_documento(alias_ordenados_doc: list):
    """
    Compila, para un documento concreto, UN ÚNICO patrón regex que contiene todos los alias como alternativas (en vez de hacer una
    búsqueda regex por cada alias, que con miles de alias y miles de frases sería extremadamente lento: O(nº_alias x nº_frases)).
 
    Con un solo patrón compilado, cada frase se analiza en una sola pasada: O(nº_frases). Las alternativas se ordenan por longitud
    descendente para que, ante solapamiento, el regex prefiera la coincidencia más larga (p.ej. 'Milans Del Bosch' antes que 'Milans').
 
    Devuelve (patron_compilado, alias_a_canonico) donde alias_a_canonico es un diccionario {alias_en_minusculas: nombre_canonico} ya con los
    alias locales del documento aplicados (y con prioridad sobre los globales si coinciden, por construir_alias_para_documento).
    """
    alias_unicos = sorted({alias for alias, _ in alias_ordenados_doc}, key=lambda a: (-len(a), a))
    if not alias_unicos:
        return None, {}
    patron = re.compile(
        r"\b(" + "|".join(re.escape(a) for a in alias_unicos) + r")\b",
        re.IGNORECASE,
    )
    alias_a_canonico = dict(alias_ordenados_doc)
    return patron, alias_a_canonico
 
 
def detectar_entidades_en_frase(frase: str, patron, alias_a_canonico: dict):
    """
    Aplica el patrón combinado (una sola pasada) y traduce cada coincidencia a su nombre canónico. Devuelve el conjunto de nombres canónicos
    detectados en la frase.
    """
    if patron is None:
        return set()
    frase_lower = frase.lower()
    encontrados = set()
    for m in patron.finditer(frase_lower):
        alias_encontrado = m.group(1)
        canonico = alias_a_canonico.get(alias_encontrado, alias_encontrado)
        encontrados.add(canonico)
    return encontrados
 
 
# Ventana de caracteres antes del verbo donde se busca una negación.
# Suficiente para cubrir "no se reunió", "nunca autorizó", "tampoco solicitó", pero corto para no capturar negaciones de otra parte de la frase que no afectan gramaticalmente a este verbo.
VENTANA_NEGACION_CHARS = 25
PATRON_NEGACION = re.compile(r"\b(no|nunca|tampoco|ni)\b", re.IGNORECASE)
 
 
def detectar_relaciones_en_frase(frase_sin_acentos: str):
    """
    Devuelve una lista de tuplas (relacion, negada) por cada relación cuyo
    patrón coincide en la frase.
 
    'negada' es True si justo antes del verbo que disparó la relación aparece una palabra de negación (no/nunca/tampoco/ni) dentro de una
    ventana corta de caracteres - es decir, la negación se comprueba localmente junto al verbo, no en toda la frase, para no marcar como
    negada una relación cuya negación en realidad pertenece a otra parte de la frase.
 
    No se descarta ninguna relación negada (se conserva la información), para que pueda filtrarse o revisarse después según convenga.
    """
    relaciones_encontradas = []
    for relacion, patrones in COMPILED_PATTERNS.items():
        for patron in patrones:
            m = patron.search(frase_sin_acentos)
            if m:
                inicio_ventana = max(0, m.start() - VENTANA_NEGACION_CHARS)
                ventana = frase_sin_acentos[inicio_ventana:m.start()]
                negada = bool(PATRON_NEGACION.search(ventana))
                relaciones_encontradas.append((relacion, negada))
                break  # con un patrón que matchee es suficiente para esta relación
    return relaciones_encontradas
 
 

# 3. Pipeline principal

def main():
    with open(CORPUS_JSON_PATH, encoding="utf-8") as f:
        corpus = json.load(f)
 
    print(f"Documentos cargados: {len(corpus)}")
 
    overrides_manuales = cargar_overrides_manuales(OVERRIDES_MANUALES_PATH)
 
    mapeo_canonico = cargar_mapeo_canonico(CANONICAL_MAP_PATH)
    alias_dict = construir_diccionario_alias(corpus, mapeo_canonico)
    print(f"Alias de entidades indexados: {len(alias_dict)}")
 
    # Ordenar alias por longitud descendente para el matching greedy
    alias_ordenados_global = sorted(alias_dict.items(), key=lambda kv: -len(kv[0]))
 
    alias_locales = cargar_alias_locales(ALIAS_LOCALES_PATH)
    total_alias_locales = sum(len(v) for v in alias_locales.values())
    print(f"Alias locales por documento cargados: {total_alias_locales} "
          f"(en {len(alias_locales)} documentos)")
    print(f"Overrides manuales cargados: {len(overrides_manuales)} documentos")
 
    filas_salida = []
    total_frases = 0
    frases_con_2_o_mas_entidades = 0
 
    for i, doc in enumerate(corpus, 1):
        doc_id = doc.get("id")
        doc_title = doc.get("title", "")
        doc_url = doc.get("source_url", "").strip()
        if not doc_url:
            # Fallback: la URL es determinista a partir del id, según el
            # propio patrón de 0_DescargarDatos.py (DOC_URL). Esto cubre
            # los casos donde source_url no se guardó correctamente en la
            # descarga original.
            doc_url = f"https://23fbuscador.rtve.es/document/ocr/{doc_id}"
        texto = doc.get("clean_text") or doc.get("text") or ""
        doc_fecha = extraer_fecha(doc_title, texto)
 
        # Segmentos del documento: normalmente uno solo (todo el texto),
        # pero si hay overrides con 'secciones' (p.ej. varias "CINTA"s con
        # distinto significado para un mismo término ambiguo), se divide
        # en varios trozos, cada uno con su propio diccionario de alias.
        segmentos = obtener_segmentos_documento(texto, doc_id, alias_locales, overrides_manuales)
 
        n_frases_doc = 0
        for texto_segmento, alias_extra_segmento in segmentos:
            extra = [(t.lower(), c) for t, c in alias_extra_segmento.items()]
            alias_ordenados_seg = sorted(alias_ordenados_global + extra, key=lambda kv: -len(kv[0]))
            patron_seg, alias_a_canonico_seg = compilar_detector_documento(alias_ordenados_seg)
 
            frases = dividir_en_frases(texto_segmento)
            n_frases_doc += len(frases)
 
            for frase in frases:
                total_frases += 1
                entidades = detectar_entidades_en_frase(frase, patron_seg, alias_a_canonico_seg)
 
                if len(entidades) < 2:
                    continue
                frases_con_2_o_mas_entidades += 1
 
                frase_sin_acentos = quitar_acentos(frase.lower())
                relaciones = detectar_relaciones_en_frase(frase_sin_acentos)
 
                if not relaciones:
                    # Decisión acordada: sin verbo de relación se descarta 
                    continue
 
                # Relación no dirigida: una fila por cada par de entidades distintas y cada relación detectada en la frase.
                for e1, e2 in combinations(sorted(entidades), 2):
                    for relacion, negada in relaciones:
                        filas_salida.append({
                            "documento_id": doc_id,
                            "documento_titulo": doc_title,
                            "documento_url": doc_url,
                            "documento_fecha": doc_fecha,
                            "entidad_1": e1,
                            "relacion": relacion,
                            "negada": negada,
                            "entidad_2": e2,
                            "frase_evidencia": frase,
                        })
 
        print(f"  [{i:3d}/{len(corpus)}] doc {doc_id} - {n_frases_doc} frases "
              f"({len(segmentos)} segmento{'s' if len(segmentos) != 1 else ''})", flush=True)
 
    n_negadas = sum(1 for f in filas_salida if f["negada"])
    print(f"Frases analizadas: {total_frases}")
    print(f"Frases con 2+ entidades: {frases_con_2_o_mas_entidades}")
    print(f"Relaciones extraídas (filas): {len(filas_salida)}")
    print(f"  de las cuales marcadas como negadas: {n_negadas} "
          f"({100*n_negadas/len(filas_salida):.1f}%)" if filas_salida else "")
 
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "documento_id", "documento_titulo", "documento_url", "documento_fecha",
                "entidad_1", "relacion", "negada", "entidad_2", "frase_evidencia",
            ],
        )
        writer.writeheader()
        writer.writerows(filas_salida)
 
    print(f"Guardado CSV en: {OUTPUT_CSV_PATH.resolve()}")
 
    # ── Generar también el JSON con esquema subject/predicate/object ──────
    # NOTA sobre 'pagina': el corpus de RTVE no conserva la paginación
    # original (se elimina como ruido OCR en la fase de limpieza), así que
    # este campo se deja siempre en null. Si en el futuro se conserva esa
    # información, bastaría con propagarla aquí.
    filas_json = []
    for fila in filas_salida:
        filas_json.append({
            "subject": fila["entidad_1"],
            "predicate": fila["relacion"],
            "negada": fila["negada"],
            "object": fila["entidad_2"],
            "fecha": fila["documento_fecha"],
            "documento": f"DOC_{fila['documento_id']}",
            "documento_url": fila["documento_url"],
            "pagina": None,
            "texto": fila["frase_evidencia"],
        })
 
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(filas_json, f, ensure_ascii=False, indent=2)
 
    print(f"Guardado JSON en: {OUTPUT_JSON_PATH.resolve()}")
 
 
if __name__ == "__main__":
    main()
 