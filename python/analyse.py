#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse.py — GeMTeX Kohorten-Analyse (FHIR R4, MII-Kerndatensatz).

Ablauf:
  1. Suche alle DocumentReference (paginiert) inkl. subject/encounter (_include)
  2. Löse referenzierte Encounter auf & normalisiere auf Einrichtungskontakt (Fall)
  3. Suche Diagnosen der Fälle (beide Richtungen: Encounter.diagnosis und
     Condition?encounter=), ohne Duplikate
  4. Löse Patienten auf
  5. Verknüpfungs-Check (Broken-Reference-Check) + Profil-Check (lightweight)
  6. Statistik (statistik.berechne) -> menschenlesbaren Text + strukturiertes JSON

Aufruf:
  python3 analyse.py [base_url]
  Standard: https://hapi.fhir.org/baseR4
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import fhir_client
import konzepte
import statistik

DEFAULT_BASE = "https://hapi.fhir.org/baseR4"
AUSGABE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ausgabe")
MAX_CONDITION_SUCHEN = 500  # Sicherheitslimit für Einzel-Suchen (Condition?encounter=)


# ---------------------------------------------------------------------------
# Resolver mit Cache (Auflösen von Referenzen, mit Typ-Verifikation)
# ---------------------------------------------------------------------------
class Resolver:
    def __init__(self, base: str):
        self.base = base
        self.cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self.encounter_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def key(self, ref: Any) -> str:
        if not isinstance(ref, dict):
            return ""
        return ref.get("reference") or ""

    def resolve(self, ref: Any, expected_type: Optional[str] = None):
        k = self.key(ref)
        if k in self.cache:
            res = self.cache[k]
        else:
            res, status = fhir_client.resolve_reference(self.base, ref)
            self.cache[k] = res
        if res is None:
            return None, False, None
        rtype = res.get("resourceType")
        typ_ok = (expected_type is None) or (rtype == expected_type)
        return res, typ_ok, 200

    def resolve_encounter(self, ref: Any):
        res, typ_ok, _ = self.resolve(ref, "Encounter")
        if res is None or not typ_ok:
            return None
        eid = res.get("id")
        self.encounter_cache[eid] = res
        return res

    # Schnittstelle für konzepte.fall_aufloesen
    def resolve_reference(self, base: str, ref: Any):
        return fhir_client.resolve_reference(base, ref)


# ---------------------------------------------------------------------------
# Verknüpfungs-Check (Broken-Reference-Check)
# ---------------------------------------------------------------------------
VERBINDUNGEN: List[Dict[str, Any]] = []


def _check_edge(resolver: Resolver, kante: str, referenz: Any, expected: str) -> None:
    res, typ_ok, status = resolver.resolve(referenz, expected)
    ok = res is not None
    ref_str = referenz.get("reference") if isinstance(referenz, dict) else str(referenz)
    VERBINDUNGEN.append({
        "kante": kante,
        "referenz": ref_str,
        "erwarteter_typ": expected,
        "aufloesbar": ok,
        "typ_ok": bool(ok and typ_ok),
        "status": status,
    })


# ---------------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------------
def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    resolver = Resolver(base)

    print(f"Hiermit werden Daten von {base} geladen …\n")

    # ---- Schritt 1: DocumentReference (paginiert) ----------------------
    docs, included = fhir_client.search(
        base, "DocumentReference",
        {"_include": ["DocumentReference:subject", "DocumentReference:encounter"]},
    )
    print(f"[1] DocumentReference gefunden: {len(docs)}")

    included_encounters: Dict[str, Dict[str, Any]] = {}
    included_patienten: Dict[str, Dict[str, Any]] = {}
    for res in included:
        rtype = res.get("resourceType")
        rid = res.get("id")
        if rtype == "Encounter" and rid:
            included_encounters[rid] = res
        elif rtype == "Patient" and rid:
            included_patienten[rid] = res

    # ---- Schritt 2: Fälle (Einrichtungskontakte) aus Dokumenten ableiten --
    # faelle_tree: id -> encounter  (alle Encounters, die in einem Fall-Baum
    # liegen: Einrichtungskontakt + partOf-Vorfahren). Nur für Fälle, die über
    # Dokument->context.encounter erreicht werden (Kohorte).
    faelle_tree: Dict[str, Dict[str, Any]] = {}

    for doc in docs:
        doc_id = doc.get("id")
        ctx = doc.get("context") or {}
        for ref in ctx.get("encounter") or []:
            if not ref:
                continue
            _check_edge(resolver, "DocumentReference.context.encounter->Encounter", ref, "Encounter")
            enc = resolver.resolve_encounter(ref)
            if enc is None:
                continue
            # partOf zur Einrichtung aufsteigen (Baum sammeln)
            chain, fall = _steige_zu_einrichtung(base, enc, resolver)
            faelle_tree.update(chain)
            if fall is not None:
                faelle_tree[fall.get("id")] = fall

    faelle_map: Dict[str, Dict[str, Any]] = {}  # fall_id -> fall-dict
    for doc in docs:
        doc_id = doc.get("id")
        ctx = doc.get("context") or {}
        for ref in ctx.get("encounter") or []:
            enc = resolver.encounter_cache.get(ref.get("reference", "").split("/")[-1])
            if enc is None:
                continue
            fall_id = _fall_id_von(base, enc, resolver)
            if not fall_id:
                continue
            f = faelle_map.setdefault(fall_id, {
                "fall_id": fall_id,
                "patient_id": None,
                "start": None,
                "end": None,
                "fachabteilung": None,
                "geschlecht": None,
                "alter": None,
                "diagnosen_icd": [],
                "dokumente": [],
            })
            if doc_id not in f["dokumente"]:
                f["dokumente"].append(doc_id)

    # Source-Encounter (Abteilung/Versorgungsstelle) für period/serviceType etc.
    # pro Fall: wir nutzen den Einrichtungskontakt selbst.
    for fid in list(faelle_map.keys()):
        enc = faelle_tree.get(fid)
        if enc is None:
            enc = included_encounters.get(fid) or resolver.encounter_cache.get(fid)
        if enc:
            period = enc.get("period") or {}
            faelle_map[fid]["start"] = konzepte.iso_datum_parsen(period.get("start"))
            faelle_map[fid]["end"] = konzepte.iso_datum_parsen(period.get("end"))
            faelle_map[fid]["fachabteilung"] = (
                konzepte.code_extrahieren(enc.get("serviceType"), konzepte.CS_FA_ABTEILUNG)
                or konzepte.code_extrahieren(enc.get("serviceType"), konzepte.CS_FA_ABTEILUNG_ERW)
            )

    print(f"[2] Fälle (Einrichtungskontakte) über Dokumente: {len(faelle_map)}")

    # ---- Schritt 3: Diagnosen (beide Richtungen) --------------------------
    diagnostik: Dict[str, Dict[str, Any]] = {}  # condition_id -> condition

    # Richtung 2: Condition?encounter=  für alle Encounter der Fall-Bäume
    for enc in faelle_tree.values():
        eid = enc.get("id")
        if not eid:
            continue
        if enc.get("partOf"):
            _check_edge(resolver, "Encounter.partOf->Encounter", enc["partOf"], "Encounter")
        # Encounter.diagnosis.condition -> Condition (Richtung 1, ohne extra Query)
        for d in enc.get("diagnosis", []) or []:
            cond_ref = d.get("condition")
            if not cond_ref:
                continue
            _check_edge(resolver, "Encounter.diagnosis.condition->Condition", cond_ref, "Condition")
            cond, typ_ok, _ = resolver.resolve(cond_ref, "Condition")
            if cond is not None and typ_ok:
                diagnostik.setdefault(cond.get("id"), cond)

    # Zusätzlich Condition?encounter= für die Fall-Baum-Encounters
    queried = 0
    for enc in faelle_tree.values():
        eid = enc.get("id")
        if not eid or queried >= MAX_CONDITION_SUCHEN:
            continue
        conditions, _ = fhir_client.search(base, "Condition", {"encounter": eid})
        queried += 1
        for cond in conditions:
            if cond.get("encounter"):
                _check_edge(resolver, "Condition.encounter->Encounter", cond["encounter"], "Encounter")
            diagnostik.setdefault(cond.get("id"), cond)

    # Diagnosen den Fällen zuordnen (fallweise, dedupliziert)
    for fid, fall in faelle_map.items():
        # aus Encounter.diagnosis
        enc = faelle_tree.get(fid) or included_encounters.get(fid) or resolver.encounter_cache.get(fid)
        if enc:
            for d in enc.get("diagnosis", []) or []:
                cond_ref = d.get("condition")
                if not cond_ref:
                    continue
                cond_id = cond_ref.get("reference", "").split("/")[-1]
                cond = diagnostik.get(cond_id)
                if cond:
                    _zugewiesene_icd(fall, cond)
        # aus Condition.encounter (Hochsteigen über partOf zum Fall)
        for cond in diagnostik.values():
            cenc = cond.get("encounter")
            if not isinstance(cenc, dict):
                continue
            cref = cenc.get("reference")
            if not cref:
                continue
            c_enc = resolver.encounter_cache.get(cref.split("/")[-1])
            if c_enc is None:
                c_enc = resolver.resolve_encounter(cenc)
            c_fall_id = _fall_id_von(base, c_enc, resolver) if c_enc else None
            if c_fall_id == fid:
                _zugewiesene_icd(fall, cond)

    print(f"[3] Diagnosen (Condition) gefunden: {len(diagnostik)}")

    # ---- Schritt 4: Patienten auflösen & Fall-Attribute -------------------
    for fid, fall in faelle_map.items():
        enc = faelle_tree.get(fid) or included_encounters.get(fid) or resolver.encounter_cache.get(fid)
        patient_ref = None
        if enc:
            patient_ref = enc.get("patient") or enc.get("subject")
        if patient_ref:
            _check_edge(resolver, "Encounter.patient->Patient", patient_ref, "Patient")
        if patient_ref is None:
            # über Dokumente des Falls
            for doc_id in fall["dokumente"]:
                doc = next((d for d in docs if d.get("id") == doc_id), None)
                if doc and doc.get("subject"):
                    patient_ref = doc["subject"]
                    _check_edge(resolver, "DocumentReference.subject->Patient", patient_ref, "Patient")
                    break
        if patient_ref:
            pat, typ_ok, _ = resolver.resolve(patient_ref, "Patient")
            if pat is not None and typ_ok:
                fall["patient_id"] = pat.get("id")
                fall["geschlecht"] = pat.get("gender")
                fall["alter"] = konzepte.alter_vollendete_jahre(pat.get("birthDate"), fall["start"])

    # DocumentReference.subject auch für alle Dokumente prüfen (Verknüpfungs-Check)
    for doc in docs:
        if doc.get("subject"):
            _check_edge(resolver, "DocumentReference.subject->Patient", doc["subject"], "Patient")

    patientenzahl = len({f["patient_id"] for f in faelle_map.values() if f.get("patient_id")})
    print(f"[4] Patienten (Kohorte): {patientenzahl}")

    # ---- Schritt 5: Profil-Check ------------------------------------------
    profilcheck: List[Dict[str, Any]] = []
    for doc in docs:
        p = konzepte.profil_check_documentreference(doc)
        p["doc_id"] = doc.get("id")
        p["gesamt"] = all(p[k] for k in
                          ["profil", "status", "type", "subject", "content", "context_encounter"])
        profilcheck.append(p)
    n_konform = sum(1 for p in profilcheck if p["gesamt"])
    print(f"[5] Profil-Check: {n_konform}/{len(profilcheck)} Dokumente vollständig konform")

    # ---- Schritt 6: Zusammenstellen & ausgeben ----------------------------
    daten = {
        "dokumente": docs,
        "faelle": list(faelle_map.values()),
        "patienten": {},
        "verknuepfungscheck": VERBINDUNGEN,
        "profilcheck": profilcheck,
    }
    ergebnis = statistik.berechne(daten)
    text = menschenlesbar(ergebnis)

    os.makedirs(AUSGABE_DIR, exist_ok=True)
    json_path = os.path.join(AUSGABE_DIR, "ergebnis.json")
    txt_path = os.path.join(AUSGABE_DIR, "bericht.txt")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(ergebnis, fh, ensure_ascii=False, indent=2)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    print("\n" + text)
    print(f"\nErgebnis geschrieben nach:\n  {json_path}\n  {txt_path}")
    return 0


def _zugewiesene_icd(fall: Dict[str, Any], cond: Dict[str, Any]) -> None:
    code = konzepte.code_extrahieren(cond.get("code"), konzepte.CS_ICD10GM)
    if code and code not in fall["diagnosen_icd"]:
        fall["diagnosen_icd"].append(code)


def _fall_id_von(base: str, enc: Optional[Dict[str, Any]], resolver: Resolver) -> Optional[str]:
    """Liefert die Fall-id (Einrichtungskontakt) für einen Encounter."""
    if enc is None:
        return None
    fall = konzepte.fall_aufloesen(base, enc, resolver.encounter_cache, resolver)
    return fall.get("id") if fall else None


def _steige_zu_einrichtung(base: str, enc: Dict[str, Any], resolver: Resolver):
    """Sammelt die partOf-Kette (chain: id->encounter) und liefert (chain, fall)."""
    chain: Dict[str, Dict[str, Any]] = {}
    current = enc
    for _ in range(10):
        eid = current.get("id")
        if eid:
            chain[eid] = current
        ebene = konzepte.kontaktebene(current)
        partof = konzepte.partof_referenz(current)
        if ebene is None or ebene == konzepte.EBENE_EINRICHTUNG or partof is None:
            return chain, current
        parent = resolver.resolve_encounter({"reference": partof})
        if parent is None:
            return chain, current
        current = parent
    return chain, current


# ---------------------------------------------------------------------------
# Menschenslesbare Ausgabe
# ---------------------------------------------------------------------------
def menschenlesbar(e: Dict[str, Any]) -> str:
    L: List[str] = []
    u = e["uebersicht"]
    L.append("=" * 64)
    L.append("GeMTeX – Kohorten-Analyse (FHIR R4 / MII)")
    L.append("=" * 64)
    L.append(f"Dokumente (DocumentReference): {u['anzahl_dokumente']}")
    L.append(f"Patienten mit ≥1 Dokument:     {u['anzahl_patienten']}")
    L.append(f"Fälle (Einrichtungskontakte):  {u['anzahl_faelle']}")
    L.append("")

    L.append("Geschlechterverteilung (fallweise):")
    _dict_zeilen(L, e["geschlechter"])
    L.append("")

    L.append("Altersverteilung (fallweise, [a,b)):")
    _dict_zeilen(L, e["alter"])
    L.append("")

    L.append("Fachabteilungen (Top 10 + übrige + keine Angabe):")
    fa = e["fachabteilungen"]
    for t in fa["top10"]:
        L.append(f"  {t['code']:<20} {t['anzahl']}")
    L.append(f"  {'[übrige]':<20} {fa['uebrige']}")
    L.append(f"  {'[keine Angabe]':<20} {fa['keine_angabe']}")
    L.append("")

    L.append("Anzahl Fälle pro Patient:")
    _dict_zeilen(L, e["faelle_pro_patient"])
    L.append("")

    L.append("Anzahl DocumentReferences pro Fall:")
    _dict_zeilen(L, e["docs_pro_fall"])
    L.append("")

    L.append("Liegezeit (Tage, 10 Gruppen):")
    _dict_zeilen(L, e["liegezeit"])
    L.append("")

    L.append("ICD-10 (erste 3 Stellen, je Fall/Diagnoseinstanz):")
    _dict_zeilen(L, e["icd"])
    L.append("")

    dt = e["documentreference_type"]
    L.append("DocumentReference.type – KDL-System:")
    _dict_zeilen(L, dt["kdl"])
    L.append("DocumentReference.type – XDS-System:")
    _dict_zeilen(L, dt["xds"])
    L.append(f"type nicht definiert (Vorkommen): {dt['nicht_definiert']}")
    L.append("")

    L.append("Verknüpfungs-Check (Broken-Reference-Check):")
    vk = e["verknuepfungscheck"]
    if not vk:
        L.append("  (keine zu prüfenden Referenzen vorhanden)")
    else:
        # Zusammenfassung je Kante
        L.append("  Zusammenfassung je Kante:")
        per_kante: Dict[str, Dict[str, int]] = {}
        for v in vk:
            k = v["kante"]
            d = per_kante.setdefault(k, {"ok": 0, "broken": 0})
            if v["aufloesbar"] and v["typ_ok"]:
                d["ok"] += 1
            else:
                d["broken"] += 1
        for k, d in per_kante.items():
            L.append(f"    {k:<45} OK={d['ok']}  broken={d['broken']}")
        # nur kaputte Referenzen im Detail
        broken = [v for v in vk if not (v["aufloesbar"] and v["typ_ok"])]
        if broken:
            L.append("  Kaputte Referenzen im Detail:")
            for v in broken[:50]:
                L.append(f"    {v['kante']} -> {v['referenz']} (HTTP {v['status']})")
            if len(broken) > 50:
                L.append(f"    … und {len(broken)-50} weitere")
    L.append("")

    L.append("Profil-Check (DocumentReference, lightweight):")
    pc = e["profilcheck"]
    if not pc:
        L.append("  (keine Dokumente vorhanden)")
    for p in pc:
        flag = "KONFORM" if p["gesamt"] else "ABWEICHUNG"
        L.append(f"  [{flag}] {p['doc_id']}: profil={p['profil']} status={p['status']} "
                 f"type={p['type']} subject={p['subject']} content={p['content']} "
                 f"context.encounter={p['context_encounter']}")
    L.append("")
    return "\n".join(L)


def _dict_zeilen(L: List[str], d: Dict[str, int]) -> None:
    if not d:
        L.append("  (keine Daten)")
        return
    for k, v in d.items():
        L.append(f"  {str(k):<30} {v}")


if __name__ == "__main__":
    sys.exit(main())
