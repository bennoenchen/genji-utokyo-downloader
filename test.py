"""Offline tests; run with: py -m unittest -v test_genji_download.py"""
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import genji_download as g


SAMPLE_HTML = '''<html><body>
<article about="/portal/assets/c1ea8e6b-9403-4394-8619-96aad0ec6329">
<a rel="bookmark" href="/portal/assets/c1ea8e6b-9403-4394-8619-96aad0ec6329">桐壺</a></article>
<article about="/portal/assets/4c7f22cf-9fe1-5405-1f3a-c53b39e3a45e">
<a rel="bookmark" href="/portal/assets/4c7f22cf-9fe1-5405-1f3a-c53b39e3a45e">帚木</a></article>
<a href="/portal/collection/asia">other collection</a>
</body></html>'''


class FakeResponse:
    def __init__(self, image_bytes):
        self.image_bytes = image_bytes

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def iter_content(self, chunk_size):
        yield self.image_bytes


class FakeHttp:
    def __init__(self):
        img = Image.new("RGB", (32, 32), "red")
        image = io.BytesIO()
        img.save(image, format="JPEG")
        self.image = image.getvalue()
        self.image_requests = 0

    def json(self, url):
        if url.endswith("/manifest"):
            return {"@id": url, "sequences": [{"canvases": [
                {"images": [{"resource": {"@id": "https://example.org/1.jpg"}}]},
                {"images": [{"resource": {"@id": "https://example.org/2.jpg"}}]},
            ]}]}
        return {"title": "桐壺"}

    def get(self, url, stream=False):
        self.image_requests += 1
        return FakeResponse(self.image)


class GenjiTests(unittest.TestCase):
    def test_html_parsing_and_sorting(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "genji.html"
            path.write_text(SAMPLE_HTML, encoding="utf-8")
            index = g.parse_html(path)
            self.assertEqual([x["number"] for x in index], [1, 2])
            self.assertEqual(index[0]["folder"], "01_桐壺")
            self.assertEqual(index[1]["uuid"], "4c7f22cf-9fe1-5405-1f3a-c53b39e3a45e")

    def test_iiif_v3(self):
        manifest = {"items": [{"items": [{"items": [{"motivation": "painting", "body":
            {"id": "https://example.org/image.jpg"}}]}]}]}
        self.assertEqual(g.page_images(manifest), ["https://example.org/image.jpg"])

    def test_resume_and_pdf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter = {"number": 1, "title": "桐壺", "uuid": g.UUID.search(SAMPLE_HTML).group(), "folder": "01_桐壺"}
            http = FakeHttp()
            first = g.process_chapter(http, root, chapter)
            self.assertEqual(first["expected_pages"], 2)
            self.assertTrue(first["pdf_complete"])
            self.assertEqual(http.image_requests, 2)
            second = g.process_chapter(http, root, chapter)
            self.assertTrue(second["pdf_complete"])
            self.assertEqual(http.image_requests, 2, "Second run must not request images again")
            self.assertEqual(g.pdf_pages(root / "01_桐壺" / "01_桐壺.pdf"), 2)

    def test_master_requires_all_54(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertFalse(g.merge_master(root, [{"number": 1}], []))

    def test_master_54_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index, statuses = [], []
            for number, title in enumerate(g.CHAPTERS, 1):
                folder = "{:02d}_{}".format(number, g.re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title))
                chapter = {"number": number, "title": title, "uuid": "test-{:02d}".format(number), "folder": folder}
                images = root / folder / "images"
                images.mkdir(parents=True)
                image = images / "page_0001.jpg"
                Image.new("RGB", (16, 16), "white").save(image)
                g.chapter_pdf([image], root / folder / (folder + ".pdf"))
                index.append(chapter)
                statuses.append({**chapter, "expected_pages": 1, "downloaded_pages": 1, "pdf_complete": True})
            self.assertTrue(g.merge_master(root, index, statuses))
            self.assertEqual(g.pdf_pages(root / "Genji_Monogatari_Gesamt.pdf"), 54)


if __name__ == "__main__":
    unittest.main()
