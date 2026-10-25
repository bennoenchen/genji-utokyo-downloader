# Genji Collection Downloader
- `--collection-preview` liest Asset-Links, die direkt auf der Genji-Landingpage aufgeführt sind.
- Ohne diese Option wird der Suchendpunkt mit `collection=genji` verwendet.
- Gefundene UUIDs werden anhand ihrer Archiv-Detailseite geprüft, bevor Bilder abgerufen werden.
- Die Vorschau ist **kein vollständiger Katalog**: Sie enthält nur die Einträge, die die Landingpage verlinkt.

## Voraussetzungen

- Python 3.10 oder neuer
- Internetzugang zum Digital Archive der Universität Tokio
- Pakete aus `requirements.txt`: `requests`, `beautifulsoup4` und `Pillow`

## Installation unter Windows / PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Starten

Optionen anzeigen:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-5.py --help
```

Nur die Sammlungs-Vorschau erkennen und verifizieren, ohne Bilder herunterzuladen:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-5.py --collection-preview --discover-only
```

Suchmodus ohne Bilddownload prüfen:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-5.py --discover-only
```

Mit der im Skript hinterlegten Test-UUID testen:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-5.py --test-uuid
```

Höchstens zwei gefundene Einträge verarbeiten:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-5.py --max-items 2
```

## Wichtige Optionen

| Option | Bedeutung |
|---|---|
| `--collection-preview` | Direkt auf der Genji-Landingpage verlinkte Einträge verwenden; unvollständig |
| `--test-uuid` | Nur die im Skript hinterlegte Test-UUID verwenden |
| `--discover-only` | Kandidaten suchen und prüfen, ohne Bilder herunterzuladen |
| `--output PFAD` | Ausgabeordner; Standard: `UTokyo_Genji_Archive` |
| `--max-items N` | Höchstens N verifizierte Einträge verarbeiten |
| `--max-pages N` | Maximale Suchseitenanzahl; Standard: `100` |
| `--delay SEKUNDEN` | Pause zwischen Anfragen; mindestens `0.3`, Standard: `0.5` |
| `--timeout SEKUNDEN` | HTTP-Zeitlimit; Standard: `25` |
| `--retries N` | Wiederholungsversuche; Standard: `2` |
| `--no-pdf` | PDF-Erstellung ausschalten |
| `--allow-partial-pdf` | PDF auch bei fehlenden Seiten erzeugen |
| `--rebuild-pdf` | Bestehende PDFs neu erzeugen |
| `--full-resolution` | Versucht, die verfügbare Bildgröße über IIIF `info.json` auszuhandeln |

Nutze `--help` für die vollständige Liste und die Standardwerte.

## Ausgaben und Fehlerprüfung

Standardmäßig schreibt das Programm nach `UTokyo_Genji_Archive`. Dazu gehören Discovery-, Status-, Fehler- und Zusammenfassungsdateien, Metadaten, IIIF-Manifeste, Bilder und gegebenenfalls PDFs. Prüfe `discovery.json`, `summary.json`, `errors.json` und die Statusdateien. Eine PDF kann unvollständig sein, wenn Seiten nicht geladen wurden.

Die Vorschau kann nicht garantieren, dass alle Kapitel enthalten sind. Bei `403`, `429` oder Verbindungsabbrüchen die Anfragen reduzieren, `--discover-only` verwenden und später erneut versuchen.

## Nutzung von KI zur Weiterentwicklung

Eine KI kann beim Erklären des Codes, beim Schreiben von Tests und bei der Fehlersuche helfen. Teile konkrete Logs, den exakten Startbefehl und die Python-Version. Bitte die KI, nicht bestätigte Endpunkte oder Archivfunktionen nicht zu erfinden, Änderungen klein zu halten und Tests mitzuliefern. Kontrolliere den Patch mit `git diff` und teste zunächst mit `--discover-only` und `--max-items 1`, bevor du einen größeren Download startest.
