---
name: fristen-docketing-light
description: "Exportiert berechnete Fristen (aus fristenrechner-de) als iCal/CSV für Kanzlei-Kalender oder Kanzleisoftware. Triggert bei Fristen exportieren, Fristenkalender-Import, iCal/CSV der Fristen, Docketing. Work-in-progress (Welle 4)."
status: Work-in-progress
welle: 4
plugin: fristen-termine
rdg_einordnung: "Technischer Export rechnerisch ermittelter Termine; keine Fristenverwaltung als Dienstleistung."
daten_hinweis: "Fristdaten können Aktenzeichen tragen — Exportdateien wie Akten behandeln."
haftung: "Import und Kontrolle im Zielsystem verantwortet die Kanzlei; ersetzt keinen Fristenkalender mit Vier-Augen-Prinzip."
---

# fristen-docketing-light

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 4).

## Zweck

Exportiert berechnete Fristen (aus fristenrechner-de) als iCal/CSV zum Import in Kanzlei-Kalender oder Kanzleisoftware.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
