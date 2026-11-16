# GeMTeX Kohorte — Überarbeitete fachliche Anleitung (fachlich revidiert)

Diese Datei ist die **fachlich überarbeitete** Version der Aufgabenstellung. Kernänderungen gegenüber der ursprünglichen Anleitung sind markiert und am Ende zusammengefasst. Die technischen Details wurden anhand der offiziellen MII-Spezifikationen (2027.0.0-ballot, Basis- und Dokumentmodul) sowie des `http://fhir.de/CodeSystem/Kontaktebene` verifiziert.

---

## 1. Ziel

Ein kompaktes **Python-Skript**, das von einem FHIR-R4-Server mit wenigen Suchanfragen:

1. die **Verlinkung** der Ressourcen `DocumentReference`, `Encounter`, `Patient`, `Diagnose` (Condition) testet;
2. prüft, ob `DocumentReference` dem **MII-Dokument-Profil** (lightweight) entspricht;
3. eine **Kohortenbeschreibung** der Patienten mit mindestens einer `DocumentReference` liefert;
4. **Diagnosen** und **Fachabteilungen** der Fälle in der Kohorte auswertet.

Ein **R-Skript** erzeugt daraus ein **PDF** mit Tabellen, Balkendiagrammen und Histogrammen.

**Testlauf-Server:** `https://hapi.fhir.org/baseR4` *(korrigiert: ursprünglich war fälschlich fairdomhub.org genannt — dieses System ist kein FHIR-Server).*

---

## 2. Ressourcen-Definition (revidiert)

> **Revidiert gegenüber Original:** Die Ebenen werden nicht nur über `Encounter.type` im Allgemeinen, sondern über das **Slice `type:Kontaktebene`** mit dem CodeSystem `http://fhir.de/CodeSystem/Kontaktebene` definiert (Codes: `einrichtungskontakt`, `abteilungskontakt`, `versorgungsstellenkontakt`).

### 2.1 Fall = Einrichtungskontakt (Encounter)

Offiziell: `MII PR Fall Kontakt mit einer Gesundheitseinrichtung` (Modul FALL, `StructureDefinition-mii-pr-fall-kontakt-gesundheitseinrichtung`).

Drei Kontaktebenen über `Encounter.type:Kontaktebene`:

| Ebene | Code | partOf |
|---|---|---|
| Einrichtungskontakt | `einrichtungskontakt` | kein partOf (oberste Ebene) |
| Abteilungskontakt | `abteilungskontakt` | partOf → Einrichtungskontakt |
| Versorgungsstellenkontakt | `versorgungsstellenkontakt` | partOf → Abteilungskontakt |

**Hierarchie:** Versorgungsstellenkontakt →(partOf)→ Abteilungskontakt →(partOf)→ Einrichtungskontakt.

**„Fall“ = Einrichtungskontakt.**

### 2.2 Fall-Auflösung (resolve_to_einrichtungskontakt)

> **Revidiert:** Das Aufsteigen wird präzisiert; „kein partOf ⇒ Einrichtungskontakt“ wird nur bei fehlendem `type:Kontaktebene-Coding` verwendet.

Für einen betroffenen Encounter:

1. Kontaktebene aus `type:Kontaktebene` (System `http://fhir.de/CodeSystem/Kontaktebene`) bestimmen.
2. **Falls** `type:Kontaktebene` nicht definiert **oder** kein `partOf` vorhanden → als Einrichtungskontakt behandeln.
3. **Falls** Coding = `einrichtungskontakt` → Fall gefunden.
4. **Falls** Coding = `abteilungskontakt` → über `partOf` eine Stufe zum Einrichtungskontakt.
5. **Falls** Coding = `versorgungsstellenkontakt` → über `partOf` zwei Stufen zum Einrichtungskontakt.
6. `partOf` ist 0..1; die Kette wird ggf. mehrfach verfolgt, bis `type:Kontaktebene = einrichtungskontakt` oder `partOf` leer ist.

Verweist ein Attribut (z.B. `DocumentReference.context.encounter`, `Condition.encounter`) auf einen Encounter → erst prüfen, ob es der Einrichtungskontakt ist; wenn nicht, über `partOf` aufsteigen.

### 2.3 MII-Profile (2027.0.0-ballot)

- **Patient:** `MII PR Person Patient` — `gender`, `birthDate`.
- **Diagnose:** `MII PR Diagnose Condition` — `code.coding:icd10-gm` (System `http://fhir.de/CodeSystem/bfarm/icd-10-gm`), Verknüpfung über `Condition.encounter` bzw. `Encounter.diagnosis.condition`.
- **Dokument:** `MII PR Dokument Dokument` auf `DocumentReference` (Modul Dokument) — `meta.profile`, `status`, `type.coding` (Slices KDL/LNC/SCT/XDS), `subject`, `content`, `context.encounter`.

> **Revidiert:** Das MII-Dokument-Profil (Modul **Dokument**, nicht Basis) ist die Grundlage für den Profil-Check.

### 2.4 Diagnose ↔ Fall-Verknüpfung

- **Richtung A (Fall→Diagnose):** `Encounter.diagnosis.condition` → `Condition`.
- **Richtung B (Diagnose→Fall):** `Condition.encounter` → `Encounter`.

> **Revidiert/Klarstellung:** Laut aktuellem MII-Stand verweist `Condition.encounter` typischerweise auf den **Abteilungskontakt**. Da nur Einrichtungskontakte gezählt werden, muss das Skript beim Hochlaufen zur Diagnose über `partOf` zum **Einrichtungskontakt** aufsteigen (1–2 Stufen). Diagnoseressourcen werden dedupliziert.

---

## 3. FHIR-Abfrage-Strategie („wenige Suchanfragen“)

1. `GET /DocumentReference` (paginiert) mit `_include` für `subject` (Patient) und `context.encounter` (Encounter). → Kohorte.
2. `partOf`-Ketten der gefundenen Encounter gezielt auflösen (bis Einrichtungskontakt).
3. Diagnosen: von `Encounter.diagnosis.condition` referenzierte Conditions (`Condition?_id=…`) UND Conditions, die auf Fälle der Kohorte zeigen (`Condition?encounter=…`). **Deduplizieren.**
4. Fehlende Patienten ggf. `Patient?_id=…`.

---

## 4. Checks

### 4.1 Verlinkungs-Check (Broken References)
Auflösbarkeit + korrekter ResourceType je Kante:
- `DocumentReference.subject` → `Patient`
- `DocumentReference.context.encounter` → `Encounter`
- `Encounter.partOf` → `Encounter`
- `Encounter.diagnosis.condition` → `Condition`
- `Condition.encounter` → `Encounter`

### 4.2 Profil-Check DocumentReference (lightweight, ohne Validator)
- `meta.profile` referenziert das MII-Dokument-Profil;
- Must-Support-Elemente vorhanden: `status`, `type` (mind. ein `type.coding`), `subject`, `content` (mit `attachment`), `context.encounter`.

> **Revidiert:** „Konformität“ wird als Lightweight-Check (meta.profile + Must-Support) umgesetzt; eine volle Validierung erfordert einen externen Validator und ist nicht Teil des kompakten Skripts.

---

## 5. Statistiken

### 5.1 Kohortenbeschreibung (fallweise)
- **Fallbezogen:** mehrere `DocumentReference` pro Fall → Attribut 1× pro Fall; mehrere Fälle pro Patient → jeder Fall einzeln.
- **Geschlecht:** `Patient.gender`.
- **Alter:** vollendete Jahre zwischen `birthDate` (bestmöglich mit Jahr/Monat) und `Encounter.period.start`.
  - Gruppen (halboffen): `[0,18) [18,30) [30,40) [40,50) [50,60) [60,70) [70,80) [80+)` + „unbekannt“.
  - Robustes ISO-8601-Parsing (Zeitzone ignorieren).

### 5.2 Fachabteilungen (`Encounter.serviceType`)
- `serviceType.coding` Fachabteilungsschlüssel (System `http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel`, ggf. erweitert).
- Top 10 nach Anzahl, Gruppe 11 „übrige“, Gruppe 12 „keine Angabe“.

### 5.3 Anzahl Fälle pro Patient (Histogramm)

### 5.4 Anzahl DocumentReferences pro Fall (Histogramm)

### 5.5 Liegezeit (`period.end − period.start`)
- Nur vollständiges Datumspaar; Dauer in Tagen.
- 10 Gruppen: 1…9 Tage, Gruppe 10 = „10+ Tage“.
- Unvollständig → separater Zähler „Liegezeit nicht bestimmbar“.

### 5.6 Diagnosen: erste 3 Stellen des ICD-10-GM-Codes
- Beide Verknüpfungsrichtungen (5.4 / 2.4) beachten; Diagnose-Ressourcen deduplizieren.
- Zählen je dem Fall zugeordneter Diagnoseinstanz.

### 5.7 Dokumentart (`DocumentReference.type`)
- Getrennt nach KDL-System (`http://dvmd.de/fhir/CodeSystem/kdl`) und XDS-System (`http://ihe-d.de/CodeSystems/IHEXDStypeCode`).
- Zähler „type nicht definiert“ (kein `type.coding`).

---

## 6. Ausgabe

- **Python:** lesbarer Text (Konsole/Datei) **und** strukturierte JSON-Datei für R.
- **R:** liest JSON → PDF mit Tabellen/Balkendiagrammen/Histogrammen (ggplot2, dplyr, jsonlite, knitr).

---

## 7. Revisions-Zusammenfassung (Deltas zum Original)

1. **Testserver korrigiert:** `hapi.fhir.org/baseR4` statt `fairdomhub.org` (kein FHIR-Server).
2. **Kontaktebenen konkretisiert:** `type:Kontaktebene` mit CodeSystem `http://fhir.de/CodeSystem/Kontaktebene`; Codes `einrichtungskontakt`/`abteilungskontakt`/`versorgungsstellenkontakt`.
3. **„Kein partOf ⇒ Einrichtungskontakt“** nur bei fehlendem `type:Kontaktebene`-Coding angewandt; sonst gezieltes 1–2-stufiges Aufsteigen über `partOf`.
4. **Diagnose-Verknüpfung präzisiert:** `Condition.encounter` zeigt i.d.R. auf Abteilungskontakt → beim Fall-Hochlaufen über `partOf` zum Einrichtungskontakt aufsteigen; beide Richtungen (`Encounter.diagnosis` / `Condition.encounter`) berücksichtigen; Dokumente/Diagnosen deduplizieren.
5. **Profil-Check als lightweight** (meta.profile + Must-Support), kein externer Validator.
6. **Age-Gruppen halboffen** `[a,b)` + „unbekannt“; Alter stets bezgl. `Encounter.period.start`.
7. **Liegezeit** nur mit vollständigem Datumspaar + Auffangzähler.
8. **Dokumenttyp-Statistik** nach KDL- und XDS-System getrennt + „type nicht definiert“.
