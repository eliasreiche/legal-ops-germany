#!/usr/bin/env python3
"""honorar-mahnwesen — CLI-Executor (P2/P3): offene Posten rein, Auswertungs-
Report raus.

Ruft den deterministischen Kern core/calc/opos/rechner.py auf. Das Modell
(Claude) rechnet nie selbst — es übergibt die Datei, liest den Report und
draftet daraus Schreiben-Entwürfe (Versand entscheidet die Kanzlei). Jeder
Betrag, jedes Datum, jede Mahnstufe und jede Priorität im Report ist ein
Executor-Ergebnis (Deterministik-Grenze, CONVENTIONS.md P3).

Zwei Eingabe-Quellen (genau eine angeben):

  --opos-csv FILE   OPOS-CSV (präzise Primärquelle; Schema: schema/README.md)
  --extf FILE       EXTF-Buchungsstapel (Format 700, über core/calc/extf/
                    parser.py; vereinfachte Belegfeld-1-Aggregation)

Weitere Argumente:
  --stichtag JJJJ-MM-TT   Pflicht. Bezugstag für 'Tage seit Fälligkeit' —
                          kommt aus der Eingabe, nie aus der Wall-Clock
                          (Idempotenz: gleiche Eingabe → gleicher Report).
  --zahlungsziel-tage N   nur --extf; Fälligkeit = Rechnungsdatum + N Tage
                          (Default 14, dokumentierte Annahme, da EXTF kein
                          Fälligkeitsdatum trägt).
  --mahnstufen-config F   optionale JSON-Datei mit Tagesschwellen (Default:
                          Erinnerung ab 0, 1. Mahnung ab 14, 2. Mahnung ab 30).
  --output FILE           Report-Zieldatei (Default: stdout).

Exit-Codes: 0 = Report erzeugt, 2 = Eingabe-/Formatfehler (dann keine Datei).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SKILL_DIR.parents[1]
_CALC_DIR = _PLUGIN_ROOT / "core" / "calc"
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from opos.rechner import (  # noqa: E402
    OposEingabeFehler, bewerte, lade_mahnstufen_config, lade_opos_csv,
    stapel_zu_posten,
)
from extf.parser import ExtfParseFehler, parse_extf_datei  # noqa: E402
from wertgebuehr_formel import WertgebuehrFehler, parse_datum_strikt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    quelle = parser.add_mutually_exclusive_group(required=True)
    quelle.add_argument("--opos-csv", help="OPOS-CSV (Semikolon-getrennt, Kopfzeile)")
    quelle.add_argument("--extf", help="EXTF-Buchungsstapel (Format 700)")
    parser.add_argument("--stichtag", required=True, help="Bezugstag JJJJ-MM-TT (Pflicht)")
    parser.add_argument("--zahlungsziel-tage", type=int, default=14,
                        help="nur --extf: Fälligkeit = Rechnungsdatum + N Tage (Default 14)")
    parser.add_argument("--mahnstufen-config", help="optionale JSON-Datei mit Tagesschwellen")
    parser.add_argument("--output", help="Report-Zieldatei (Default: stdout)")
    args = parser.parse_args(argv)

    try:
        stichtag = parse_datum_strikt(args.stichtag, "--stichtag")
    except WertgebuehrFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    mahnstufen = None
    if args.mahnstufen_config:
        cfg_pfad = Path(args.mahnstufen_config)
        if not cfg_pfad.is_file():
            print(f"Fehler: Mahnstufen-Konfiguration nicht gefunden: {cfg_pfad}", file=sys.stderr)
            return 2
        try:
            cfg = json.loads(cfg_pfad.read_text(encoding="utf-8"))
            mahnstufen = lade_mahnstufen_config(cfg)
        except json.JSONDecodeError as exc:
            print(f"Fehler: Mahnstufen-Konfiguration ist kein gültiges JSON: {exc}", file=sys.stderr)
            return 2
        except OposEingabeFehler as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 2

    nicht_zuordenbar: list = []
    try:
        if args.opos_csv:
            pfad = Path(args.opos_csv)
            if not pfad.is_file():
                print(f"Fehler: OPOS-CSV nicht gefunden: {pfad}", file=sys.stderr)
                return 2
            posten = lade_opos_csv(pfad)
            quelle_meta = {"quelle_format": "opos-csv", "quelle_datei": str(pfad)}
        else:
            pfad = Path(args.extf)
            stapel = parse_extf_datei(pfad)
            posten, nicht_zuordenbar = stapel_zu_posten(stapel, args.zahlungsziel_tage)
            quelle_meta = {
                "quelle_format": "extf",
                "quelle_datei": str(pfad),
                "zahlungsziel_tage": args.zahlungsziel_tage,
            }
        report = bewerte(posten, stichtag, mahnstufen,
                         nicht_zuordenbar=nicht_zuordenbar, quelle_meta=quelle_meta)
    except (OposEingabeFehler, ExtfParseFehler, WertgebuehrFehler, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Fehler: Report-Datei kann nicht geschrieben werden: {exc}", file=sys.stderr)
            return 2
    else:
        print(ausgabe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
