# UTokyo Digital Archive Downloader

Dieses Kommandozeilenwerkzeug archiviert Bildmaterial aus gespeicherten Suchergebnissen des Digitalarchivs der Universität Tokio. Es liest UTokyo-Asset-Einträge aus einer HTML-Datei, lädt die Bilder aus den jeweiligen IIIF-Manifests und erzeugt für vollständige Bildsätze einzelne PDFs. Eine Gesamt-PDF wird ausschließlich mit `--master-pdf` erstellt.

## Voraussetzungen und Installation

Python 3.10 oder neuer sowie Netzwerkzugriff zum UTokyo Digital Archive.

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

## Eingabe vorbereiten

Suche im UTokyo Digital Archive nach den gewünschten Objekten und speichere die Suchergebnisseite im Browser als HTML-Datei. Übergib sie mit `--html`. Die aktuelle Implementierung erkennt Asset-Einträge mit UUID unter `/portal/assets/` und IIIF Presentation API 2- oder 3-Manifeste mit Bildressourcen. Das deckt nicht automatisch alle UTokyo-Websites, Inhalte oder Dateitypen ab.

## Beispiele

HTML prüfen und Assets anzeigen, ohne etwas herunterzuladen:

```sh
python utokyo_archive_downloader.py --html suche.html --list-only
```

Alle gefundenen Assets herunterladen:

```sh
python utokyo_archive_downloader.py --html suche.html --output UTokyo_Archive
```

Erst zwei Assets als Probelauf laden:

```sh
python utokyo_archive_downloader.py --html suche.html --max-assets 2
```

Gesamt-PDF ausdrücklich anfordern:

```sh
python utokyo_archive_downloader.py --html suche.html --output UTokyo_Archive --master-pdf UTokyo_Archive/Sammlung.pdf
```

Alle Optionen und Standardwerte:

```sh
python utokyo_archive_downloader.py --help
```

## Ausgabe und Wiederaufnahme

Die Ausgabe enthält für jedes Asset einen Ordner mit `manifest.json`, `status.json`, `images/` und (sofern alle Seiten vorhanden sind) einer PDF. Katalogmetadaten werden nach Möglichkeit als `metadata.json` gespeichert. Im Hauptordner liegen `index.json`, `summary.json` und `errors.json`.

Ein erneuter Lauf prüft das aktuelle Manifest und setzt fehlende oder beschädigte Bildseiten fort. Erkennt das Programm ein geändertes Manifest, bewahrt es alte Bilder und PDFs in separat benannten Dateien auf und lädt die neuen Bildseiten erneut. Die Gesamt-PDF wird nur erstellt, wenn alle im HTML gefundenen Assets vollständig sind. Bei `--max-assets` wird sie übersprungen.

## Genji-Beispiel

Die mitgelieferte `genji.html` enthält 54 Kapitel des Genji Monogatari. Optional kann `--genji` verwendet werden, um Kapitelnamen zu validieren und die bekannte Kapitelreihenfolge anzuwenden:

```sh
python utokyo_archive_downloader.py --html genji.html --genji --output UTokyo_Genji_Archive --master-pdf UTokyo_Genji_Archive/Genji.pdf
```

## Grenzen und Nutzungsbedingungen

- Der Download hängt von der Verfügbarkeit und den Zugriffsregeln des UTokyo Digital Archive ab.
- Andere UTokyo-Bereiche können abweichende Seitenformate oder IIIF-Varianten nutzen.
- Beachte vor Weiterverwendung oder Veröffentlichung die Rechteangaben und Nutzungsbedingungen des jeweiligen Objekts.

## Entwicklung

Offline-Tests ausführen:

```sh
python -m unittest -v test.py
```
