# Projektskizze: GeMTeX-Kohorten-Analyse (FHIR R4)

**Status:** Weitgehend umgesetzt — Python (`python/analyse.py` + Module) und R-Bericht (`r/bericht.R`) implementiert und getestet; Build über `Makefile` (inkl. `clean`).
**Ziel:** Ein kompaktes Python-Skript, das mit wenigen FHIR-Suchanfragen von einem FHIR-R4-Server eine Kohorte von Patienten mit mindestens einer `DocumentReference` beschreibt und die Verlinkung der FHIR-Ressourcen prüft; dazu ein R-Skript, das daraus ein PDF mit Grafiken/Tabellen erzeugt.

---

## 1. Ausgangslage und Zielsetzung

Das Projekt **GeMTeX** erlaubt Krankenhäusern, Arztbriefe/Entlassbriefe und weitere Dokumente als `DocumentReference` in einen FHIR-R4-Server zu referenzieren.

Das Skript soll in einem **ersten Testlauf** gegen eine öffentliche Demo-FHIR-Instanz laufen und:
1. testen, ob die Verlinkung der FHIR-Ressourcen `DocumentReference`, `Encounter`, `Patient`, `Diagnose` (Condition) funktioniert;
2. prüfen, ob `DocumentReference` dem MII-Dokument-Profil (lightweight) entspricht;
3. eine **Kohortenbeschreibung** aller Patienten mit mindestens einer `DocumentReference` liefern (Geschlecht, Alter);
4. Wissen über **Diagnosen** und **Fachabteilungen** der Fälle in der Kohorte liefern.

---

## 2. Festgelegte Testumgebung

- **Server (initial):** `https://hapi.fhir.org/baseR4` (öffentlicher HAPI-FHIR-R4-Demoserver).
  - *Hinweis:* Die dortigen Ressourcen sind überwiegend Test-/Beispieldaten und NICHT MII-profilkonform. Das ist für den ersten Testlauf gewollt: Der Profil-Check und der Verlinkungs-Check müssen diese Abweichungen korrekt melden.
- **Server (später, produktiv):** lokale/Landeskrankenhaus-FHIR-Server (FHIR R4), konform zu MII-Kerndatensatz.

---

## 3. Fachliche Modellierung (MII-Basis)

### 3.1 Fall = Einrichtungskontakt (Encounter)

Offiziell definiert in: `StructureDefinition-mii-pr-fall-kontakt-gesundheitseinrichtung` (Modul FALL, 2027.0.0-ballot).

Drei Kontaktebenen, unterschieden über `Encounter.type` mit dem Slice **`type:Kontaktebene`**:

| Code (System `http://fhir.de/CodeSystem/Kontaktebene`) | Bedeutung | partOf-Beziehung |
|---|---|---|
| `einrichtungskontakt` | gesamter Aufenthalt/Besuch | kein partOf |
| `abteilungskontakt` | Aufenthalt in einer Abteilung | partOf → Einrichtungskontakt |
| `versorgungsstellenkontakt` | Aufenthalt an einer Versorgungsstelle/Station | partOf → Abteilungskontakt |

**Hierarchie:** Versorgungsstellenkontakt →(partOf)→ Abteilungskontakt →(partOf)→ Einrichtungskontakt.

**Definition „Fall“ im Skript:** ausschließlich **Einrichtungskontakt**.

**Fall-Auflösung (resolve_to_einrichtungskontakt):** Für einen betroffenen Encounter:
1. Bestimme Kontaktebene aus `type:Kontaktebene`.
2. **Wenn** `type` nicht definiert **oder** kein `partOf` vorhanden → als Einrichtungskontakt behandeln.
3. **Wenn** `type = einrichtungskontakt` → Fall gefunden.
4. **Wenn** `type = abteilungskontakt` → über `partOf` 1 Stufe zum Einrichtungskontakt.
5. **Wenn** `type = versorgungsstellenkontakt` → über `partOf` 2 Stufen (2. Stufe = Einrichtungskontakt).
   - `partOf` ist 0..1; die Kette wird ggf. mehrfach verfolgt, bis `type: Kontaktebene = einrichtungskontakt` oder bis `partOf` leer ist.

### 3.2 Weitere relevante Profile (MII, 2027.0.0-ballot)

- **Patient:** `MII_PR_Person_Patient` — relevant: `gender`, `birthDate` (ggf. nur Jahr oder Jahr+Monat).
- **Diagnose:** `MII_PR_Diagnose_Condition` — relevant: `code.coding:icd10-gm` (System `http://fhir.de/CodeSystem/bfarm/icd-10-gm`), Verknüpfung über `Condition.encounter` bzw. `Encounter.diagnosis.condition`.
- **Dokument:** `MII_PR_Dokument_Dokument` (Modul Dokument) auf `DocumentReference` — relevant: `meta.profile` (muss das MII-Dokument-Profil referenzieren), `status`, `type.coding` (Slices KDL/LNC/SCT/XDS), `subject` → Patient, `content`, `context.encounter` → Fall.

### 3.3 Diagnose ↔ Fall-Verknüpfung

- **Richtung A:** `Encounter.diagnosis.condition` → `Condition` (Fall verweist auf Diagnose).
- **Richtung B:** `Condition.encounter` → `Encounter` (Diagnose verweist auf Fall).

**Wichtige Festlegung:** Laut aktuellem MII-Stand zeigt `Condition.encounter` typischerweise auf den **Abteilungskontakt** (nicht auf den Einrichtungskontakt). Da nur Einrichtungskontakte gezählt werden, muss das Skript bei der Diagnose-Verknüpfung **über `partOf` zum Einrichtungskontakt hochsteigen** (1–2 Stufen), falls der verweisende Encounter ein Abteilungs-/Versorgungsstellenkontakt ist.

### 3.4 Logik: Encounter-Auflösung / Fall-Normalisierung

- Wenn eine `DocumentReference` in `context.encounter` auf einen Encounter zeigt, mit der oben genannten Logik auf den **Einrichtungskontakt** normalisieren.
- Duplikate vermeiden (dieselbe Resource mehrfach referenziert → nur einmal einbeziehen).

---

## 4. FHIR-Abfrage-Strategie („wenige Suchanfragen“)

Grobe, zu verifizierende Routen (Implementierungsdetail: exakte SearchParameter-Namen an der Demo-Instanz prüfen):

1. **Query A – alle Dokumente inkl. Anker:** `GET /DocumentReference?_include=...subject&_include=...encounter&_count=N` (paginiert, `_getpages`-Folge).
   - Liefert alle `DocumentReference` + eingebettete `Patient` (subject) und `Encounter` (context.encounter).
2. **Query B – partOf-Ketten auflösen:** Für die in A gefundenen Encounter ggf. `GET /Encounter?_id=...` für die referenzierten parent-`partOf`-Encounter (bis Einrichtungskontakt erreicht). (Kann auch per gezieltem `_id`-Batch erfolgen.)
3. **Query C – Diagnosen zur Kohorte:**
   - Von `Encounter.diagnosis.condition` referenzierte Conditions: `GET /Condition?_id=...`.
   - Conditions, die auf Fälle der Kohorte zeigen: `GET /Condition?encounter=...#...`.
   - **Deduplizieren** über Resource-ID (keine Duplikate, auch wenn dieselbe Diagnose über beide Richtungen gefunden wird).
4. **Query D – fehlende Patienten:** Für Patienten ohne subject-Include ggf. `GET /Patient?_id=...`.

Ziel: Die Kohorte wird über **DocumentReference** betreten; Encounter, Patienten und Diagnosen werden über **Include/Referenz-Auflösung** eingesammelt — nicht über eine Voll-Scan jede Ressource.

---

## 5. Verlinkungs-Check (Broken References)

Für jede relevante Referenz prüfen: **existiert die Zieltressource auf dem Server und hat sie erwarteten ResourceType?** (ein GET pro Ziel; Auflösbarkeit = 200 + korrekter Typ).

Zu prüfende Kanten:

| Von | Nach | Bemerkung |
|---|---|---|
| `DocumentReference.subject` | `Patient` | Pflicht deutet auf Patient |
| `DocumentReference.context.encounter` | `Encounter` | 0..*, mind. einer erwartet |
| `Encounter.partOf` | `Encounter` | Hierarchie |
| `Encounter.diagnosis.condition` | `Condition` | Fall→Diagnose |
| `Condition.encounter` | `Encounter` | Diagnose→Fall |

Ergebnis je Kante: Anzahl OK / fehlend (404) / falscher Typ / nicht referenziert.

---

## 6. Profil-Check DocumentReference (lightweight)

Kein externer Validator. Je Dokument:
- `meta.profile` enthält das MII-Dokument-Profil (`https://www.medizininformatik-initiative.de/fhir/ext/modul-dokument/StructureDefinition/mii-pr-dokument-dokument`, Pfad/Version exakt aus dem IG übernehmen);
- Pflicht-/Must-Support-Elemente vorhanden: `status`, `type` (mind. ein `type.coding`), `subject`, `content` (m. `attachment`), `context.encounter`.
- Ergebnis als aggregierte Statistik (Anzahl konform / Abweichungen) + Auflistung der häufigsten fehlenden Elemente.

*Optional ausbaufähig (nicht Teil des kompakten Laufs):* volle Validierung über externen FHIR-Validator.

---

## 7. Definition der Statistiken

### 7.1 Kohortenbeschreibung (fallweise)
- **Ausgangsmenge:** alle Patienten mit mindestens einer `DocumentReference`, die zu einem gültigen Einrichtungskontakt aufgelöst werden kann.
- **Fallbezogen:** 
  - Bei mehreren `DocumentReference` pro Fall → Attribut nur **einmal** für diesen Fall zählen.
  - Bei mehreren Fällen (Einrichtungskontakten) desselben Patienten → **jeden Fall einzeln** zählen.
- **Geschlechterverteilung** (`Patient.gender`): z.B. male/female/other/unknown + „nicht angegeben“.
- **Altersverteilung:** Alter = vollendete Jahre zwischen `Patient.birthDate` (bestmöglich mit Jahr, ggf. Monat) und `Encounter.period.start`.
  - Gruppen (halboffen): `[0,18) [18,30) [30,40) [40,50) [50,60) [60,70) [70,80) [80+)` sowie **„unbekannt“** (kein verwertbares birthDate oder kein period.start).
  - *Hinweis:* Datumsangaben können Form `value="1997-09-26T05:15:21+02:00"` haben → robustes Parsen (ISO-8601) erforderlich; Zeitanteil/Zeitzone ignorieren.

### 7.2 Fachabteilungen (`Encounter.serviceType`)
- Nur Einrichtungskontakte (fallweise, gleiche Dedup-Logik wie 7.1).
- Nutze `serviceType.coding` mit Fachabteilungsschlüssel (System `http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel`; ggf. auch erweiterter Schlüssel).
- Zählung: **Top 10 Gruppen** nach Anzahl absteigend; **Gruppe 11** „übrige“ (alle weiteren, zusammengefasst); **Gruppe 12** „keine Angabe“ (Encounter ohne serviceType).

### 7.3 Verteilung: Anzahl Fälle pro Patient (Histogramm)
- Für jeden Patienten: Anzahl Einrichtungskontakte in der Kohorte. → Histogramm (1, 2, 3, … Fälle).

### 7.4 Verteilung: Anzahl DocumentReferences pro Fall (Histogramm)
- Für jeden Einrichtungskontakt: Anzahl zugeordneter `DocumentReference` (nach Dedup auf Fall-Ebene). → Histogramm.

### 7.5 Liegezeit (`Encounter.period.end − period.start`)
- Nur Einrichtungskontakte mit vollständigem `period.start` **und** `period.end`.
- Dauer in Tagen (auf ganze Tage) → **10 Gruppen**: „1 Tag“, „2 Tage“, …, „9 Tage“, **„10+ Tage“** (Gruppe 10 enthält Aufenthalte über 10 Tage).
- Fälle ohne vollständiges Datumspaar → **separater Zähler** „Liegezeit nicht bestimmbar“ (z.B. noch nicht entlassen).

### 7.6 Diagnosen: erste 3 Stellen des ICD-10-GM-Codes
- Zusammenhang beachten: Fall→Diagnose (`Encounter.diagnosis.condition`) UND Diagnose→Fall (`Condition.encounter`, über partOf zum Einrichtungskontakt hochsteigen).
- Je dem Fall zugeordneter Diagnose: ICD-10-GM-Code (`code.coding:icd10-gm`) → **erste 3 Zeichen** (Kapitel/Block, z.B. `I21`), zählen.
- Deduplizierung wie in Abschnitt 4 (keine Duplikate bei der Ressourcen-Ermittlung).
- Ergebnisse: Häufigkeit je 3-Stellen-Präfix (mind. Top-N ausweisen), Anzahl Diagnosen ohne ICD-10-GM-Code.

### 7.7 Dokumentart (`DocumentReference.type`)
- Getrennte Zählungen je Codingsystem:
  - **KDL:** Code(s) mit System `http://dvmd.de/fhir/CodeSystem/kdl`;
  - **XDS:** Code(s) mit System `http://ihe-d.de/CodeSystems/IHEXDStypeCode`.
- Zähler „type nicht definiert“: Dokumente **ohne** jedes `type.coding`.
- (LOINC/SNOMED-Slices ggf. separat ausweisen, aber KDL und XDS sind gefordert.)

---

## 8. Ausgabe

### 8.1 Python-Skript
Produziert **beides**:
- (a) **menschenlesbaren Text** (Konsole und/oder `.txt`-Datei) mit allen Kennzahlen aus Abschnitt 7 sowie Ergebnis der Checks (Abschnitt 5, 6);
- (b) **strukturierte JSON-Datei** (z.B. `ergebnis.json`) mit allen Kennzahlen, die das R-Skript einliest.
- Konfigurierbar über Kommandozeile/Config: `base_url`, Paginierungs-Größe, optionale Ausgabepfade, optional Zeitraumfilter.

*(Geplante, noch nicht umgesetzte Schnittstelle — Details der JSON-Struktur werden bei der Umsetzung fixiert.)*

### 8.2 R-Skript (`r/bericht.R`)

**Aufgabe:** Liest die JSON-Datei (`ergebnis.json`) und erzeugt daraus ein **PDF** (`bericht.pdf`) mit Tabellen, Balken- und Histogramm-Grafiken.

**Aufruf:**
```
Rscript r/bericht.R [pfad/zu/ergebnis.json] [pfad/zum/bericht.pdf]
```

**Grafik-Stil („Journal-Stil“, z. B. JAMIA):**
- Gedeckte graue Balken (`grey45`), schlanke **schwarze Achsen**, **keine Gitterlinien**.
- Alle Beschriftungen **innerhalb der Grafiken sind Englisch**.
- Jeder Balken trägt seinen **Zahlenwert** direkt über dem Balken.
- Gemeinsames Theme über `theme_journal()` (black axes, `panel.grid = element_blank()`, `panel.background = element_blank()`).

**Verbindliche Grafik-Regeln:**
1. **Alle Verteilungen: Balken stehen SENKRECHT** (Kategorie/Intervall auf der x-Achse, Häufigkeit auf der y-Achse). `bar_plot(..., vertical = TRUE)` ist die Voreinstellung; keine horizontalen Balken (`coord_flip`).
2. **Altersverteilung = Histogramm, kein Balkendiagramm:** Die (bereits geclusterten) Altersklassen werden als Rechtecke über ihrer Altersspanne auf einer **kontinuierlichen x-Achse in Jahren** gezeichnet (`age_hist()` via `geom_rect`). Die Balkenbreite spiegelt die Altersspanne; Klassen sortieren nach aufsteigender Altersgrenze. Offene Klasse `80+` wird bei der Anzeige oben gekappt; `unbekannt`/`unknown` (nicht auf der Achse platzierbar) wird als Caption unten ausgewiesen.
3. **Liegezeit wird nach Tagen sortiert, nicht nach Häufigkeit** (`order = "natural"`, aufsteigend 1 Tag, 2 Tage, …, 10+ Tage), vertikale Balken, Kategorie ohne Zahl („nicht bestimmbar“) ans Ende.
4. **Übrige Kategorien (Geschlecht, Fachabteilungen, ICD-Präfixe, KDL/XDS):** Vertikale Balken; Sortierung nach Häufigkeit absteigend (`order = "count"`).

**Darstellung je Kennzahl (Abschnitt 7):**

| Kennzahl | Darstellung | Sortierung |
|---|---|---|
| Übersicht (Dok/Patient/Fall) | Tabelle | — |
| Geschlechter | vertikale Balken | Häufigkeit |
| Alter | **Histogramm** (kontinuierliche Jahre-Achse) | aufsteigende Altersgrenze |
| Fachabteilungen (Top 10 + Übrige + keine Angabe) | vertikale Balken | Häufigkeit |
| Fälle pro Patient | Histogramm (vertikale Balken) | ganzzahlige x-Achse |
| DocumentReferences pro Fall | Histogramm (vertikale Balken) | ganzzahlige x-Achse |
| Liegezeit (10 Gruppen + „nicht bestimmbar“) | vertikale Balken | **nach Tagen** (natural) |
| ICD-10 (erste 3 Stellen) | vertikale Balken | Häufigkeit |
| Dokumentart KDL / XDS | vertikale Balken (Multi-Panel) | Häufigkeit |
| Verknüpfungs-Check, Profil-Check | Tabellen | — |

- Multi-Panel-Layouts (z. B. KDL/XDS, Fälle/Docs) über `gridExtra::grid.arrange`; gemeinsamer Titel oben.
- Einzeldiagramme über `plot_one()` mit Titelbalken; Seiten-Titel über `new_page()`.
- PDF-Ausgabe über `cairo_pdf()` (breite/hohe Seiten 11×8.5 in, `onefile = TRUE`).

**Benötigte R-Pakete:** `jsonlite`, `ggplot2`, `gridExtra` sowie das Basis-Paket `grid`.
Skript zum Installieren: `r/install_libs.sh` (installiert fehlende Pakete von `https://cloud.r-project.org`; `--force` erzwingt Neuinstallation). Voraussetzung: R mit **Cairo**-Unterstützung für `cairo_pdf()`.

---

## 9. Projektstruktur

Als **GitHub-Projekt** organisiert (inkl. `Makefile`, `README.md`, `.gitignore`). Die
Dokumentation liegt in `doc/`:

```
GeMTeX-Kohorte/
├── Makefile                # Build-/Clean-Targets: ergebnis.json, bericht.pdf, clean
├── README.md               # Projekt-Übersicht, DIZ-orientiert (Python-Erzeugung + Einreichung)
├── .gitignore              # schließt generierte Ausgaben (ausgabe/…, __pycache__/) aus
├── doc/
│   ├── PROJEKTSKIZZE.md        # dieses Dokument (gesamte Projektskizze)
│   ├── R-Bericht.md            # Doku zur (optionalen, zentralen) R-Bericht-Erzeugung
│   └── anleitung_ueberarbeitet.md  # überarbeitete fachliche Anleitung (siehe Abschnitt 10)
├── python/
│   ├── analyse.py          # Hauptskript (FHIR-Abfragen, Checks, Statistiken, Ausgabe)   [umgesetzt]
│   ├── fhir_client.py      # schlanker FHIR-Client (Paginierung, Referenz-Auflösung)     [umgesetzt]
│   ├── konzepte.py         # Einrichtungskontakt-Auflösung, Profil-Check                 [umgesetzt]
│   ├── statistik.py        # Berechnung der Kennzahlen (7.x)                            [umgesetzt]
│   └── requirements.txt    # Python-Abhängigkeiten (requests)
├── r/
│   ├── bericht.R           # liest ergebnis.json, erzeugt PDF (OPTIONAL, zentral)        [umgesetzt]
│   └── install_libs.sh     # installiert benötigte R-Pakete (jsonlite, ggplot2, gridExtra)
└── ausgabe/                # ergebnis.json, bericht.txt, bericht.pdf  (generiert, gitignored)
    └── .gitkeep            # hält das Ausgabe-Verzeichnis im Repo
```

**Verteilung (DIZ ↔ zentral):**
- **Jedes DIZ** trägt nur seine FHIR-Server-URL ein, führt **Python** aus
  (`python/analyse.py`) und erhält `ausgabe/ergebnis.json` (+ `bericht.txt`).
  Das JSON wird an GeMTeX zentral übermittelt.
- Der **R-Bericht** (`bericht.pdf`) ist **optional** und wird **zentral** aus dem
  übermittelten JSON erzeugt (siehe [`doc/R-Bericht.md`](R-Bericht.md)).

**Build-Ablauf (Makefile):**
- `make` / `make all` → erzeugt `ausgabe/ergebnis.json` (+ `bericht.txt`) via `python/analyse.py`, dann `ausgabe/bericht.pdf` via `r/bericht.R` (letzteres nur zentral).
- `make json` → nur die Python-Ausgabe (DIZ-Fall); `make pdf` → nur der R-Bericht (zentral).
- `make BASE_URL=…` → anderer FHIR-Endpunkt.
- `make clean` → löscht alle selbst erzeugten Dateien (`ergebnis.json`, `bericht.txt`, `bericht.pdf`, `python/__pycache__/`).

---

## 10. Überarbeitete fachliche Anleitung (Kurzfassung der Kernregeln)

1. **Fall = Einrichtungskontakt** (Encounter). Ebenen via `type:Kontaktebene` (`einrichtungskontakt`/`abteilungskontakt`/`versorgungsstellenkontakt`) und `partOf`-Hierarchie.
2. `type` fehlt oder kein `partOf` → als Einrichtungskontakt behandeln. Sonst über `partOf` (1–2 Stufen) zum Einrichtungskontakt aufsteigen.
3. Verweist ein Attribut auf einen Encounter, erst prüfen, ob es der Einrichtungskontakt ist; wenn nicht, über `partOf` aufsteigen.
4. Diagnosen: Richtung Fall→Diagnose (`Encounter.diagnosis`) und Diagnose→Fall (`Condition.encounter`) berücksichtigen; beim Hochlaufen zur Diagnose ggf. zum Einrichtungskontakt aufsteigen; **keine Duplikate**.
5. Alter stets **bezgl. `Encounter.period.start`**; `birthDate` kann unvollständig sein (nur Jahr/Monat); Datumsformate robust (ISO-8601 mit Zeitzone) parsen.
6. Kohorten-Statistiken **fallweise** (Dedup je Fall, aber jeder Fall einzeln).
7. Liegezeit nur mit vollständigem Datumspaar; Auffangzähler für Rest.
8. Fachabteilungen über `Encounter.serviceType` (Top 10 + „übrige“ + „keine Angabe“).
9. ICD-Statistik über die ersten 3 Stellen des ICD-10-GM-Codes.
10. Dokumentart-Statistik je KDL-System und XDS-System getrennt + „type nicht definiert“.

---

## 11. Offene Punkte / zu verifizieren (bei Umsetzung)

- Exakte `SearchParameter`-Namen für Include/Chaining (`subject`, `encounter`, `diagnosis`, `part-of`) an der Demo-Instanz bestätigen.
- Kanonische URL/Version des MII-Dokument-Proffis für den `meta.profile`-Abgleich exakt aus dem IG übernehmen (bei Umsetzung aktuellen Pfad prüfen).
- Entscheiden, ob die ICD-Statistik je **Fall** (dedupliziert) oder je **Diagnoseinstanz** gezählt wird (Voreinstellung: je dem Fall zugeordneter Diagnoseinstanz, Ressourcen dedupliziert).
- Paginierungs-Größe und ggf. Zeitraumfilter als Parameter.
- HAPI-Demo-Daten → Ergebnisse werden erwartungsgemäß stark von Proffi-Verstößen geprägt sein (Plausibilität des Tests prüfen).
