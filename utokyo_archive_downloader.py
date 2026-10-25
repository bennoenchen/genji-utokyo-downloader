#!/usr/bin/env python3
"""Archive image assets from a saved UTokyo Digital Archive search-results page."""
import argparse
import hashlib
import io
import json
import logging
import re
import shutil
import sys
import time
from pathlib import Path

import img2pdf
import requests
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader, PdfWriter


HOST = "https://da.dl.itc.u-tokyo.ac.jp"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
GENJI_CHAPTERS = (
    "桐壺", "帚木", "空蝉", "夕顔", "若紫", "末摘花", "紅葉加(紅葉賀)", "花宴", "葵", "龍眼木(賢木 , 榊)",
    "花散里", "須磨", "赤石(明石)", "水衝石(澪標)", "蓬生", "関屋", "檜合", "松風", "薄雲", "槿",
    "乙女", "玉鬘", "初音", "胡蝶", "蛍", "床夏(常夏)", "篝火", "野分", "行幸", "蘭(藤袴)",
    "真木柱", "梅枝", "藤裏葉", "若菜 上", "若菜 下", "柏木", "横笛", "鈴虫", "夕霧", "御法",
    "幻", "匂宮", "紅梅", "竹川", "橋姫", "椎本", "総角", "早蕨", "寄生", "東屋",
    "浮舟", "蜻蛉", "手習", "夢浮橋",
)
ORDINAL = {name: index for index, name in enumerate(GENJI_CHAPTERS, 1)}
LOG = logging.getLogger("utokyo_archive")


def write_json(path, obj):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_html(path, genji=False):
    """Read asset records from UTokyo search-result HTML, ignoring navigation links."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")
    entries, seen_uuids, seen_titles = [], set(), set()
    for article in soup.select('article[about^="/portal/assets/"]'):
        asset_id = article.get("about", "").rsplit("/", 1)[-1].lower()
        link = article.select_one('a[rel="bookmark"]')
        title = link.get_text(" ", strip=True) if link else ""
        if not UUID.fullmatch(asset_id) or not title:
            raise ValueError(f"Unrecognized UTokyo asset record in HTML: {asset_id} {title!r}")
        if genji and title not in ORDINAL:
            raise ValueError(f"Asset is not a recognized Genji chapter: {title!r}")
        if asset_id in seen_uuids or (genji and title in seen_titles):
            raise ValueError(f"Duplicate asset UUID or Genji chapter title in HTML: {title}")
        seen_uuids.add(asset_id)
        seen_titles.add(title)
        number = ORDINAL[title] if genji else len(entries) + 1
        # Every title here is the catalog's exact Japanese spelling.
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
        entries.append({"number": number, "title": title, "uuid": asset_id,
                        "folder": f"{number:02d}_{safe}"})
    if not entries:
        raise ValueError("No UTokyo asset records found. Save a search-results page as HTML.")
    return sorted(entries, key=lambda entry: entry["number"])


class Http:
    def __init__(self, delay, timeout, retries):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "UTokyo-Digital-Archive-personal-archiver/1.0"
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.previous = 0.0

    def get(self, url, stream=False):
        if not url.startswith(HOST + "/portal/") and not url.startswith("https://"):
            raise ValueError(f"Unexpected URL: {url}")
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self.previous)
            if wait > 0:
                time.sleep(wait)
            self.previous = time.monotonic()
            try:
                response = self.session.get(url, timeout=self.timeout, stream=stream)
                if response.status_code in (403, 429):
                    response.close()
                    raise PermissionError(f"HTTP {response.status_code} (no automatic retry): {url}")
                if response.status_code in (500, 502, 503, 504) and attempt < self.retries:
                    response.close()
                    time.sleep(min(2 ** attempt, 8))
                    continue
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout):
                if attempt >= self.retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("Retry limit exhausted")

    def json(self, url):
        with self.get(url) as response:
            return response.json()


def page_images(manifest):
    """IIIF Presentation API v2 and v3, preserving canvas order."""
    pages = []
    if "sequences" in manifest:
        for sequence in manifest["sequences"]:
            for canvas in sequence.get("canvases", []):
                annotations = canvas.get("images", [])
                resource = annotations[0].get("resource", {}) if annotations else {}
                if isinstance(resource, str):
                    resource = {"@id": resource}
                pages.append(resource.get("@id") or resource.get("id"))
    elif "items" in manifest:
        for canvas in manifest["items"]:
            url = None
            for layer in canvas.get("items", []):
                for annotation in layer.get("items", []):
                    if annotation.get("motivation") != "painting":
                        continue
                    body = annotation.get("body", {})
                    if isinstance(body, list):
                        body = next((b for b in body if isinstance(b, dict) and b.get("type") == "Image"), {})
                    if isinstance(body, str):
                        body = {"id": body}
                    url = body.get("id") or body.get("@id")
                    break
                if url:
                    break
            pages.append(url)
    else:
        raise ValueError("Unknown IIIF manifest format")
    if not pages or any(not u for u in pages):
        raise ValueError("IIIF manifest has no images or contains an empty canvas")
    return pages


def valid_image(path):
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def find_image(folder, number):
    for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".jp2"):
        path = folder / f"page_{number:04d}{ext}"
        if path.is_file() and valid_image(path):
            return path
    return None


def get_image(http, url, directory, number):
    with http.get(url, stream=True) as response:
        data = io.BytesIO()
        for chunk in response.iter_content(131072):
            data.write(chunk)
            if data.tell() > 600_000_000:
                raise ValueError("Image exceeded 600 MB safety limit")
    raw = data.getvalue()
    with Image.open(io.BytesIO(raw)) as image:
        fmt = image.format
        image.verify()
    extension = {"JPEG": "jpg", "PNG": "png", "TIFF": "tif", "WEBP": "webp", "JPEG2000": "jp2"}.get(fmt)
    if not extension:
        raise ValueError(f"Unsupported image format: {fmt}")
    target = directory / f"page_{number:04d}.{extension}"
    temporary = directory / f"page_{number:04d}.{extension}.part"
    temporary.write_bytes(raw)
    temporary.replace(target)
    return target


def pdf_pages(path):
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return -1


def chapter_pdf(images, target):
    temporary = target.with_suffix(".pdf.part")
    try:
        with temporary.open("wb") as out:
            img2pdf.convert([str(path) for path in images], outputstream=out)
        if pdf_pages(temporary) != len(images):
            raise ValueError("Generated PDF page count does not match image count")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def import_old_images(root, chapter, target, total):
    """Copy, never move/delete, verified pages from an older UUID-suffixed folder."""
    for old in root.iterdir():
        if not old.is_dir() or old == target.parent or not old.name.endswith("_" + chapter["uuid"]):
            continue
        old_images = old / "images"
        if not old_images.is_dir():
            continue
        for number in range(1, total + 1):
            if find_image(target, number):
                continue
            source = find_image(old_images, number)
            if source:
                shutil.copy2(source, target / source.name)


def process_asset(http, root, asset):
    directory = root / asset["folder"]
    directory.mkdir(parents=True, exist_ok=True)
    pictures = directory / "images"
    pictures.mkdir(exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest_url = f"{HOST}/portal/repo/iiif/{asset['uuid']}/manifest"
    previous_manifest = None
    if manifest_path.exists():
        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            LOG.warning("Ignoring unreadable saved manifest for %s", asset["title"])
    manifest = http.json(manifest_url)
    identifier = manifest.get("id") or manifest.get("@id") or ""
    if identifier and asset["uuid"] not in identifier:
        raise ValueError("Manifest ID does not match expected UUID")
    manifest_fingerprint = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    previous_status_path = directory / "status.json"
    previous_fingerprint = None
    if previous_manifest is not None:
        previous_fingerprint = hashlib.sha256(
            json.dumps(previous_manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    manifest_changed = False
    if previous_status_path.is_file():
        try:
            previous = json.loads(previous_status_path.read_text(encoding="utf-8"))
            manifest_changed = previous.get("manifest_sha256", previous_fingerprint) not in (None, manifest_fingerprint)
            if manifest_changed:
                LOG.warning("%s: manifest changed; rechecking saved pages", asset["title"])
        except (OSError, ValueError):
            pass
    urls = page_images(manifest)
    if manifest_changed:
        prior_hash = previous.get("manifest_sha256", previous_fingerprint or "unknown")
        suffix = f"{prior_hash[:12]}_{time.time_ns()}"
        stale_pictures = directory / f"images_manifest_{suffix}"
        if pictures.exists() and not stale_pictures.exists():
            pictures.replace(stale_pictures)
            pictures.mkdir()
        old_pdf = directory / f"{asset['folder']}.pdf"
        if old_pdf.exists():
            old_pdf.replace(directory / f"{asset['folder']}_manifest_{suffix}.pdf")
    else:
        import_old_images(root, asset, pictures, len(urls))
    write_json(manifest_path, manifest)
    status = {**asset, "manifest_url": manifest_url, "expected_pages": len(urls),
              "downloaded_pages": 0, "missing_pages": [], "pdf_complete": False,
              "manifest_sha256": manifest_fingerprint}
    files = []
    for number, url in enumerate(urls, 1):
        path = find_image(pictures, number)
        if path is None:
            try:
                path = get_image(http, url, pictures, number)
            except PermissionError:
                raise
            except Exception as exc:
                LOG.error("%02d %s: image %d failed: %s", asset["number"], asset["title"], number, exc)
        if path:
            files.append(path)
        else:
            status["missing_pages"].append(number)
        status["downloaded_pages"] = len(files)
        width = 24
        filled = width * number // len(urls)
        bar = "#" * filled + "-" * (width - filled)
        progress = (f"\r{asset['number']:02d} {asset['title']}: [{bar}] "
                    f"{number}/{len(urls)} pages ({len(files)} complete, "
                    f"{len(status['missing_pages'])} missing)")
        sys.stderr.write(progress)
        sys.stderr.flush()
        write_json(directory / "status.json", status)
    sys.stderr.write("\n")
    if len(files) == len(urls):
        target = directory / f"{asset['folder']}.pdf"
        if pdf_pages(target) != len(urls):
            chapter_pdf(files, target)
        status["pdf_complete"] = pdf_pages(target) == len(urls)
    write_json(directory / "status.json", status)
    # Metadata are useful but can be unavailable even when images are public.
    meta_path = directory / "metadata.json"
    if not meta_path.exists():
        try:
            metadata = http.json(f"{HOST}/portal/en/assets/{asset['uuid']}?_format=json")
            write_json(meta_path, metadata)
        except Exception as exc:
            LOG.warning("Metadata for %s unavailable: %s", asset["title"], exc)
    return status


def merge_master(root, index, statuses, target):
    if len(statuses) != len(index):
        LOG.info("No master PDF: at least one asset or page is missing")
        return False
    by_uuid = {s.get("uuid"): s for s in statuses}
    ordered = [by_uuid.get(chapter.get("uuid")) for chapter in index]
    if any(status is None or not status.get("pdf_complete") for status in ordered):
        LOG.info("No master PDF: at least one asset or page is missing")
        return False
    for chapter, status in zip(index, ordered):
        if (status.get("uuid") != chapter.get("uuid") or status.get("number") != chapter["number"]
                or status.get("expected_pages", 0) < 1
                or status.get("downloaded_pages") != status["expected_pages"]):
            LOG.error("No master PDF: asset identity/page count mismatch for %s", chapter["title"])
            return False
        folder = root / chapter["folder"] / "images"
        if any(find_image(folder, i) is None for i in range(1, status["expected_pages"] + 1)):
            LOG.error("No master PDF: missing or corrupt image in %s", chapter["title"])
            return False
    parts = [root / chapter["folder"] / f"{chapter['folder']}.pdf" for chapter in index]
    count = sum(s["expected_pages"] for s in ordered)
    if any(pdf_pages(path) != status["expected_pages"] for path, status in zip(parts, ordered)):
        LOG.error("No master PDF: an asset PDF failed its page-count check")
        return False
    target = Path(target)
    if target.resolve() in {path.resolve() for path in parts}:
        raise ValueError("Master PDF path must not overwrite an asset PDF")
    master_state = target.with_suffix(target.suffix + ".json")
    signature = [{"uuid": status["uuid"], "manifest_sha256": status.get("manifest_sha256"),
                  "expected_pages": status["expected_pages"]} for status in ordered]
    try:
        saved_signature = json.loads(master_state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved_signature = None
    if pdf_pages(target) == count and saved_signature == signature:
        LOG.info("Master PDF already complete: %s", target)
        return True
    size = sum(path.stat().st_size for path in parts)
    if shutil.disk_usage(root).free < size * 1.2:
        LOG.error("Not enough free disk space for master PDF (about %.1f GB needed)", size * 1.2 / 1e9)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    writer = PdfWriter()
    try:
        for path in parts:
            LOG.info("Master PDF: adding %s", path.name)
            writer.append(str(path))
        with temporary.open("wb") as stream:
            writer.write(stream)
        if pdf_pages(temporary) != count:
            raise ValueError("Master PDF page count differs from total of chapter PDFs")
        temporary.replace(target)
        write_json(master_state, signature)
        return True
    finally:
        writer.close()
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        "Example: python utokyo_archive_downloader.py --html search.html --max-assets 2"))
    parser.add_argument("--html", type=Path, required=True, help="Saved UTokyo search-results HTML file")
    parser.add_argument("--output", type=Path, default=Path("UTokyo_Archive"), metavar="DIR", help="Output directory (default: UTokyo_Archive)")
    parser.add_argument("--max-assets", dest="max_assets", type=int, default=0, metavar="N", help="Process only the first N assets (0 = all; useful for a trial run)")
    parser.add_argument("--genji", action="store_true", help="Validate ordering against the 54 Genji chapters")
    parser.add_argument("--master-pdf", type=Path, metavar="PATH", help="Create one combined PDF at this path (off by default)")
    parser.add_argument("--retries", type=int, default=2, help="Retries for transient network errors (default: 2)")
    parser.add_argument("--delay", type=float, default=0.5, metavar="SECONDS", help="Minimum delay between requests (default: 0.5; minimum: 0.3)")
    parser.add_argument("--timeout", type=float, default=30, metavar="SECONDS", help="Request timeout (default: 30)")
    parser.add_argument("--list-only", action="store_true", help="Validate the HTML and list assets without downloading")
    args = parser.parse_args()
    if args.delay < 0.3 or args.max_assets < 0 or args.timeout <= 0 or args.retries < 0:
        parser.error("Use --delay >= 0.3, positive --timeout, and non-negative --max-assets/--retries")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not args.html.is_file():
        parser.error(f"HTML file not found: {args.html}")
    index = parse_html(args.html, genji=args.genji)
    LOG.info("Saved HTML contains %d distinct UTokyo assets", len(index))
    if args.list_only:
        for chapter in index:
            LOG.info("%02d %s", chapter["number"], chapter["title"])
    if args.list_only:
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    chosen = index[:args.max_assets] if args.max_assets else index
    LOG.info("Selected %d of %d assets", len(chosen), len(index))
    write_json(args.output / "index.json", {"html_source": str(args.html),
                                             "found_assets": len(index), "selected_assets": len(chosen),
                                             "assets": chosen})
    http = Http(args.delay, args.timeout, args.retries)
    statuses, errors = [], []
    for chapter in chosen:
        LOG.info("Downloading %02d %s", chapter["number"], chapter["title"])
        try:
            statuses.append(process_asset(http, args.output, chapter))
        except Exception as exc:
            LOG.error("Asset %02d stopped: %s", chapter["number"], exc)
            errors.append({"asset": chapter, "error": str(exc)})
            if isinstance(exc, PermissionError):
                LOG.error("HTTP 403/429: stopping requests; try again when access is available")
                break
        write_json(args.output / "errors.json", errors)
        write_json(args.output / "summary.json", {"found_assets": len(index),
                   "selected_assets": len(chosen), "processed_assets": len(statuses), "assets": statuses,
                   "images_downloaded": sum(x["downloaded_pages"] for x in statuses),
                   "expected_images": sum(x["expected_pages"] for x in statuses),
                   "complete_pdfs": sum(x["pdf_complete"] for x in statuses)})
    # Re-read selected statuses so interrupted runs can be resumed safely.
    completed = []
    for chapter in chosen:
        path = args.output / chapter["folder"] / "status.json"
        if path.is_file():
            completed.append(json.loads(path.read_text(encoding="utf-8")))
    master = False
    if args.master_pdf and not errors and len(chosen) == len(index):
        master = merge_master(args.output, chosen, completed, args.master_pdf)
    elif args.master_pdf and len(chosen) < len(index):
        LOG.info("Master PDF skipped: --max-assets selected only part of the input")
    write_json(args.output / "errors.json", errors)
    write_json(args.output / "summary.json", {"found_assets": len(index), "selected_assets": len(chosen),
               "processed_this_run": len(statuses), "complete_assets": sum(s.get("pdf_complete", False) for s in completed),
               "expected_images": sum(s["expected_pages"] for s in completed),
               "downloaded_images": sum(s["downloaded_pages"] for s in completed),
               "master_pdf_complete": master, "errors": errors})
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
