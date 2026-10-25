# Genji Collection Downloader

- Standard ist `--source collection`: Es werden direkt auf der Genji-Landingpage verlinkte Einträge verarbeitet. Das ist nur eine Vorschau, kein vollständiger Katalog.
- `--source api` versucht die breitere Suche am Archiv-Suchendpunkt.
- `--collection-html PFAD` liest eine lokale HTML-Datei statt die Sammlungsseite live abzurufen.
- Eine erfolgreich geladene Live-Sammlungsseite wird im Ausgabeordner als `collection_genji.html` gespeichert. Falls ein späterer Live-Abruf scheitert, wird dieser Cache verwendet, sofern vorhanden.
- Ein vorhandener Eintragsordner mit derselben UUID wird bevorzugt weiterverwendet, damit bereits gespeicherte Bilder nicht wegen eines geänderten oder fehlenden Titels verloren gehen.

## Voraussetzungen

- Python 3.10 oder neuer
- Internetzugang für Live-Abrufe; bei einer passenden lokalen HTML-Datei ist dieser für die Erkennung nicht zwingend erforderlich
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
.\.venv\Scripts\python.exe .\download_genji_collection-6.py --help
```

Standardmodus nur zur Erkennung und Prüfung verwenden:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-6.py --source collection --discover-only
```

Eine lokal gespeicherte HTML-Datei verwenden:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-6.py --collection-html .\genji-collection.html --discover-only
```

Die HTML-Datei muss die Asset-Links der Genji-Sammlungsseite enthalten. Eine beliebige Suchergebnisseite ist nicht automatisch geeignet.

Die breitere Suche ausdrücklich aktivieren:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-6.py --source api --discover-only
```

Mit der eingebauten Test-UUID testen:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-6.py --test-uuid
```

Höchstens zwei Einträge verarbeiten:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-6.py --max-items 2
```

## Wichtige Optionen

| Option | Bedeutung |
|---|---|
| `--source collection` | Standard: direkt verlinkte Einträge der Genji-Landingpage |
| `--source api` | Versucht den breiteren Suchmodus; kann durch Serverbeschränkungen scheitern |
| `--collection-html PFAD` | Lokale HTML-Datei verwenden; nicht mit `--source api` kombinieren |
| `--collection-preview` | Veralteter Alias für den Collection-Modus |
| `--test-uuid` | Nur die im Skript hinterlegte Test-UUID verwenden |
| `--discover-only` | Einträge suchen und prüfen, ohne Bilder herunterzuladen |
| `--output PFAD` | Ausgabeordner; Standard: `UTokyo_Genji_Archive` |
| `--max-items N` | Höchstens N Einträge verarbeiten |
| `--max-pages N` | Maximale Suchseitenzahl im API-Modus; Standard: `100` |
| `--delay SEKUNDEN` | Pause zwischen Anfragen; mindestens `0.3`, Standard: `0.5` |
| `--timeout SEKUNDEN` | HTTP-Zeitlimit; Standard: `25` |
| `--retries N` | Wiederholungsversuche; Standard: `2` |
| `--no-pdf` | PDF-Erstellung ausschalten |
| `--allow-partial-pdf` | PDF trotz fehlender Seiten erzeugen |
| `--rebuild-pdf` | Bestehende PDFs neu erzeugen |
| `--full-resolution` | Versucht, verfügbare Bildgröße über IIIF `info.json` auszuhandeln |

Die vollständige Optionsliste steht in `--help`.

## Ausgaben und Fehlerprüfung

Standardmäßig liegen die Ergebnisse in `UTokyo_Genji_Archive`. Dort können `collection_genji.html`, `discovery.json`, `summary.json`, `errors.json`, Metadaten, IIIF-Manifeste, Bilder, Statusdateien und PDFs entstehen. Prüfe die Status- und Fehlerdateien, bevor du PDFs als vollständig behandelst.

Der lokale HTML-Cache hilft bei vorübergehenden Problemen, ersetzt aber keine vollständige Katalogsuche. Bei `403`, `429` oder Verbindungsabbrüchen zuerst den Erkennungsmodus verwenden, die Anfragen verlangsamen und später erneut versuchen.

## Nutzung von KI zur Weiterentwicklung

Gib einer KI die genaue Fehlermeldung, den Startbefehl, die Python-Version und relevante Statusdateien. Bitte sie, zuerst die Ursache zu erklären und dann einen kleinen, testbaren Patch vorzuschlagen. API-Endpunkte, UUID-Titel-Zuordnungen und erfolgreiche Downloads dürfen nicht geraten werden. Teste Änderungen zunächst mit einer gespeicherten HTML-Datei oder `--discover-only`, prüfe den Code mit `git diff` und lade erst danach einzelne Einträge herunter.
