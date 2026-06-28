"""
7_ExportarNeo4j.py — Exporta el grafo a CSV listos para Neo4j (LOAD CSV)
─────────────────────────────────────────────────────────────────────
Entrada : data/grafo_23f.json            (de 6_ConstruirGrafo.py)
Salida  : data/neo4j_nodos.csv
          data/neo4j_aristas.csv
          data/importar_neo4j.cypher     (script de importación)
 
Patrón usado (estándar en Neo4j, sin necesitar el plugin APOC):
    Cada nodo recibe DOS etiquetas:
        - Una genérica  :Entidad   (permite enlazar aristas sin tener
                                     que saber de qué tipo es cada nodo)
        - Una específica :Persona / :Institución / :Lugar / :Documento
 
    Las aristas se cargan en bloques separados por tipo de relación
    (CONOCE, INFORMA, PERTENECE, LLAMA, ASISTE, ORDENA, MENCIONA,
    PROPONE, SOLICITA, COLABORA, AUTORIZA, NIEGA), porque Cypher no
    permite parametrizar el tipo de relación dinámicamente sin APOC.
 
    Relaciones repetidas entre el mismo par de entidades (p.ej. "Tejero
    CONOCE a Milans" mencionado en 5 documentos distintos) se fusionan en
    UNA SOLA arista mediante MERGE, en vez de crear 5 aristas paralelas
    idénticas — esto evita inflar artificialmente el grado de los nodos
    y las métricas de centralidad. Para no perder información, la
    evidencia de cada mención se ACUMULA en propiedades tipo lista:
        r.veces_mencionado       -> cuántas veces se detectó esta relación
        r.documentos_id          -> lista de documentos donde aparece
        r.frases_evidencia       -> lista de frases textuales de evidencia
        r.relaciones_originales  -> lista de las 13 relaciones detalladas
                                     que se mapearon a esta arista
        r.negada_alguna_vez      -> true si en AL MENOS una mención se
                                     detectó una negación cercana al verbo
 
Uso:
    python scripts/7_ExportarNeo4j.py
 
Después, copia neo4j_nodos.csv y neo4j_aristas.csv a la carpeta
'import' de tu base de datos Neo4j (o usa file:/// con la ruta
absoluta), abre Neo4j Browser y ejecuta el contenido de
importar_neo4j.cypher.
"""
 
import argparse
import csv
import json
from pathlib import Path
 
DEFAULT_GRAFO_JSON = Path(__file__).resolve().parent.parent / "data" / "grafo_23f.json"
DEFAULT_NODOS_CSV   = Path(__file__).resolve().parent.parent / "data" / "neo4j_nodos.csv"
DEFAULT_ARISTAS_CSV = Path(__file__).resolve().parent.parent / "data" / "neo4j_aristas.csv"
DEFAULT_CYPHER       = Path(__file__).resolve().parent.parent / "data" / "importar_neo4j.cypher"
 
TIPOS_NODO = ["Persona", "Institución", "Lugar", "Documento"]
TIPOS_ARISTA = [
    "CONOCE", "INFORMA", "PERTENECE", "LLAMA", "ASISTE", "ORDENA",
    "MENCIONA", "PROPONE", "SOLICITA", "COLABORA", "AUTORIZA", "NIEGA",
]
 
 
def exportar_csvs(grafo: dict, nodos_csv: Path, aristas_csv: Path):
    with open(nodos_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label", "tipo", "documento_id", "url", "fecha"])
        for n in grafo["nodes"]:
            writer.writerow([
                n["id"],
                n.get("label", n["id"]),
                n.get("tipo", ""),
                n.get("documento_id", ""),
                n.get("url", ""),
                n.get("fecha", ""),
            ])
 
    with open(aristas_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "origen", "destino", "tipo", "relacion_original",
            "negada", "documento_id", "documento_fecha", "frase_evidencia",
        ])
        for a in grafo["edges"]:
            writer.writerow([
                a["origen"], a["destino"], a["tipo"], a.get("relacion_original", ""),
                a.get("negada", False), a.get("documento_id", ""),
                a.get("documento_fecha", ""), a.get("frase_evidencia", ""),
            ])
 
 
def generar_cypher() -> str:
    lineas = []
    lineas.append("// ── Importación del grafo 23-F en Neo4j ──────────────────────────")
    lineas.append("// Copia neo4j_nodos.csv y neo4j_aristas.csv a la carpeta 'import' de")
    lineas.append("// tu base de datos Neo4j antes de ejecutar este script.")
    lineas.append("")
    lineas.append("// ── 1. Restricción de unicidad (también crea índice automáticamente) ──")
    lineas.append("CREATE CONSTRAINT entidad_id_unica IF NOT EXISTS")
    lineas.append("FOR (e:Entidad) REQUIRE e.id IS UNIQUE;")
    lineas.append("")
    lineas.append("// ── 2. Cargar nodos (una pasada por tipo, añade la etiqueta específica) ──")
    for tipo in TIPOS_NODO:
        lineas.append(f"// -- Nodos de tipo {tipo} --")
        lineas.append("LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodos.csv' AS row")
        lineas.append(f"WITH row WHERE row.tipo = '{tipo}'")
        lineas.append("MERGE (n:Entidad {id: row.id})")
        lineas.append("SET n.label = row.label, n.tipo = row.tipo")
        if tipo == "Documento":
            lineas.append("SET n.documento_id = row.documento_id, n.url = row.url, n.fecha = row.fecha")
        lineas.append(f"SET n:`{tipo}`;")
        lineas.append("")
    lineas.append("// ── 3. Cargar aristas (una pasada por tipo de relación) ──")
    for tipo in TIPOS_ARISTA:
        lineas.append(f"// -- Aristas de tipo {tipo} --")
        lineas.append("LOAD CSV WITH HEADERS FROM 'file:///neo4j_aristas.csv' AS row")
        lineas.append(f"WITH row WHERE row.tipo = '{tipo}'")
        lineas.append("MATCH (a:Entidad {id: row.origen})")
        lineas.append("MATCH (b:Entidad {id: row.destino})")
        lineas.append(f"MERGE (a)-[r:{tipo}]->(b)")
        lineas.append("SET r.veces_mencionado = coalesce(r.veces_mencionado, 0) + 1,")
        lineas.append("    r.relaciones_originales = coalesce(r.relaciones_originales, []) + row.relacion_original,")
        lineas.append("    r.documentos_id = coalesce(r.documentos_id, []) + row.documento_id,")
        lineas.append("    r.fechas_documentos = coalesce(r.fechas_documentos, []) + row.documento_fecha,")
        lineas.append("    r.frases_evidencia = coalesce(r.frases_evidencia, []) + row.frase_evidencia,")
        lineas.append("    r.negada_alguna_vez = coalesce(r.negada_alguna_vez, false) OR toBoolean(row.negada);")
        lineas.append("")
    return "\n".join(lineas)
 
 
def main():
    parser = argparse.ArgumentParser(description="Exporta el grafo del 23-F a CSV/Cypher para Neo4j")
    parser.add_argument("--grafo", type=Path, default=DEFAULT_GRAFO_JSON)
    parser.add_argument("--out-nodos", type=Path, default=DEFAULT_NODOS_CSV)
    parser.add_argument("--out-aristas", type=Path, default=DEFAULT_ARISTAS_CSV)
    parser.add_argument("--out-cypher", type=Path, default=DEFAULT_CYPHER)
    args = parser.parse_args()
 
    if not args.grafo.exists():
        raise SystemExit(f"No se encontró: {args.grafo} — ejecuta antes 6_ConstruirGrafo.py")
 
    with open(args.grafo, encoding="utf-8") as f:
        grafo = json.load(f)
 
    exportar_csvs(grafo, args.out_nodos, args.out_aristas)
    print(f"Nodos exportados   : {len(grafo['nodes'])}  -> {args.out_nodos}")
    print(f"Aristas exportadas : {len(grafo['edges'])}  -> {args.out_aristas}")
 
    cypher = generar_cypher()
    args.out_cypher.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_cypher, "w", encoding="utf-8") as f:
        f.write(cypher)
    print(f"Script Cypher generado en: {args.out_cypher}")
    print("\nPasos siguientes:")
    print("  1. Copia neo4j_nodos.csv y neo4j_aristas.csv a la carpeta 'import' de tu BD Neo4j.")
    print("  2. Abre Neo4j Browser y pega/ejecuta el contenido de importar_neo4j.cypher.")
 
 
if __name__ == "__main__":
    main()