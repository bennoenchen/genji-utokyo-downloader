# UTokyo Genji Collection Downloader (Prototype)

Ein experimenteller Python-Prototyp, der die Genji-Sammlungsseite im UTokyo Digital Archive durchsucht, UUIDs sammelt, Metadaten und IIIF-Manifeste ausprobiert, Bildseiten lädt und nach Möglichkeit PDFs erstellt.

> **Wichtige Einschränkung:** Dies ist ausdrücklich ein **Prototyp, kein zuverlässiger Vollsammlungs-Downloader**. Die aktuelle Link-Erkennung kann die Genji-Sammlung verlassen und andere Sammlungen oder allgemeine Archivseiten ansteuern. Das wurde im Laufprotokoll beobachtet. Bitte nicht unbeaufsichtigt auf die ganze Sammlung loslassen, bevor die Erkennung gezielt repariert und getestet wurde.

## Funktionen des vorhandenen Prototyps

- Startet bei `https://da.dl.itc.u-tokyo.ac.jp/portal/en/collection/genji`.
- Sammelt UUIDs aus erkannten Links.
- Ruft JSON-Metadaten und mögliche IIIF-Manifeste ab.
- Unterstützt übliche IIIF-Presentation-2- und -3-Strukturen.
- Lädt Bilder herunter und erstellt optional PDFs.
- Schreibt `discovery.json`, `summary.json`, Metadaten und Manifestkopien zur Diagnose.
- Wartet zwischen Anfragen und überspringt bereits vorhandene Bilddateien.

Die Erkennung ist heuristisch und kann unvollständig sein. Sie kann Einträge übersehen oder irrelevante UUIDs aufnehmen.

## Voraussetzungen

- Python 3.10 oder neuer empfohlen
- Internetzugang
- Python-Pakete `requests`, `Pillow` und `beautifulsoup4`

## Installation unter Windows

Öffne PowerShell im Repository-Ordner:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Ohne Aktivierung kann `.venv\Scripts\python.exe` verwendet werden.

## Aufruf

Kleiner Testlauf (der Prototyp kann dennoch zusätzliche Suchseiten besuchen):

```powershell
python download_all_genji.py --max-items 1 --max-pages 3 --delay 1.0
```

Nur Bilder, keine PDFs:

```powershell
python download_all_genji.py --max-items 3 --no-pdf --delay 1.0
```

Hilfe zu allen vorhandenen Optionen:

```powershell
python download_all_genji.py --help
```

Optionen:

- `--max-items N`: bearbeitet höchstens N gefundene UUIDs.
- `--max-pages N`: begrenzt die Zahl besuchter Suchseiten (Standard: 100).
- `--delay SEKUNDEN`: Pause zwischen Anfragen (Standard: 0.35 Sekunden).
- `--no-pdf`: Bilder laden, aber keine PDFs erstellen.
- `--retry-failed`: ist zwar als CLI-Option definiert, wird im aktuellen Programmablauf aber nicht ausgewertet und hat daher derzeit keine Wirkung. Vor einer Veröffentlichung entfernen oder korrekt implementieren.

## Ausgabe

Der Standard-Ausgabeordner heißt `UTokyo_Genji_Archive/`. Darin können unter anderem entstehen:

- `discovery.json`: gefundene UUIDs und Links
- `summary.json`: Status pro bearbeitetem Eintrag
- `metadata_<UUID>.json`: Rohmetadaten
- pro Eintrag ein Ordner mit `manifest.json`, `manifest_url.txt`, `images/` und optionaler PDF
- `*.failed.txt`: Fehlerhinweise zu fehlgeschlagenen Bildern

## Bekannte Probleme aus dem Testlauf

Im protokollierten Lauf besuchte das Programm URLs wie `/portal/en/collection`, `/portal/collection/asia` und `/portal/collection/agawa`, also Seiten außerhalb der Genji-Sammlung. Außerdem traten `403 Forbidden` und `RemoteDisconnected` auf. Solche Meldungen sind Server-/Zugriffsantworten; sie beweisen nicht allein, dass die lokale Internetverbindung defekt ist.

Die Ursache liegt vor allem in der generischen Regel, die Links mit Wörtern wie `collection`, `assets`, `page` oder JSON-Endungen in die Warteschlange legt. Vor einer Vollsammlung muss das ersetzt werden durch eine exakt begrenzte Erkennung von Genji-Paginierungsseiten und den offiziell referenzierten Datensatz-Links. Nur die Ausgangs-URL auf `/collection/genji` zu setzen, reicht nicht.

## Empfohlene sichere Weiterentwicklung

1. Im Browser die Genji-Sammlungsseite öffnen.
2. In den Entwicklerwerkzeugen unter **Network** prüfen, welche Requests beim Seitenwechsel bzw. beim Laden weiterer Ergebnisse ausgelöst werden.
3. Das echte Paginierungs-/Suchschema und den echten IIIF-Manifest-Link eines einzelnen Eintrags ermitteln.
4. Eine Allowlist zulässiger Pfade definieren. Keine beliebige `collection`- oder `assets`-URL automatisch als nächste Crawl-Seite behandeln.
5. Mit einem einzigen Eintrag testen und prüfen, ob Titel, UUID, Manifest, Anzahl Bilder und Reihenfolge stimmen.
6. Erst danach schrittweise auf mehr Einträge ausweiten.

## Nutzung von KI

KI eignet sich, um den Code zu erklären, HTML/JSON-Beispiele zu analysieren und Regressionstests zu entwerfen. Sie sollte nicht dazu verwendet werden, Endpunkte oder Archivstrukturen zu erfinden. Stelle der KI diesen Kontext und die relevanten Dateien/Antworten bereit, und verlange, dass sie unbestätigte Annahmen klar kennzeichnet.

Beispielprompt zur Korrektur:

> Repariere diesen Downloader so, dass er ausschließlich Datensätze findet, die tatsächlich zur UTokyo-Genji-Sammlung gehören. Lies zuerst den vorhandenen Code und diese Laufprotokolle. Erfinde keine API-Endpunkte. Entwirf eine Discovery-Funktion mit expliziter Allowlist und dokumentierter Paginierung; wenn das reale Schema nicht belegt ist, baue einen Diagnosemodus statt eines geratenen Crawlers. Ergänze Tests mit gespeicherten HTML-/JSON-Fixtures, einen Dry-Run-Modus, Wiederholungen mit Backoff und eine übersichtliche Fehlerzusammenfassung. Zeige alle Änderungen und erkläre, wie ich sie lokal prüfen kann.

KI-Ausgaben nicht ungeprüft übernehmen. Vor einem Commit: `--max-items 1`, kurze Laufgrenzen, keine unnötige parallele Last und Prüfen von `discovery.json`.

## Archivbedingungen

Beachte die aktuellen Nutzungsbedingungen und Wiederverwendungsangaben des UTokyo-Archivs: <https://www.lib.u-tokyo.ac.jp/ja/library/general/reuse>. Prüfe die Lizenz und Metadaten jedes Datensatzes. Öffentliche Sichtbarkeit bedeutet nicht automatisch, dass jede Weiterverwendung erlaubt ist.

## Projektstruktur

```text
.
├── README.md
├── requirements.txt
├── .gitignore
└── download_all_genji.py
```
