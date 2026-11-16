#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fhir_client.py — Schlanker FHIR R4 REST-Client.

Funktionen:
  - fhir_get(base, path, params) : einfacher GET mit JSON-Accept.
  - search(base, resource, params): paginierte Suche (searchset), liefert
    (hauptressourcen, included_resources).
  - resolve_reference(base, ref): löst eine Referenz auf -> (resource, status).
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

TIMEOUT = 60  # Sekunden pro Request (Demo-HAPI kann langsam sein)
HEADERS = {"Accept": "application/fhir+json"}


def _err(msg: str) -> None:
    print(f"[FEHLER] {msg}", file=sys.stderr)


def _fetch(url: str) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """GET und JSON-Parsing; Fehlertolerante Rückgabe (status, data)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        _err(f"Netzwerkfehler bei {url}: {e}")
        return None, None
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def _split_bundle(base: str, resource: str,
                  bundle: Dict[str, Any],
                  out: List[Dict[str, Any]],
                  included: List[Dict[str, Any]]) -> None:
    """Extrahiert Hauptressourcen und Inkludes aus einem searchset-Bundle."""
    for entry in bundle.get("entry", []):
        res = entry.get("resource")
        if not res:
            continue
        mode = (entry.get("search") or {}).get("mode", "match")
        if mode == "include" or res.get("resourceType") != resource:
            included.append(res)
        else:
            out.append(res)


def fhir_get(base: str, path: str,
             params: Optional[Dict[str, Any]] = None) -> Optional[Tuple[int, Dict[str, Any]]]:
    """GET auf base + path. Gibt (status, json) oder None bei Netzwerkfehler."""
    url = base.rstrip("/") + "/" + path.lstrip("/")
    if params:
        from urllib.parse import urlencode
        url = url + ("&" if "?" in url else "?") + urlencode(params, doseq=True)
    status, data = _fetch(url)
    if status is None:
        return None
    return status, data


def search(base: str, resource: str,
           params: Optional[Dict[str, Any]] = None,
           page_size: int = 50,
           max_pages: int = 100000) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Paginierte Suche über alle Seiten eines searchset-Bundles.
    Gibt (hauptressourcen_vom_typ, alle_included_resources) zurück.
    Fehlerhafte/abbruchige Seiten führen zu einem Teil-Ergebnis (nicht Absturz).
    """
    if params is None:
        params = {}
    params = dict(params)
    params["_count"] = page_size

    out: List[Dict[str, Any]] = []
    included: List[Dict[str, Any]] = []

    url = base.rstrip("/") + "/" + resource
    from urllib.parse import urlencode
    first_run = True

    for _ in range(max_pages):
        if first_run:
            full_url = url + "?" + urlencode(params, doseq=True)
            first_run = False
        else:
            full_url = url  # next-URL (bereits absolut bzw. absolut vom Server)

        status, bundle = _fetch(full_url)
        if status != 200 or not isinstance(bundle, dict):
            _err(f"Suche abgebrochen bei {full_url} (HTTP {status})")
            break

        if "entry" in bundle:
            _split_bundle(base, resource, bundle, out, included)

        nxt = None
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                nxt = link.get("url")
                break
        if not nxt:
            break
        url = nxt

    return out, included


def resolve_reference(base: str, ref: Any) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """
    Löst eine FHIR-Reference auf. Unterstützt relative ('Patient/123',
    'Encounter/45/_history/2') und absolute Referenzen.
    Interne '#…'-Fragmente (contained) werden nicht aufgelöst -> (None, None).
    Gibt (resource_dict, http_status | None) zurück.
    """
    if not isinstance(ref, dict):
        return None, None
    reference = ref.get("reference")
    if not reference:
        return None, None

    if reference.startswith("#"):
        # contained Resource: nicht per REST auflösbar
        return None, None

    path = reference.split("/_history/")[0]

    if reference.lower().startswith("http://") or reference.lower().startswith("https://"):
        url = reference
    else:
        if path.count("/") < 1:
            return None, None
        url = base.rstrip("/") + "/" + path

    status, data = _fetch(url)
    if status is None:
        return None, None
    return data, status
