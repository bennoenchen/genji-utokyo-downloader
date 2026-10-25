# UTokyo Digital Archive Downloader

This command-line tool archives image assets from saved search results in the University of Tokyo Digital Archive. It reads UTokyo asset records from an HTML file, downloads images from each asset's IIIF manifest, and creates a PDF for each asset when all of its pages are available. A combined PDF is created only when you explicitly pass `--master-pdf`.

## Requirements and installation

Python 3.10 or later and an internet connection to the UTokyo Digital Archive are required.

Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux/macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Prepare a collection's search-results HTML

The downloader takes a saved search-results page as input. To get the results for a collection:

1. Open the collection page in the UTokyo Digital Archive. For example, [this collection](https://da.dl.itc.u-tokyo.ac.jp/portal/en/collection/search/134).
2. On the collection page, select **See more** to open its search-results page.
3. On the search-results page, make sure the complete collection results are displayed. If the page offers pagination or a control to show more results, continue until all results are included. The downloader can only process asset records present in the saved HTML.
4. Save that search-results page from your browser as an HTML file (for example, `collection.html`). In most browsers, use **Save page as…** and choose **HTML only** or **Webpage, HTML only**. Do not save the collection landing page: save the search-results page reached through **See more**.
5. Pass the saved file to the downloader with `--html`.

The output numbering and processing order follow the asset order in the saved HTML. Asset folder names use the exact titles shown in the UTokyo catalog. Thus, you can use the same steps for a different collection; the downloader does not need a predefined collection order. The parser currently recognizes asset records with UUIDs under `/portal/assets/` and IIIF Presentation API 2 or 3 manifests containing image resources. Other UTokyo sites, content types, or file types may not be supported.

## Examples

Check the HTML and list its assets without downloading anything:

```sh
python utokyo_archive_downloader.py --html collection.html --list-only
```

Download all assets found in the HTML:

```sh
python utokyo_archive_downloader.py --html collection.html --output UTokyo_Archive
```

Download only the first two assets as a trial run:

```sh
python utokyo_archive_downloader.py --html collection.html --max-assets 2
```

Explicitly request a combined PDF:

```sh
python utokyo_archive_downloader.py --html collection.html --output UTokyo_Archive --master-pdf UTokyo_Archive/Collection.pdf
```

See all options and defaults:

```sh
python utokyo_archive_downloader.py --help
```

## Output and resuming a download

Each asset gets its own folder containing `manifest.json`, `status.json`, an `images/` directory, and a PDF if all pages are available. Catalog metadata is saved as `metadata.json` when available. The output root contains `index.json`, `summary.json`, and `errors.json`.

Running the downloader again checks the current manifest and resumes by fetching missing or damaged image pages. If an asset's manifest has changed, the downloader preserves the old images and PDF under separately named files and fetches the current image pages again. A combined PDF is created only when every asset found in the HTML is complete. It is skipped when `--max-assets` selects only part of the input.

## Genji collection

The optional `--genji` flag is specific to the 54 chapters of *The Tale of Genji*. It validates the Japanese chapter titles and applies the predefined Genji chapter order, regardless of their order in the HTML. Do not use this flag for other collections. Without `--genji`, the downloader follows the order in the saved HTML, including for Genji results.

```sh
python utokyo_archive_downloader.py --html genji.html --genji --output UTokyo_Genji_Archive --master-pdf UTokyo_Genji_Archive/Genji.pdf
```

## Limitations and terms of use

- Downloads depend on the availability and access rules of the UTokyo Digital Archive.
- Other parts of the UTokyo site may use different page formats or IIIF variants.
- Before reusing or publishing downloaded material, check the rights information and terms of use for each item.

## Development

Run the offline tests:

```sh
python -m unittest -v test.py
```
