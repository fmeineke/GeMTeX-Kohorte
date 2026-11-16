# GeMTeX-Kohorte — Makefile
#
# Ablauf:
#   DIZ (lokal)  : nur die Python-Ausgabe (ergebnis.json + bericht.txt)
#   zentral      : optional der PDF-R-Bericht aus dem übermittelten JSON
#
# Beispiele:
#   make                  # DIZ: erzeugt nur ausgabe/ergebnis.json (+ bericht.txt)
#   make central          # zentral: erzeugt JSON + PDF-R-Bericht
#   make pdf              # zentral: nur den PDF-Bericht (aus vorhandenem JSON)
#   make BASE_URL=https://…   # anderes FHIR-Endpunkt
#   make clean            # löscht alle selbst erzeugten Dateien
#
# Voraussetzungen:
#   DIZ: Python 3 (+ requests, siehe python/requirements.txt)
#   zentral PDF: zusätzlich R mit Paketen jsonlite/ggplot2/gridExtra
#                (r/install_libs.sh)

.PHONY: all json central pdf setup install clean

# ---------------------------------------------------------------------------
# Konfiguration (per Kommandozeile überschreibbar, z. B. make BASE_URL=…)
# ---------------------------------------------------------------------------
BASE_URL ?= https://hapi.fhir.org/baseR4
PYTHON   ?= python3
RSCRIPT  ?= Rscript

AUSGABE := ausgabe
JSON    := $(AUSGABE)/ergebnis.json
TXT     := $(AUSGABE)/bericht.txt
PDF     := $(AUSGABE)/bericht.pdf

PY_SRC  := python/analyse.py python/fhir_client.py python/konzepte.py python/statistik.py
R_SRC   := r/bericht.R

# ---------------------------------------------------------------------------
# Ziele
# ---------------------------------------------------------------------------
# DIZ-Fall (Standard): nur die Python-Ausgabe.
all: $(JSON)

# Zentral-Fall: JSON + PDF-R-Bericht.
central: $(PDF)

# ergebnis.json + bericht.txt werden in einem Lauf von analyse.py erzeugt.
$(JSON): $(PY_SRC)
	$(PYTHON) python/analyse.py "$(BASE_URL)"

# Bericht.pdf hängt von der JSON-Ausgabe und dem R-Skript ab (optional, zentral).
$(PDF): $(JSON) $(R_SRC)
	$(RSCRIPT) r/bericht.R "$(JSON)" "$(PDF)"

# Bequeme Teil-Ziele
json: $(JSON)
pdf:  $(PDF)

# R-Bibliotheken installieren (nur zentral nötig)
setup:
	./r/install_libs.sh

install: setup

# ---------------------------------------------------------------------------
# Aufräumen
# ---------------------------------------------------------------------------
clean:
	rm -f $(JSON) $(TXT) $(PDF)
	rm -rf python/__pycache__
	@echo "Self-generated files removed."
