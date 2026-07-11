# CONVENTIONS — Hausregeln

Verbindlich für jeden Skill, Executor und jede Doku-Seite in diesem Repo.
Der [Struktur-Lint](core/verify/struktur_lint.py) erzwingt die maschinenprüfbaren Teile in CI.

## Sprache & Zielgruppe

- **Deutsch** ist die Arbeits- und Doku-Sprache (Zielgruppe: deutsche Boutique- und Kleinkanzleien).
- Fachbegriffe (RVG, GwG, ZPO, beA, DATEV, e-Akte) werden nicht übersetzt.

## Fünf Grundprinzipien (Kurzform)

1. **Prozesszentrierte Taxonomie** — 7 Prozesskategorien = 7 Plugins; kein Rechtsgebiets-Schnitt.
2. **Datei-Schnittstelle immer, Connector optional** — jeder Skill definiert Ein-/Ausgaben als Dateien (CSV, PDF, EML, iCal, EXTF, DOCX); Live-Adapter (MS Graph, Sanktionslisten) füttern dieselbe Schnittstelle.
3. **Deterministik-Grenze** — alles mit Zahlen, Daten, Fristen oder Geld rechnet ein Python-Executor in `core/calc/`, nie das Modell. Modellgenerierte Werte in Zahlenfeldern sind ein Testfehler.
4. **Test-Disziplin trägt die Glaubwürdigkeit** — jeder Skill hat `tests/`; Rechner haben Orakel-Fälle gegen borghei `legal_calc`; CI läuft bei jedem Push.
5. **Berufsrechts-Gate** — jedes `SKILL.md` trägt `rdg_einordnung`, `daten_hinweis`, `haftung` im Frontmatter (Pflichtfelder, Lint-erzwungen).

## Skill-Frontmatter (Pflichtfelder)

```yaml
---
name: <verzeichnisname>            # muss dem Ordnernamen entsprechen
status: ungetestet | beta | getestet   # Reifegrad-Leiter, siehe unten
welle: 1-5                         # Build-Reihenfolge
plugin: <plugin> | querschnitt
rdg_einordnung: "Warum keine Rechtsdienstleistung / wo die Grenze des Outputs liegt."
daten_hinweis: "Welche Daten hinein dürfen; § 203 StGB / DSGVO / BRAO-konformer Modellzugang."
haftung: "Zweitkontroll-Klausel; bei Fristen/Gebühren zwingend."
haendisch_getestet: JJJJ-MM-TT     # nur bei status: getestet (Pflicht, Datum der Abnahme)
---
```

### Reifegrad-Leiter

| Status | Bedeutung | Lint-Voraussetzung |
|---|---|---|
| 🚧 `ungetestet` | Stub oder Implementierung ohne Absicherung | — |
| 🧪 `beta` | Tests gegen Testdaten/Orakel-Fälle laufen grün in CI | echte Dateien in `tests/` |
| ✅ `getestet` | zusätzlich **händisch abgenommen** (durch den Maintainer) | wie `beta` + `haendisch_getestet: <Datum>` |

Ein Status wird nie übersprungen dokumentiert: `getestet` setzt inhaltlich voraus, dass
die `beta`-Kriterien erfüllt sind. Automatisierte Tests allein rechtfertigen höchstens `beta`.

## Zitierdisziplin (3-Zustands-Marker)

Jede Norm-, Urteils- oder Fundstellen-Angabe in generierten Texten trägt einen Marker:

- ✅ **verifiziert** — gegen Quelle/Executor geprüft
- ⚠️ **nicht prüfbar** — Quelle lag nicht vor; Angabe stammt aus dem Input
- ❌ **abweichend** — Prüfung ergab eine Abweichung (mit Fundstelle)

Unmarkierte Zitate sind ein Lint-/Review-Fehler. Der Querschnitts-Skill
[`zitat-verifier-de`](core/verify/zitat-verifier-de/SKILL.md) automatisiert die Prüfung.

## Anti-Halluzination

- Kein Skill erfindet Aktenzeichen, Beträge, Daten oder Normzitate. Fehlende Angaben werden als **Lücke** ausgewiesen, nie ergänzt.
- Output-Kontrakt: jeder Zahlen-/Datums-/Geldwert ist als Executor-Ergebnis gekennzeichnet.
- Skills, die Schreiben draften (`kommunikation`), erzeugen **Entwürfe** — Versand ist immer Kanzlei-Entscheidung.

## Gliederung eines SKILL.md

`# <name>` → Zweck → Eingaben (Datei-Kontrakt) → Ablauf → Output-Format → Beispiele.

## Was dieses Repo nicht ist

Keine Rechtsberatung, keine Rechtsgebiets-Skills (Schriftsätze, Gutachten), kein Hosting,
keine beA-/DATEV-Live-Integration (nur Datei-Brücken). Details: Projekt-Doku.
