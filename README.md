# Genji Monogatari Downloader

Lädt die digitalisierten historischen Handschriften des Genji Monogatari (源氏物語) aus dem Digitalarchiv der Universität Tokio herunter und erstellt daraus eine vollständige lokale Sammlung.

Die finale Version verwendet eine lokal gespeicherte `genji.html`, die alle 54 Kapitel der Sammlung enthält. Dadurch entfällt die fehleranfällige Online-Erkennung früherer Versionen und der Download erfolgt reproduzierbar.

## Funktionen

- Download aller 54 Kapitel
- Nutzung der offiziellen UTokyo-Asset-UUIDs
- Speicherung der Metadaten (`manifest.json`)
- Download der hochauflösenden Manuskriptbilder
- Automatische Erstellung einer PDF pro Kapitel
- Optionale Gesamt-PDF aller Kapitel
- Wiederaufnahme unterbrochener Downloads
- Überspringen bereits vorhandener Dateien
- Fortschrittsanzeige während des Downloads

## Projektstruktur

```
genji-downloader-54/
├── genji_download.py
├── genji.html
├── test_genji_download.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Voraussetzungen

- Python 3.10 oder neuer
- Windows, Linux oder macOS
- Internetverbindung

## Installation

### Windows

```
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Linux / macOS

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Verwendung

### Download aller Kapitel

```
python download_genji_collection.py
```

### Tests ausführen

```
python test.py
```

## Ausgabe

Nach erfolgreichem Download entsteht beispielsweise folgende Struktur:

```
output/
├── chapter_01_桐壺/
│   ├── manifest.json
│   ├── page_0001.jpg
│   ├── page_0002.jpg
│   └── chapter.pdf
├── chapter_02_帚木/
│   └── ...
├── ...
└── Genji_Monogatari_Complete.pdf
```

## Abhängigkeiten

`requirements.txt`

```
requests
beautifulsoup4
Pillow
img2pdf
```

## Bekannte Einschränkungen

- Das Projekt hängt von der Verfügbarkeit des UTokyo-Digitalarchivs ab.
- Änderungen an der IIIF-API oder den Asset-URLs können Anpassungen erforderlich machen.
- Einzelne Kapitel können serverseitig zeitweise nicht erreichbar sein; vorhandene Dateien werden bei einem erneuten Lauf nicht erneut heruntergeladen.

## Entwicklung mit KI

Dieses Projekt entstand iterativ mit Unterstützung einer KI und wurde über mehrere Versionen weiterentwickelt.

### Bewährter Workflow

1. Kleine Änderungen einzeln umsetzen.
2. Neue Funktionen zunächst an einem Kapitel testen.
3. Anschließend den vollständigen Lauf über alle 54 Kapitel prüfen.
4. Bei Änderungen an der Archivstruktur zuerst `genji.html` und die IIIF-Manifeste überprüfen.

### Nützlicher Prompt für Weiterentwicklungen

> Erweitere den bestehenden `download_genji_collection.py`, ohne die bestehende Downloadlogik zu verändern. Nutze weiterhin `genji.html` als Quelle für die 54 Kapitel, achte auf Kompatibilität mit der IIIF Presentation API und erhalte die Wiederaufnahme bereits heruntergeladener Dateien.

## Datenquelle

Digital Archive der Universität Tokio (UTokyo).

Die Manuskriptbilder stammen aus den öffentlich zugänglichen Digitalisaten der Genji-Monogatari-Sammlung der Universität Tokio. Bitte beachte die jeweiligen Nutzungsbedingungen des Archivs für Weiterverwendung oder Veröffentlichung der heruntergeladenen Bilder.

## Lizenz

Dieses Repository enthält ausschließlich den Downloader und Hilfsdateien.

Die heruntergeladenen Digitalisate stammen von der Universität Tokio und unterliegen den dort angegebenen Nutzungsbedingungen.