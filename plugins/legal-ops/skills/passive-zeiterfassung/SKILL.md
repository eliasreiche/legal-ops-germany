---
name: passive-zeiterfassung
description: "Rekonstruiert aus MS-Graph-Kalender und -Mail-Metadaten Zeiterfassungs-Vorschläge je Akte zum Bestätigen oder Verwerfen. Triggert bei Zeiterfassung, Stunden rekonstruieren, Timesheet-Vorschlag, erfasste Zeiten je Akte. Work-in-progress (Welle 3)."
status: Work-in-progress
welle: 3
plugin: zeit-abrechnung
rdg_einordnung: "Interner Verwaltungsvorschlag; keine Rechtsdienstleistung."
daten_hinweis: "Metadaten-Auswertung des Kanzlei-Tenants — Betroffenen-Transparenz intern klären; DSGVO-/BRAO-konformer Modellzugang."
haftung: "Vorschläge sind Schätzungen aus Metadaten; abrechnungsrelevante Zeiten bestätigt die Kanzlei."
---

# passive-zeiterfassung

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 3).

## Zweck

Rekonstruiert aus MS-Graph-Kalender und -Mail-Metadaten Zeiterfassungs-Vorschläge je Akte, die die Kanzlei bestätigt oder verwirft.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
