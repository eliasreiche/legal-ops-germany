---
name: posteingang-ocr-routing
description: "OCR über gescannten Papier-Posteingang, extrahiert Absender/Aktenzeichen/Fristbezug und routet in eine Hotfolder-Ablage. Triggert bei Posteingang scannen, OCR Papierpost, Post routen, Scan-Ablage. Work-in-progress (Welle 4)."
status: Work-in-progress
welle: 4
plugin: post-akte
rdg_einordnung: "Organisatorische Postverarbeitung; keine inhaltliche Bearbeitung."
daten_hinweis: "Scans tragen Mandatsbezug — lokale OCR bevorzugen, sonst DSGVO-/BRAO-konformer Modellzugang; § 203 StGB beachten."
haftung: "Fristauslösende Eingänge sind gesondert der Fristenkontrolle zuzuführen; OCR-Fehler möglich."
---

# posteingang-ocr-routing

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 4).

## Zweck

OCR über gescannten Papier-Posteingang, extrahiert Absender/Aktenzeichen/Fristbezug und routet in eine Hotfolder-Ablagekonvention.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
