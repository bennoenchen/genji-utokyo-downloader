#!/usr/bin/env python3
"""
UTokyo Digital Archive: Genji Monogatari Bulk Downloader

Ziele:
- Die Genji-Sammlungsseite und ihre paginierten Einträge durchsuchen.
- JSON-Metadaten und IIIF-Manifeste finden.
- Aus IIIF Presentation API 2/3 die Bildseiten extrahieren.
- Bilder in Kapitel-/Werkordnern speichern.
- Pro Manifest eine PDF aus den heruntergeladenen Seiten erstellen.
- Eine Zusammenfassung und die gefundenen Metadaten lokal speichern.

Voraussetzungen:
    python -m pip install requests pillow beautifulsoup4

Start:
    python download_all_genji.py

Optionen:
    python download_all_genji.py --max-items 10
    python download_all_genji.py --no-pdf
    python download_all_genji.py --delay 0.5

Bitte beachten:
- Das Skript arbeitet mit öffentlichen Seiten und IIIF-Endpunkten.
- Es begrenzt die Anfragerate und überspringt bereits heruntergeladene Dateien.
- Die konkrete HTML-/API-Struktur der Website kann sich ändern. Wenn die
  Sammlung nicht zuverlässig erkannt wird, wird die Diagnose gespeichert.
- Beachte die Nutzungsbedingungen des Archivs und belaste den Server nicht.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from PIL import Image

BASE = "https://da.dl.itc.u-tokyo.ac.jp"
COLLECTION_URL = BASE + "/portal/en/collection/genji"
ASSET_API = BASE + "/portal/en/assets/{uuid}?_format=json"
IIIF_MANIFEST_CANDIDATES = [
    BASE + "/portal/repo/iiif/{uuid}/manifest",
    BASE + "/portal/repo/iiif/{uuid}/manifest.json",
]
OUT_ROOT = Path("UTokyo_Genji_Archive")
USER_AGENT = "PersonalGenjiArchiveDownloader/1.0 (polite bulk access)"


def slugify(value: str, limit: int = 90) -> str:
    value = re.sub(r"[^\w\-ぁ-ゖァ-ヺ一-龯]+", "_", value, flags=re.UNICODE)
    value = value.strip("_")[:limit]
    return value or "untitled"


def canonical_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/")


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html, */*",
    })
    return s


def get_json(session: requests.Session, url: str, timeout: int = 40):
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def safe_get(session: requests.Session, url: str, timeout: int = 40):
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r


def extract_uuid(url: str) -> str | None:
    # UUIDs in asset URLs, e.g. /portal/en/assets/<uuid>
    match = re.search(
        r"/assets/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        url,
    )
    return match.group(1) if match else None


def walk_json_for_urls(obj, base_url: str, found: set[str]):
    """Recursively find likely asset, manifest, and collection URLs in JSON."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and (
                key.lower() in {"url", "href", "id", "@id", "manifest", "api"}
                or "assets/" in value
                or "manifest" in value.lower()
            ):
                candidate = urljoin(base_url, value)
                if urlparse(candidate).scheme in {"http", "https"}:
                    found.add(canonical_url(candidate))
            else:
                walk_json_for_urls(value, base_url, found)
    elif isinstance(obj, list):
        for value in obj:
            walk_json_for_urls(value, base_url, found)


def discover_from_collection(session, delay: float, max_pages: int | None):
    """
    Discover asset UUIDs by crawling collection pages and linked JSON.
    Follows pagination links and gathers /assets/<uuid> links.
    """
    queue = [COLLECTION_URL]
    seen_pages = set()
    uuids = set()
    raw_links = set()
    page_count = 0

    while queue:
        url = queue.pop(0)
        url = canonical_url(url)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        page_count += 1

        if max_pages and page_count > max_pages:
            break

        print(f"[Suche] {url}")
        try:
            response = safe_get(session, url)
        except Exception as exc:
            print(f"  Warnung: Seite nicht abrufbar: {exc}")
            continue

        ctype = response.headers.get("content-type", "").lower()
        if "json" in ctype or url.endswith(".json") or "_format=json" in url:
            try:
                data = response.json()
                found = set()
                walk_json_for_urls(data, url, found)
                raw_links.update(found)
                for item_url in found:
                    uid = extract_uuid(item_url)
                    if uid:
                        uuids.add(uid)
                    if "collection/genji" in item_url and item_url not in seen_pages:
                        queue.append(item_url)
            except Exception:
                pass
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup.find_all(["a", "link"]):
                href = tag.get("href")
                if not href:
                    continue
                full = canonical_url(urljoin(url, href))
                if urlparse(full).netloc != urlparse(BASE).netloc:
                    continue
                raw_links.add(full)
                uid = extract_uuid(full)
                if uid:
                    uuids.add(uid)

                # Pagination / collection subpages / JSON links
                path = urlparse(full).path.lower()
                query = urlparse(full).query.lower()
                is_pagination = (
                    any(token in path for token in ("page", "collection", "assets"))
                    or "page=" in query
                    or "_format=json" in query
                    or path.endswith(".json")
                )
                if is_pagination and full not in seen_pages:
                    queue.append(full)

            # Some archives expose JSON-LD or embedded API links.
            for match in re.findall(
                r"""(?:href|src|url|api|manifest)["'\s:=]+["']([^"']+)["']""",
                response.text,
                flags=re.IGNORECASE,
            ):
                full = canonical_url(urljoin(url, match))
                uid = extract_uuid(full)
                if uid:
                    uuids.add(uid)
                if urlparse(full).netloc == urlparse(BASE).netloc:
                    raw_links.add(full)

        time.sleep(delay)

    return sorted(uuids), sorted(raw_links), page_count


def title_from_metadata(metadata: dict, fallback: str) -> str:
    # Drupal/JSON-LD-like formats vary. Try common title fields.
    candidates = []
    if isinstance(metadata, dict):
        for key in ("title", "label", "name", "dc:title", "dcterms:title"):
            value = metadata.get(key)
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(str(v) for v in value if isinstance(v, (str, int)))
            elif isinstance(value, dict):
                candidates.extend(
                    str(v) for v in value.values() if isinstance(v, str)
                )
        for key in ("data", "attributes", "metadata", "descriptiveMetadata"):
            value = metadata.get(key)
            if isinstance(value, dict):
                nested = title_from_metadata(value, "")
                if nested:
                    candidates.append(nested)
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if candidate:
            return candidate
    return fallback


def service_id(service):
    if isinstance(service, list):
        for item in service:
            result = service_id(item)
            if result:
                return result
        return None
    if isinstance(service, dict):
        return service.get("id") or service.get("@id")
    return None


def resource_image_url(resource: dict) -> str | None:
    sid = service_id(resource.get("service"))
    if sid:
        # IIIF Image API 2/3 services generally support this request.
        return sid.rstrip("/") + "/full/full/0/default.jpg"
    return resource.get("id") or resource.get("@id")


def extract_iiif_images(manifest: dict):
    results = []
    # IIIF Presentation 2
    if manifest.get("sequences"):
        canvases = manifest["sequences"][0].get("canvases", [])
        for canvas in canvases:
            images = canvas.get("images", [])
            if not images:
                continue
            resource = images[0].get("resource", {})
            url = resource_image_url(resource)
            if url:
                results.append({
                    "label": canvas.get("label", ""),
                    "url": url,
                    "canvas_id": canvas.get("@id", ""),
                })
        return results

    # IIIF Presentation 3
    for canvas in manifest.get("items", []):
        found = None
        for annotation_page in canvas.get("items", []):
            for annotation in annotation_page.get("items", []):
                body = annotation.get("body", {})
                bodies = body if isinstance(body, list) else [body]
                for resource in bodies:
                    if not isinstance(resource, dict):
                        continue
                    url = resource_image_url(resource)
                    if url:
                        found = url
                        break
                if found:
                    break
            if found:
                break
        if found:
            results.append({
                "label": canvas.get("label", ""),
                "url": found,
                "canvas_id": canvas.get("id", ""),
            })
    return results


def manifest_title(manifest: dict, fallback: str) -> str:
    label = manifest.get("label", fallback)
    if isinstance(label, dict):
        # IIIF 3 language map
        for values in label.values():
            if isinstance(values, list) and values:
                return str(values[0])
        return fallback
    if isinstance(label, list):
        return str(label[0]) if label else fallback
    return str(label) if label else fallback


def try_manifest(session, uuid: str):
    last_error = None
    for url in IIIF_MANIFEST_CANDIDATES:
        manifest_url = url.format(uuid=uuid)
        try:
            response = safe_get(session, manifest_url)
            data = response.json()
            if isinstance(data, dict) and (
                "sequences" in data or "items" in data
            ):
                return manifest_url, data
            last_error = f"JSON at {manifest_url} is not a recognized IIIF manifest"
        except Exception as exc:
            last_error = f"{manifest_url}: {exc}"

    # Try asset JSON and look for manifest links.
    try:
        asset_data = get_json(session, ASSET_API.format(uuid=uuid))
        found = set()
        walk_json_for_urls(asset_data, BASE, found)
        for candidate in found:
            if "manifest" not in candidate.lower():
                continue
            try:
                response = safe_get(session, candidate)
                data = response.json()
                if isinstance(data, dict) and (
                    "sequences" in data or "items" in data
                ):
                    return candidate, data
            except Exception:
                continue
    except Exception as exc:
        last_error = f"asset JSON: {exc}"

    return None, last_error


def make_pdf(image_paths: list[Path], pdf_path: Path):
    if not image_paths:
        return False
    pages = []
    try:
        for path in image_paths:
            with Image.open(path) as image:
                pages.append(image.convert("RGB").copy())
        pages[0].save(
            pdf_path,
            "PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=150.0,
        )
        return True
    finally:
        for page in pages:
            page.close()


def main():
    parser = argparse.ArgumentParser(description="Download all Genji scans from UTokyo IIIF.")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Test mode: process at most this many discovered asset IDs.")
    parser.add_argument("--max-pages", type=int, default=100,
                        help="Maximum collection/pagination pages to crawl (default: 100).")
    parser.add_argument("--delay", type=float, default=0.35,
                        help="Delay in seconds between requests (default: 0.35).")
    parser.add_argument("--no-pdf", action="store_true",
                        help="Download images but do not assemble PDFs.")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Retry downloads even if a previous failure marker exists.")
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    session = make_session()

    print("Durchsuche die UTokyo-Genji-Sammlung nach Asset-IDs ...")
    uuids, discovered_links, page_count = discover_from_collection(
        session, args.delay, args.max_pages
    )

    # Always include the example item supplied by the user as a seed.
    seed_uuid = "c1ea8e6b-9403-4394-8619-96aad0ec6329"
    if seed_uuid not in uuids:
        uuids.insert(0, seed_uuid)

    if args.max_items:
        uuids = uuids[:args.max_items]

    discovery = {
        "collection_url": COLLECTION_URL,
        "pages_visited": page_count,
        "asset_uuids": uuids,
        "discovered_links": discovered_links,
    }
    (OUT_ROOT / "discovery.json").write_text(
        json.dumps(discovery, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Gefundene Asset-IDs: {len(uuids)}")
    print(f"Besuchte Sammlungsseiten: {page_count}")
    print(f"Ausgabeordner: {OUT_ROOT.resolve()}")

    summary = []
    for item_index, uuid in enumerate(uuids, start=1):
        print(f"\n=== Werk {item_index}/{len(uuids)}: {uuid} ===")
        asset_url = ASSET_API.format(uuid=uuid)
        metadata = {}
        try:
            metadata = get_json(session, asset_url)
            (OUT_ROOT / f"metadata_{uuid}.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"Metadaten konnten nicht geladen werden: {exc}")

        title = title_from_metadata(metadata, uuid)
        folder = OUT_ROOT / f"{slugify(title)}_{uuid[:8]}"
        folder.mkdir(parents=True, exist_ok=True)

        manifest_url, manifest_or_error = try_manifest(session, uuid)
        if not manifest_url:
            print(f"Kein IIIF-Manifest erkannt: {manifest_or_error}")
            summary.append({
                "uuid": uuid, "title": title, "status": "no_manifest",
                "error": str(manifest_or_error),
            })
            time.sleep(args.delay)
            continue

        manifest = manifest_or_error
        (folder / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (folder / "manifest_url.txt").write_text(manifest_url + "\n", encoding="utf-8")
        title = manifest_title(manifest, title)
        print(f"Titel: {title}")
        print(f"Manifest: {manifest_url}")

        pages = extract_iiif_images(manifest)
        print(f"Bildseiten im Manifest: {len(pages)}")
        if not pages:
            summary.append({
                "uuid": uuid, "title": title, "status": "empty_manifest",
                "manifest": manifest_url,
            })
            continue

        images_dir = folder / "images"
        images_dir.mkdir(exist_ok=True)
        saved = []

        for page_num, page in enumerate(pages, start=1):
            extension = ".jpg"
            path = images_dir / f"page_{page_num:04d}{extension}"
            if path.exists() and path.stat().st_size > 0:
                saved.append(path)
                continue

            print(f"  [{page_num}/{len(pages)}] lade Bild ...")
            try:
                response = session.get(page["url"], timeout=90)
                response.raise_for_status()
                data = response.content
                with Image.open(io.BytesIO(data)) as im:
                    im.verify()
                path.write_bytes(data)
                saved.append(path)
            except Exception as exc:
                print(f"    FEHLER: {exc}")
                (images_dir / f"page_{page_num:04d}.failed.txt").write_text(
                    f"URL: {page['url']}\nFehler: {exc}\n",
                    encoding="utf-8",
                )
            time.sleep(args.delay)

        pdf_ok = None
        pdf_path = folder / f"{slugify(title)}.pdf"
        if not args.no_pdf and saved:
            print(f"Erstelle PDF aus {len(saved)} Bildern ...")
            try:
                pdf_ok = make_pdf(saved, pdf_path)
            except Exception as exc:
                pdf_ok = False
                print(f"PDF konnte nicht erstellt werden: {exc}")

        status = "complete" if len(saved) == len(pages) else "partial"
        summary.append({
            "uuid": uuid,
            "title": title,
            "status": status,
            "manifest": manifest_url,
            "page_count_manifest": len(pages),
            "images_downloaded": len(saved),
            "pdf_created": bool(pdf_ok),
            "output_folder": str(folder),
        })
        print(f"Status: {status} ({len(saved)}/{len(pages)} Bilder)")
        time.sleep(args.delay)

    (OUT_ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nFertig. Zusammenfassung:")
    for item in summary:
        print(f"- {item.get('title', item['uuid'])}: {item['status']}")
    print(f"\nDetails: {(OUT_ROOT / 'summary.json').resolve()}")
    print(f"Gefundene URLs: {(OUT_ROOT / 'discovery.json').resolve()}")


if __name__ == "__main__":
    main()
