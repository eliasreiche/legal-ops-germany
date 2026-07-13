---
name: datev-export
description: "Erzeugt aus Kanzlei-Belegdaten importierbare DATEV-EXTF-Buchungsstapel (dateibasiert). Triggert bei DATEV-Export, Buchungsstapel, EXTF, Buchhaltung übergeben, Belege exportieren. Work-in-progress (Welle 4)."
status: Work-in-progress
welle: 4
plugin: wissen-qm
rdg_einordnung: "Technische Formatkonvertierung für die Buchhaltung; keine Steuer- oder Rechtsberatung."
daten_hinweis: "Buchungsdaten enthalten Mandantennamen — Export minimieren, DSGVO beachten."
haftung: "EXTF-Stapel vor Import in DATEV durch Buchhaltung/Steuerberater prüfen; Summen werden deterministisch berechnet."
---

# datev-export

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 4).

## Zweck

Erzeugt aus Kanzlei-Belegdaten importierbare DATEV-EXTF-Buchungsstapel (dateibasiert, core/calc/extf) — die einzige offene DATEV-Tür.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
