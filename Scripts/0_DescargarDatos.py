"""
0_DescargarDatos.py — Descarga del corpus 23-F desde el buscador de RTVE
─────────────────────────────────────────────────────────────────────
Fuente  : https://23fbuscador.rtve.es/
Método  : scraping con requests + BeautifulSoup
Salida  : data/rtve_23f_corpus.json

Uso:
    python scripts/00_download.py
    python scripts/00_download.py --page-size 25 --delay 1.0
    python scripts/00_download.py --force          # re-descarga aunque ya exista
    python scripts/00_download.py --output data/corpus.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────
BASE_URL  = "https://23fbuscador.rtve.es"
LIST_URL  = BASE_URL + "/"
DOC_URL   = BASE_URL + "/document/ocr/{id}"
OUT_PATH  = Path(__file__).resolve().parent.parent / "data" / "rtve_23f_corpus.json"
PAGE_SIZE = 25
DELAY     = 0.8    # segundos entre peticiones (cortesía al servidor)
TIMEOUT   = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE_URL,
}


# ── Paso 1: recopilar todos los IDs desde las páginas de listado ───────────────

def get_doc_ids(session: requests.Session, page_size: int) -> list[int]:
    """
    Recorre todas las páginas del listado y devuelve la lista de IDs de documento.
    Detecta el fin de paginación cuando la página viene vacía o igual a la anterior.
    """
    all_ids   = []
    seen_ids  = set()
    page      = 1

    print("Recopilando IDs de documentos...")

    while True:
        params = {"page_size": page_size, "page": page}
        resp   = session.get(LIST_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Selector flexible: href que contenga /document/ocr/ (relativo o absoluto)
        links = soup.select('a[href*="/document/ocr/"]')

        if not links:
            print(f"  Página {page}: sin documentos → fin de paginación")
            # Debug: mostrar algunos hrefs para diagnóstico
            sample = [a.get("href","") for a in soup.find_all("a", href=True)[:8]]
            print(f"  (hrefs de muestra: {sample})")
            break

        page_ids = []
        for a in links:
            href = a.get("href", "")
            # Extraer el ID numérico con regex — robusto ante query params y trailing slashes
            m = re.search(r"/document/ocr/(\d+)", href)
            if not m:
                continue
            doc_id = int(m.group(1))
            if doc_id not in seen_ids:
                page_ids.append(doc_id)
                seen_ids.add(doc_id)

        if not page_ids:
            print(f"  Página {page}: sin IDs nuevos → fin de paginación")
            break

        all_ids.extend(page_ids)
        print(f"  Página {page}: {len(page_ids)} documentos  "
              f"(total acumulado: {len(all_ids)})")

        # Detectar si hay botón "Siguiente" habilitado
        siguiente = soup.find("a", string=lambda t: t and "Siguiente" in t)
        if not siguiente or not siguiente.get("href"):
            print(f"  No hay más páginas.")
            break

        page += 1
        time.sleep(DELAY)

    return all_ids


# ── Paso 2: descargar cada documento ──────────────────────────────────────────

def fetch_document(session: requests.Session, doc_id: int) -> dict | None:
    """
    Descarga la página de un documento individual y extrae:
      - id       : identificador numérico
      - title    : título del documento (h2)
      - text     : transcripción completa (.text-box-large, sección "TEXTO COMPLETO")
      - summary  : resumen (.text-box sin large)
      - personas : entidades de tipo persona etiquetadas por RTVE
      - lugares  : entidades de tipo lugar etiquetadas por RTVE
      - keywords : palabras clave etiquetadas por RTVE
    """
    url  = DOC_URL.format(id=doc_id)
    resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)

    if resp.status_code == 404:
        print(f"    [{doc_id}] 404 — omitido")
        return None
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Título (h2 dentro de .page-header)
    h2 = soup.select_one("h2")
    title = h2.get_text(strip=True) if h2 else "23F Documentos Desclasificados"

    # TEXTO COMPLETO: sección con clase .text-box-large (transcripción limpia)
    # Es el bloque bajo el encabezado "TEXTO COMPLETO" en la página
    text_box_large = soup.select_one(".text-box-large")
    text = text_box_large.get_text(separator="\n") if text_box_large else ""

    # Si no está disponible, fallback al <pre> (OCR crudo)
    if not text.strip():
        pre = soup.select_one("pre")
        text = pre.get_text() if pre else ""

    # RESUMEN: primer .text-box sin .text-box-large
    text_boxes = soup.select(".text-box")
    summary = ""
    for tb in text_boxes:
        if "text-box-large" not in tb.get("class", []):
            summary = tb.get_text(strip=True)
            break

    # Entidades ya etiquetadas por RTVE
    personas = [el.get_text(strip=True)
                for el in soup.select(".tag-group-people .tag-chip")]
    lugares  = [el.get_text(strip=True)
                for el in soup.select(".tag-group-places .tag-chip")]
    keywords = [el.get_text(strip=True)
                for el in soup.select(".tag-group-keywords .tag-chip")]

    return {
    "id":         doc_id,
    "source_url": url,
    "title":      title,
    "text":       text,
    "summary":    summary,
    "personas":   personas,
    "lugares":    lugares,
    "keywords":   keywords,
    }


# ── Programa principal ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Descarga el corpus 23-F de RTVE (23fbuscador.rtve.es)"
    )
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE,
                        help=f"Documentos por página en el listado (default: {PAGE_SIZE})")
    parser.add_argument("--delay", type=float, default=DELAY,
                        help=f"Segundos de espera entre peticiones (default: {DELAY})")
    parser.add_argument("--output", type=Path, default=OUT_PATH,
                        help="Ruta de salida del JSON")
    parser.add_argument("--force", action="store_true",
                        help="Re-descargar aunque el fichero ya exista")
    args = parser.parse_args()

    out = Path(args.output)

    # Si ya existe y no se pide force, salir
    if out.exists() and not args.force:
        with open(out, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"Corpus ya descargado: {out.name} ({len(existing)} documentos)")
        print("  Usa --force para volver a descargar.")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    # ── 1. Recopilar IDs ──────────────────────────────────────────────────────
    doc_ids = get_doc_ids(session, args.page_size)
    if not doc_ids:
        print("No se encontraron documentos. Revisa la conexión o la URL.")
        sys.exit(1)
    print(f"\nTotal IDs recopilados: {len(doc_ids)}\n")

    # ── 2. Descargar documentos ───────────────────────────────────────────────
    print("Descargando documentos individuales...")
    corpus   = []
    errors   = []

    for i, doc_id in enumerate(doc_ids, 1):
        print(f"  [{i:3d}/{len(doc_ids)}] doc_{doc_id}...", end=" ", flush=True)
        try:
            doc = fetch_document(session, doc_id)
            if doc:
                corpus.append(doc)
                chars = len(doc["text"])
                print(f"({chars:,} chars)")
            time.sleep(args.delay)
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            errors.append(doc_id)
            time.sleep(args.delay * 2)   # espera más tras un error

    # ── 3. Guardar ────────────────────────────────────────────────────────────
    with open(out, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"{len(corpus)} documentos guardados en {out}")
    if errors:
        print(f"{len(errors)} errores: IDs {errors}")
    if corpus:
        lengths = [len(d["text"]) for d in corpus]
        print(f"  Texto OCR — min: {min(lengths):,}  "
              f"max: {max(lengths):,}  "
              f"media: {sum(lengths)//len(lengths):,} chars")


if __name__ == "__main__":
    main()
