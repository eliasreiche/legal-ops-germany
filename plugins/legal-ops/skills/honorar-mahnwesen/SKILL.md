---
name: honorar-mahnwesen
description: "Wertet offene Posten (CSV/EXTF-Export) aus, priorisiert Forderungen und draftet interne Mahn-/Zahlungserinnerungsschreiben an eigene Mandanten. Triggert bei Mahnwesen, offene Rechnungen, Zahlungserinnerung, überfällige Forderungen, offene Posten. Work-in-progress (Welle 4)."
status: Work-in-progress
welle: 4
plugin: zeit-abrechnung
rdg_einordnung: "Internes Forderungsmanagement der Kanzlei in eigener Sache; keine Inkasso-Dienstleistung für Dritte."
daten_hinweis: "Zahlungsdaten von Mandanten — DSGVO-/BRAO-konformen Modellzugang nutzen."
haftung: "Beträge und Verzugsdaten stammen aus dem Executor; Versand der Schreiben entscheidet die Kanzlei."
---

# honorar-mahnwesen

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 4).

## Zweck

Wertet offene Posten (CSV/EXTF-Export) aus, priorisiert Forderungen und draftet interne Mahn-/Erinnerungsschreiben der Kanzlei an eigene Mandanten.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
