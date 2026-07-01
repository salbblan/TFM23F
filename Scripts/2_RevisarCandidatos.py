"""
2_RevisarCandidatos.py - Pre-revisión asistida de candidatos de fusión
─────────────────────────────────────────────────────────────────────
Entrada : data/entity_merge_candidates.csv        (bruto de 1_LimpiarDatos.py)
Salida  : data/entity_merge_candidates_revisado.csv
 
Qué hace (heurística automática, NO decide fusiones por sí sola):
    1. Detecta "términos genéricos / hub": nombres que aparecen emparejados
       con muchas entidades distintas (cargos como "Capitán", "Fiscal",
       "Guardia Civil"...) cuyos compañeros de pareja son muy heterogéneos
       entre sí (poca similitud de palabras significativas). Estos se
       marcan automáticamente como "no" - fusionarlos sería un falso
       positivo casi seguro (mismo cargo, personas distintas).
    2. Para el resto de pares (los candidatos "reales"), agrupa por
       clúster (componentes conexas, usando solo palabras realmente
       infrecuentes en el corpus como conexión) y añade una columna
       'cluster_id' para revisar decisiones relacionadas juntas en
       lugar de fila por fila.
    3. Deja la columna 'aprobar_fusion(si/no)' VACÍA en todo lo que no
       sea claramente genérico - la decisión final de aprobar es manual
 
Tras revisar y completar el CSV (escribiendo 'si'/'no' donde falte),
se usa 3_ValidarDatos.py para aplicar fusiones.
 
Uso:
    python scripts/2_RevisarCandidatos.py
    python scripts/2_RevisarCcandidatos.py --hub-min-degree 5 --hub-max-avgsim 0.15
"""
 
import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from itertools import combinations
from pathlib import Path
 
DEFAULT_INPUT  = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates_revisado.csv"
 
# Umbral de "hub": un nombre que aparece emparejado con >= este número de
# entidades distintas es candidato a ser un término genérico (cargo, rol...).
DEFAULT_HUB_MIN_DEGREE = 5
 
# Si la similitud media entre los "compañeros" de un hub es menor que esto,
# se considera que el hub conecta cosas heterogéneas (= término genérico).
DEFAULT_HUB_MAX_AVGSIM = 0.15
 
# Palabras a ignorar al comparar similitud entre nombres (cargos, partículas,
# títulos genéricos en español). No afecta a los nombres en sí, solo a la
# comparación interna usada para decidir si un hub es genérico.
STOPWORDS = set("""
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
 
MIN_WORD_LEN = 4          # ignorar palabras muy cortas al comparar similitud
RARE_WORD_MAX_DF = 4      # palabra "infrecuente" = aparece en <= N nombres distintos
 
 
def palabras_significativas(nombre: str) -> set[str]:
    """Extrae palabras relevantes de un nombre (sin cargos/títulos/partículas) para comparar similitud entre dos nombres de forma robusta a mayúsculas, acentos y paréntesis."""
    n = nombre.lower()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"[^a-záéíóúñü\s]", " ", n)
    return {w for w in n.split() if len(w) > MIN_WORD_LEN and w not in STOPWORDS}
 
 
def detectar_terminos_genericos(
    rows: list[dict],
    hub_min_degree: int,
    hub_max_avgsim: float,
) -> set[str]:
    """
    Identifica nombres que actúan como 'hub' (emparejados con muchas entidades distintas) cuyos compañeros son heterogéneos entre sí (poca similitud de palabras), señal de que el nombre es un cargo o
    rol genérico y no una persona concreta.
    """
    partners: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        a, b = r["nombre_a"].strip(), r["nombre_b"].strip()
        partners[a].add(b)
        partners[b].add(a)
 
    genericos = set()
    for nombre, companeros in partners.items():
        if len(companeros) < hub_min_degree:
            continue
 
        companeros = list(companeros)
        sw = {c: palabras_significativas(c) for c in companeros}
        similitudes = []
        for c1, c2 in combinations(companeros, 2):
            s1, s2 = sw[c1], sw[c2]
            if not s1 and not s2:
                continue
            union = s1 | s2
            inter = s1 & s2
            similitudes.append(len(inter) / len(union) if union else 0.0)
 
        avg_sim = sum(similitudes) / len(similitudes) if similitudes else 0.0
        if avg_sim < hub_max_avgsim:
            genericos.add(nombre)
 
    return genericos
 
 
def construir_clusters(
    rows: list[dict],
    genericos: set[str],
    rare_word_max_df: int,
) -> dict[str, int]:
    """
    Agrupa nombres NO genéricos en clústeres (componentes conexas) usando como criterio de unión que compartan al menos una palabra significativa realmente infrecuente en el conjunto (aparece en pocos nombres distintos
    del dataset). Esto evita el 'efecto cadena' de unir por palabras comunes (p.ej. 'Juan', 'España', 'Rey') que mezclarían personas distintas.Devuelve {nombre: cluster_id} solo para nombres en clústeres de >1 miembro.
    """
    todos_los_nombres = set()
    for r in rows:
        todos_los_nombres.add(r["nombre_a"].strip())
        todos_los_nombres.add(r["nombre_b"].strip())
 
    palabras_por_nombre = {n: palabras_significativas(n) for n in todos_los_nombres}
 
    frecuencia_palabra: dict[str, int] = defaultdict(int)
    for palabras in palabras_por_nombre.values():
        for w in palabras:
            frecuencia_palabra[w] += 1
 
    parent: dict[str, str] = {}
 
    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x
 
    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry
 
    for r in rows:
        a, b = r["nombre_a"].strip(), r["nombre_b"].strip()
        if a in genericos or b in genericos:
            continue
        compartidas = palabras_por_nombre[a] & palabras_por_nombre[b]
        if any(frecuencia_palabra[w] <= rare_word_max_df for w in compartidas):
            find(a)
            find(b)
            union(a, b)
 
    clusters: dict[str, list[str]] = defaultdict(list)
    for n in parent:
        clusters[find(n)].append(n)
 
    cluster_id_de: dict[str, int] = {}
    for i, (_, miembros) in enumerate(
        sorted(clusters.items(), key=lambda kv: -len(kv[1])), start=1
    ):
        if len(miembros) <= 1:
            continue
        for m in miembros:
            cluster_id_de[m] = i
 
    return cluster_id_de
 
 
def main():
    parser = argparse.ArgumentParser(
        description="Pre-revisión asistida de candidatos de fusión de entidades"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--hub-min-degree", type=int, default=DEFAULT_HUB_MIN_DEGREE)
    parser.add_argument("--hub-max-avgsim", type=float, default=DEFAULT_HUB_MAX_AVGSIM)
    parser.add_argument("--rare-word-max-df", type=int, default=RARE_WORD_MAX_DF)
    args = parser.parse_args()
 
    if not args.input.exists():
        raise SystemExit(f"No se encontró: {args.input} - ejecuta antes 1_LimpiezaDatos.py")
 
    with open(args.input, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
 
    print(f"Pares candidatos cargados : {len(rows)}")
 
    genericos = detectar_terminos_genericos(rows, args.hub_min_degree, args.hub_max_avgsim)
    print(f"Términos genéricos detectados (auto 'no') : {len(genericos)}")
 
    cluster_id_de = construir_clusters(rows, genericos, args.rare_word_max_df)
    n_clusters = len(set(cluster_id_de.values()))
    print(f"Clústeres de candidatos reales para revisar : {n_clusters}")
 
    n_auto_no = 0
    for r in rows:
        a, b = r["nombre_a"].strip(), r["nombre_b"].strip()
        if a in genericos or b in genericos:
            r["aprobar_fusion(si/no)"] = "no"
            r["motivo_revision"] = "Termino generico/hub detectado automaticamente"
            n_auto_no += 1
        else:
            r.setdefault("aprobar_fusion(si/no)", "")
            r["motivo_revision"] = ""
        # cluster_id solo informativo, para agrupar visualmente al revisar
        cid_a = cluster_id_de.get(a)
        cid_b = cluster_id_de.get(b)
        r["cluster_id"] = cid_a if cid_a == cid_b and cid_a is not None else ""
 
    fieldnames = list(rows[0].keys())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
 
    pendientes = sum(1 for r in rows if not r["aprobar_fusion(si/no)"])
    print(f"{'─' * 50}")
    print(f"Filas marcadas automáticamente 'no' : {n_auto_no}")
    print(f"Filas pendientes de tu decisión      : {pendientes}")
    print(f"\nGuardado en: {args.output}")
    print(f"\n Abre el CSV, ordénalo por 'cluster_id' para revisar juntos los")
    print(f"  candidatos relacionados, y completa 'si'/'no' donde esté vacío.")
    print(f"  Luego ejecuta 3_ValidarDatos.py con ese CSV ya completado.")
 
 
if __name__ == "__main__":
    main()