# core/calc/retention — Retention-Hinweis-Executor (KEIN Auto-Delete)

Liest `kontext/mandate/*.md` und berechnet je beendetem Mandat
(`status: beendet` + gesetztes `mandatsende`) die Aufbewahrungsfrist nach
§ 50 Abs. 1 BRAO: **6 Jahre Handakten**, Fristbeginn mit dem Schluss des
Kalenderjahres, in dem das Mandat endete (analog § 199 BGB). Löschbar ab dem
1. Januar des siebten auf das Mandatsende folgenden Jahres.

> ⚠️ **Statische Belehrung, kein Einzelfall-Check.** Berücksichtigt keine
> abweichenden Sonderfristen (Steuerunterlagen, Sozietätsvertrag,
> Kammerauflagen, laufende Verjährungs-/Regresshemmung). Vor tatsächlicher
> Löschung ist zwingend anwaltlich zu prüfen.

**Der Executor löscht nie.** Er erzeugt ausschließlich einen Hinweis-Report
(JSON + optional Markdown) — was ab wann löschbar wäre, was überfällig ist.
Die Löschentscheidung und -durchführung bleibt manuelle Kanzleisache.

## CLI

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/core/calc/retention/executor.py \
  --kontext <kontext-verzeichnis> [--stichtag JJJJ-MM-TT] \
  [--output-json report.json] [--output-md report.md]
```

`--stichtag` (Default: heute) ist der Bezugstag für „überfällig vs. noch
nicht löschbar" — nützlich für reproduzierbare Testläufe und um einen
zukünftigen Stichtag zu simulieren.

## Einordnung je Mandat

| Einordnung | Bedeutung |
|---|---|
| `loeschbar_ueberfaellig` | Stichtag ≥ `loeschbar_ab` — Löschung wäre nach der 6-Jahres-Frist zulässig, Kanzlei sollte prüfen. |
| `noch_nicht_loeschbar` | Stichtag < `loeschbar_ab` — Frist läuft noch. |
| `nicht_anwendbar` | Mandat nicht `beendet` oder `mandatsende` fehlt/nicht auswertbar — Retentionsfrist noch nicht bewertbar. |

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Report erzeugt (unabhängig davon, ob Mandate überfällig sind — das ist ein Hinweis, kein Fehlerzustand). |
| `2` | Eingabefehler — `--kontext` kein Verzeichnis, `--stichtag` kein ISO-Datum. |

## Löschkonzept / Retention — Setup-Checkliste (D10-Auflage)

Bevor eine Kanzlei diesen Report für tatsächliche Löschungen nutzt, muss sie
je Speicherort dokumentieren:

1. **Speicherort** — wo liegen die Handakten tatsächlich (Papier,
   e-Akte/DMS, Kanzleisoftware, `kontext/`-Verweise, Backups)? Der Report
   deckt nur ab, was in `kontext/mandate/*.md` als `mandatsende` erfasst ist —
   **nicht** automatisch alle Kopien/Backups.
2. **Begründung je Speicherort** — warum diese Aufbewahrungsdauer für diesen
   Speicherort gilt (Regelfrist § 50 Abs. 1 BRAO vs. abweichende
   Sonderfristen, z. B. Steuerunterlagen, laufende Verfahren, Regressgefahr).
3. **Retention** — die tatsächlich angewandte Frist je Speicherort
   (Regelfall: 6 Jahre; Abweichung dokumentieren, wenn eine der
   Sonderkonstellationen oben greift).
4. **Manuelle Löschung** — wer löscht, wann, mit welcher Freigabe
   (Vier-Augen-Prinzip empfohlen); der Report ist die Entscheidungsgrundlage,
   nie die Ausführung.

## Bewusste Grenzen

- **Kein Auto-Delete, keine Löschausführung** — reine Hinweisliste.
- **Nur `kontext/`** — erfasst nicht Backups, Papierakten oder Kopien
  außerhalb des Kontext-Layers.
- **Statischer Norm-Hinweis** — keine Prüfung laufender
  Verjährungs-/Regresshemmung, keine Sonderfristen-Erkennung.
