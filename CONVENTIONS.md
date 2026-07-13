# CONVENTIONS — Hausregeln

Verbindlich für jeden Skill, Executor und jede Doku-Seite in diesem Repo.
Der [Struktur-Lint](plugins/legal-ops/core/verify/struktur_lint.py) erzwingt die maschinenprüfbaren Teile in CI.

## Sprache & Zielgruppe

- **Deutsch** ist die Arbeits- und Doku-Sprache (Zielgruppe: deutsche Boutique- und Kleinkanzleien).
- Fachbegriffe (RVG, GwG, ZPO, beA, DATEV, e-Akte) werden nicht übersetzt.

## Fünf Grundprinzipien (Kurzform)

1. **Prozesszentrierte Taxonomie** — 7 Prozesskategorien (Frontmatter-Feld `plugin:`), ausgeliefert als **ein** Plugin `legal-ops` (`core/` liegt darin, siehe D14); kein Rechtsgebiets-Schnitt.
2. **Datei-Schnittstelle immer, Connector optional** — jeder Skill definiert Ein-/Ausgaben als Dateien (CSV, PDF, EML, iCal, EXTF, DOCX); Live-Adapter (MS Graph, Sanktionslisten) füttern dieselbe Schnittstelle.
3. **Deterministik-Grenze** — alles mit Zahlen, Daten, Fristen oder Geld rechnet ein Python-Executor in `core/calc/`, nie das Modell. Modellgenerierte Werte in Zahlenfeldern sind ein Testfehler.
4. **Test-Disziplin trägt die Glaubwürdigkeit** — jeder Skill hat `tests/`; Rechner haben Orakel-Fälle gegen borghei `legal_calc`; CI läuft bei jedem Push.
5. **Berufsrechts-Gate** — jedes `SKILL.md` trägt `rdg_einordnung`, `daten_hinweis`, `haftung` im Frontmatter (Pflichtfelder, Lint-erzwungen).

## Naming-Konvention für Skill-Slugs (D17)

Der Ordnername unter `plugins/legal-ops/skills/` (== `name:`-Frontmatter, Lint-erzwungen) folgt:

- **Deutschsprachig** — wie der Rest der Doku (siehe Sprache & Zielgruppe oben).
- **Funktion statt Implementierung** — der Slug benennt, was der Skill für die
  Kanzlei tut (`fristenrechner`, `zitat-pruefer`, `sachstandsmitteilung`),
  nicht wie oder womit er es tut. Kein Technologie-Wort im Namen, das das
  nächste Refactoring bricht.
- **Kein `-de`-Suffix** — der deutsche Rechtsraum ist der Scope des gesamten
  Repos (siehe Sprache & Zielgruppe), kein Merkmal einzelner Skills. Ein Skill
  ohne DE-Suffix ist genauso deutsch wie einer mit.
- **Kein `-light`-Suffix** — Reifegrad steht im Frontmatter (`status:`,
  Reifegrad-Leiter unten), nicht im Namen. Ein Skill, der heute ein
  Platzhalter ist, kann morgen ausgebaut werden, ohne dass sein Slug lügt.

## Skill-Frontmatter (Pflichtfelder)

```yaml
---
name: <verzeichnisname>            # muss dem Ordnernamen entsprechen
description: "Was der Skill tut + wann er triggert (Skill-Discovery)."
status: Work-in-progress | beta | getestet   # Reifegrad-Leiter, siehe unten
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
| 🚧 `Work-in-progress` | **noch nicht entwickelt** (Stub) **oder** Code vorhanden, aber **noch kein Test-Run** — keine Zusicherung | — |
| 🧪 `beta` | **gegen Testdaten durch Agenten getestet** (Tests/Orakel-Fälle laufen grün in CI); noch keine Live-Abnahme | echte Dateien in `tests/` |
| ✅ `getestet` | **live (händisch) getestet** durch den Maintainer — **aber keine Garantie für die Funktionsweise in Production** | wie `beta` + `haendisch_getestet: <Datum>` |

Ein Status wird nie übersprungen dokumentiert: `getestet` setzt inhaltlich voraus, dass
die `beta`-Kriterien erfüllt sind. Automatisierte Tests allein rechtfertigen höchstens `beta`;
`getestet` ist eine ehrliche Live-Abnahme, kein Produktions-Freibrief.

## Zitierdisziplin (3-Zustands-Marker)

Jede Norm-, Urteils- oder Fundstellen-Angabe in generierten Texten trägt einen Marker:

- ✅ **verifiziert** — gegen Quelle/Executor geprüft
- ⚠️ **nicht prüfbar** — Quelle lag nicht vor; Angabe stammt aus dem Input
- ❌ **abweichend** — Prüfung ergab eine Abweichung (mit Fundstelle)

Unmarkierte Zitate sind ein Lint-/Review-Fehler. Der Querschnitts-Skill
[`zitat-pruefer`](plugins/legal-ops/skills/zitat-pruefer/SKILL.md) automatisiert die Prüfung.

## Anti-Halluzination

- Kein Skill erfindet Aktenzeichen, Beträge, Daten oder Normzitate. Fehlende Angaben werden als **Lücke** ausgewiesen, nie ergänzt.
- Output-Kontrakt: jeder Zahlen-/Datums-/Geldwert ist als Executor-Ergebnis gekennzeichnet.
- Skills, die Schreiben draften (`kommunikation`), erzeugen **Entwürfe** — Versand ist immer Kanzlei-Entscheidung.

## Gliederung eines SKILL.md

`# <name>` → Zweck → Eingaben (Datei-Kontrakt) → Ablauf → Output-Format → Beispiele.

## Review-Gate (unabhängig)

Kein Skill geht ins Repo, ohne dass ein **unabhängiges zweites Augenpaar** die
Änderung freigegeben hat (kod-decisions D12, präzisiert D9). Konkret:

- Freigabe erteilt der Subagent [`.claude/agents/reviewer.md`](.claude/agents/reviewer.md),
  **nicht** das Modell, das den Skill implementiert oder architektiert hat —
  niemand gibt seine eigene Arbeit frei.
- Der Reviewer ist **kontext-blind**: er bekommt nur Kontrakt (`SKILL.md`,
  `schema/`, `core/`) und den Diff, nicht die Implementierungs-Begründung.
- Er liefert genau ein Verdikt: **APPROVED** oder **REJECTED**. Ein `REJECTED`
  trägt zu jedem Blocker einen **reproduzierbaren Fehler** (Kommando mit
  erwartet/tatsächlich oder `datei:zeile`).
- Er ist read-only, hebt **nie** einen Status an und bestätigt **nie**
  `getestet` — das bleibt die händische Abnahme des Maintainers.

Der Reviewer automatisiert damit die Gates dieses Dokuments (Struktur-Lint,
Tests, P3/P5, Zitier- und Anti-Halluzinations-Disziplin) als Torwächter vor dem
Commit.

## Kontext-Layer (D11, D19)

Ein per-Kanzlei-Ordner `kontext/` ist die **einzige** Schnittstelle der
Skills zu Kanzlei-Wissen (Mandate, Parteien, Termine, Kontakte). Kein Skill
liest oder schreibt Kanzleisoftware direkt — Anbindung läuft ausschließlich
über Adapter/MCP-Sync nach `kontext/` (D11a: für Microsoft 365 der
offizielle M365-MCP-Konnektor statt eines eigenen `msgraph`-Adapters; für
Dateien der Referenz-Adapter `filesystem`).

Vollständiger Kontrakt (Ordner-Format, Mandats-Schema, Validierung, Adapter-
Vertrag, Retention): [`core/context/README.md`](plugins/legal-ops/core/context/README.md),
[`core/adapters/README.md`](plugins/legal-ops/core/adapters/README.md),
[`core/calc/retention/README.md`](plugins/legal-ops/core/calc/retention/README.md).
Orchestrierender Skill: [`kontext-sync`](plugins/legal-ops/skills/kontext-sync/SKILL.md).

### Neue optionale Frontmatter-Felder

Ein Skill, der `kontext/` liest oder schreibt, deklariert das im SKILL.md:

```yaml
kontext_reads:
  - mandate/*.md
  - kontakte.md
kontext_writes:
  - mandate/*.md
```

**Kein Pflichtfeld** — die bestehenden 18 Skills bleiben ohne diese Felder
gültig. Wenn vorhanden: Werte müssen nicht-leere Strings sein und mit einem
dokumentierten `kontext/`-Bereich beginnen (`kanzlei.md`, `mandate/`,
`kontakte.md`, `posteingang/`, `export/`) — vom Struktur-Lint erzwungen.

### Retention-Grundsatz — kein Auto-Delete

`mandatsende` im Mandats-Frontmatter speist einen Hinweis-Report
(§ 50 Abs. 1 BRAO, 6 Jahre Handakten, Fristbeginn Schluss des
Kalenderjahres der Mandatsbeendigung). Der zuständige Executor
(`core/calc/retention/executor.py`) **löscht nie** — er markiert nur, was ab
wann löschbar wäre. Die Löschentscheidung und -durchführung bleibt manuelle
Kanzleisache (D10-Auflage: Begründung je Speicherort, Retention, manuelle
Löschung dokumentieren).

## Was dieses Repo nicht ist

Keine Rechtsberatung, keine Rechtsgebiets-Skills (Schriftsätze, Gutachten), kein Hosting,
keine beA-/DATEV-Live-Integration (nur Datei-Brücken). Details: Projekt-Doku.
