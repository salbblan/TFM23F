"""
4_ResolverGenericosLocal.py — Resolución local de términos genéricos
─────────────────────────────────────────────────────────────────────
Entrada : data/entity_merge_candidates_revisado.csv  (de 2_RevisarCandidatos.py)
          data/rtve_23f_corpus_final.json            (de 3_ValidarDatos.py)
Salida  : data/alias_locales_por_documento.json
 
Motivación:
    A nivel de todo el corpus, "Coronel" es un término genérico (se
    refiere a muchas personas distintas según el documento, por eso
    2_RevisarCandidatos.py lo marca 'no' y no se fusiona globalmente).
 
    Pero DENTRO de un único documento, si ese documento solo menciona
    a UN coronel con nombre propio (p. ej. "Coronel Ibáñez"), entonces
    cuando el texto de ESE documento diga simplemente "el Coronel" sin
    más, es razonable asumir que se refiere a esa misma persona.
 
    Este script resuelve esa ambigüedad documento por documento:
      - Si en un documento hay exactamente 1 persona cuyo nombre
        contiene el término genérico (p.ej. 1 sola persona con
        "Coronel" en su nombre) -> se resuelve el genérico a esa
        persona, traducida a su nombre canónico final.
      - Si hay 0 o 2+ coincidencias -> se deja SIN resolver (ambiguo),
        no se arriesga una asignación incorrecta.
 
Uso:
    python scripts/4_ResolverGenericosLocal.py
    python scripts/4_ResolverGenericosLocal.py --hub-min-degree 5 --hub-max-avgsim 0.15
"""
 
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
 
DEFAULT_CANDIDATOS = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates_revisado.csv"
DEFAULT_CORPUS     = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus_final.json"
DEFAULT_OUTPUT      = Path(__file__).resolve().parent.parent / "data" / "alias_locales_por_documento.json"
 
DEFAULT_HUB_MIN_DEGREE = 5
DEFAULT_HUB_MAX_AVGSIM = 0.15
DECISIONES_APROBADAS = {"si", "sí", "yes", "y"}
 
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
MIN_WORD_LEN = 4
 
 
# ── Funciones reutilizadas (mismas que en 2_RevisarCandidatos.py / 3_ValidarDatos.py) ──
 
def palabras_significativas(nombre: str) -> set[str]:
    n = nombre.lower()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"[^a-záéíóúñü\s]", " ", n)
    return {w for w in n.split() if len(w) > MIN_WORD_LEN and w not in STOPWORDS}
 
 
def detectar_terminos_genericos(rows: list[dict], hub_min_degree: int, hub_max_avgsim: float) -> set[str]:
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
 
 
class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}
 
    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        raiz = x
        while self.parent[raiz] != raiz:
            raiz = self.parent[raiz]
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
 
 
def construir_mapeo_canonico(rows: list[dict], corpus: list[dict]) -> dict[str, str]:
    uf = UnionFind()
    for r in rows:
        if r.get("aprobar_fusion(si/no)", "").strip().lower() not in DECISIONES_APROBADAS:
            continue
        uf.union(r["nombre_a"].strip(), r["nombre_b"].strip())
 
    grupos = uf.grupos()
    multi = {raiz: m for raiz, m in grupos.items() if len(m) > 1}
 
    frecuencia: Counter[str] = Counter()
    for doc in corpus:
        for nombre in doc.get("personas", []):
            frecuencia[nombre.strip()] += 1
 
    mapeo: dict[str, str] = {}
    for miembros in multi.values():
        canonico = max(miembros, key=lambda m: (frecuencia.get(m, 0), len(m), m))
        for m in miembros:
            mapeo[m] = canonico
    return mapeo
 
 
# ── Resolución local por documento ───────────────────────────────────────────
 
def resolver_genericos_por_documento(
    corpus: list[dict],
    genericos: set[str],
    mapeo_canonico: dict[str, str],
) -> dict[str, dict[str, str]]:
    """
    Para cada documento, intenta resolver cada término genérico a una
    persona concreta SOLO si hay exactamente una persona en ese documento
    cuyo nombre contiene el término genérico como subcadena.
    """
    alias_por_documento: dict[str, dict[str, str]] = {}
    resueltos = 0
    ambiguos = 0
 
    for doc in corpus:
        doc_id = str(doc.get("id"))
        personas_doc = doc.get("personas", [])
        alias_doc: dict[str, str] = {}
 
        for generico in genericos:
            generico_lower = generico.strip().lower()
            candidatos = [
                p for p in personas_doc
                if generico_lower in p.lower()
                and p.strip().lower() != generico_lower
                # Excluir otros términos genéricos como posible "resolución":
                # p.ej. "Defensor" no debe resolverse a "Defensores" (ambos
                # son genéricos, ninguno es una persona concreta).
                and p.strip() not in genericos
            ]
            # quitar duplicados conservando orden
            candidatos = list(dict.fromkeys(candidatos))
 
            if len(candidatos) == 1:
                persona_resuelta = candidatos[0]
                canonico = mapeo_canonico.get(persona_resuelta, persona_resuelta)
                alias_doc[generico] = canonico
                resueltos += 1
            elif len(candidatos) > 1:
                ambiguos += 1
            # 0 candidatos -> no se hace nada (el genérico no aparece con nombre en este doc)
 
        if alias_doc:
            alias_por_documento[doc_id] = alias_doc
 
    print(f"Resoluciones locales encontradas (1 sola candidata) : {resueltos}")
    print(f"Casos ambiguos (2+ candidatas, descartados)          : {ambiguos}")
    return alias_por_documento
 
 
# ── Programa principal ───────────────────────────────────────────────────────
 
def main():
    parser = argparse.ArgumentParser(
        description="Resuelve términos genéricos a personas concretas, documento por documento"
    )
    parser.add_argument("--candidatos", type=Path, default=DEFAULT_CANDIDATOS)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--hub-min-degree", type=int, default=DEFAULT_HUB_MIN_DEGREE)
    parser.add_argument("--hub-max-avgsim", type=float, default=DEFAULT_HUB_MAX_AVGSIM)
    args = parser.parse_args()
 
    if not args.candidatos.exists():
        raise SystemExit(f"No se encontró: {args.candidatos}")
    if not args.corpus.exists():
        raise SystemExit(f"No se encontró: {args.corpus} — ejecuta antes 3_ValidarDatos.py")
 
    with open(args.candidatos, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(args.corpus, encoding="utf-8") as f:
        corpus = json.load(f)
 
    genericos = detectar_terminos_genericos(rows, args.hub_min_degree, args.hub_max_avgsim)
    print(f"Términos genéricos detectados : {len(genericos)}")
 
    mapeo_canonico = construir_mapeo_canonico(rows, corpus)
    print(f"Variantes con nombre canónico : {len(mapeo_canonico)}")
 
    alias_por_documento = resolver_genericos_por_documento(corpus, genericos, mapeo_canonico)
 
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(alias_por_documento, f, ensure_ascii=False, indent=2)
 
    print(f"{'─' * 50}")
    print(f"Documentos con al menos 1 alias local resuelto : {len(alias_por_documento)}")
    print(f"Guardado en: {args.output}")
    print(f"\nFormato del archivo: {{ \"id_documento\": {{ \"termino_generico\": \"nombre_canonico\" }} }}")
    print(f"Úsalo en extraer_relaciones.py para resolver menciones genéricas")
    print(f"dentro de cada documento antes de detectar relaciones.")
 
 
if __name__ == "__main__":
    main()