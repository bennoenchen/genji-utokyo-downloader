# Genji Kiritsubo Downloader

Ein kleines Python-Skript, das die im UTokyo Digital Archive verlinkten IIIF-Bildseiten eines einzelnen Genji-Eintrags herunterlädt und daraus eine PDF erzeugt.

> **Status:** Experimenteller Einzelobjekt-Downloader. Der im Skript eingetragene Manifest-Endpunkt und die Zuordnung der UUID zu 桐壺 müssen gegen das aktuelle Archiv geprüft werden. Das Skript wurde in diesem Projekt nicht als vollständig erfolgreich heruntergeladen verifiziert.

## Funktionen

- Ruft ein fest eingetragenes IIIF-Manifest ab.
- Unterstützt typische Strukturen der IIIF Presentation API 2 und 3.
- Lädt erkannte Seitenbilder herunter und prüft, ob die Antworten Bilddateien sind.
- Erstellt aus den geladenen Bildern eine PDF.
- Speichert das Manifest bei unerwarteter Struktur zur Diagnose.

Die PDF enthält **Manuskriptbilder**, keine Transkription und keine OCR.

## Voraussetzungen

- Python 3.10 oder neuer empfohlen
- Internetzugang
- Die Bibliotheken `requests` und `Pillow`

## Installation unter Windows

Öffne PowerShell im Repository-Ordner und führe aus:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install requests pillow
```

Falls PowerShell die Aktivierung blockiert, kannst du das Skript auch ohne Aktivierung starten, indem du `.venv\Scripts\python.exe` verwendest.

## Start

```powershell
python download_genji_kiritsubo.py
```

## Ausgabe

Das Skript erstellt den Ordner `Genji_Kiritsubo/`. Er soll die Seitenbilder `seite_0001.jpg`, `seite_0002.jpg` usw. sowie `Genji_Kiritsubo.pdf` enthalten. Wenn das Manifest nicht gelesen oder kein Bild erkannt wird, kann auch eine `manifest.json` zur Fehlerdiagnose entstehen.

## Fehlerbehebung

- **HTTP 403/404 oder Verbindungsabbruch:** Der Archiv-Endpunkt kann geändert sein, Anfragen begrenzen oder vorübergehend nicht erreichbar sein. Nicht mit zufälligen URLs fortfahren; Manifest im Browser und im Network-Tab der Entwicklerwerkzeuge prüfen.
- **Keine Bild-URLs:** `manifest.json` ansehen und die tatsächliche IIIF-Struktur prüfen. IIIF-2- und IIIF-3-Manifeste unterscheiden sich.
- **PDF fehlt oder unvollständig:** Im Konsolenprotokoll nach Bildfehlern suchen. Erfolgreich geladene Bilder können trotzdem gespeichert worden sein.
- **Leere/unerwartete Dateien:** Die HTTP-Antwort allein genügt nicht; kontrolliere Dateigröße und ob sie sich als Bild öffnen lässt.

## Datenschutz, Rechte und verantwortungsvolle Nutzung

Das Skript sendet Anfragen an den Server des Archivs. Verwende es nur für öffentlich zugängliche Inhalte, halte die Abrufrate niedrig und beachte die aktuellen Nutzungs- und Wiederverwendungsbedingungen des Archivs: <https://www.lib.u-tokyo.ac.jp/ja/library/general/reuse>. Prüfe die Rechteangaben für den konkreten Datensatz selbst. Öffentliche Abrufbarkeit ist nicht automatisch eine allgemeine Erlaubnis für jede Nutzung.

## Nutzung von KI bei der Weiterentwicklung

KI kann beim Erklären von Fehlermeldungen, beim Prüfen von Manifest-JSON und beim Ergänzen von Tests helfen. Gib der KI bei Fehlern den vollständigen Traceback, Python-Version, Betriebssystem und ein anonymisiertes Manifest-Beispiel. Lass sie nicht raten, welche URL funktionieren müsste: Bitte sie, den verwendeten Endpunkt anhand belegbarer Daten zu prüfen und Unsicherheiten ausdrücklich zu markieren.

Beispielprompt:

> Prüfe dieses Python-Skript für den Download eines einzelnen IIIF-Manifests. Ändere nur, was nötig ist. Unterstütze IIIF Presentation API 2 und 3, sortiere Bilder in Manifestreihenfolge, behandle HTTP-Fehler mit aussagekräftigen Meldungen und schreibe Tests mit lokalen Beispiel-Manifests. Behaupte nicht, dass der UTokyo-Endpunkt funktioniert, wenn er nicht tatsächlich verifiziert wurde. Erkläre jeden geänderten Teil.

KI-generierten Code erst prüfen und mit einem einzelnen Datensatz testen, bevor große Downloads starten.

## Projektstruktur

```text
.
├── README.md
├── requirements.txt
├── .gitignore
└── download_genji_kiritsubo.py
```
