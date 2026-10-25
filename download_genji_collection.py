#!/usr/bin/env python3
"""Download UTokyo's 54 Genji manuscripts from a locally saved search HTML.

Usage: py genji_download.py --html genji.html --max-chapters 2
       py genji_download.py --html genji.html
"""
import argparse
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
CHAPTERS = (
    "桐壺", "帚木", "空蝉", "夕顔", "若紫", "末摘花", "紅葉加(紅葉賀)", "花宴", "葵", "龍眼木(賢木 , 榊)",
    "花散里", "須磨", "赤石(明石)", "水衝石(澪標)", "蓬生", "関屋", "檜合", "松風", "薄雲", "槿",
    "乙女", "玉鬘", "初音", "胡蝶", "蛍", "床夏(常夏)", "篝火", "野分", "行幸", "蘭(藤袴)",
    "真木柱", "梅枝", "藤裏葉", "若菜 上", "若菜 下", "柏木", "横笛", "鈴虫", "夕霧", "御法",
    "幻", "匂宮", "紅梅", "竹川", "橋姫", "椎本", "総角", "早蕨", "寄生", "東屋",
    "浮舟", "蜻蛉", "手習", "夢浮橋",
)
ORDINAL = {name: index for index, name in enumerate(CHAPTERS, 1)}
LOG = logging.getLogger("genji")


def write_json(path, obj):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_html(path):
    """Only read real asset records, never site navigation or related links."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")
    entries, seen_uuids, seen_titles = [], set(), set()
    for article in soup.select('article[about^="/portal/assets/"]'):
        asset_id = article.get("about", "").rsplit("/", 1)[-1].lower()
        link = article.select_one('a[rel="bookmark"]')
        title = link.get_text(" ", strip=True) if link else ""
        if not UUID.fullmatch(asset_id) or title not in ORDINAL:
            raise ValueError(f"Unrecognized Genji record in HTML: {asset_id} {title!r}")
        if asset_id in seen_uuids or title in seen_titles:
            raise ValueError(f"Duplicate UUID or chapter title in HTML: {title}")
        seen_uuids.add(asset_id)
        seen_titles.add(title)
        number = ORDINAL[title]
        # Every title here is the catalog's exact Japanese spelling.
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
        entries.append({"number": number, "title": title, "uuid": asset_id,
                        "folder": f"{number:02d}_{safe}"})
    if not entries:
        raise ValueError("No manuscript records in HTML. Save the search result page as HTML.")
    return sorted(entries, key=lambda entry: entry["number"])


class Http:
    def __init__(self, delay, timeout, retries):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "UTokyo-Genji-personal-archiver/1.0"
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


def process_chapter(http, root, chapter):
    directory = root / chapter["folder"]
    directory.mkdir(parents=True, exist_ok=True)
    pictures = directory / "images"
    pictures.mkdir(exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest_url = f"{HOST}/portal/repo/iiif/{chapter['uuid']}/manifest"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = http.json(manifest_url)
        identifier = manifest.get("id") or manifest.get("@id") or ""
        if identifier and chapter["uuid"] not in identifier:
            raise ValueError("Manifest ID does not match expected UUID")
        write_json(manifest_path, manifest)
    urls = page_images(manifest)
    import_old_images(root, chapter, pictures, len(urls))
    status = {**chapter, "manifest_url": manifest_url, "expected_pages": len(urls),
              "downloaded_pages": 0, "missing_pages": [], "pdf_complete": False}
    files = []
    for number, url in enumerate(urls, 1):
        path = find_image(pictures, number)
        if path is None:
            try:
                path = get_image(http, url, pictures, number)
            except PermissionError:
                raise
            except Exception as exc:
                LOG.error("%02d %s: image %d failed: %s", chapter["number"], chapter["title"], number, exc)
        if path:
            files.append(path)
        else:
            status["missing_pages"].append(number)
        status["downloaded_pages"] = len(files)
        write_json(directory / "status.json", status)
    if len(files) == len(urls):
        target = directory / f"{chapter['folder']}.pdf"
        if pdf_pages(target) != len(urls):
            chapter_pdf(files, target)
        status["pdf_complete"] = pdf_pages(target) == len(urls)
    write_json(directory / "status.json", status)
    # Metadata are useful but can be unavailable even when images are public.
    meta_path = directory / "metadata.json"
    if not meta_path.exists():
        try:
            metadata = http.json(f"{HOST}/portal/en/assets/{chapter['uuid']}?_format=json")
            write_json(meta_path, metadata)
        except Exception as exc:
            LOG.warning("Metadata for %s unavailable: %s", chapter["title"], exc)
    return status


def merge_master(root, index, statuses):
    if len(index) != 54 or sorted(c["number"] for c in index) != list(range(1, 55)):
        LOG.info("No master PDF: the HTML does not contain all 54 chapters")
        return False
    if len(statuses) != 54 or any(not s.get("pdf_complete") for s in statuses):
        LOG.info("No master PDF: at least one chapter or page is missing")
        return False
    for chapter, status in zip(index, statuses):
        if (status.get("uuid") != chapter["uuid"] or status.get("number") != chapter["number"]
                or status.get("expected_pages", 0) < 1
                or status.get("downloaded_pages") != status["expected_pages"]):
            LOG.error("No master PDF: chapter identity/page count mismatch for %s", chapter["title"])
            return False
        folder = root / chapter["folder"] / "images"
        if any(find_image(folder, i) is None for i in range(1, status["expected_pages"] + 1)):
            LOG.error("No master PDF: missing or corrupt image in %s", chapter["title"])
            return False
    parts = [root / chapter["folder"] / f"{chapter['folder']}.pdf" for chapter in index]
    count = sum(s["expected_pages"] for s in statuses)
    if any(pdf_pages(path) != status["expected_pages"] for path, status in zip(parts, statuses)):
        LOG.error("No master PDF: a chapter PDF failed its page-count check")
        return False
    target = root / "Genji_Monogatari_Gesamt.pdf"
    if pdf_pages(target) == count:
        LOG.info("Master PDF already complete: %s", target)
        return True
    size = sum(path.stat().st_size for path in parts)
    if shutil.disk_usage(root).free < size * 1.2:
        LOG.error("Not enough free disk space for master PDF (about %.1f GB needed)", size * 1.2 / 1e9)
        return False
    temporary = root / "Genji_Monogatari_Gesamt.pdf.part"
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
        return True
    finally:
        writer.close()
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, default=Path("genji.html"))
    parser.add_argument("--output", type=Path, default=Path("UTokyo_Genji_Archive"))
    parser.add_argument("--max-chapters", type=int, default=0, help="0 = all records from saved HTML")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--no-master", action="store_true")
    parser.add_argument("--list-only", action="store_true", help="Check the HTML and show all chapters, no downloads")
    args = parser.parse_args()
    if args.delay < 0.3 or args.max_chapters < 0:
        parser.error("Use --delay >= 0.3 and --max-chapters >= 0")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not args.html.is_file():
        parser.error(f"HTML file not found: {args.html}")
    index = parse_html(args.html)
    LOG.info("Saved HTML contains %d distinct Genji chapters", len(index))
    for chapter in index:
        LOG.info("%02d %s", chapter["number"], chapter["title"])
    if args.list_only:
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "index.json", {"html_source": str(args.html),
                                             "found_chapters": len(index), "chapters": index})
    chosen = index[:args.max_chapters] if args.max_chapters else index
    http = Http(args.delay, args.timeout, 2)
    statuses, errors = [], []
    for chapter in chosen:
        LOG.info("Downloading %02d %s", chapter["number"], chapter["title"])
        try:
            statuses.append(process_chapter(http, args.output, chapter))
        except Exception as exc:
            LOG.error("Chapter %02d stopped: %s", chapter["number"], exc)
            errors.append({"chapter": chapter, "error": str(exc)})
            if isinstance(exc, PermissionError):
                LOG.error("HTTP 403/429: stopping requests; try again when access is available")
                break
        write_json(args.output / "errors.json", errors)
        write_json(args.output / "summary.json", {"found_chapters": len(index),
                   "processed_chapters": len(statuses), "chapters": statuses,
                   "images_downloaded": sum(x["downloaded_pages"] for x in statuses),
                   "expected_images": sum(x["expected_pages"] for x in statuses),
                   "complete_pdfs": sum(x["pdf_complete"] for x in statuses)})
    # Re-read existing statuses: a short test run can still recognize an already
    # completed 54-chapter archive without downloading anything twice.
    completed = []
    for chapter in index:
        path = args.output / chapter["folder"] / "status.json"
        if path.is_file():
            completed.append(json.loads(path.read_text(encoding="utf-8")))
    master = False
    if not args.no_master and not errors:
        master = merge_master(args.output, index, completed)
    write_json(args.output / "errors.json", errors)
    write_json(args.output / "summary.json", {"found_chapters": len(index),
               "processed_this_run": len(statuses), "complete_chapters": sum(s.get("pdf_complete", False) for s in completed),
               "expected_images": sum(s["expected_pages"] for s in completed),
               "downloaded_images": sum(s["downloaded_pages"] for s in completed),
               "master_pdf_complete": master, "errors": errors})
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
