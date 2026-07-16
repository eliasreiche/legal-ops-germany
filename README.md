# legal-ops-germany

[![CI](https://github.com/eliasreiche/legal-ops-germany/actions/workflows/ci.yml/badge.svg)](https://github.com/eliasreiche/legal-ops-germany/actions/workflows/ci.yml)

Open-Source-Library aus **Claude-Skills und deterministischen Python-Executors** für die
**non-billable Workflows** deutscher Boutique- und Kleinkanzleien — Fristenberechnung
(ZPO/BGB) mit Kalender-Export, Gebühren (RVG/GKG), GwG-Risikoklassifizierung mit
verifizierter Hochrisiko-Länderliste, Aktenkopf-Extraktion, Interessenkollisions-Check,
DATEV-EXTF-Export und mehr. **19 Skills, davon 1 `getestet` und 9 in `beta`** (Status-Tabelle unten).
Funktionsweise ausschließlich nach deutschem Recht.

> **Keine Rechtsberatung.** Diese Library unterstützt organisatorische und rechnerische
> Abläufe der Kanzlei. Jedes Ergebnis unterliegt der Zweitkontrolle durch die Kanzlei;
> Fristen- und Gebührenergebnisse ersetzen keine anwaltliche Kontrolle.

> **Unofficial & in aktiver Entwicklung.** Unabhängiges Community-Projekt für
> [Claude Code](https://claude.com/claude-code) — not affiliated with, endorsed,
> or sponsored by Anthropic PBC; „Claude" und „Anthropic" sind Marken der
> Anthropic PBC. Die Library wird laufend weiterentwickelt; **Feedback, Issues
> und Erfahrungsberichte sind ausdrücklich willkommen.**

## Zulässigkeit & Grenzen

Diese Library ist in Gänze **Beta und kein geprüftes Produkt** — es hat keine unabhängige
juristische oder aufsichtsrechtliche Prüfung stattgefunden. Das gilt auch dann, wenn ein Label „getestet" lautet oder von händischen oder automatisierten Testläufen gesprochen wird. Sie trifft **keine Aussage**
zur Zulässigkeit eines Einsatzes im konkreten Mandat oder Unternehmen. Ob und wie die
Skills produktiv genutzt werden dürfen, muss die Kanzlei vor dem Einsatz selbst prüfen —
insbesondere im Hinblick auf:

- **Berufsrecht & Mandatsgeheimnis** — §§ 203, 204 StGB, § 43a Abs. 2 / § 43e BRAO, § 2
  BORA, §§ 53, 97, 160a StPO.
- **Datenschutz** — DSGVO / BDSG, einschließlich **Drittlandtransfer** (Art. 44 ff. DSGVO)
  und der Reichweite von **US Cloud Act / FISA** beim gewählten Modell- und Hosting-Anbieter.
- **KI-Verordnung** — VO (EU) 2024/1689 (Risiko-Einstufung, Transparenz- und
  Betreiberpflichten).

**Mandantendaten gehören ausschließlich in regulatorisch und technisch sichere Tools.** Optionale Live-Anbindungen (vorhandene MCP-Konnektoren, z. B. Microsoft 365;
EU-/UN-Sanktionslisten geplant) geben Daten nach außen — Freigabe des jeweiligen
Datenflusses ist Sache der Kanzlei.

## Wie es funktioniert

- **Claude orchestriert, Python rechnet.** Alles mit Zahlen, Daten, Fristen oder Geld
  wird von Executors in [`plugins/legal-ops/core/calc/`](plugins/legal-ops/core/calc/)
  deterministisch berechnet — nie vom Modell generiert.
- **Datei rein, Datei raus.** Jeder Skill arbeitet über Datei-Schnittstellen (CSV, PDF,
  EML, iCal, DATEV-EXTF, DOCX) — kompatibel mit dem Export/Import jeder Kanzleisoftware.
  Live-Anbindung ist optional und nutzt **vorhandene MCP-Konnektoren** (z. B.
  Microsoft 365), gebündelt in genau einem Skill (`kontext-sync`) — eigener
  Integrations-Code für Kanzleisoftware ist bewusst nicht enthalten (Verweis auf
  die API-Doku des Herstellers bzw. „Integration geplant").
- **Kontext-Layer.** Ein per-Kanzlei-Ordner `kontext/` (Kanzlei-Profil,
  `mandate/<az>.md`, Kontakte) ist die einzige Schnittstelle der Skills zu
  Kanzlei-Wissen — befüllt per Datei-Adapter oder MCP-Sync, von einem Executor
  validiert ([`plugins/legal-ops/core/context/`](plugins/legal-ops/core/context/)).
  Aufbewahrungs-Hinweise nach § 50 BRAO liefert ein Retention-Executor — **gelöscht
  wird nie automatisch**.
- **Ehrliche Labels.** Jeder Skill trägt sichtbar seinen Reifegrad:
  - 🚧 `Work-in-progress` — noch nicht entwickelt (Stub) oder Code vorhanden, aber noch kein Test-Run.
  - 🧪 `beta` — gegen Testdaten durch Agenten getestet (Tests/Orakel-Fälle laufen grün in CI).
  - ✅ `getestet` — live (händisch) getestet durch den Maintainer, **aber keine Garantie für die Funktionsweise in Production**.

  Automatisierte Tests allein rechtfertigen höchstens `beta`; `getestet` ist eine ehrliche Live-Abnahme, kein Produktions-Freibrief.
- **Berufsrechts-Gate.** Jeder Skill dokumentiert im Frontmatter seine RDG-Einordnung,
  Datenhinweise (§ 203 StGB, DSGVO/BRAO) und Haftungsgrenzen — vom Lint erzwungen.

Hausregeln: [CONVENTIONS.md](CONVENTIONS.md) · Struktur: ein Plugin
[`legal-ops`](plugins/legal-ops/) bündelt alle Skills (fachlich in Prozessbereiche
plus Querschnitt gegliedert, Feld `bereich:` im Frontmatter) **und** die
geteilten Rechner unter [`plugins/legal-ops/core/`](plugins/legal-ops/core/) —
so ist `core/` Teil der Auslieferung und jeder Executor-Skill nach dem Install
lauffähig.

## Skill-Status

Tabelle wird generiert von [`plugins/legal-ops/core/verify/struktur_lint.py`](plugins/legal-ops/core/verify/struktur_lint.py) (`--write-readme`).

<!-- skill-status:start -->
| Skill | Bereich | Welle | Status |
|---|---|---|---|
| [`fristenrechner`](plugins/legal-ops/skills/fristenrechner/SKILL.md) | `fristen-termine` | 1 | ✅ `getestet` |
| [`zitat-pruefer`](plugins/legal-ops/skills/zitat-pruefer/SKILL.md) | `querschnitt` | 1 | 🚧 `Work-in-progress` |
| [`rvg-gkg-rechner`](plugins/legal-ops/skills/rvg-gkg-rechner/SKILL.md) | `zeit-abrechnung` | 1 | 🧪 `beta` |
| [`gwg-risiko-check`](plugins/legal-ops/skills/gwg-risiko-check/SKILL.md) | `compliance` | 2 | 🧪 `beta` |
| [`interessenkollision-check`](plugins/legal-ops/skills/interessenkollision-check/SKILL.md) | `compliance` | 2 | 🧪 `beta` |
| [`aktenkopf-extraktor`](plugins/legal-ops/skills/aktenkopf-extraktor/SKILL.md) | `intake` | 2 | 🧪 `beta` |
| [`email-akten-zuordnung`](plugins/legal-ops/skills/email-akten-zuordnung/SKILL.md) | `post-akte` | 3 | 🧪 `beta` |
| [`kontext-sync`](plugins/legal-ops/skills/kontext-sync/SKILL.md) | `querschnitt` | 3 | 🧪 `beta` |
| [`passive-zeiterfassung`](plugins/legal-ops/skills/passive-zeiterfassung/SKILL.md) | `zeit-abrechnung` | 3 | 🧪 `beta` |
| [`taetigkeitstext-rvg`](plugins/legal-ops/skills/taetigkeitstext-rvg/SKILL.md) | `zeit-abrechnung` | 3 | 🧪 `beta` |
| [`gwg-live-screening`](plugins/legal-ops/skills/gwg-live-screening/SKILL.md) | `compliance` | 4 | 🚧 `Work-in-progress` |
| [`fristen-docketing-light`](plugins/legal-ops/skills/fristen-docketing-light/SKILL.md) | `fristen-termine` | 4 | 🚧 `Work-in-progress` |
| [`posteingang-ocr-verteilung`](plugins/legal-ops/skills/posteingang-ocr-verteilung/SKILL.md) | `post-akte` | 4 | 🚧 `Work-in-progress` |
| [`datev-export`](plugins/legal-ops/skills/datev-export/SKILL.md) | `zeit-abrechnung` | 4 | 🧪 `beta` |
| [`honorar-mahnwesen`](plugins/legal-ops/skills/honorar-mahnwesen/SKILL.md) | `zeit-abrechnung` | 4 | 🚧 `Work-in-progress` |
| [`termin-assistent`](plugins/legal-ops/skills/termin-assistent/SKILL.md) | `fristen-termine` | 5 | 🚧 `Work-in-progress` |
| [`sachstandsmitteilung`](plugins/legal-ops/skills/sachstandsmitteilung/SKILL.md) | `kommunikation` | 5 | 🚧 `Work-in-progress` |
| [`kanzlei-sop-qualitygate`](plugins/legal-ops/skills/kanzlei-sop-qualitygate/SKILL.md) | `wissen-qm` | 5 | 🚧 `Work-in-progress` |
| [`wissensmanagement-precedents`](plugins/legal-ops/skills/wissensmanagement-precedents/SKILL.md) | `wissen-qm` | 5 | 🚧 `Work-in-progress` |
<!-- skill-status:ende -->

## Nutzung

Voraussetzung ist ein datenschutzkonformer Claude-Zugang der Kanzlei (z. B. Claude Code /
Cowork über AWS Bedrock, Region Frankfurt). Die Kanzlei lädt dieses Repo selbst — es gibt
kein Hosting und keine Datenhaltung durch die Library.

**Weg 1 — mit Git (empfohlen, bekommt Updates):** in Claude Code

```
/plugin marketplace add eliasreiche/legal-ops-germany
/plugin install legal-ops@legal-ops-germany
```

Aktualisieren später mit `claude plugin marketplace update legal-ops-germany`.

**Weg 2 — per ZIP (ohne Git):** auf der
[Releases-Seite](https://github.com/eliasreiche/legal-ops-germany/releases)
beim aktuellen Release „Source code (zip)" laden, entpacken, dann in Claude Code:

```
/plugin marketplace add /pfad/zum/entpackten/ordner
/plugin install legal-ops@legal-ops-germany
```

> Die ZIP-Installation ist ein **eingefrorener Stand** — sie aktualisiert sich
> nicht. Für einen neuen Stand das ZIP des neuesten Release laden und den
> Marketplace-Eintrag auf den neuen Ordner zeigen lassen.

Details je Skill im jeweiligen `SKILL.md`; Manifest:
[`marketplace.json`](.claude-plugin/marketplace.json).

### Voraussetzungen

Python ≥ 3.x und `pytest` sind unter [Entwicklung](#entwicklung) beschrieben
(nur zum Ausführen der Tests nötig, nicht für den Skill-Betrieb selbst).

**Optionale System-Werkzeuge** — je nachdem, welche eingehenden
Dokumentformate ein Skill verarbeiten soll:

| Werkzeug | Wofür |
|---|---|
| `poppler` | PDF-Textextraktion und -Rendering |
| `pandoc` | DOCX → Markdown-Konvertierung |

```bash
# macOS
brew install poppler pandoc

# Debian/Ubuntu
apt-get install poppler-utils pandoc
```

Ohne diese Werkzeuge laufen die Executors unverändert weiter — sie
bündeln keine Binärabhängigkeiten (Claude-Code-Plugin = Skripte + Markdown).
Nur die Dokument-Konvertierung davor (PDF/DOCX → Text/Markdown) braucht dann
Handarbeit oder andere Werkzeuge.

## Entwicklung

```bash
python3 plugins/legal-ops/core/verify/struktur_lint.py   # Struktur-Lint (P4/P5 + Containment)
pip install pytest && pytest -q                           # Tests (inkl. Install-Smoke-Test)
```

## Lizenz

[Apache-2.0](LICENSE) · Attributionen: [NOTICE](NOTICE)
