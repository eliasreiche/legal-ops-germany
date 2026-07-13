---
name: email-triage-eakte
description: "Ordnet eingehende E-Mails (MS-Graph-Adapter oder EML-Dateien) Akten zu, priorisiert und schlägt Ablage in der e-Akte vor. Triggert bei E-Mail-Triage, Posteingang zuordnen, e-Akte-Ablage, Mail-Priorisierung. Work-in-progress (Welle 3)."
status: Work-in-progress
welle: 3
plugin: post-akte
rdg_einordnung: "Organisatorische Posteingangs-Sortierung; keine inhaltliche Bearbeitung der Korrespondenz."
daten_hinweis: "Mandats-E-Mails — MS-Graph-Zugang nur auf Kanzlei-Tenant, Verarbeitung über DSGVO-/BRAO-konformen Modellzugang; § 203 StGB beachten."
haftung: "Zuordnungsvorschläge sind zu bestätigen; fristauslösende Post ist gesondert der Fristenkontrolle zuzuführen."
---

# email-triage-eakte

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 3).

## Zweck

Ordnet eingehende E-Mails (via MS-Graph-Adapter oder EML-Dateien) Akten zu, priorisiert und schlägt Ablage in der e-Akte-Struktur vor.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
