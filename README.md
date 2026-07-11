# claude-for-legal-non-billable-germany

[![CI](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/actions/workflows/ci.yml/badge.svg)](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/actions/workflows/ci.yml)

Open-Source-Library aus **Claude-Skills und deterministischen Python-Executors** für die
**non-billable Workflows** deutscher Boutique- und Kleinkanzleien — Fristenberechnung
(ZPO/BGB), Gebühren (RVG/GKG), GwG-Risikoprüfung, Intake, E-Mail-Triage, Konflikt-Check
und mehr. Funktionsweise ausschließlich nach deutschem Recht.

> **Keine Rechtsberatung.** Diese Library unterstützt organisatorische und rechnerische
> Abläufe der Kanzlei. Jedes Ergebnis unterliegt der Zweitkontrolle durch die Kanzlei;
> Fristen- und Gebührenergebnisse ersetzen keine anwaltliche Kontrolle.

## Zulässigkeit & Grenzen

Diese Library ist **Beta und kein geprüftes Produkt** — es hat keine unabhängige
juristische oder aufsichtsrechtliche Prüfung stattgefunden. Sie trifft **keine Aussage**
zur Zulässigkeit eines Einsatzes im konkreten Mandat oder Unternehmen. Ob und wie die
Skills produktiv genutzt werden dürfen, muss die Kanzlei vor dem Einsatz selbst prüfen —
insbesondere im Hinblick auf:

- **Berufsrecht & Mandatsgeheimnis** — §§ 203, 204 StGB, § 43a Abs. 2 / § 43e BRAO, § 2
  BORA, §§ 53, 97, 160a StPO.
- **Datenschutz** — DSGVO / BDSG, einschließlich **Drittlandtransfer** (Art. 44 ff. DSGVO)
  und der Reichweite von **US Cloud Act / FISA** beim gewählten Modell- und Hosting-Anbieter.
- **KI-Verordnung** — VO (EU) 2024/1689 (Risiko-Einstufung, Transparenz- und
  Betreiberpflichten).

**Mandantendaten gehören ausschließlich in Tools mit Auftragsverarbeitungsvertrag (AVV)
und EU-Hosting.** Die optionalen Live-Adapter (Microsoft Graph, Sanktionslisten) geben
Daten nach außen — Freigabe des jeweiligen Datenflusses ist Sache der Kanzlei.

## Wie es funktioniert

- **Claude orchestriert, Python rechnet.** Alles mit Zahlen, Daten, Fristen oder Geld
  wird von Executors in [`core/calc/`](core/calc/) deterministisch berechnet — nie vom
  Modell generiert.
- **Datei rein, Datei raus.** Jeder Skill arbeitet über Datei-Schnittstellen (CSV, PDF,
  EML, iCal, DATEV-EXTF, DOCX) — kompatibel mit dem Export/Import jeder Kanzleisoftware.
  Live-Adapter (Microsoft Graph, EU-/UN-Sanktionslisten) sind optional.
- **Ehrliche Labels.** Jeder Skill trägt sichtbar seinen Reifegrad: 🚧 `ungetestet` →
  🧪 `beta` (Tests gegen Testdaten/Orakel-Fälle laufen grün in CI) → ✅ `getestet`
  (zusätzlich händisch abgenommen). Automatisierte Tests allein rechtfertigen höchstens `beta`.
- **Berufsrechts-Gate.** Jeder Skill dokumentiert im Frontmatter seine RDG-Einordnung,
  Datenhinweise (§ 203 StGB, DSGVO/BRAO) und Haftungsgrenzen — vom Lint erzwungen.

Hausregeln: [CONVENTIONS.md](CONVENTIONS.md) · Struktur: 7 Prozesskategorien = 7 Plugins
unter [`plugins/`](plugins/), geteilte Rechner unter [`core/`](core/).

## Skill-Status

Tabelle wird generiert von [`core/verify/struktur_lint.py`](core/verify/struktur_lint.py) (`--write-readme`).

<!-- skill-status:start -->
| Skill | Plugin | Welle | Status |
|---|---|---|---|
| [`fristenrechner-de`](plugins/fristen-termine/skills/fristenrechner-de/SKILL.md) | `fristen-termine` | 1 | 🚧 `ungetestet` |
| [`zitat-verifier-de`](core/verify/zitat-verifier-de/SKILL.md) | `querschnitt` | 1 | 🚧 `ungetestet` |
| [`rvg-gko-rechner`](plugins/zeit-abrechnung/skills/rvg-gko-rechner/SKILL.md) | `zeit-abrechnung` | 1 | 🚧 `ungetestet` |
| [`gwg-risiko-check`](plugins/compliance/skills/gwg-risiko-check/SKILL.md) | `compliance` | 2 | 🚧 `ungetestet` |
| [`konflikt-check-offline`](plugins/compliance/skills/konflikt-check-offline/SKILL.md) | `compliance` | 2 | 🚧 `ungetestet` |
| [`akten-intake-strukturierer`](plugins/intake/skills/akten-intake-strukturierer/SKILL.md) | `intake` | 2 | 🚧 `ungetestet` |
| [`email-triage-eakte`](plugins/post-akte/skills/email-triage-eakte/SKILL.md) | `post-akte` | 3 | 🚧 `ungetestet` |
| [`passive-zeiterfassung`](plugins/zeit-abrechnung/skills/passive-zeiterfassung/SKILL.md) | `zeit-abrechnung` | 3 | 🚧 `ungetestet` |
| [`zeitnarrativ-rvg`](plugins/zeit-abrechnung/skills/zeitnarrativ-rvg/SKILL.md) | `zeit-abrechnung` | 3 | 🚧 `ungetestet` |
| [`gwg-live-screening`](plugins/compliance/skills/gwg-live-screening/SKILL.md) | `compliance` | 4 | 🚧 `ungetestet` |
| [`fristen-docketing-light`](plugins/fristen-termine/skills/fristen-docketing-light/SKILL.md) | `fristen-termine` | 4 | 🚧 `ungetestet` |
| [`posteingang-ocr-routing`](plugins/post-akte/skills/posteingang-ocr-routing/SKILL.md) | `post-akte` | 4 | 🚧 `ungetestet` |
| [`datev-buchhaltungsbruecke`](plugins/wissen-qm/skills/datev-buchhaltungsbruecke/SKILL.md) | `wissen-qm` | 4 | 🚧 `ungetestet` |
| [`ar-mahnwesen-light`](plugins/zeit-abrechnung/skills/ar-mahnwesen-light/SKILL.md) | `zeit-abrechnung` | 4 | 🚧 `ungetestet` |
| [`scheduling-assistent-de`](plugins/fristen-termine/skills/scheduling-assistent-de/SKILL.md) | `fristen-termine` | 5 | 🚧 `ungetestet` |
| [`mandantenkommunikation-status`](plugins/kommunikation/skills/mandantenkommunikation-status/SKILL.md) | `kommunikation` | 5 | 🚧 `ungetestet` |
| [`kanzlei-sop-qualitygate`](plugins/wissen-qm/skills/kanzlei-sop-qualitygate/SKILL.md) | `wissen-qm` | 5 | 🚧 `ungetestet` |
| [`wissensmanagement-precedents`](plugins/wissen-qm/skills/wissensmanagement-precedents/SKILL.md) | `wissen-qm` | 5 | 🚧 `ungetestet` |
<!-- skill-status:ende -->

## Nutzung

Voraussetzung ist ein datenschutzkonformer Claude-Zugang der Kanzlei (z. B. Claude Code /
Cowork über AWS Bedrock, Region Frankfurt). Die Kanzlei lädt dieses Repo selbst — es gibt
kein Hosting und keine Datenhaltung durch die Library.

```bash
git clone https://github.com/eliasreiche/claude-for-legal-non-billable-germany.git
```

Einbindung als Claude-Code-/Cowork-Plugin über [`marketplace.json`](marketplace.json);
Details je Skill im jeweiligen `SKILL.md`.

## Entwicklung

```bash
python3 core/verify/struktur_lint.py   # Struktur-Lint (P4/P5)
pip install pytest && pytest -q        # Tests
```

## Lizenz

[Apache-2.0](LICENSE) · Attributionen: [NOTICE](NOTICE)
