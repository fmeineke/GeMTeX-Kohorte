# R-Bericht (`bericht.pdf`) — Erzeugung & Dokumentation

Der R-Bericht ist **optional** und wird **zentral** (bei GeMTeX) erzeugt — nicht
zwingend an den einzelnen DIZ. Die DIZ liefern lediglich die strukturierte
`ergebnis.json` (siehe [`README.md`](../README.md)).

Dieses Dokument beschreibt, wie der PDF-Bericht aus der `ergebnis.json` erzeugt
wird, welche R-Pakete nötig sind, und wie die Grafiken aufgebaut sind.

---

## Übersicht

| Schritt | Ort | Ausgabe |
|---|---|---|
| Analyse (FHIR-Abfrage, Statistik) | **jedes DIZ** (`python/analyse.py`) | `ausgabe/ergebnis.json`, `ausgabe/bericht.txt` |
| **PDF-Bericht** | **zentral** (`r/bericht.R`) | `ausgabe/bericht.pdf` |

---

## Aufruf

```bash
Rscript r/bericht.R [pfad/zu/ergebnis.json] [pfad/zum/bericht.pdf]
```

Standardwerte (bei fehlenden Argumenten):

- `ergebnis.json` → `../ausgabe/ergebnis.json`
- `bericht.pdf` → `../ausgabe/bericht.pdf`

> Die Pfade sind relativ zum Skript-Verzeichnis (`r/`); der Aufruf erfolgt
> üblicherweise aus `r/` heraus.

Beispiel:

```bash
cd r
Rscript bericht.R ../ausgabe/ergebnis.json ../ausgabe/bericht.pdf
```

---

## Benötigte R-Pakete

- `jsonlite` — Einlesen von `ergebnis.json`
- `ggplot2` — Balkendiagramme, Histogramme
- `gridExtra` — Multi-Panel-Layouts, Tabellen
- `grid` — Basispaket von R (kein Installieren nötig)

Installation:

```bash
./r/install_libs.sh            # nur fehlende Pakete
./r/install_libs.sh --force    # Neuinstallation erzwingen
```

**Systemvoraussetzung:** R muss mit **Cairo**-Unterstützung gebaut sein
(`cairo_pdf()`), z. B. `r-base` + `libcairo2-dev` unter Debian/Ubuntu.

---

## PDF-Layout

- PDF-Erzeugung über `cairo_pdf()`.
- Seitenformat **11 × 8.5 Zoll** (`onefile = TRUE`).
- Seiten-Titel über `new_page()`; Einzeldiagramme über `plot_one()`;
  Multi-Panel-Layouts über `gridExtra::grid.arrange`.

### Seitenaufbau

| Inhalt | Darstellung |
|---|---|
| Übersicht (Dokumente / Patienten / Fälle) | Tabelle |
| Geschlechterverteilung | vertikale Balken |
| Altersverteilung | **Histogramm** (kontinuierliche Jahre-Achse) |
| Fachabteilungen (Top 10 + Übrige + keine Angabe) | vertikale Balken |
| Fälle pro Patient / Dokumente pro Fall | Histogramme (Multi-Panel) |
| Liegezeit | vertikale Balken, **nach Tagen** sortiert |
| ICD-10 (erste 3 Stellen) | vertikale Balken |
| DocumentReference.type (KDL / XDS) | vertikale Balken (Multi-Panel) |
| Verknüpfungs- und Profil-Check | Tabellen |

---

## Grafik-Stil („Journal-Stil", z. B. JAMIA)

- Gedeckte **graue Balken** (`grey45`), schlanke **schwarze Achsen**, **keine Gitterlinien**.
- Alle Beschriftungen **innerhalb der Grafiken auf Englisch**.
- Jeder Balken trägt seinen **Zahlenwert** direkt über dem Balken.
- Gemeinsames Theme über `theme_journal()` (schwarze Achsen,
  `panel.grid = element_blank()`, `panel.background = element_blank()`).

### Verbindliche Grafik-Regeln

1. **Alle Verteilungen: Balken stehen SENKRECHT** (Kategorie/Intervall auf der
   x-Achse, Häufigkeit auf der y-Achse). `bar_plot(..., vertical = TRUE)` ist die
   Voreinstellung; keine horizontalen Balken (`coord_flip`).
2. **Altersverteilung = Histogramm, kein Balkendiagramm:** Die bereits
   geclusterten Altersklassen werden als Rechtecke über ihrer Altersspanne auf
   einer **kontinuierlichen x-Achse in Jahren** gezeichnet (`age_hist()` via
   `geom_rect`). Die Balkenbreite spiegelt die Altersspanne; Klassen sortieren
   nach aufsteigender Altersgrenze. Offene Klasse `80+` wird bei der Anzeige oben
   gekappt; `unbekannt`/`unknown` (nicht auf der Achse platzierbar) wird als
   Caption unten ausgewiesen.
3. **Liegezeit wird nach Tagen sortiert, nicht nach Häufigkeit**
   (`order = "natural"`, aufsteigend 1 Tag, 2 Tage, …, 10+ Tage), vertikale
   Balken; Kategorie ohne Zahl („nicht bestimmbar") ans Ende.
4. **Übrige Kategorien** (Geschlecht, Fachabteilungen, ICD-Präfixe, KDL/XDS):
   vertikale Balken, Sortierung nach Häufigkeit absteigend (`order = "count"`).

---

## Implementierungs-Hinweise

- `bar_plot(df, titel, vertical, order, …)` — Balkendiagramm im Journal-Stil.
- `hist_plot(nv, titel, xlab, …)` — Histogramm bei ganzzahligen Verteilungen.
- `age_hist(nv, titel, …)` — Histogramm der Altersverteilung (`geom_rect`).
- `arrange_plots(grobs, titel, ncol)` — zwei/mehr Diagramme auf einer Seite.
- `plot_one(grob, titel)` — ein Diagramm auf einer Seite.
- `age_order(cats)` — natürliche (numerische) Reihenfolge von Kategorien.

---

Weitere fachliche Details zu den Kennzahlen finden sich in der
[`PROJEKTSKIZZE.md`](PROJEKTSKIZZE.md).
