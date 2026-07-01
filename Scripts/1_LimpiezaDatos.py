"""
1_LimpiarDatos.py - Limpieza y normalización del corpus 23-F
─────────────────────────────────────────────────────────────────────
Entrada : data/rtve_23f_corpus.json        (crudo, de 0_DescargarDatos.py)
Salida  : data/rtve_23f_corpus_clean.json  (limpio)
 
Qué hace (SIEMPRE, automático y seguro):
    1. Limpia ruido OCR en el texto (espacios, saltos de línea extra)
    2. Normaliza mayúsculas/minúsculas en entidades
    3. Elimina entidades duplicadas exactas dentro de cada documento
 
Qué NO hace automáticamente (requiere revisión humana):
    Unificar variantes de la misma persona (ej. 'TEJERO' y 'Teniente Coronel TEJERO'). El campo 'personas' del corpus mezcla personas reales, instituciones y grupos genéricos - la fusión
    automática por similitud de texto puede juntar entidades que no son la misma persona. En su lugar, este script genera un CSV de candidatos para que el usuario decida cuál mantener.
 
    data/entity_merge_candidates.csv   (columnas: nombre_a, nombre_b, score)
 
Uso:
    python 1_LimpiarDatos.py
    python 1_LimpiarDatos.py --candidate-threshold 80   # más candidatos 
"""
 
import argparse
import csv
import json
import re
from pathlib import Path
 
from rapidfuzz import fuzz
 
DEFAULT_INPUT  = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus_clean.json"
DEFAULT_CANDS  = Path(__file__).resolve().parent.parent / "data" / "entity_merge_candidates.csv"
 
DEFAULT_CANDIDATE_THRESHOLD = 80  # umbral para sugerir candidatos (no fusiona solo, se necesita revisión)
 
KNOWN_ACRONYMS = {
    "CESID", "REY", "REINA", "TCOL", "ONU", "OTAN", "PSOE", "UCD", "PCE",
}
 
RANKS_AND_TITLES = [
    "teniente coronel", "teniente general", "general de división",
    "general de brigada", "comandante general", "capitán general",
    "coronel", "comandante", "capitán", "teniente", "general",
    "almirante", "sargento", "cabo", "gobernador civil de",
    "presidente del congreso", "presidente de", "ministro de",
    "secretario de estado", "defensor", "fiscal", "sr\\.", "sra\\.",
    "don ", "doña ", "d\\.", "dña\\.",
]
RANK_PATTERN = re.compile(
    r"^(?:" + "|".join(RANKS_AND_TITLES) + r")\s+", flags=re.IGNORECASE
)
 
 
def strip_rank(name: str) -> str:
    prev = None
    cleaned = name.strip()
    while cleaned != prev:
        prev = cleaned
        cleaned = RANK_PATTERN.sub("", cleaned).strip()
    return cleaned if cleaned else name
 
 
# Limpieza de texto OCR
 
def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()
 
 
def normalize_case(name: str) -> str:
    name = re.sub(r"\s{2,}", " ", name).strip()
    words = name.split(" ")
    out = []
    for w in words:
        bare = re.sub(r"[^\wÁÉÍÓÚÑ]", "", w.upper())
        if bare in KNOWN_ACRONYMS:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)
 
 
def split_entity(raw: str) -> tuple[str, str | None]:
    if ":" in raw:
        nombre, cargo = raw.split(":", 1)
        return nombre.strip(), cargo.strip()
    return raw.strip(), None
 
 
# Generar candidatos de fusión
 
def generate_merge_candidates(
    all_names: list[str],
    name_to_docs: dict[str, list],
    threshold: int,
) -> list[tuple[str, str, int, str, str]]:
    """
    Compara cada PAR de nombres directamente (sin encadenar transitivamente) y devuelve los pares cuyo score de similitud (sobre el núcleo, sin rango)
    supera el umbral. No decide nada por sí mismo - son candidatos a revisar. Incluye en qué documento(s) aparece cada nombre, para validar contra el texto.
    """
    unique_names = sorted(set(all_names))
    cores = {n: strip_rank(n) for n in unique_names}
 
    candidates = []
    for i, a in enumerate(unique_names):
        for b in unique_names[i + 1:]:
            core_a, core_b = cores[a], cores[b]
            if len(core_a) < 3 or len(core_b) < 3:
                continue
            score = fuzz.token_set_ratio(core_a, core_b)
            if score >= threshold:
                docs_a = "; ".join(name_to_docs.get(a, []))
                docs_b = "; ".join(name_to_docs.get(b, []))
                candidates.append((a, b, score, docs_a, docs_b))
 
    candidates.sort(key=lambda x: -x[2])
    return candidates
 
 
# Programa principal
 
def main():
    parser = argparse.ArgumentParser(description="Limpia y normaliza el corpus 23-F")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidates-out", type=Path, default=DEFAULT_CANDS)
    parser.add_argument("--candidate-threshold", type=int, default=DEFAULT_CANDIDATE_THRESHOLD)
    args = parser.parse_args()
 
    if not args.input.exists():
        raise SystemExit(f"No se encontró el archivo de entrada: {args.input}")
 
    with open(args.input, encoding="utf-8") as f:
        corpus = json.load(f)
 
    cleaned_docs = []
    all_persona_names = []
    name_to_docs: dict[str, list] = {}
 
    for doc in corpus:
        text = clean_text(doc.get("text", ""))
        doc_id = doc.get("id")
        doc_url = doc.get("source_url", "")
        doc_label = f"id={doc_id}" + (f" ({doc_url})" if doc_url else "")
 
        personas_norm, seen_p = [], set()
        for raw in doc.get("personas", []):
            nombre, _ = split_entity(raw)
            if not nombre or nombre.lower() == "no consta":
                continue
            n = normalize_case(nombre)
            if n not in seen_p:
                seen_p.add(n)
                personas_norm.append(n)
                all_persona_names.append(n)
            name_to_docs.setdefault(n, [])
            if doc_label not in name_to_docs[n]:
                name_to_docs[n].append(doc_label)
 
        lugares_norm, seen_l = [], set()
        for raw in doc.get("lugares", []):
            nombre, _ = split_entity(raw)
            if nombre:
                n = normalize_case(nombre)
                key = n.lower()
                if key not in seen_l:
                    seen_l.add(key)
                    lugares_norm.append(n)
 
        keywords_norm, seen_k = [], set()
        for k in doc.get("keywords", []):
            k = k.strip()
            if k and k.lower() not in seen_k:
                seen_k.add(k.lower())
                keywords_norm.append(k)
 
        cleaned_docs.append({
            "id":         doc.get("id"),
            "source_url": doc.get("source_url", ""),
            "title":      doc.get("title", "").strip(),
            "text":       text,
            "summary":    clean_text(doc.get("summary", "")),
            "personas":   personas_norm,
            "lugares":    lugares_norm,
            "keywords":   keywords_norm,
        })
 
    # Guardar JSON limpio (SIN fusionar nombres todavía)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(cleaned_docs, f, ensure_ascii=False, indent=2)
 
    # Generar candidatos de fusión para revisión manual
    candidates = generate_merge_candidates(all_persona_names, name_to_docs, args.candidate_threshold)
    args.candidates_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.candidates_out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "nombre_a", "documentos_a",
            "nombre_b", "documentos_b",
            "score", "aprobar_fusion(si/no)",
        ])
        for a, b, score, docs_a, docs_b in candidates:
            writer.writerow([a, docs_a, b, docs_b, score, ""])
 
    print(f"\n")
    print(f"Documentos procesados        : {len(cleaned_docs)}")
    print(f"Personas únicas (sin fusionar): {len(set(all_persona_names))}")
    print(f"Pares candidatos a revisar    : {len(candidates)}")
    print(f"\nJSON limpio guardado en      : {args.output}")
    print(f"Candidatos de fusión en      : {args.candidates_out}")
    print(f"\n Abre el CSV de candidatos, escribe 'si' en la columna")
    print(f"  'aprobar_fusion' para los pares que SÍ sean la misma persona,")
    
 
 
if __name__ == "__main__":
    main()
 