#!/usr/bin/env python3
"""core/calc/retention/executor — Retention-Hinweis-Executor (P2/P3). KEIN Auto-Delete.

Liest `kontext/mandate/*.md` (Frontmatter, über `core/context/schema.py`,
keine erneute Schema-Prüfung — dafür ist `core/context/validator.py`
zuständig) und berechnet je beendetem Mandat die Aufbewahrungsfrist:

  * **Standard: 6 Jahre Handakten, § 50 Abs. 1 BRAO.** Fristbeginn mit dem
    Schluss des Kalenderjahres, in dem das Mandat endete (`mandatsende`) —
    analog zur Verjährungssystematik des § 199 BGB. Löschbar ab dem 1. Januar
    des siebten auf das Mandatsende folgenden Jahres.

    ⚠️ **Statische Belehrung** — dieser Executor prüft nicht den Einzelfall
    und berücksichtigt keine abweichenden Sonderfristen (Steuerunterlagen,
    Sozietätsvertrag, Kammerauflagen, laufende Verjährungs-/Regresshemmung).
    Vor tatsächlicher Löschung ist zwingend anwaltlich zu prüfen.

Der Executor **löscht nie** — er erzeugt ausschließlich einen Hinweis-Report
(JSON + Markdown): was ab wann löschbar wäre, was überfällig ist. Die
Löschentscheidung und -durchführung bleibt manuelle Kanzleisache (D10).

CLI:
    python3 executor.py --kontext KONTEXT_DIR [--stichtag JJJJ-MM-TT]
                        [--output-json REPORT.json] [--output-md REPORT.md]

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler (kontext/-Verzeichnis fehlt,
--stichtag kein ISO-Datum).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_SKILL_DIR = Path(__file__).resolve().parent  # core/calc/retention
_CORE_DIR = _SKILL_DIR.parents[1]              # core
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from context.schema import STATUS_WERTE, lese_mandate  # noqa: E402

NORM_HINWEIS = (
    "✅ § 50 Abs. 1 BRAO — Aufbewahrungsfrist Handakten: 6 Jahre, Fristbeginn "
    "mit dem Schluss des Kalenderjahres der Mandatsbeendigung. Statische "
    "Belehrung, kein Einzelfall-Check: berücksichtigt keine abweichenden "
    "Sonderfristen (Steuerunterlagen, Sozietätsvertrag, Kammerauflagen, "
    "laufende Verjährungs-/Regresshemmung). Vor tatsächlicher Löschung "
    "zwingend anwaltlich prüfen — dieser Executor löscht nie."
)

# Statische Norm-Belehrungen dieses Moduls, für den CI-Marker-Konsistenz-Test
# (tests/test_zitiermarker_statisch.py) als benannte Konstante statt fragilem
# Quelltext-Grep. Rein additiv — NORM_HINWEIS wird weiterhin unverändert in
# baue_report()/baue_markdown() verwendet, kein Verhaltens-Impact.
STATISCHE_NORM_BELEHRUNGEN: list[dict[str, str]] = [
    {"marker": "✅", "text": NORM_HINWEIS},
]

AUFBEWAHRUNG_JAHRE = 6

EINORDNUNG_UEBERFAELLIG = "loeschbar_ueberfaellig"
EINORDNUNG_NOCH_NICHT = "noch_nicht_loeschbar"
EINORDNUNG_NICHT_ANWENDBAR = "nicht_anwendbar"


class RetentionEingabeFehler(ValueError):
    """Eingabefehler → Exit 2 mit klarer Meldung, nie Traceback."""


def _iso(datum: _dt.date) -> str:
    return datum.isoformat()


def _parse_iso(wert: str, feld: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(wert)
    except ValueError:
        raise RetentionEingabeFehler(f"'{feld}' ist kein ISO-Datum (JJJJ-MM-TT): {wert!r}")


def berechne_retention(mandatsende: _dt.date) -> tuple[_dt.date, _dt.date]:
    """(retention_bis, loeschbar_ab) — Fristbeginn Schluss des Kalenderjahres
    der Mandatsbeendigung, 6 Jahre Frist, danach löschbar ab 1. Januar."""
    jahr_ende = mandatsende.year
    retention_bis = _dt.date(jahr_ende + AUFBEWAHRUNG_JAHRE, 12, 31)
    loeschbar_ab = _dt.date(jahr_ende + AUFBEWAHRUNG_JAHRE + 1, 1, 1)
    return retention_bis, loeschbar_ab


def baue_report(kontext_dir: Path, stichtag: _dt.date) -> dict[str, Any]:
    mandate = lese_mandate(kontext_dir)
    eintraege: list[dict[str, Any]] = []
    fehler: list[str] = []
    anzahl_ueberfaellig = 0
    anzahl_noch_nicht = 0
    anzahl_nicht_anwendbar = 0

    for pfad, fm in mandate:
        ref = str(pfad)
        az = (fm.get("az") or (None, None))[0]
        mandant = (fm.get("mandant") or (None, None))[0]
        status_wert = (fm.get("status") or (None, None))[0]
        mandatsende_roh = fm.get("mandatsende")
        mandatsende_wert = mandatsende_roh[0] if mandatsende_roh else None

        basis = {
            "datei": ref,
            "az": az,
            "mandant": mandant,
            "status": status_wert,
            "mandatsende": mandatsende_wert,
        }

        if status_wert not in STATUS_WERTE:
            anzahl_nicht_anwendbar += 1
            eintraege.append({
                **basis, "einordnung": EINORDNUNG_NICHT_ANWENDBAR,
                "hinweis": "kein gültiger 'status' im Frontmatter — Retention nicht bewertbar",
            })
            continue

        if status_wert != "beendet" or not mandatsende_wert:
            anzahl_nicht_anwendbar += 1
            eintraege.append({
                **basis, "einordnung": EINORDNUNG_NICHT_ANWENDBAR,
                "hinweis": ("Mandat nicht beendet oder 'mandatsende' nicht gesetzt — "
                           "Retentionsfrist läuft erst ab Mandatsende (§ 50 Abs. 1 BRAO)"),
            })
            continue

        try:
            mandatsende_datum = _parse_iso(mandatsende_wert, f"{ref}: mandatsende")
        except RetentionEingabeFehler as exc:
            fehler.append(str(exc))
            eintraege.append({
                **basis, "einordnung": EINORDNUNG_NICHT_ANWENDBAR,
                "hinweis": f"'mandatsende' nicht auswertbar: {exc}",
            })
            continue

        retention_bis, loeschbar_ab = berechne_retention(mandatsende_datum)
        ueberfaellig = stichtag >= loeschbar_ab
        if ueberfaellig:
            anzahl_ueberfaellig += 1
        else:
            anzahl_noch_nicht += 1
        eintraege.append({
            **basis,
            "retention_bis": _iso(retention_bis),
            "loeschbar_ab": _iso(loeschbar_ab),
            "einordnung": EINORDNUNG_UEBERFAELLIG if ueberfaellig else EINORDNUNG_NOCH_NICHT,
            "quelle": "executor",
        })

    return {
        "meta": {
            "erzeugt_von": "plugins/legal-ops/core/calc/retention/executor.py",
            "kontext_dir": str(kontext_dir),
            "stichtag": _iso(stichtag),
            "norm_hinweis": NORM_HINWEIS,
            "loescht_nie": True,
            "quelle": "executor",
        },
        "mandate": eintraege,
        "fehler": fehler,
        "zusammenfassung": {
            "anzahl_mandate": len(eintraege),
            EINORDNUNG_UEBERFAELLIG: anzahl_ueberfaellig,
            EINORDNUNG_NOCH_NICHT: anzahl_noch_nicht,
            EINORDNUNG_NICHT_ANWENDBAR: anzahl_nicht_anwendbar,
        },
    }


# --------------------------------------------------------------------------
# Markdown-Darstellung
# --------------------------------------------------------------------------

def baue_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    zeilen = [
        "# Retention-Hinweis-Report",
        "",
        f"Stichtag: {meta['stichtag']} · kontext/-Verzeichnis: `{meta['kontext_dir']}`",
        "",
        f"> {meta['norm_hinweis']}",
        "",
        "**Dieser Report löscht nichts.** Er ist ausschließlich eine Hinweisliste zur "
        "manuellen Prüfung und Löschentscheidung durch die Kanzlei.",
        "",
        "| Az. | Mandant | Status | Mandatsende | Löschbar ab | Einordnung |",
        "|---|---|---|---|---|---|",
    ]
    badge = {
        EINORDNUNG_UEBERFAELLIG: "🔴 überfällig",
        EINORDNUNG_NOCH_NICHT: "🟢 noch nicht löschbar",
        EINORDNUNG_NICHT_ANWENDBAR: "⚪ nicht anwendbar",
    }
    for e in report["mandate"]:
        zeilen.append(
            f"| {e.get('az') or '—'} | {e.get('mandant') or '—'} | {e.get('status') or '—'} "
            f"| {e.get('mandatsende') or '—'} | {e.get('loeschbar_ab') or '—'} "
            f"| {badge.get(e['einordnung'], e['einordnung'])} |")
    z = report["zusammenfassung"]
    zeilen += [
        "",
        f"Zusammenfassung: {z['anzahl_mandate']} Mandat(e) geprüft — "
        f"{z[EINORDNUNG_UEBERFAELLIG]} überfällig, {z[EINORDNUNG_NOCH_NICHT]} noch nicht "
        f"löschbar, {z[EINORDNUNG_NICHT_ANWENDBAR]} nicht anwendbar.",
    ]
    if report["fehler"]:
        zeilen.append("")
        zeilen.append("## Fehler beim Einlesen")
        for f in report["fehler"]:
            zeilen.append(f"- {f}")
    return "\n".join(zeilen) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kontext", required=True, help="kontext/-Verzeichnis")
    parser.add_argument("--stichtag", help="Stichtag ISO JJJJ-MM-TT (Default: heute)")
    parser.add_argument("--output-json", help="Zieldatei für JSON-Report (Default: stdout)")
    parser.add_argument("--output-md", help="Zieldatei für Markdown-Report (optional)")
    args = parser.parse_args(argv)

    kontext_dir = Path(args.kontext)
    if not kontext_dir.is_dir():
        print(f"Fehler: --kontext ist kein Verzeichnis: {kontext_dir}", file=sys.stderr)
        return 2

    try:
        stichtag = (_parse_iso(args.stichtag, "--stichtag") if args.stichtag
                   else _dt.date.today())
    except RetentionEingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    report = baue_report(kontext_dir, stichtag)

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(ausgabe + "\n", encoding="utf-8")
    else:
        print(ausgabe)

    if args.output_md:
        Path(args.output_md).write_text(baue_markdown(report), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
