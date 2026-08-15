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

# Plugin-Wurzel: skills/<skill>/executor.py -> <plugin>/core.
_CORE = Path(__file__).resolve().parents[2] / "core"
sys.path[:0] = [str(p) for p in (_CORE, _CORE / "calc", _CORE / "adapters")
                if str(p) not in sys.path]

from cli import CliFehler, schreibe_report  # noqa: E402
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

    try:
        schreibe_report(report, args.output)
    except CliFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
