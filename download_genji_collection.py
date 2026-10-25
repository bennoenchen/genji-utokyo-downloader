#!/usr/bin/env python3
"""Conservative, resumable downloader for UTokyo's Genji manuscript collection.

No recursive crawling.  The only discovery source is the documented OpenSearch
endpoint with collection=genji; downloaded candidates are independently checked
against their archive detail page before any image requests.
"""
import argparse
import io
import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError

BASE = "https://da.dl.itc.u-tokyo.ac.jp"
SEARCH = BASE + "/portal/search"
COLLECTION = BASE + "/portal/en/collection/genji"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
ASSET_RE = re.compile(r"/portal/(?:en/)?assets/([0-9a-f-]{36})(?:[/?#]|$)", re.I)
TEST_UUID = "c1ea8e6b-9403-4394-8619-96aad0ec6329"
LOG = logging.getLogger("genji")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def safe_name(name):
    name = unicodedata.normalize("NFKC", str(name or "Untitled"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (name[:90] or "Untitled")


def localized(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((localized(x) for x in value if localized(x)), "")
    if isinstance(value, dict):
        for key in ("ja", "none", "en", "@value", "value", "title", "label"):
            if key in value:
                return localized(value[key])
    return ""


def html_title(soup):
    h = soup.find("h1")
    return h.get_text(" ", strip=True) if h else ""


class Client:
    def __init__(self, delay, timeout, retries):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "GenjiManuscriptArchiver/1.0 (personal academic preservation)", "Accept": "application/json, application/ld+json, text/html;q=0.9, */*;q=0.5"})
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.last = 0.0

    def get(self, url, params=None, stream=False):
        if urlparse(url).scheme != "https":
            raise ValueError("Only HTTPS URLs are allowed: " + str(url))
        for attempt in range(self.retries + 1):
            pause = self.delay - (time.monotonic() - self.last)
            if pause > 0:
                time.sleep(pause)
            self.last = time.monotonic()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout,
                                            stream=stream, allow_redirects=True)
                if response.status_code in (403, 429):
                    response.close()
                    raise RuntimeError(f"HTTP {response.status_code}; no automatic retry: {url}")
                if response.status_code in (500, 502, 503, 504) and attempt < self.retries:
                    response.close()
                    time.sleep(min(2 ** attempt, 8))
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError):
                if attempt == self.retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("Retry limit reached")

    def json(self, url, params=None):
        with self.get(url, params=params) as r:
            return r.json()


def candidate_uuids(payload):
    """Extract asset identifiers only from explicit asset URLs/record IDs.

    Never scoop arbitrary UUIDs from nested related-asset fields.
    """
    if isinstance(payload, list):
        for obj in payload:
            yield from candidate_uuids(obj)
    elif isinstance(payload, dict):
        # Search API formats vary. Walk result arrays, not every opaque field.
        for key in ("results", "items", "data", "rows", "nodes", "search_results", "@graph"):
            if isinstance(payload.get(key), (list, dict)):
                yield from candidate_uuids(payload[key])
        for key in ("url", "link", "uri", "id", "@id", "path", "uuid", "nid"):
            v = payload.get(key)
            if isinstance(v, str):
                match = ASSET_RE.search(v)
                if match:
                    yield match.group(1).lower()
                elif key == "uuid" and UUID_RE.fullmatch(v):
                    yield v.lower()


def search_discovery(client, max_pages, page_size=20):
    found = []
    seen = set()
    reports = []
    for page in range(max_pages):
        params = {"collection": "genji", "_format": "json", "items_per_page": page_size, "page": page}
        data = client.json(SEARCH, params=params)
        ids = list(dict.fromkeys(candidate_uuids(data)))
        # Some Drupal formats return top-level records keyed by UUID.
        if not ids and isinstance(data, dict):
            for key in data:
                if UUID_RE.fullmatch(key):
                    ids.append(key.lower())
        reports.append({"page": page, "uuids": ids, "response_type": type(data).__name__})
        fresh = [u for u in ids if u not in seen]
        seen.update(fresh)
        found.extend(fresh)
        LOG.info("Search page %s: %s records, %s new", page, len(ids), len(fresh))
        if not ids:
            break
        if not fresh:
            raise RuntimeError("Search page repeated without new UUIDs; pagination schema needs inspection")
        if len(ids) < page_size:
            break
    else:
        raise RuntimeError("Maximum search pages reached; raise --max-pages after inspection")
    if not found:
        raise RuntimeError("Search API returned no recognizable asset URLs; inspect its JSON before changing extraction")
    return found, reports


def preview_discovery(client):
    """Read only asset links on the Genji collection landing page (not its search page).

    This page advertises a small preview, not the complete inventory. Never
    interpret these results as an exhaustive collection download.
    """
    with client.get(COLLECTION) as response:
        soup = BeautifulSoup(response.text, "html.parser")
    ids = []
    for link in soup.find_all("a", href=True):
        url = urljoin(COLLECTION, link["href"])
        if urlparse(url).netloc != urlparse(BASE).netloc:
            continue
        match = ASSET_RE.search(urlparse(url).path)
        if match and match.group(1).lower() not in ids:
            ids.append(match.group(1).lower())
    if not ids:
        raise RuntimeError("No Genji preview asset links found on collection landing page")
    return ids, [{"mode": "collection-preview-only", "source": COLLECTION,
                  "uuids": ids, "exhaustive": False}]


def verify_asset(client, uuid):
    url = f"{BASE}/portal/en/assets/{uuid}"
    with client.get(url) as r:
        soup = BeautifulSoup(r.text, "html.parser")
    # Distinctive same-origin link to canonical Genji collection; not related
    # material, arbitrary surrounding text, or a mere word match.
    links = [urljoin(url, a.get("href", "")) for a in soup.find_all("a", href=True)]
    member = any(urlparse(x).netloc == urlparse(BASE).netloc and
                 re.fullmatch(r"/portal/(?:en/)?collection/genji/?", urlparse(x).path)
                 for x in links)
    if not member:
        raise ValueError("Asset detail page does not link to the Genji collection")
    manifests = [x for x in links if re.search(r"/portal/repo/iiif/" + re.escape(uuid) + r"/manifest/?$", urlparse(x).path, re.I)]
    if not manifests:
        raise ValueError("No matching IIIF manifest linked from verified detail page")
    return {"uuid": uuid, "title": html_title(soup) or uuid,
            "detail_url": url, "manifest_url": manifests[0], "collection": "genji"}


def extract_pages(manifest):
    """Return ordered (canvas label, image URL, service IDs) from IIIF v2/v3."""
    result = []
    if manifest.get("sequences") is not None:  # Presentation 2
        canvases = [c for s in manifest.get("sequences", []) for c in s.get("canvases", [])]
        for canvas in canvases:
            images = canvas.get("images", [])
            resource = (images[0].get("resource") or {}) if images else {}
            if isinstance(resource, str):
                resource = {"@id": resource}
            result.append({"label": localized(canvas.get("label")),
                           "url": resource.get("@id") or resource.get("id"),
                           "services": service_ids(resource.get("service"))})
    elif manifest.get("items") is not None:  # Presentation 3
        for canvas in manifest.get("items", []):
            body = None
            for page in canvas.get("items", []):
                for annotation in page.get("items", []):
                    if annotation.get("motivation") in ("painting", ["painting"]):
                        body = annotation.get("body")
                        break
                if body is not None:
                    break
            if isinstance(body, list):
                body = next((x for x in body if isinstance(x, dict) and x.get("type") == "Image"), None)
            if isinstance(body, str):
                body = {"id": body}
            body = body or {}
            result.append({"label": localized(canvas.get("label")),
                           "url": body.get("id") or body.get("@id"),
                           "services": service_ids(body.get("service"))})
    else:
        raise ValueError("Not a recognized IIIF Presentation v2 or v3 manifest")
    return result


def service_ids(service):
    if isinstance(service, dict):
        return [service.get("id") or service.get("@id")] if (service.get("id") or service.get("@id")) else []
    if isinstance(service, list):
        return [sid for item in service for sid in service_ids(item)]
    return []


def image_sources(page, full_size=False):
    """Prefer the manifest's explicit image URL; don't assume a universal IIIF syntax.

    Optional full-size requests are attempted only after inspecting Image API
    info.json to learn the service version and maxima.
    """
    url = page.get("url")
    sources = [url] if url else []
    if full_size:
        sources += [(s.rstrip("/") + "/info.json") for s in page["services"] if s]
    return sources


def negotiated_image_url(client, page):
    for sid in page.get("services", []):
        if not sid:
            continue
        info = client.json(sid.rstrip("/") + "/info.json")
        context = json.dumps(info.get("@context", ""))
        protocol = info.get("protocol", "")
        if "image/3" in context or "image/3" in protocol:
            size = "max"
        elif "image/2" in context or "image/2" in protocol:
            size = "full"
        else:
            continue
        width, height = info.get("width"), info.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            continue
        # Image API 2/3 may restrict maximum area/width/height.
        limits = []
        if info.get("maxWidth"):
            limits.append(info["maxWidth"] / width)
        if info.get("maxHeight"):
            limits.append(info["maxHeight"] / height)
        if info.get("maxArea"):
            limits.append((info["maxArea"] / (width * height)) ** .5)
        factor = min([1.0] + limits)
        if factor < 1:
            size = f"{max(1, int(width * factor))},"
        return sid.rstrip("/") + f"/full/{size}/0/default.jpg"
    return page.get("url")


def save_image(client, url, prefix):
    if not url:
        raise ValueError("No image resource URL in canvas")
    with client.get(url, stream=True) as response:
        chunks = io.BytesIO()
        for piece in response.iter_content(128 * 1024):
            chunks.write(piece)
            if chunks.tell() > 600 * 1024 * 1024:
                raise ValueError("Image exceeds 600 MB safety limit")
        raw = chunks.getvalue()
    with Image.open(io.BytesIO(raw)) as img:
        img.verify()
    with Image.open(io.BytesIO(raw)) as img:
        fmt = (img.format or "").upper()
    ext = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tif", "WEBP": ".webp", "JP2": ".jp2"}.get(fmt)
    if not ext:
        raise ValueError("Unsupported image format: " + fmt)
    target = prefix.with_suffix(ext)
    temp = target.with_suffix(ext + ".part")
    temp.write_bytes(raw)
    temp.replace(target)
    return target


def existing_image(prefix):
    for path in sorted(prefix.parent.glob(prefix.name + ".*")):
        if path.suffix not in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".jp2"):
            continue
        try:
            with Image.open(path) as img:
                img.verify()
            return path
        except (OSError, UnidentifiedImageError):
            LOG.warning("Invalid existing image: %s", path)
    return None


def create_pdf(paths, target):
    # Page count is checked first; convert per page to RGB to support PNG/RGBA.
    images = []
    try:
        for path in paths:
            with Image.open(path) as src:
                fixed = ImageOps.exif_transpose(src)
                if fixed.mode in ("RGBA", "LA") or "transparency" in fixed.info:
                    bg = Image.new("RGB", fixed.size, "white")
                    bg.paste(fixed.convert("RGBA"), mask=fixed.convert("RGBA").getchannel("A"))
                    images.append(bg)
                else:
                    images.append(fixed.convert("RGB"))
        temp = target.with_suffix(".pdf.part")
        images[0].save(temp, format="PDF", save_all=True, append_images=images[1:], resolution=150)
        temp.replace(target)
    finally:
        for image in images:
            image.close()


def run_item(client, item, root, args, errors):
    uuid, title = item["uuid"], item["title"]
    folder = root / (safe_name(title) + "_" + uuid)
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    (folder / "manifest_url.txt").write_text(item["manifest_url"] + "\n", encoding="utf-8")
    metadata_path = root / ("metadata_" + uuid + ".json")
    try:
        if not metadata_path.exists():
            dump(metadata_path, client.json(f"{BASE}/portal/en/assets/{uuid}?_format=json"))
    except Exception as exc:
        errors.append({"uuid": uuid, "stage": "metadata", "error": str(exc)})
    try:
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = client.json(item["manifest_url"])
            dump(manifest_path, manifest)
        pages = extract_pages(manifest)
        if not pages:
            raise ValueError("Manifest has zero canvases")
    except Exception as exc:
        errors.append({"uuid": uuid, "stage": "manifest", "error": str(exc)})
        return {**item, "status": "manifest_error", "expected_pages": 0, "downloaded_pages": 0, "pdf": False}
    image_dir = folder / "images"
    image_dir.mkdir(exist_ok=True)
    saved = []
    for index, page in enumerate(pages, 1):
        prefix = image_dir / f"page_{index:04d}"
        path = existing_image(prefix)
        if path is None:
            try:
                url = negotiated_image_url(client, page) if args.full_resolution else page.get("url")
                path = save_image(client, url, prefix)
            except Exception as exc:
                errors.append({"uuid": uuid, "stage": "image", "page": index,
                               "label": page.get("label"), "error": str(exc)})
        saved.append(path)
    complete = all(saved)
    pdf_ok = False
    if not args.no_pdf and (complete or args.allow_partial_pdf) and any(saved):
        target = folder / (safe_name(title) + ("_PARTIAL" if not complete else "") + ".pdf")
        try:
            if not target.exists() or args.rebuild_pdf:
                create_pdf([p for p in saved if p], target)
            pdf_ok = True
        except Exception as exc:
            errors.append({"uuid": uuid, "stage": "pdf", "error": str(exc)})
    result = {**item, "status": "complete" if complete else "incomplete", "expected_pages": len(pages),
              "downloaded_pages": sum(bool(p) for p in saved), "pdf": pdf_ok,
              "missing_pages": [i for i, p in enumerate(saved, 1) if not p]}
    dump(folder / "status.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("UTokyo_Genji_Archive"))
    parser.add_argument("--max-items", type=int, default=0, help="0 = all verified search results")
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--test-uuid", action="store_true", help="Verify and process only the Kiritsubo test asset")
    parser.add_argument("--collection-preview", action="store_true",
                        help="Use only visible Genji landing-page asset links; NOT a complete collection")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--allow-partial-pdf", action="store_true")
    parser.add_argument("--rebuild-pdf", action="store_true")
    parser.add_argument("--full-resolution", action="store_true", help="Negotiate IIIF Image API size via info.json")
    args = parser.parse_args(argv)
    if args.delay < 0.3 or args.max_items < 0 or args.max_pages < 1 or args.retries < 0:
        parser.error("Use --delay >= 0.3, nonnegative max-items/retries and positive max-pages")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    client = Client(args.delay, args.timeout, args.retries)
    errors = []
    records = []
    try:
        if args.test_uuid:
            ids, reports = [TEST_UUID], [{"mode": "test-uuid", "uuids": [TEST_UUID]}]
        elif args.collection_preview:
            ids, reports = preview_discovery(client)
        else:
            ids, reports = search_discovery(client, args.max_pages)
        # Bound the detail-page verification requests during small test runs.
        verified = []
        candidates = ids[:args.max_items] if args.max_items else ids
        for uuid in candidates:
            try:
                item = verify_asset(client, uuid)
                verified.append(item)
            except Exception as exc:
                errors.append({"uuid": uuid, "stage": "membership", "error": str(exc)})
        dump(root / "discovery.json", {"source": COLLECTION if args.collection_preview else SEARCH,
                                       "filter": "collection=genji", "exhaustive": not (args.collection_preview or args.test_uuid),
                                       "candidate_count": len(ids), "verified_count": len(verified),
                                       "pages": reports, "assets": verified})
        if not verified:
            raise RuntimeError("No verified Genji assets; no images will be downloaded")
        if not args.discover_only:
            for pos, item in enumerate(verified, 1):
                LOG.info("Asset %s/%s: %s [%s]", pos, len(verified), item["title"], item["uuid"])
                records.append(run_item(client, item, root, args, errors))
                dump(root / "errors.json", errors)
                dump(root / "summary.json", summary(ids, verified, records))
    except (KeyboardInterrupt, Exception) as exc:
        errors.append({"stage": "run", "error": str(exc)})
        LOG.error("Stopped: %s", exc)
        dump(root / "errors.json", errors)
        dump(root / "summary.json", summary(locals().get("ids", []), locals().get("verified", []), records))
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    dump(root / "errors.json", errors)
    dump(root / "summary.json", summary(ids, verified, records))
    LOG.info("Finished: %d items, %d errors", len(records), len(errors))
    return 0 if not errors else 2


def summary(ids, verified, records):
    return {"found_candidates": len(ids), "verified_assets": len(verified),
            "processed_assets": len(records), "expected_pages": sum(x["expected_pages"] for x in records),
            "downloaded_pages": sum(x["downloaded_pages"] for x in records),
            "pdfs": sum(bool(x["pdf"]) for x in records),
            "complete_assets": sum(x["status"] == "complete" for x in records), "assets": records}


if __name__ == "__main__":
    sys.exit(main())
