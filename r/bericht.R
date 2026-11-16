#!/usr/bin/env Rscript
#
# bericht.R — Erzeugt einen PDF-Bericht (Tabellen, Balken, Histogramme) aus der
# von analyse.py erzeugten ergebnis.json.
#
# Grafiken im Stil eines Fachartikels (z. B. JAMIA): dezent gehaltene Balken,
# klare schwarze Achsen, keine unnötigen Gitterlinien, englische Beschriftung.
# Besonderheiten:
#   * Altersverteilung ist nach Altersklasse (Altersgruppe) sortiert, nicht nach
#     Häufigkeit.
#   * Liegezeit wird mit VERTIKALEN Balken dargestellt.
#   * Alle Beschriftungen innerhalb der Grafiken sind Englisch.
#
# Aufruf:
#   Rscript bericht.R [pfad/zu/ergebnis.json] [pfad/zum/ausgabe.pdf]
#
# Benötigte Pakete: jsonlite, ggplot2, gridExtra

suppressMessages({
  for (p in c("jsonlite", "ggplot2", "gridExtra")) {
    if (!requireNamespace(p, quietly = TRUE)) {
      install.packages(p, repos = "https://cloud.r-project.org", quiet = TRUE)
    }
    library(p, character.only = TRUE)
  }
})

# ---------------------------------------------------------------------------
# Argumente / Pfade
# ---------------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
json_in <- if (length(args) >= 1) args[1] else file.path("..", "ausgabe", "ergebnis.json")
pdf_out <- if (length(args) >= 2) args[2] else file.path("..", "ausgabe", "bericht.pdf")

if (!file.exists(json_in)) stop("ergebnis.json nicht gefunden: ", json_in)
e <- jsonlite::fromJSON(json_in, simplifyVector = TRUE)

# ---------------------------------------------------------------------------
# Journal-Thema (Fachzeitschriften-Stil, z. B. JAMIA)
# ---------------------------------------------------------------------------
# Gedecktes Grau für die Balken (druck-/graustufenfreundlich) und schlanke
# schwarze Achsen ohne Gitterlinien.
BAR_FILL <- "grey45"

theme_journal <- function(base_size = 10) {
  ggplot2::theme_classic(base_size = base_size) +
    ggplot2::theme(
      axis.line          = element_line(colour = "black", linewidth = 0.3),
      axis.ticks         = element_line(colour = "black", linewidth = 0.3),
      axis.text          = element_text(colour = "black"),
      axis.title         = element_text(colour = "black"),
      panel.grid         = element_blank(),
      panel.background   = element_blank(),
      plot.background    = element_blank(),
      plot.title         = element_text(size = base_size + 1, face = "bold",
                                        hjust = 0, colour = "black")
    )
}

# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------
# Neue Seite mit Titel
new_page <- function(title) {
  grid::grid.newpage()
  grid::grid.text(title, x = 0.5, y = 0.97, gp = grid::gpar(fontsize = 14, fontface = "bold"))
}

# Benannte Liste (0..n) -> data.frame(Kategorie, Anzahl)
named_df <- function(nv) {
  if (is.null(nv) || length(nv) == 0) return(data.frame())
  n <- names(nv)
  if (is.null(n)) n <- as.character(seq_along(nv))
  data.frame(Kategorie = n, Anzahl = as.numeric(unlist(nv)),
             stringsAsFactors = FALSE)
}

# Natürliche Reihenfolge von (Alters-)Kategorien: aufsteigend nach führender
# Zahl; Kategorien ohne führende Zahl (z. B. "unknown") ans Ende.
age_order <- function(cats) {
  num <- suppressWarnings(as.numeric(sub("^([0-9]+).*$", "\\1", cats)))
  has_num <- !is.na(num)
  c(cats[has_num][order(num[has_num])], cats[!has_num])
}

# Balkendiagramm im Journal-Stil.
#   vertical = TRUE  -> VERTIKALE Balken (Kategorie auf x-Achse) [Standard]
#   vertical = FALSE -> horizontale Balken (coord_flip)
#   order    = "count"    -> nach Häufigkeit absteigend
#              "natural"  -> natürliche Reihenfolge (z. B. Altersklassen),
#                            NICHT nach Häufigkeit
#              Vektor     -> explizite Reihenfolge der Kategorien
bar_plot <- function(df, titel, vertical = TRUE, order = "count",
                     xlab = "Category", ylab = "Frequency") {
  if (nrow(df) == 0) return(NULL)
  df <- aggregate(Anzahl ~ Kategorie, data = df, FUN = sum)

  if (is.character(order)) {
    if (order == "count") {
      df <- df[order(-df$Anzahl), , drop = FALSE]
      ord <- rev(df$Kategorie)
    } else if (order == "natural") {
      ord <- age_order(unique(df$Kategorie))
    } else {
      ord <- order
    }
  } else {
    ord <- order
  }
  df$Kategorie <- factor(df$Kategorie, levels = ord)

  p <- ggplot(df, aes(x = Kategorie, y = Anzahl)) +
    geom_col(fill = BAR_FILL, width = 0.7, colour = "black", linewidth = 0.2) +
    labs(title = titel, x = xlab, y = ylab) +
    theme_journal()

  if (vertical) {
    # Vertikale Balken mit Beschriftung darüber
    p + geom_text(aes(label = Anzahl), vjust = -0.5, size = 3, colour = "black") +
      scale_y_continuous(expand = expansion(mult = c(0, 0.15)))
  } else {
    # Horizontale Balken mit Beschriftung rechts daneben
    p + coord_flip() +
      geom_text(aes(label = Anzahl), hjust = -0.2, size = 3, colour = "black") +
      scale_y_continuous(expand = expansion(mult = c(0, 0.15)))
  }
}

# Histogramm für ganzzahlige Verteilung (Anzahl X je Einheit/Schritt)
hist_plot <- function(nv, titel, xlab, ylab = "Frequency") {
  if (is.null(nv) || length(nv) == 0) return(NULL)
  df <- named_df(nv)
  df$x <- suppressWarnings(as.numeric(df$Kategorie))
  if (any(is.na(df$x))) df$x <- seq_len(nrow(df))
  ggplot(df, aes(x = x, y = Anzahl)) +
    geom_col(fill = BAR_FILL, width = 0.7, colour = "black", linewidth = 0.2) +
    geom_text(aes(label = Anzahl), vjust = -0.5, size = 3, colour = "black") +
    scale_x_continuous(breaks = seq(min(df$x), max(df$x), by = 1)) +
    scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(title = titel, x = xlab, y = ylab) +
    theme_journal()
}

# Histogramm der Altersverteilung: Die Daten liegen bereits als Altersklassen
# gebündelt vor (z. B. "0-17", "18-29", ..., "80+", "unbekannt"). Jede Klasse
# wird als Rechteck über ihrem Altersintervall auf einer kontinuierlichen
# x-Achse (Jahre) gezeichnet — echte Histogramm-Darstellung, keine Balken.
# "80+" ist offen -> oben bei `open_upper` abgeschnitten (nur Anzeige).
# "unbekannt" kann nicht auf der Achse platziert werden -> als Caption ausgegeben.
age_hist <- function(nv, titel, xlab = "Age (years)", ylab = "Cases",
                     open_upper = 90) {
  if (is.null(nv) || length(nv) == 0) return(NULL)

  unknown_keys <- c("unbekannt", "unknown", "unbestimmt")
  is_unknown   <- names(nv) %in% unknown_keys
  unknown      <- sum(as.numeric(unlist(nv[is_unknown])), na.rm = TRUE)

  plot_names <- names(nv)[!is_unknown]
  if (length(plot_names) == 0) return(NULL)

  # Bin-Grenzen parsen: "a-b" -> [a, b+1) ; "a+" -> [a, open_upper)
  bins <- t(vapply(plot_names, function(k) {
    if (grepl("^([0-9]+)-([0-9]+)$", k)) {
      m <- regmatches(k, regexec("^([0-9]+)-([0-9]+)$", k))[[1]]
      c(as.numeric(m[2]), as.numeric(m[3]) + 1)
    } else if (grepl("^([0-9]+)\\+$", k)) {
      m <- regmatches(k, regexec("^([0-9]+)\\+$", k))[[1]]
      c(as.numeric(m[2]), open_upper)
    } else {
      c(NA_real_, NA_real_)
    }
  }, numeric(2)))

  df <- data.frame(xmin = bins[, 1], xmax = bins[, 2],
                   Anzahl = as.numeric(unlist(nv[plot_names])))
  df <- df[!is.na(df$xmin), , drop = FALSE]
  if (nrow(df) == 0) return(NULL)

  p <- ggplot(df) +
    geom_rect(aes(xmin = xmin, xmax = xmax, ymin = 0, ymax = Anzahl),
              fill = BAR_FILL, colour = "black", linewidth = 0.2) +
    geom_text(aes(x = (xmin + xmax) / 2, y = Anzahl, label = Anzahl),
              vjust = -0.5, size = 3, colour = "black") +
    scale_x_continuous(breaks = seq(floor(min(df$xmin)), open_upper, by = 10),
                       limits = c(floor(min(df$xmin)), open_upper)) +
    scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(title = titel, x = xlab, y = ylab) +
    theme_journal()

  if (unknown > 0) {
    p <- p + labs(caption = sprintf("Unknown age: %d case(s)", unknown))
  }
  p
}

# Zwei Grobs auf einer Seite zeichnen (Titel über grid.arrange)
arrange_plots <- function(grobs, titel, ncol = 2) {
  grobs <- Filter(Negate(is.null), grobs)
  if (length(grobs) == 0) return(invisible(NULL))
  gridExtra::grid.arrange(grobs = grobs, ncol = min(ncol, length(grobs)),
                          top = grid::textGrob(titel, gp = grid::gpar(fontsize = 14, fontface = "bold")))
}

# Ein einzelnes Diagramm auf einer Seite
plot_one <- function(grob, titel) {
  if (is.null(grob)) return(invisible(NULL))
  gridExtra::grid.arrange(grob, top = grid::textGrob(titel, gp = grid::gpar(fontsize = 14, fontface = "bold")))
}

# Minimales Tabellen-Thema im Journal-Stil
table_theme <- function() {
  gridExtra::ttheme_minimal(
    core = list(bg_params = list(fill = c("grey97", "white"))),
    colhead = list(fg_params = list(fontface = "bold"))
  )
}

# ---------------------------------------------------------------------------
# PDF öffnen
# ---------------------------------------------------------------------------
dir.create(dirname(pdf_out), showWarnings = FALSE, recursive = TRUE)
cairo_pdf(pdf_out, width = 11, height = 8.5, onefile = TRUE)

# ---- Seite 1: Übersicht + Geschlechter + Alter ----------------------------
u <- e$uebersicht
overview <- data.frame(
  `Indicator`        = c("DocumentReferences (documents)",
                         "Patients with ≥ 1 document",
                         "Cases (institution contacts)"),
  `Value`            = c(u$anzahl_dokumente, u$anzahl_patienten, u$anzahl_faelle),
  check.names         = FALSE
)
new_page("GeMTeX – Cohort Analysis (FHIR R4 / MII)")
gridExtra::grid.table(overview, rows = NULL, theme = table_theme())

# Geschlechter (Englisch)
df_g <- named_df(e$geschlechter)
if (nrow(df_g) > 0) {
  lu <- c(male = "Male", female = "Female", unknown = "Unknown",
          other = "Other", weiblich = "Female", männlich = "Male", unbekannt = "Unknown")
  df_g$Kategorie <- ifelse(df_g$Kategorie %in% names(lu),
                           unname(lu[df_g$Kategorie]), df_g$Kategorie)
  df_g <- aggregate(Anzahl ~ Kategorie, data = df_g, FUN = sum)
  plot_one(bar_plot(df_g, "Sex distribution (per case)",
                    xlab = "Sex", ylab = "Cases"),
           "Sex distribution (per case)")
}

# Alter — Histogramm der Altersklassen (kontinuierliche x-Achse in Jahren)
df_a <- named_df(e$alter)
if (nrow(df_a) > 0) {
  nv_a <- setNames(as.list(df_a$Anzahl), df_a$Kategorie)
  plot_one(age_hist(nv_a, "Age distribution (per case)",
                    xlab = "Age (years)", ylab = "Cases"),
           "Age distribution (per case)")
}

# ---- Fachabteilungen ------------------------------------------------------
fa <- e$fachabteilungen
if (length(fa$top10) > 0) {
  if (is.data.frame(fa$top10)) {
    codes_t10 <- as.character(fa$top10$code)
    anz_t10   <- as.numeric(fa$top10$anzahl)
  } else {
    codes_t10 <- vapply(fa$top10, function(x) x$code, "")
    anz_t10   <- vapply(fa$top10, function(x) as.numeric(x$anzahl), 0)
  }
  df_fa <- data.frame(
    Kategorie = c(codes_t10, "Other departments", "No information"),
    Anzahl    = c(anz_t10, fa$uebrige, fa$keine_angabe),
    stringsAsFactors = FALSE
  )
  plot_one(bar_plot(df_fa, "Departments", xlab = "Department code", ylab = "Cases"),
           "Departments (Top 10 + Other + No information)")
}

# ---- Histogramme: Fälle/Patient, Docs/Fall --------------------------------
arrange_plots(list(
  hist_plot(e$faelle_pro_patient, "Number of cases per patient", "Cases per patient"),
  hist_plot(e$docs_pro_fall, "Number of DocumentReferences per case", "Documents per case")
), "Cases per patient  &  Documents per case")

# ---- Liegezeit (VERTIKALE Balken) + ICD ------------------------------------
df_lz <- named_df(e$liegezeit)
if (nrow(df_lz) > 0) {
  df_lz$Kategorie <- vapply(df_lz$Kategorie, function(k) {
    if (grepl("Liegezeit", k)) "Not determinable"
    else {
      d <- suppressWarnings(as.numeric(sub("^([0-9]+).*$", "\\1", k)))
      if (!is.na(d)) paste0(d, " day", ifelse(d == 1, "", "s")) else k
    }
  }, "")
  plot_one(bar_plot(df_lz, "Length of stay", vertical = TRUE, order = "natural",
                    xlab = "Length of stay", ylab = "Cases"),
           "Length of stay (days)")
}

df_icd <- named_df(e$icd)
if (nrow(df_icd) > 0) {
  plot_one(bar_plot(df_icd, "ICD-10 (first 3 digits, per case/diagnosis instance)",
                    xlab = "ICD-10 code prefix", ylab = "Count"),
           "ICD-10 (first 3 digits)")
}

# ---- DocumentReference.type (KDL / XDS) -----------------------------------
dt <- e$documentreference_type
arrange_plots(list(
  bar_plot(named_df(dt$kdl), "KDL system", xlab = "KDL code", ylab = "Count"),
  bar_plot(named_df(dt$xds), "XDS system", xlab = "XDS code", ylab = "Count")
), sprintf("DocumentReference.type – KDL / XDS\n(type not defined: %d)", dt$nicht_definiert))

# ---- Verknüpfungs-Check (Zusammenfassung) ---------------------------------
vk <- e$verknuepfungscheck
new_page("Link check (broken-reference check)")
if (is.data.frame(vk) && nrow(vk) > 0) {
  vk$ok <- as.logical(vk$aufloesbar) & as.logical(vk$typ_ok)
  agg <- aggregate(vk$ok, by = list(Edge = vk$kante), FUN = function(x) c(OK = sum(x), Broken = sum(!x)))
  agg2 <- do.call(rbind, lapply(seq_len(nrow(agg)), function(i) {
    data.frame(Edge = agg$Edge[i], OK = agg$x[i][1], Broken = agg$x[i][2])
  }))
  gridExtra::grid.table(agg2, rows = NULL, theme = table_theme())
}

# ---- Profil-Check (Zusammenfassung) ---------------------------------------
pc <- e$profilcheck
new_page("DocumentReference profile check (lightweight)")
if (is.data.frame(pc) && nrow(pc) > 0) {
  s <- data.frame(
    Criterion = c("Profile referenced", "Status present", "Type present",
                  "Subject present", "Content/Attachment", "Context.Encounter",
                  "Fully conformant"),
    Count = c(sum(pc$profil), sum(pc$status), sum(pc$type),
              sum(pc$subject), sum(pc$content), sum(pc$context_encounter),
              sum(pc$gesamt)),
    stringsAsFactors = FALSE
  )
  s$`Proportion (%)` <- round(100 * s$Count / nrow(pc), 1)
  gridExtra::grid.table(s, rows = NULL, theme = table_theme())
} else {
  grid::grid.text("No documents available", y = 0.5)
}

dev.off()
cat("PDF-Bericht erzeugt:", pdf_out, "\n")
