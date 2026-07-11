---
name: fristenrechner-de
status: ungetestet
welle: 1
plugin: fristen-termine
rdg_einordnung: "Rechnerische Fristermittlung ohne Subsumtion des Einzelfalls; die rechtliche Einordnung des fristauslösenden Ereignisses bleibt beim Anwalt."
daten_hinweis: "Benötigt nur Datum, Fristart und Bundesland — keine Mandantendaten erforderlich."
haftung: "Zweitkontrolle, zwingend: Ergebnis ersetzt keine anwaltliche Fristenkontrolle (Vier-Augen-Prinzip der Kanzlei bleibt bestehen)."
---

# fristenrechner-de

> **Status: `ungetestet`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 1).

## Zweck

Berechnet Fristen nach ZPO/BGB (Ereignis-/Beginnfrist, Wochenende-/Feiertagsverschiebung, Bundesland-Feiertage) deterministisch über core/calc/fristen.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
