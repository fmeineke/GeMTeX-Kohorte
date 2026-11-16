#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
konzepte.py — Fachliche Kernlogik (MII-Kerndatensatz, 2027.0.0-ballot).

  - Kontaktebenen (Einrichtung/Abteilung/Versorgungsstelle) via
    Encounter.type:Kontaktebene (System http://fhir.de/CodeSystem/Kontaktebene)
  - fall_aufloesen(): bringt einen Encounter auf den Einrichtungskontakt (über partOf)
  - profil_check_documentreference(): lightweight MII-Dokument-Profil-Check
  - Helfer: code_extrahieren, iso_datum_parsen, alter_vollendete_jahre
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Konstante URLs / Systeme
# ---------------------------------------------------------------------------
CS_KONTAKTEBENE = "http://fhir.de/CodeSystem/Kontaktebene"
CS_FA_ABTEILUNG = "http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel"
CS_FA_ABTEILUNG_ERW = "http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel-erweitert"
CS_ICD10GM = "http://fhir.de/CodeSystem/bfarm/icd-10-gm"
CS_KDL = "http://dvmd.de/fhir/CodeSystem/kdl"
CS_XDS = "http://ihe-d.de/CodeSystems/IHEXDStypeCode"

# MII-Dokument-Profil (Modul Dokument). Bei Umsetzung aktuellen Pfad verifizieren.
PROFIL_MII_DOKUMENT = (
    "https://www.medizininformatik-initiative.de/fhir/ext/modul-dokument/"
    "StructureDefinition/mii-pr-dokument-dokument"
)

KONTAKTE_EBENE = "einrichtungskontakt"

# Kontakt-Ebenen-Codes
EBENE_EINRICHTUNG = "einrichtungskontakt"
EBENE_ABTEILUNG = "abteilungskontakt"
EBENE_VERSORGUNGSSTELLE = "versorgungsstellenkontakt"


# ---------------------------------------------------------------------------
# Helfer: Coding / CodeExtraktion
# ---------------------------------------------------------------------------
def code_extrahieren(cc: Any, system: Optional[str] = None) -> Optional[str]:
    """
    Liefert den ersten passenden code aus einem CodeableConcept (list unter
    'coding'). Optional kann nach einem bestimmten System gefiltert werden.
    """
    if not isinstance(cc, dict):
        return None
    for coding in cc.get("coding", []):
        if not isinstance(coding, dict):
            continue
        if system is None or coding.get("system") == system:
            code = coding.get("code")
            if code:
                return str(code)
    return None


def code_extrahieren_alle(cc: Any) -> List[Tuple[Optional[str], str]]:
    """Liefert Liste von (system, code) für alle Codings eines CodeableConcept."""
    out: List[Tuple[Optional[str], str]] = []
    if not isinstance(cc, dict):
        return out
    for coding in cc.get("coding", []):
        if not isinstance(coding, dict):
            continue
        code = coding.get("code")
        if code:
            out.append((coding.get("system"), str(code)))
    return out


# ---------------------------------------------------------------------------
# Datums-/Alters-Helfer
# ---------------------------------------------------------------------------
_ISO_RE = re.compile(
    r"^(?P<year>\d{4})(?:-(?P<month>\d{2}))?(?:-(?P<day>\d{2}))?"
    r"(?:[T ](?P<hour>\d{2}):(?P<min>\d{2})(?::(?P<sec>\d{2}))?"
    r"(?:[.,]\d+)?\s*(?P<tz>[+-]\d{2}:?\d{2}|Z)?)?$"
)


def iso_datum_parsen(value: Any) -> Optional[date]:
    """
    Parst FHIR-dateTime/date-Strings (ISO-8601, mit/ohne Uhrzeit/Zeitzone).
    Unterstützt unvollständige Datumsangaben (nur Jahr, Jahr+Monat).
    Gibt ein date-Objekt zurück (fehlende Monat/Tag -> 01) oder None.
    """
    if value is None:
        return None
    m = _ISO_RE.match(str(value).strip())
    if not m:
        return None
    year = int(m.group("year"))
    month = int(m.group("month")) if m.group("month") else 1
    day = int(m.group("day")) if m.group("day") else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def alter_vollendete_jahre(birth: Any, referenz: Any) -> Optional[int]:
    """
    Vollendete Jahre zwischen birthDate und referenz-Datum.
    Gibt None, wenn birth oder referenz nicht parsebar sind, oder wenn das
    Geburtsdatum NACH dem Referenzdatum liegt (negatives Alter).
    """
    b = iso_datum_parsen(birth)
    r = iso_datum_parsen(referenz)
    if b is None or r is None:
        return None
    years = r.year - b.year
    if (r.month, r.day) < (b.month, b.day):
        years -= 1
    if years < 0:
        return None
    return years


# ---------------------------------------------------------------------------
# Kontaktebene & Fall-Auflösung
# ---------------------------------------------------------------------------
def kontaktebene(encounter: Dict[str, Any]) -> Optional[str]:
    """Liefert die Kontaktebene aus Encounter.type (Kontaktebene-Coding) oder None."""
    for t in encounter.get("type", []):
        code = code_extrahieren(t, CS_KONTAKTEBENE)
        if code:
            return code
    return None


def partof_referenz(encounter: Dict[str, Any]) -> Optional[str]:
    """Gibt die partOf-Referenz des Encounters zurück (ohne '#'), sonst None."""
    partof = encounter.get("partOf")
    if isinstance(partof, dict):
        ref = partof.get("reference")
        if ref and not ref.startswith("#"):
            return ref
    return None


def fall_aufloesen(base: str, encounter: Dict[str, Any],
                   cache: Dict[str, Dict[str, Any]],
                   dienst: Any) -> Dict[str, Any]:
    """
    Bringt einen Encounter auf den Einrichtungskontakt (Fall) hoch.
    - Nutzt den übergebenen 'dienst' (Client mit resolve_reference) zum Auflösen
      von partOf-Ketten.
    - cache: id -> encounter, um wiederholte GETs zu vermeiden (neben dem
      übergebenen dienst, der selbst referenzierte Encounter vorhält).
    Übergabe 'dienst' = Modul fhir_client (hat resolve_reference(base, ref)).
    Gibt den Einrichtungskontakt-Encounter zurück (oder den ursprünglichen,
    wenn dieser bereits einer ist bzw. kein partOf/type hat).
    """
    current = encounter
    # Sicherheitslimit gegen zyklische partOf-Ketten
    for _ in range(10):
        ebene = kontaktebene(current)
        partof = partof_referenz(current)

        # Regel: type nicht definiert ODER kein partOf -> als Einrichtungskontakt
        # behandeln.
        if ebene is None or (ebene == EBENE_EINRICHTUNG) or (partof is None):
            return current

        # ebene ist abteilungskontakt oder versorgungsstellenkontakt -> partOf folgen
        parent = _get_encounter(base, partof, cache, dienst)
        if parent is None:
            # partOf nicht auflösbar -> behandle aktuellen als Fall (best effort)
            return current
        current = parent

    return current


def _get_encounter(base: str, ref: str, cache: Dict[str, Dict[str, Any]], dienst: Any) -> Optional[Dict[str, Any]]:
    """Encounter anhand Referenz holen (mit Cache und Typ-Prüfung)."""
    # ID aus Referenz extrahieren
    res_id = ref.split("/")[-1] if "/" in ref else ref
    if res_id in cache:
        return cache[res_id]
    res, status = dienst.resolve_reference(base, {"reference": ref})
    if status is None or status != 200 or not res:
        return None
    if res.get("resourceType") != "Encounter":
        return None
    cache[res_id] = res
    return res


# ---------------------------------------------------------------------------
# Profil-Check DocumentReference (lightweight)
# ---------------------------------------------------------------------------
def profil_check_documentreference(doc: Dict[str, Any]) -> Dict[str, bool]:
    """
    Lightweight-Prüfung gegen MII-Dokument-Profil.
    Liefert dict mit Einzelprüfungen (bool).
    """
    meta = doc.get("meta") or {}
    profiles = meta.get("profile") or []

    # profilreferenz: irgendeine meta.profile-URL enthält den MII-Dokument-Pfad
    profil_ok = any(
        isinstance(p, str) and ("modul-dokument" in p and "dokument" in p)
        for p in profiles
    )

    status_ok = bool(doc.get("status"))

    # type: mind. ein type.coding vorhanden
    type_codings = []
    raw_types = doc.get("type")
    if raw_types is None:
        raw_types = []
    elif not isinstance(raw_types, list):
        raw_types = [raw_types]
    for t in raw_types:
        if isinstance(t, dict):
            type_codings.extend(code_extrahieren_alle(t))
    type_ok = len(type_codings) > 0

    subject_ok = isinstance(doc.get("subject"), dict) and bool(doc.get("subject", {}).get("reference"))

    # content mit attachment
    content_ok = False
    for c in doc.get("content", []):
        if isinstance(c, dict) and isinstance(c.get("attachment"), dict):
            content_ok = True
            break

    # context.encounter
    ctx = doc.get("context") or {}
    encounter_refs = ctx.get("encounter") or []
    encounter_ok = len(encounter_refs) > 0

    return {
        "profil": profil_ok,
        "status": status_ok,
        "type": type_ok,
        "subject": subject_ok,
        "content": content_ok,
        "context_encounter": encounter_ok,
    }
