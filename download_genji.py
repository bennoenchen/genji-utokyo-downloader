
import io
import json
import re
from pathlib import Path

import requests
from PIL import Image

MANIFEST_URL = (
    "https://da.dl.itc.u-tokyo.ac.jp/portal/repo/iiif/"
    "4c7f22cf-9fe1-5405-1f3a-c53b39e3a45e/manifest"
)

OUT = Path("genji_hahakigi")
OUT.mkdir(exist_ok=True)

session = requests.Session()
session.headers["User-Agent"] = "GenjiResearch/1.0"

response = session.get(MANIFEST_URL, timeout=30)
response.raise_for_status()
manifest = response.json()

# IIIF Presentation API 2 und 3 unterstützen
if "sequences" in manifest:
    canvases = manifest["sequences"][0]["canvases"]
    pages = []

    for canvas in canvases:
        images = canvas.get("images", [])
        if not images:
            continue

        resource = images[0]["resource"]
        service = resource.get("service", {})
        service_id = service.get("@id") or service.get("id")

        if service_id:
            image_url = service_id.rstrip("/") + "/full/full/0/default.jpg"
        else:
            image_url = resource.get("@id") or resource.get("id")

        pages.append(image_url)

else:
    canvases = manifest.get("items", [])
    pages = []

    for canvas in canvases:
        for annotation_page in canvas.get("items", []):
            for annotation in annotation_page.get("items", []):
                body = annotation.get("body", {})
                if isinstance(body, list):
                    body = body[0] if body else {}

                service_list = body.get("service", [])
                if isinstance(service_list, dict):
                    service_list = [service_list]

                if service_list:
                    service = service_list[0]
                    sid = service.get("id") or service.get("@id")
                    pages.append(sid.rstrip("/") + "/full/full/0/default.jpg")
                else:
                    image_id = body.get("id")
                    if image_id:
                        pages.append(image_id)

print(f"Gefundene Seiten: {len(pages)}")

images = []

for i, url in enumerate(pages, 1):
    print(f"Lade Seite {i}/{len(pages)}")

    r = session.get(url, timeout=60)
    r.raise_for_status()

    path = OUT / f"seite_{i:03}.jpg"
    path.write_bytes(r.content)

    with Image.open(io.BytesIO(r.content)) as image:
        images.append(image.convert("RGB").copy())

if not images:
    raise RuntimeError(
        "Keine Bilder gefunden. "
        "Die IIIF-Struktur muss geprüft werden."
    )

pdf_path = OUT / "Genji_Hahakigi.pdf"
images[0].save(
    pdf_path,
    "PDF",
    save_all=True,
    append_images=images[1:],
    resolution=150,
)

print(f"Fertig: {pdf_path.resolve()}")
print(f"Einzelbilder: {OUT.resolve()}")
