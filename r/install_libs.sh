#!/usr/bin/env bash
#
# install_libs.sh — Installiert alle R-Pakete, die für bericht.R benötigt werden.
#
# Benötigt werden:
#   - jsonlite   (Einlesen von ergebnis.json)
#   - ggplot2    (Balkendiagramme, Histogramme)
#   - gridExtra  (Multi-Panel-Layouts, Tabellen)
#   - grid       (Teil der R-Basisinstallation -> kein explizites Installieren nötig)
#
# Systemabhängigkeit für cairo_pdf (PDF-Erzeugung):
#   R muss mit Cairo-Unterstützung gebaut sein (apt: r-base / libcairo2-dev).
#
# Aufruf:
#   ./install_libs.sh            # installiert nur fehlende Pakete
#   ./install_libs.sh --force    # erzwingt Neuinstallation
#
# Ggf. ausführbar machen:  chmod +x install_libs.sh

set -euo pipefail

REPO="https://cloud.r-project.org"
FORCE=""

if [[ "${1:-}" == "--force" ]]; then
  FORCE="--force"
  echo ">> Modus: erzwungene Neuinstallation (--force)"
fi

# Alle benötigten Pakete (grid wird von R mitgeliefert und hier der Vollständigkeit
# halber geprüft, braucht aber kein install.packages).
PACKAGES=(jsonlite ggplot2 gridExtra grid)

for pkg in "${PACKAGES[@]}"; do
  echo "------------------------------------------------------------"
  echo ">> Prüfe Paket: ${pkg}"

  # --force -> immer neu installieren; sonst nur, wenn nicht vorhanden
  if [[ -n "${FORCE}" ]] || ! Rscript -e "quit(status = !requireNamespace('${pkg}', quietly = TRUE))"; then
    echo ">> Installiere ${pkg} von ${REPO} ..."
    Rscript -e "install.packages('${pkg}', repos = '${REPO}', dependencies = TRUE)"
  else
    echo ">> ${pkg} ist bereits installiert — übersprungen."
  fi
done

echo "------------------------------------------------------------"
echo ">> Fertig. Verfügbare Pakete:"
Rscript -e '
  for (p in c("jsonlite", "ggplot2", "gridExtra", "grid")) {
    cat(sprintf("%-12s %s\n", p, if (requireNamespace(p, quietly = TRUE)) "OK" else "FEHLT"))
  }
'
