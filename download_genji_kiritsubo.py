#!/usr/bin/env python3
"""
Lädt die digitalisierten Seiten des UTokyo-Genji-Kapitels 桐壺 (Kiritsubo)
über das IIIF-Manifest herunter und erstellt eine PDF aus den Seitenbildern.

Voraussetzungen:
    python -m pip install requests pillow

Aufruf:
    python download_genji_kiritsubo.py

Hinweis:
Die PDF enthält die Manuskriptbilder, keine Transkription/OCR.
Die Bilder sind laut UTokyo-Archiv als Public Domain gekennzeichnet.
Bitte prüfe die aktuellen Nutzungsbedingungen des Archivs:
https://www.lib.u-tokyo.ac.jp/ja/library/general/reuse
"""

import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

MANIFEST_URL = (
    "https://da.dl.itc.u-tokyo.ac.jp/portal/repo/iiif/"
    "c1ea8e6b-9403-4394-8619-96aad0ec6329/manifest"
)
OUTPUT_DIR = Path("Genji_Kiritsubo")
PDF_PATH = OUTPUT_DIR / "Genji_Kiritsubo.pdf"


def get_service_id(service):
    if isinstance(service, list):
        for item in service:
            result = get_service_id(item)
            if result:
                return result
        return None
    if isinstance(service, dict):
        return service.get("id") or service.get("@id")
    return None


def image_url_from_resource(resource):
    """Unterstützt gängige IIIF-Presentation-2- und -3-Strukturen."""
    service_id = get_service_id(resource.get("service"))
    if service_id:
        # IIIF Image API: vollständiges Bild in JPEG anfordern.
        return service_id.rstrip("/") + "/full/full/0/default.jpg"

    # Fallback: manche Manifeste verlinken die Bilddatei direkt.
    return resource.get("id") or resource.get("@id")


def collect_urls(manifest):
    urls = []

    # IIIF Presentation API 2
    if manifest.get("sequences"):
        for canvas in manifest["sequences"][0].get("canvases", []):
            for annotation in canvas.get("images", []):
                resource = annotation.get("resource", {})
                url = image_url_from_resource(resource)
                if url:
                    urls.append(url)
        return urls

    # IIIF Presentation API 3
    for canvas in manifest.get("items", []):
        for annotation_page in canvas.get("items", []):
            for annotation in annotation_page.get("items", []):
                body = annotation.get("body", {})
                bodies = body if isinstance(body, list) else [body]
                for resource in bodies:
                    if not isinstance(resource, dict):
                        continue
                    url = image_url_from_resource(resource)
                    if url:
                        urls.append(url)
                        break
                if urls and len(urls) >= len(manifest.get("items", [])):
                    # Nur ein einfacher Schutz; normale Schleife läuft weiter,
                    # falls das Manifest mehrere Annotationen je Seite enthält.
                    pass
    return urls


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "GenjiManuscriptDownloader/1.0 (personal research)"
    })

    print("Rufe IIIF-Manifest für 桐壺 (Kiritsubo) ab ...")
    try:
        response = session.get(MANIFEST_URL, timeout=45)
        response.raise_for_status()
        manifest = response.json()
    except Exception as exc:
        sys.exit(
            "Manifest konnte nicht abgerufen werden.\n"
            "Bitte Internetverbindung prüfen und erneut versuchen.\n"
            f"Details: {exc}"
        )

    urls = collect_urls(manifest)
    # Doppelte URLs entfernen, Reihenfolge beibehalten.
    urls = list(dict.fromkeys(urls))

    if not urls:
        print("Keine Bild-URLs in der erwarteten IIIF-Struktur gefunden.")
        print("Manifeststruktur wurde gespeichert unter:")
        raw_path = OUTPUT_DIR / "manifest.json"
        raw_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(raw_path.resolve())
        sys.exit("Bitte manifest.json prüfen; die IIIF-Struktur könnte abweichen.")

    print(f"{len(urls)} Bild-URLs gefunden.")
    downloaded = []

    for index, url in enumerate(urls, start=1):
        suffix = ".jpg"
        target = OUTPUT_DIR / f"seite_{index:04d}{suffix}"
        print(f"[{index}/{len(urls)}] {target.name}")

        try:
            image_response = session.get(url, timeout=90)
            image_response.raise_for_status()
            data = image_response.content

            # Validieren, dass die Antwort wirklich ein Bild ist.
            with Image.open(io.BytesIO(data)) as im:
                im.verify()

            target.write_bytes(data)
            downloaded.append(target)
        except Exception as exc:
            print(f"  FEHLER bei dieser Seite: {exc}")
            print(f"  URL: {url}")

        # Den Server nicht mit unnötig schnellen Anfragen belasten.
        time.sleep(0.15)

    if not downloaded:
        sys.exit("Es wurde kein Bild erfolgreich heruntergeladen.")

    print("Erstelle PDF ...")
    pdf_images = []
    for path in downloaded:
        with Image.open(path) as im:
            pdf_images.append(im.convert("RGB").copy())

    pdf_images[0].save(
        PDF_PATH,
        "PDF",
        save_all=True,
        append_images=pdf_images[1:],
        resolution=150.0,
    )

    for im in pdf_images:
        im.close()

    print("\nFertig!")
    print(f"Seiten erfolgreich geladen: {len(downloaded)} von {len(urls)}")
    print(f"PDF: {PDF_PATH.resolve()}")
    print(f"Einzelbilder: {OUTPUT_DIR.resolve()}")
    if len(downloaded) != len(urls):
        print("Achtung: Nicht alle Seiten konnten geladen werden; siehe Fehlermeldungen.")


if __name__ == "__main__":
    main()
