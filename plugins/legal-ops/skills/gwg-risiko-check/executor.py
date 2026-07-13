#!/usr/bin/env python3
"""gwg-risiko-check — CLI-Executor (P2/P3): Mandats-JSON rein, Report-JSON raus.

Ruft den regelbasierten Rechner core/calc/gwg/rechner.py auf. Das Modell
(Claude) rechnet und klassifiziert nie selbst — es füllt nur den Fragebogen aus
dem, was Nutzer/Akte hergeben (fehlend = 'unklar', nie geraten), übergibt die
Mandatsdatei, liest den erzeugten Report und rendert ihn als
Akten-Dokumentation. Jeder Status-, Faktoren- und Fundstellenwert im Report
stammt aus dem Rechner (Deterministik-Grenze, CONVENTIONS.md P3).

Eingabe (JSON-Datei, Schema siehe schema/README.md):

    {
      "kataloggeschaeft": "immobilien_gewerbe_kauf",
      "mandant_typ": "juristische_person",
      "sitz_land": "DE",
      "pep": "nein",
      "wirtschaftlich_berechtigter_geklaert": "ja",
      "bargeldintensiv": "nein",
      ...
    }

CLI:
    python3 executor.py --mandat MANDAT.json [--output REPORT.json]

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# core/calc auf den Importpfad legen (gwg-Paket liegt dort, nicht im Skill).
# Self-relativ innerhalb des Plugins: skill -> skills -> <plugin-root>/core/calc.
_SKILL_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SKILL_DIR.parents[1]
_CALC_DIR = _PLUGIN_ROOT / "core" / "calc"
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from gwg.rechner import GwGEingabeFehler, klassifiziere  # noqa: E402


def baue_report(mandat: dict[str, Any], quelle_datei: str) -> dict[str, Any]:
    rumpf = klassifiziere(mandat)
    return {
        "meta": {
            "erzeugt_von": "plugins/legal-ops/skills/gwg-risiko-check/executor.py",
            "quelle_datei": quelle_datei,
            "deterministik": ("Alle Status-, Faktoren- und Fundstellenwerte in "
                              "diesem Report sind regelbasierte "
                              "Executor-Ergebnisse (P3), nicht modellgeneriert."),
            "hinweis_bewertung": ("Der Klassifikationsvorschlag ist ein "
                                  "Vorschlag zur Aktendokumentation — die "
                                  "Risikobewertung und Maßnahmenentscheidung "
                                  "trifft der Verpflichtete (§ 10 Abs. 2 GwG)."),
        },
        **rumpf,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mandat", required=True,
                        help="JSON-Eingabedatei (Fragebogen zum Mandat)")
    parser.add_argument("--output",
                        help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    mandat_pfad = Path(args.mandat)
    if not mandat_pfad.is_file():
        print(f"Fehler: Mandatsdatei nicht gefunden: {mandat_pfad}",
              file=sys.stderr)
        return 2

    try:
        mandat = json.loads(mandat_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Fehler: Mandatsdatei ist kein gültiges JSON: {exc}",
              file=sys.stderr)
        return 2
    if not isinstance(mandat, dict):
        print("Fehler: Mandat muss ein JSON-Objekt sein", file=sys.stderr)
        return 2

    try:
        report = baue_report(mandat, quelle_datei=str(mandat_pfad))
    except (GwGEingabeFehler, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Fehler: Report-Datei kann nicht geschrieben werden: {exc}",
                  file=sys.stderr)
            return 2
    else:
        print(ausgabe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
