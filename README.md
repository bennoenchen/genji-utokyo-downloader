# Genji Collection Downloader

## Funktionsumfang

- Sucht Kandidaten über den archivseitigen Suchendpunkt mit dem Filter `collection=genji`.
- Prüft gefundene Kandidaten anhand der jeweiligen Archiv-Detailseite, bevor Bilder angefordert werden.
- Liest IIIF-Manifeste und lädt die darin aufgeführten Manuskriptseiten herunter.
- Erstellt eine PDF pro Eintrag, sofern der Download vollständig ist. Unvollständige PDFs benötigen `--allow-partial-pdf`.
- Speichert Discovery-, Status-, Fehler- und Zusammenfassungsdaten und kann vorhandene Daten für die Fortsetzung wiederverwenden.
- `--full-resolution` versucht, die Bildgröße über die IIIF Image API auszuhandeln.

Dies ist kein rekursiver Link-Crawler. Die Vollständigkeit hängt dennoch davon ab, welche Einträge der Suchendpunkt tatsächlich zurückgibt. Die Verfügbarkeit und Struktur des externen Archivdienstes kann sich ändern.

## Voraussetzungen

- Python 3.10 oder neuer
- Internetzugang zum Digital Archive der Universität Tokio
- Pakete aus `requirements.txt`: `requests`, `beautifulsoup4` und `Pillow`

## Installation unter Windows / PowerShell

Öffne PowerShell im jeweiligen Repository-Ordner:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Starten

Verwende den Skriptnamen, der in deinem Repository liegt.

Version 3:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-3.py --help
.\.venv\Scripts\python.exe .\download_genji_collection-3.py --test-uuid
.\.venv\Scripts\python.exe .\download_genji_collection-3.py --discover-only
```

Version 4:

```powershell
.\.venv\Scripts\python.exe .\download_genji_collection-4.py --help
.\.venv\Scripts\python.exe .\download_genji_collection-4.py --test-uuid
.\.venv\Scripts\python.exe .\download_genji_collection-4.py --discover-only
```

Kleine Testläufe:

```powershell
# Ersetze den Skriptnamen passend zur Version:
.\.venv\Scripts\python.exe .\download_genji_collection-3.py --max-items 2
.\.venv\Scripts\python.exe .\download_genji_collection-3.py --output .\test-download --max-items 1
```

## Wichtige Optionen

| Option | Bedeutung |
|---|---|
| `--output PFAD` | Ausgabeordner; Standard: `UTokyo_Genji_Archive` |
| `--max-items N` | Höchstens N verifizierte Einträge verarbeiten; `0` bedeutet alle gefundenen Kandidaten |
| `--max-pages N` | Maximale Zahl der Suchseiten; Standard: `100` |
| `--delay SEKUNDEN` | Pause zwischen Anfragen; mindestens `0.3`, Standard: `0.5` |
| `--timeout SEKUNDEN` | HTTP-Zeitlimit; Standard: `25` |
| `--retries N` | Wiederholungsversuche; Standard: `2` |
| `--test-uuid` | Nur die im Skript hinterlegte Test-UUID verarbeiten |
| `--discover-only` | Suche und Prüfung ohne Bilddownload ausführen |
| `--no-pdf` | PDF-Erstellung ausschalten |
| `--allow-partial-pdf` | PDF trotz fehlender Seiten erzeugen; Dateiname erhält `_PARTIAL` |
| `--rebuild-pdf` | Vorhandene PDF neu erzeugen |
| `--full-resolution` | Verfügbare Bildgröße über IIIF `info.json` auszuhandeln versuchen |

Die vollständige Optionsliste und aktuelle Standardwerte stehen in `--help`.

## Ausgaben und Fehlerprüfung

Im Ausgabeordner können unter anderem `discovery.json`, `summary.json`, `errors.json`, `metadata_<UUID>.json`, IIIF-Manifeste, Bilder, `status.json` und PDFs liegen. Eine vorhandene PDF bedeutet nicht automatisch, dass alle Seiten enthalten sind. Prüfe Status- und Fehlerdateien.

Bei HTTP-Fehlern wie `403`, `429` oder Verbindungsabbrüchen zuerst mit `--discover-only` testen, die Pausen erhöhen und später erneut versuchen. Nicht in einer engen Schleife wiederholen.

## Nutzung von KI zur Weiterentwicklung

Du kannst eine KI bitten, den Code zu erklären, Tests zu ergänzen oder einen konkreten Fehler zu untersuchen. Gib dafür die vollständige Fehlermeldung, den Befehl, die Python-Version und relevante Logdateien an. Bitte die KI, Änderungen klein zu halten und zunächst Tests zu schreiben. Lass sie keine Archiv-URLs, API-Endpunkte oder Erfolgsraten erfinden: Unbestätigte Annahmen sollen ausdrücklich markiert und durch echte Antworten des Archivdienstes überprüft werden. Prüfe Änderungen mit `git diff`, bevor du sie übernimmst.
