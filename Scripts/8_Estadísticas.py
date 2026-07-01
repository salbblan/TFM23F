"""
estadisticas_cap4.py
────────────────────
Genera todas las estadísticas del Capítulo 4 del TFM a partir de los
ficheros de datos producidos por el pipeline. Ejecutar desde /app/Scripts:
 
    python estadisticas_cap4.py
 
o con rutas personalizadas:
 
    python estadisticas_cap4.py --csv-fusion ../data/entity_merge_candidates_revisado.csv
"""
 
import argparse
import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
 
# ── Rutas por defecto ─────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent / "data"
D = {
    "corpus_clean":   BASE / "rtve_23f_corpus_clean.json",
    "corpus_final":   BASE / "rtve_23f_corpus_final.json",
    "csv_fusion":     BASE / "entity_merge_candidates_revisado.csv",
    "alias_locales":  BASE / "alias_locales_por_documento.json",
    "relaciones_csv": BASE / "relaciones_extraidas.csv",
    "grafo_json":     BASE / "grafo_23f.json",
}
 
SEP = "─" * 60
 
 
def cargar_csv_fusion(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows
 
 
def seccion_4_1(args):
   
    print("  Corpus y resolución de entidades")
   

    # Corpus 
    with open(args.corpus_clean, encoding="utf-8") as f:
        corpus_clean = json.load(f)
    with open(args.corpus_final, encoding="utf-8") as f:
        corpus_final = json.load(f)
 
    print(f"\n[Corpus]")
    print(f"  Documentos totales                : {len(corpus_clean)}")
 
    # ── CSV de fusión ─────────────────────────────────────────────────────
    rows = cargar_csv_fusion(args.csv_fusion)
    total_candidatos = len(rows)
    aprobados = sum(1 for r in rows if r.get("aprobar_fusion(si/no)", "").strip().lower() == "si")
    rechazados = sum(1 for r in rows if r.get("aprobar_fusion(si/no)", "").strip().lower() == "no")
    vacios     = total_candidatos - aprobados - rechazados
 
    print(f"\n[Candidatos de fusión - entity_merge_candidates_revisado.csv]")
    print(f"  Total candidatos generados        : {total_candidatos}")
    print(f"  Aprobados ('si')                  : {aprobados}  ({aprobados/total_candidatos*100:.1f}%)")
    print(f"  Rechazados ('no')                 : {rechazados}  ({rechazados/total_candidatos*100:.1f}%)")
    if vacios:
        print(f"  Sin decisión (vacíos)             : {vacios} revisar")
 
    # Términos genéricos detectados 
    STOPWORDS = set("""
        el la los las de del don dona doña sr sra señor señora excmo excma
        general teniente coronel capitan capitán comandante sargento cabo soldado
        guardia civil militar consejero togado juez especial presidente
        secretario fiscal defensor letrado abogado ministro ministerio gobierno
        estado director division cuerpo armada ejercito ejército fuerzas
        jefe jefatura oficial mando comandancia infanteria dem
    """.split())
    MIN_LEN = 4
    HUB_MIN = 5
    HUB_SIM = 0.15
 
    def palabras(n):
        import re
        n = n.lower()
        n = re.sub(r"\([^)]*\)", " ", n)
        n = re.sub(r"[^a-záéíóúñü\s]", " ", n)
        return {w for w in n.split() if len(w) > MIN_LEN and w not in STOPWORDS}
 
    partners = defaultdict(set)
    for r in rows:
        a, b = r["nombre_a"].strip(), r["nombre_b"].strip()
        partners[a].add(b)
        partners[b].add(a)
 
    n_genericos = 0
    for nombre, comp in partners.items():
        if len(comp) < HUB_MIN:
            continue
        comp = list(comp)
        sw = {c: palabras(c) for c in comp}
        sims = []
        for c1, c2 in combinations(comp, 2):
            s1, s2 = sw[c1], sw[c2]
            if not s1 and not s2:
                continue
            u = s1 | s2
            sims.append(len(s1 & s2) / len(u) if u else 0.0)
        avg = sum(sims) / len(sims) if sims else 0.0
        if avg < HUB_SIM:
            n_genericos += 1
 
    print(f"\n[Términos genéricos]")
    print(f"  Términos genéricos detectados     : {n_genericos}")
 
    # Union-Find: clústeres y variantes
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a
 
    for r in rows:
        if r.get("aprobar_fusion(si/no)", "").strip().lower() == "si":
            union(r["nombre_a"].strip(), r["nombre_b"].strip())
 
    clusters = defaultdict(set)
    for n in parent:
        clusters[find(n)].add(n)
 
    clusters_reales = {k: v for k, v in clusters.items() if len(v) > 1}
    n_variantes = sum(len(v) - 1 for v in clusters_reales.values())  # excluye el canónico
 
    print(f"\n[Union-Find - fusión de entidades]")
    print(f"  Clústeres con ≥2 variantes        : {len(clusters_reales)}")
    print(f"  Variantes fusionadas a canónico   : {sum(len(v) for v in clusters_reales.values()) - len(clusters_reales)}")
 
    # Resolución local de genéricos
    with open(args.alias_locales, encoding="utf-8") as f:
        alias_locales = json.load(f)
 
    total_alias = sum(len(v) for v in alias_locales.values())
    docs_con_alias = len(alias_locales)
 
    print(f"\n[Resolución de genéricos a nivel de documento - alias_locales_por_documento.json]")
    print(f"  Documentos con al menos 1 alias   : {docs_con_alias}")
    print(f"  Resoluciones aceptadas (1 cand.)  : {total_alias}")
 
 
def seccion_4_2(args):
   
    print("  Grafo de conocimiento")
   
 
    # Nodos del grafo
    with open(args.grafo_json, encoding="utf-8") as f:
        grafo = json.load(f)
 
    nodos = grafo["nodes"]
    aristas = grafo["edges"]
    tipo_nodo = Counter(n["tipo"] for n in nodos)
 
    print(f"\n[Nodos]")
    print(f"  Total nodos                       : {len(nodos)}")
    for tipo, n in sorted(tipo_nodo.items(), key=lambda x: -x[1]):
        print(f"    {tipo:<15}               : {n}")
 
    # Aristas del grafo (en bruto)
    tipo_arista = Counter(a["tipo"] for a in aristas)
 
    print(f"\n[Aristas en bruto - antes de fusión en Neo4j]")
    print(f"  Total aristas                     : {len(aristas)}")
    for tipo, n in sorted(tipo_arista.items(), key=lambda x: -x[1]):
        print(f"    {tipo:<15}               : {n}")
 
    # Aristas únicas tras fusión
    triples = Counter((a["origen"], a["tipo"], a["destino"]) for a in aristas)
    n_unicas = len(triples)
    n_repetidas = len(aristas) - n_unicas
 
    print(f"\n[Aristas únicas - tras MERGE en Neo4j]")
    print(f"  Aristas únicas (origen+tipo+dest) : {n_unicas}")
    print(f"  Aristas colapsadas por MERGE      : {n_repetidas}  ({n_repetidas/len(aristas)*100:.1f}%)")
 
    # Negadas
    with open(args.relaciones_csv, encoding="utf-8") as f:
        rels = list(csv.DictReader(f))
 
    negadas = sum(1 for r in rels if r.get("negada", "").strip().lower() in ("true", "1", "yes", "sí", "si"))
    total_rels = len(rels)
    pct_negadas = negadas / total_rels * 100 if total_rels else 0
 
    print(f"\n[Negación]")
    print(f"  Total relaciones extraídas        : {total_rels}")
    print(f"  Relaciones marcadas como negadas  : {negadas}  ({pct_negadas:.1f}%)")
 
    # Cobertura de fechas
    con_fecha = sum(1 for r in rels if r.get("documento_fecha", "").strip())
    docs_con_fecha = len({r["documento_id"] for r in rels if r.get("documento_fecha", "").strip()})
    docs_total = len({r["documento_id"] for r in rels})
 
    print(f"\n[Cobertura de fechas]")
    print(f"  Relaciones con fecha de documento : {con_fecha}/{total_rels}  ({con_fecha/total_rels*100:.1f}%)")
    print(f"  Documentos con fecha extraída     : {docs_con_fecha}/{docs_total}  ({docs_con_fecha/docs_total*100:.1f}%)")
 
    # Top 10 personas por grado
    grado = Counter()
    id_to_label = {n["id"]: n.get("label", n["id"]) for n in nodos}
    id_to_tipo  = {n["id"]: n.get("tipo", "") for n in nodos}
    for a in aristas:
        if a["tipo"] != "MENCIONA":
            grado[a["origen"]] += 1
            grado[a["destino"]] += 1
 
    print(f"\n[Top 15 entidades por grado (excluyendo MENCIONA)]")
    print(f"  {'Entidad':<50} {'Tipo':<15} Grado")
    
    for nid, g in grado.most_common(15):
        label = id_to_label.get(nid, nid)
        tipo  = id_to_tipo.get(nid, "?")
        print(f"  {label:<50} {tipo:<15} {g}")
 

 
def main():
    parser = argparse.ArgumentParser(description="Estadísticas del Capítulo 4 del TFM")
    parser.add_argument("--corpus-clean",   type=Path, default=D["corpus_clean"])
    parser.add_argument("--corpus-final",   type=Path, default=D["corpus_final"])
    parser.add_argument("--csv-fusion",     type=Path, default=D["csv_fusion"])
    parser.add_argument("--alias-locales",  type=Path, default=D["alias_locales"])
    parser.add_argument("--relaciones-csv", type=Path, default=D["relaciones_csv"])
    parser.add_argument("--grafo-json",     type=Path, default=D["grafo_json"])
    parser.add_argument("--out-txt",        type=Path, default=BASE / "estadisticas_cap4.txt",
                        help="Ruta del fichero de texto con el informe completo (por defecto: data/estadisticas_cap4.txt)")
    parser.add_argument("--out-csv",        type=Path, default=BASE / "estadisticas_cap4_metricas.csv",
                        help="Ruta del CSV con las métricas clave para el TFM (por defecto: data/estadisticas_cap4_metricas.csv)")
    args = parser.parse_args()
 
    # Capturar toda la salida de consola
    import io, sys
    buffer = io.StringIO()
    sys.stdout = buffer
 
    try:
        
        print("  Estadísticas TFM Grafo de conocimiento 23-F")
        
 
        # Recopilar métricas clave en un diccionario para el CSV
        metricas = {}
 
        # 4.1
        seccion_4_1(args)
 
        # Calcular métricas para el CSV
        with open(args.corpus_clean, encoding="utf-8") as f:
            corpus_clean = json.load(f)
        rows = cargar_csv_fusion(args.csv_fusion)
        total_c = len(rows)
        aprobados = sum(1 for r in rows if r.get("aprobar_fusion(si/no)", "").strip().lower() == "si")
        with open(args.alias_locales, encoding="utf-8") as f:
            alias_locales = json.load(f)
        total_alias = sum(len(v) for v in alias_locales.values())
 
        metricas["Documentos en el corpus"] = len(corpus_clean)
        metricas["Candidatos de fusión generados"] = total_c
        metricas["Pares aprobados (sí)"] = aprobados
        metricas["Ratio de aprobación (%)"] = f"{aprobados/total_c*100:.1f}"
        metricas["Resoluciones de genéricos aceptadas (nivel documento)"] = total_alias
 
        # 4.2 
        seccion_4_2(args)
 
        with open(args.grafo_json, encoding="utf-8") as f:
            grafo = json.load(f)
        nodos = grafo["nodes"]
        aristas = grafo["edges"]
        tipo_nodo = Counter(n["tipo"] for n in nodos)
        tipo_arista = Counter(a["tipo"] for a in aristas)
        n_unicas = len(set((a["origen"], a["tipo"], a["destino"]) for a in aristas))
 
        with open(args.relaciones_csv, encoding="utf-8") as f:
            rels = list(csv.DictReader(f))
        negadas = sum(1 for r in rels if r.get("negada", "").strip().lower() in ("true", "1", "yes", "sí", "si"))
        docs_con_fecha = len({r["documento_id"] for r in rels if r.get("documento_fecha", "").strip()})
        docs_total_rels = len({r["documento_id"] for r in rels})
 
        metricas["Nodos totales"] = len(nodos)
        for t, n in tipo_nodo.items():
            metricas[f"  Nodos — {t}"] = n
        metricas["Aristas totales (en bruto)"] = len(aristas)
        for t, n in sorted(tipo_arista.items(), key=lambda x: -x[1]):
            metricas[f"  Aristas — {t}"] = n
        metricas["Aristas únicas tras MERGE en Neo4j"] = n_unicas
        metricas["Aristas colapsadas por MERGE"] = len(aristas) - n_unicas
        metricas["Relaciones marcadas como negadas"] = negadas
        metricas["Relaciones negadas (%)"] = f"{negadas/len(rels)*100:.1f}"
        metricas["Documentos con fecha extraída"] = docs_con_fecha
        metricas["Total documentos con relaciones"] = docs_total_rels
        metricas["Cobertura de fechas (%)"] = f"{docs_con_fecha/docs_total_rels*100:.1f}"
 
 
    except Exception as e:
        sys.stdout = sys.__stdout__
        print(f"\nError durante la ejecución: {e}")
        import traceback
        traceback.print_exc()
        return
 
    finally:
        # Siempre restaurar stdout, pase lo que pase
        sys.stdout = sys.__stdout__
 
    informe = buffer.getvalue()
 
    # Imprimir también por consola
    print(informe)
 
    # Guardar fichero de texto completo
    args.out_txt.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_txt, "w", encoding="utf-8") as f:
        f.write(informe)
    print(f"Informe completo guardado en : {args.out_txt}")
 
    # Guardar CSV de métricas clave
    with open(args.out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Métrica", "Valor"])
        for k, v in metricas.items():
            w.writerow([k, v])
    print(f"Métricas clave guardadas en  : {args.out_csv}")
 
 
if __name__ == "__main__":
    main()
 