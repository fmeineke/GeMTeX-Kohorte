# GeMTeX-Kohorte — Anleitung für DIZ

Dieses Repository dient als **Integrationstest** und **Kohorten-Analyse für das GeMTeX-Projekt**.
Dabei werden Anfragen an den **FHIR-R4**-Server (MII-Kerndatensatz, Module Dokument/Fall) der DIZ gestellt.

Die Analyse bündelt die Patienten mit mindestens einer `DocumentReference`
(Arztbrief/Entlassbrief) an einem FHIR-Server zu einer **Kohorte** und liefert
beschreibende Kennzahlen zu Geschlecht, Alter, Fachabteilungen, Liegezeit,
Diagnosen (ICD-10) und Dokumentarten. 

**Für die DIZ** (Betreiber der FHIR-Server, die die Daten zu GeMTeX beisteuern)
ist der Ablauf bewusst schlank gehalten:

> **Nur die Python-Ausführung läuft lokal.** Du trägst deine FHIR-Server-URL ein,
> lässt das Python-Skript laufen und übermittelst die erzeugte `ergebnis.json`
> an GeMTeX zentral. Die PDF-/R-Berichtserzeugung ist **optional** und wird
> üblicherweise **zentral** durchgeführt.

---

## Inhalt

- [Ablauf in 3 Schritten](#ablauf-in-3-schritten)
- [Projektstruktur](#projektstruktur)
- [Voraussetzungen](#voraussetzungen)
- [Schnellstart für DIZ](#schnellstart-für-diz)
- [Ausgabe](#ausgabe)
- [Einreichung an GeMTeX](#einreichung-an-gemtex)
- [Optional: PDF-R-Bericht (zentral)](#optional-pdf-r-bericht-zentral)
- [Aufräumen](#aufräumen)
- [Dokumentation](#dokumentation)
- [Lizenz](#lizenz)

---

## Ablauf in 3 Schritten

```
┌────────────────────── DIZ (lokal) ──────────────────────┐
│  1.  FHIR-Server-URL eintragen                            │
│  2.  python3 python/analyse.py  https://…/fhir/R4        │
│      → erzeugt  ausgabe/ergebnis.json  (+ bericht.txt)    │
│  3.  ausgabe/ergebnis.json an GeMTeX zentral senden      │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────── GeMTeX zentral (optional) ───────────────┐
│  Rscript r/bericht.R  …  →  ausgabe/bericht.pdf           │
└──────────────────────────────────────────────────────────┘
```

---

## Projektstruktur

```
GeMTeX-Kohorte/
├── Makefile                    # Build-/Clean-Targets
├── README.md                   # dieses Dokument (DIZ-orientiert)
├── doc/                        # Dokumentation
│   ├── PROJEKTSKIZZE.md        # gesamte fachliche Projektskizze
│   ├── R-Bericht.md            # Doku zur (optionalen, zentralen) R-Bericht-Erzeugung
│   └── anleitung_ueberarbeitet.md  # überarbeitete fachliche Anleitung (Kernregeln)
├── python/
│   ├── analyse.py              # Hauptskript (FHIR-Abfragen, Statistik, Ausgabe)
│   ├── fhir_client.py          # schlanker FHIR-Client (Paginierung, Referenz-Auflösung)
│   ├── konzepte.py             # Einrichtungskontakt-Auflösung, Profil-Check
│   ├── statistik.py            # Berechnung der Kennzahlen
│   └── requirements.txt        # Python-Abhängigkeiten (requests)
├── r/                          # OPTIONAL (zentral)
│   ├── bericht.R               # erzeugt den PDF-Bericht aus ergebnis.json
│   └── install_libs.sh         # installiert benötigte R-Pakete
└── ausgabe/                    # generierte Dateien (gitignored)
    └── .gitkeep
```

---

## Voraussetzungen (DIZ)

- **Python 3.10+**
- das Python-Paket [`requests`](https://pypi.org/project/requests/)

R wird **nicht** benötigt, wenn du nur die `ergebnis.json` erzeugen möchtest —
das R-Paket ist nur für die (optionale) zentrale PDF-Erzeugung nötig.

---

## Schnellstart für DIZ

```bash
# 1. Abhängigkeiten installieren
python3 -m pip install -r python/requirements.txt

# 2. Analyse gegen deinen FHIR-Server starten
python3 python/analyse.py "https://dein-fhir-server/fhir/R4"
```

oder über das Makefile (JSON-/Text-Ausgabe, DIZ-Fall):

```bash
make json BASE_URL="https://dein-fhir-server/fhir/R4"
```

**Alle regulären Kennzahlen** des Standardlaufs werden dabei berechnet:

- Geschlechterverteilung und Altersverteilung (fallweise)
- Fachabteilungen (Top 10 + Übrige + keine Angabe)
- Fälle pro Patient, DocumentReferences pro Fall
- Liegezeit (10 Gruppen + „nicht bestimmbar")
- ICD-10 (erste 3 Stellen)
- Dokumentart (KDL / XDS)
- Verknüpfungs-Check (Broken-Reference-Check) und Profil-Check (lightweight)

---

## Ausgabe

Nach der Python-Ausführung liegen in `ausgabe/`:

| Datei | Inhalt | Verwendung |
|---|---|---|
| `ausgabe/ergebnis.json` | strukturierte Kennzahlen | **an GeMTeX zentral senden**; Grundlage für den R-Bericht |
| `ausgabe/bericht.txt` | menschenlesbare Zusammenfassung | lokale Kontrolle / Dokumentation |

---

## Einreichung an GeMTeX

1. Führe den Schnellstart aus (siehe oben).
2. Prüfe kurz die `ausgabe/bericht.txt` auf Plausibilität.
3. Sende `ausgabe/ergebnis.json` an GeMTeX zentral (Übermittlungsweg bitte mit
   GeMTeX abstimmen).
4. Die lokale Kopie in `ausgabe/` kannst du anschließend über `make clean`
   entfernen.

---

## Optional: PDF-R-Bericht (zentral)

Der R-Bericht erzeugt aus der `ergebnis.json` ein **PDF** mit Tabellen und
Grafiken im Journal-Stil (vertikale Balken, Alters-Histogramm, Liegezeit nach
Tagen etc.):

```bash
make pdf                       # zentral
# oder manuell:
Rscript r/bericht.R ausgabe/ergebnis.json ausgabe/bericht.pdf
```

Voraussetzungen, Layout und verbindliche Grafik-Regeln sind separat dokumentiert:

➡️ **[`doc/R-Bericht.md`](doc/R-Bericht.md)**

---

## Aufräumen

```bash
make clean
```

Entfernt alle selbst erzeugten Dateien:

- `ausgabe/ergebnis.json`
- `ausgabe/bericht.txt`
- `ausgabe/bericht.pdf`
- `python/__pycache__/` (Python-Bytecode)

---

## Dokumentation

| Thema | Datei |
|---|---|
| Projekt-Übersicht (DIZ) | [`README.md`](README.md) |
| Fachliche Projektskizze (Konzepte, Statistik-Definitionen, Grafikregeln) | [`doc/PROJEKTSKIZZE.md`](doc/PROJEKTSKIZZE.md) |
| R-Bericht-Erzeugung (optional, zentral) | [`doc/R-Bericht.md`](doc/R-Bericht.md) |
| Überarbeitete fachliche Anleitung (Kernregeln) | [`doc/anleitung_ueberarbeitet.md`](doc/anleitung_ueberarbeitet.md) |

---

## Lizenz

[MIT](LICENSE) — siehe Datei [`LICENSE`](LICENSE).
