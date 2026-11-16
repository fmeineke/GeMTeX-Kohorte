#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
statistik.py — Berechnung aller Kennzahlen aus den aufbereiteten Daten.

Eingabestruktur: ein dict 'daten' (aufbereitet von analyse.py):
    {
      "dokumente":           [DocumentReference-dicts],
      "faelle":              [dict je Einrichtungskontakt-Fall]
           jeweils: {fall_id, patient_id, start, end, fachabteilung,
                     geschlecht, alter, diagnosen_icd (volle Codes),
                     dokumente (Liste von doc-ids)}
      "patienten":           {patient_id: Patient-dict},
      "verknuepfungscheck":  [dict(Kante, ok, typ_ok, status, detail)],
      "profilcheck":         [dict(doc_id, profil, status, type, subject,
                                   content, context_encounter, gesamt)],
    }

Ausgabe: dict 'ergebnis' (JSON-serialisierbar), das direkt das R-Skript liest.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import date

from konzepte import CS_KDL, CS_XDS, code_extrahieren_alle


# ---------------------------------------------------------------------------
# Altersgruppen (halboffen [a,b))
# ---------------------------------------------------------------------------
def alter_band(alter: Optional[int]) -> str:
    if alter is None:
        return "unbekannt"
    if alter < 18:
        return "0-17"
    if alter < 30:
        return "18-29"
    if alter < 40:
        return "30-39"
    if alter < 50:
        return "40-49"
    if alter < 60:
        return "50-59"
    if alter < 70:
        return "60-69"
    if alter < 80:
        return "70-79"
    return "80+"


ALTER_GRUPPEN_REIHENFOLGE = ["0-17", "18-29", "30-39", "40-49",
                             "50-59", "60-69", "70-79", "80+", "unbekannt"]


# ---------------------------------------------------------------------------
# Liegezeit (in Tagen, nur vollständige Datumspaare)
# ---------------------------------------------------------------------------
def liegezeit_tage(start: Optional[date], end: Optional[date]) -> Optional[int]:
    if start is None or end is None:
        return None
    if end < start:
        return None
    return (end - start).days


def liegezeit_band(tage: Optional[int]) -> str:
    if tage is None:
        return "Liegezeit nicht bestimmbar"
    if tage < 1:
        return "0 Tage"
    if tage <= 9:
        return f"{tage} Tage"
    return "10+ Tage"


# ---------------------------------------------------------------------------
# Kernberechnung
# ---------------------------------------------------------------------------
def berechne(daten: Dict[str, Any]) -> Dict[str, Any]:
    faelle: List[Dict[str, Any]] = daten["faelle"]
    patienten: Dict[str, Any] = daten.get("patienten", {})

    n_dokumente = len(daten["dokumente"])
    n_faelle = len(faelle)
    patient_ids = {f["patient_id"] for f in faelle if f.get("patient_id")}
    n_patienten = len(patient_ids)

    # --- Geschlechterverteilung (fallweise) --------------------------------
    geschlecht_zaehler: Dict[str, int] = {}
    for f in faelle:
        g = f.get("geschlecht") or "unbekannt"
        geschlecht_zaehler[g] = geschlecht_zaehler.get(g, 0) + 1

    # --- Altersverteilung (fallweise) --------------------------------------
    alter_zaehler: Dict[str, int] = {}
    for f in faelle:
        a = alter_band(f.get("alter"))
        alter_zaehler[a] = alter_zaehler.get(a, 0) + 1

    # --- Fachabteilungen (fallweise) --------------------------------------
    abt_zaehler: Dict[str, int] = {}
    for f in faelle:
        fa = f.get("fachabteilung") or "keine Angabe"
        abt_zaehler[fa] = abt_zaehler.get(fa, 0) + 1
    keine_angabe = abt_zaehler.pop("keine Angabe", 0)
    sortiert = sorted(abt_zaehler.items(), key=lambda kv: kv[1], reverse=True)
    top10 = [(k, v) for k, v in sortiert][:10]
    top10_codes = {k for k, _ in top10}
    uebrige = sum(v for k, v in sortiert if k not in top10_codes)

    # --- Anzahl Fälle / Patient (Histogramm) ------------------------------
    faelle_pro_patient: Dict[str, int] = {}
    for f in faelle:
        if f.get("patient_id"):
            faelle_pro_patient[f["patient_id"]] = faelle_pro_patient.get(f["patient_id"], 0) + 1
    faelle_pro_patient_hist: Dict[str, int] = {}
    for v in faelle_pro_patient.values():
        faelle_pro_patient_hist[str(v)] = faelle_pro_patient_hist.get(str(v), 0) + 1

    # --- Anzahl DocumentReferences / Fall (Histogramm) --------------------
    docs_pro_fall: Dict[str, int] = {}
    for f in faelle:
        docs_pro_fall[f["fall_id"]] = len(f.get("dokumente", []))
    docs_pro_fall_hist: Dict[str, int] = {}
    for v in docs_pro_fall.values():
        docs_pro_fall_hist[str(v)] = docs_pro_fall_hist.get(str(v), 0) + 1

    # --- Liegezeit (10 Gruppen) -------------------------------------------
    liegezeit_zaehler: Dict[str, int] = {}
    for f in faelle:
        tage = liegezeit_tage(f.get("start"), f.get("end"))
        band = liegezeit_band(tage)
        liegezeit_zaehler[band] = liegezeit_zaehler.get(band, 0) + 1

    # --- ICD (erste 3 Stellen) fallweise, je Diagnoseinstanz, dedupliziert -
    icd_zaehler: Dict[str, int] = {}
    for f in faelle:
        gesehen = set()
        for code in f.get("diagnosen_icd", []):
            if not code:
                continue
            stub = str(code)[:3].upper()
            if stub in gesehen:
                continue
            gesehen.add(stub)
            icd_zaehler[stub] = icd_zaehler.get(stub, 0) + 1

    # --- DocumentReference.type nach Systemen -----------------------------
    kdl_zaehler: Dict[str, int] = {}
    xds_zaehler: Dict[str, int] = {}
    docs_ohne_type = 0
    for doc in daten["dokumente"]:
        # type kann ein einzelnes CodeableConcept ODER Liste sein
        types = doc.get("type")
        if types is None:
            docs_ohne_type += 1
            continue
        if not isinstance(types, list):
            types = [types]
        hat_coding = False
        for t in types:
            for system, code in code_extrahieren_alle(t):
                if not code:
                    continue
                if system == CS_KDL:
                    kdl_zaehler[code] = kdl_zaehler.get(code, 0) + 1
                    hat_coding = True
                elif system == CS_XDS:
                    xds_zaehler[code] = xds_zaehler.get(code, 0) + 1
                    hat_coding = True
        # 'type nicht definiert' = kein einziges type.coding (Kriterium laut Vorgabe)
        if not hat_coding:
            docs_ohne_type += 1

    # --- Ergebnisse zusammenstellen ---------------------------------------
    ergebnis = {
        "uebersicht": {
            "anzahl_dokumente": n_dokumente,
            "anzahl_patienten": n_patienten,
            "anzahl_faelle": n_faelle,
        },
        "geschlechter": _sortiere_dict(geschlecht_zaehler),
        "alter": _reihenfolge(alter_zaehler, ALTER_GRUPPEN_REIHENFOLGE),
        "fachabteilungen": {
            "top10": [{"code": k, "anzahl": v} for k, v in top10],
            "uebrige": uebrige,
            "keine_angabe": keine_angabe,
        },
        "faelle_pro_patient": _sortiere_int(faelle_pro_patient_hist),
        "docs_pro_fall": _sortiere_int(docs_pro_fall_hist),
        "liegezeit": _sortiere_dict(liegezeit_zaehler),
        "icd": _sortiere_dict(icd_zaehler),
        "documentreference_type": {
            "kdl": _sortiere_dict(kdl_zaehler),
            "xds": _sortiere_dict(xds_zaehler),
            "nicht_definiert": docs_ohne_type,
        },
        "verknuepfungscheck": daten.get("verknuepfungscheck", []),
        "profilcheck": daten.get("profilcheck", []),
    }
    return ergebnis


def _sortiere_dict(d: Dict[str, int]) -> Dict[str, int]:
    return dict(sorted(d.items(), key=lambda kv: kv[1], reverse=True))


def _sortiere_int(d: Dict[str, int]) -> Dict[str, int]:
    # Schlüssel numerisch sortieren (z.B. "1","2",...,"12")
    try:
        return {k: d[k] for k in sorted(d, key=lambda s: int(s))}
    except ValueError:
        return dict(sorted(d.items(), key=lambda kv: kv[1], reverse=True))


def _reihenfolge(d: Dict[str, int], reihenfolge: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for k in reihenfolge:
        if k in d:
            out[k] = d[k]
    # evtl. zusätzliche Gruppen (falls vorhanden) anhängen
    for k, v in d.items():
        if k not in out:
            out[k] = v
    return out
