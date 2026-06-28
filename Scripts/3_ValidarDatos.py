"""
3_ValidarDatos.py — Aplica fusiones de personas APROBADAS MANUALMENTE
─────────────────────────────────────────────────────────────────────
Entrada : data/rtve_23f_corpus_clean.json              (de 01_LimpiezaDatos.py)
          data/entity_merge_candidates_revisado.csv      (revisado por el usuario)
          data/overrides_manuales.json                   (opcional — entidades
                                                            que RTVE no etiquetó,
                                                            añadidas a mano)
Salida  : data/rtve_23f_corpus_final.json               (listo para el resto del pipeline)
 
El CSV de candidatos tiene columnas: nombre_a, nombre_b, score, aprobar_fusion(si/no)
 
Entidades faltantes (overrides_manuales.json):
    Si en la revisión manual se encontraron personas mencionadas en el texto que
    RTVE nunca etiquetó como 'persona' (p.ej. "Teniente Ochando", mencionado
    en diálogo pero ausente de la lista de entidades), se añadirían aquí:
        { "id_documento": { "entidades_faltantes": ["Teniente Ochando", ...] } }
    Este script las inyecta en 'personas' ANTES de la fusión, así que entran
    también en el proceso de Union-Find si coinciden con algo del CSV.
    (Los campos 'alias'/'secciones' del mismo archivo, para resolver términos
    ambiguos como "A" o "Capitán" dentro de un texto concreto, los consume
    5_ExtraerRelaciones.py más adelante — no son responsabilidad de este script).
 
    Se usa Union-Find (componentes conexas): porque agrupa TODAS las filas
    aprobadas en clústeres, sin importar el orden en que aparezcan en el CSV,
    y dentro de cada clúster elige como nombre canónico el MÁS FRECUENTE en el
    corpus real (no necesariamente nombre_a) — así el resultado no depende de
    qué columna se puso primero al escribir el CSV.
 
Uso:
    python scripts/03_ValidarDatos.py
    python scripts/03_ValidarDatos.py --approved data/entity_merge_candidates_revisado.csv
    python scripts/03_ValidarDatos.py --canonical-strategy mas_largo
"""
 
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
 
DEFAULT_INPUT    = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus_clean.json"
DEFAULT_APPROVED = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates_revisado.csv"
DEFAULT_OUTPUT   = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus_final.json"
DEFAULT_OVERRIDES = Path(__file__).resolve().parent.parent / "data" / "overrides_manuales.json"  # revisión manual humana
DEFAULT_CANONICAL_MAP = Path(__file__).resolve().parent.parent / "data" / "entity_canonical_map.json"

DECISIONES_APROBADAS = {"si", "sí", "yes", "y"}
 
 
# ── Union-Find ────────────────────────────────────────────────────────────────
 
class UnionFind:
    """Estructura de conjuntos disjuntos para agrupar nombres fusionados
    sin que el resultado dependa del orden de las filas del CSV."""
 
    def __init__(self):
        self.parent: dict[str, str] = {}
 
    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        raiz = x
        while self.parent[raiz] != raiz:
            raiz = self.parent[raiz]
        # compresión de camino (path compression) para eficiencia
        while self.parent[x] != raiz:
            self.parent[x], x = raiz, self.parent[x]
        return raiz
 
    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[rx] = ry
 
    def grupos(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for nombre in self.parent:
            out[self.find(nombre)].add(nombre)
        return out
 
 
# ── Construcción del mapeo canónico ──────────────────────────────────────────
 
def construir_mapeo_canonico(
    csv_path: Path,
    corpus: list[dict],
    canonical_strategy: str,
) -> dict[str, str]:
    """
    Agrupa con Union-Find todos los pares aprobados ('si') y devuelve un
    diccionario {variante: nombre_canonico} para TODAS las variantes de
    cada clúster con más de un miembro.
 
    canonical_strategy:
        'mas_frecuente' (por defecto) -> el nombre que más veces aparece
                                          literalmente en el corpus real.
        'mas_largo'                   -> el nombre más largo del clúster
                                          (suele ser el más completo/formal).
        'nombre_a_primera_fila'       -> comportamiento equivalente al
                                          script anterior, por compatibilidad.
    """
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
 
    uf = UnionFind()
    orden_aparicion: dict[str, int] = {}
    contador = 0
 
    for r in rows:
        decision = r.get("aprobar_fusion(si/no)", "").strip().lower()
        if decision not in DECISIONES_APROBADAS:
            continue
        a, b = r["nombre_a"].strip(), r["nombre_b"].strip()
        for nombre in (a, b):
            if nombre not in orden_aparicion:
                orden_aparicion[nombre] = contador
                contador += 1
        uf.union(a, b)
 
    grupos = uf.grupos()
    multi_grupos = {raiz: miembros for raiz, miembros in grupos.items() if len(miembros) > 1}
 
    # Frecuencia real de cada nombre en el corpus (para elegir canónico)
    frecuencia: Counter[str] = Counter()
    for doc in corpus:
        for nombre in doc.get("personas", []):
            frecuencia[nombre.strip()] += 1
 
    mapeo: dict[str, str] = {}
    for miembros in multi_grupos.values():
        if canonical_strategy == "mas_largo":
            canonico = max(miembros, key=lambda m: (len(m), frecuencia.get(m, 0), m))
        elif canonical_strategy == "nombre_a_primera_fila":
            canonico = min(miembros, key=lambda m: orden_aparicion.get(m, float("inf")))
        else:  # "mas_frecuente" (por defecto)
            canonico = max(miembros, key=lambda m: (frecuencia.get(m, 0), len(m), m))
 
        for m in miembros:
            mapeo[m] = canonico
 
    return mapeo
 
 
# ── Entidades faltantes (revisión manual humana) ─────────────────────────────
 
def cargar_overrides_manuales(path: Path) -> dict:
    """
    Carga overrides_manuales.json (revisión manual humana). Solo se usa aquí
    el campo 'entidades_faltantes' de cada documento — personas que RTVE
    nunca etiquetó automáticamente y que se añaden a mano:
        { "id_documento": { "entidades_faltantes": ["Teniente Ochando", ...] } }
    (los campos 'alias'/'secciones', para resolver términos ambiguos como
    "A"/"Capitán" dentro del texto, los consume 5_ExtraerRelaciones.py).
    Si el archivo no existe, devuelve {} sin afectar al resto del script.
    """
    if not path.exists():
        print(f"(Aviso: no se encontró {path} — no se añade ninguna entidad manual)")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
 
 
def aplicar_entidades_faltantes(docs: list, overrides_manuales: dict) -> int:
    """
    Añade al campo 'personas' de cada documento las entidades que la revisión
    manual identificó como FALTANTES (RTVE nunca las etiquetó). Modifica
    'docs' in-place. Devuelve cuántas entidades se añadieron en total.
    """
    añadidas = 0
    for doc in docs:
        entry = overrides_manuales.get(str(doc.get("id")))
        if not entry:
            continue
        faltantes = entry.get("entidades_faltantes", [])
        if not faltantes:
            continue
        personas = doc.setdefault("personas", [])
        existentes = {p.strip().lower() for p in personas}
        for nombre in faltantes:
            if nombre.strip().lower() not in existentes:
                personas.append(nombre)
                existentes.add(nombre.strip().lower())
                añadidas += 1
    return añadidas
 
 
# ── Programa principal ───────────────────────────────────────────────────────
 
def main():
    parser = argparse.ArgumentParser(
        description="Aplica fusiones de personas aprobadas (versión robusta con Union-Find)"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--approved", type=Path, default=DEFAULT_APPROVED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--canonical-map-output", type=Path, default=DEFAULT_CANONICAL_MAP)
    parser.add_argument(
        "--canonical-strategy",
        choices=["mas_frecuente", "mas_largo", "nombre_a_primera_fila"],
        default="mas_frecuente",
        help="Cómo elegir el nombre canónico dentro de cada clúster fusionado",
    )
    args = parser.parse_args()
 
    if not args.input.exists():
        raise SystemExit(f"No se encontró: {args.input} — ejecuta antes 1_LimpiezaDatos.py")
    if not args.approved.exists():
        raise SystemExit(f"No se encontró: {args.approved}")
 
    with open(args.input, encoding="utf-8") as f:
        docs = json.load(f)
 
    overrides_manuales = cargar_overrides_manuales(args.overrides)
    n_faltantes = aplicar_entidades_faltantes(docs, overrides_manuales)
 
    mapeo = construir_mapeo_canonico(args.approved, docs, args.canonical_strategy)
    
    args.canonical_map_output.parent.mkdir(parents=True, exist_ok=True)

    with open(args.canonical_map_output, "w", encoding="utf-8") as f:
        json.dump(mapeo, f, ensure_ascii=False, indent=2)

    n_clusters = len(set(mapeo.values()))
 
    cambios_por_campo: Counter[str] = Counter()
    for doc in docs:
        for campo in ("personas", "lugares", "keywords"):
            originales = doc.get(campo, [])
            deduped, seen = [], set()
            for nombre in originales:
                canon = mapeo.get(nombre.strip(), nombre.strip())
                if canon != nombre.strip():
                    cambios_por_campo[campo] += 1
                if canon not in seen:
                    seen.add(canon)
                    deduped.append(canon)
            doc[campo] = deduped
 
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
 
    print(f"{'─' * 50}")
    print(f"Entidades faltantes añadidas manualmente : {n_faltantes}")
    print(f"Variantes mapeadas a un canónico : {len(mapeo)}")
    print(f"Clústeres (entidades únicas)     : {n_clusters}")
    print(f"Cambios aplicados por campo      : {dict(cambios_por_campo)}")
    print(f"JSON final guardado en           : {args.output}")
    print(f"Mapeo canónico guardado en      : {args.canonical_map_output}")
 
    if not mapeo:
        print("\n No se aplicó ninguna fusión — revisa que hayas escrito 'si'")
        print("   en la columna 'aprobar_fusion(si/no)' del CSV.")
 
 
if __name__ == "__main__":
    main()