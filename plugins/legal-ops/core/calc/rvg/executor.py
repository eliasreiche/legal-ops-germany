#!/usr/bin/env python3
"""rvg/gkg — CLI-Executor (P2/P3): JSON-Eingabe rein, JSON-Report raus.

Wird vom Skill `rvg-gkg-rechner` aufgerufen. Das Modell (Claude) rechnet nie
selbst — es übergibt die Eingabedatei, liest den Report und stellt ihn dar.
Jeder Geldbetrag im Report stammt aus diesem Executor (Deterministik-Grenze,
CONVENTIONS.md P3).

Deckt zwei unabhängige Berechnungen ab, die über getrennte Blöcke angefordert
werden (mindestens einer ist Pflicht):

  * "rvg": Anwaltsvergütung nach § 13 RVG / VV RVG (core.calc.rvg.rechner).
  * "gkg": Gerichtskosten nach § 34 GKG / KV GKG (core.calc.gkg.rechner).

RVG- und GKG-Beträge werden **nicht** automatisch zu einer Gesamtsumme
addiert — es sind unterschiedliche Forderungen mit unterschiedlichen
Kostenschuldnern (Anwaltshonorar vs. Gerichtskasse); eine stille
Zusammenrechnung wäre irreführend.

Eingabe (JSON-Datei, Schema siehe plugins/legal-ops/skills/
rvg-gkg-rechner/schema/README.md). Der RVG-Block kennt zwei Formen:
'tatbestaende' (flache Kurzform für genau EINE Angelegenheit) oder
'angelegenheiten' (volle Form — je Angelegenheit eigene Gebühren, eigene
Auslagenpauschale Nr. 7002 und eigene USt; Teil-2- und Teil-3-Tatbestände
in derselben Angelegenheit sind ein Eingabefehler):

    {
      "rvg": {
        "auftragsdatum": "2026-03-01",
        "streitwert": "10000.00",
        "angelegenheiten": [
          {"bezeichnung": "Außergerichtliche Vertretung",
           "tatbestaende": [{"nr": "2300", "satz": "1.3"}]},
          {"bezeichnung": "Rechtsstreit erster Instanz",
           "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]}
        ],
        "anrechnung_2300_auf_3100": true,
        "auslagenpauschale": true,
        "umsatzsteuer": true
      },
      "gkg": {
        "verfahrenseinleitungsdatum": "2026-03-01",
        "streitwert": "10000.00",
        "positionen": [{"nr": "1100"}, {"nr": "1210"}],
        "anrechnung_1100_auf_1210": true
      }
    }

Beide Blöcke werden strikt validiert: ein unbekannter Key (Tippfehler) ist
ein Eingabefehler mit Exit 2 und Nennung des Keys, nie ein stilles Ignorieren.

CLI:
    python3 core/calc/rvg/executor.py --input ANFRAGE.json [--output REPORT.json]

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler.
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any

_RVG_DIR = Path(__file__).resolve().parent
_CALC_DIR = _RVG_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from cli import (  # noqa: E402
    CliFehler,
    lese_json_objekt,
    pflichtfeld,
    schreibe_report,
    standard_parser,
)
from wertgebuehr_formel import WertgebuehrFehler, parse_datum_strikt  # noqa: E402
from rvg.rechner import RVGEingabeFehler, berechne as rvg_berechne  # noqa: E402
from gkg.rechner import GKGEingabeFehler, berechne as gkg_berechne  # noqa: E402


_pflichtfeld = functools.partial(pflichtfeld, fehler=WertgebuehrFehler)

# Strikte Eingabe-Validierung (Geldpfad): ein unbekannter Key ist ein
# Eingabefehler mit Exit 2 und Nennung des Keys — nie stilles Ignorieren.
# Ein Tippfehler wie "anrechnung_1100_1210" würde sonst als *nicht*
# angeforderte Anrechnung durchlaufen und einen zu hohen Betrag ausweisen.
_RVG_FELDER = ("auftragsdatum", "streitwert", "angelegenheiten", "tatbestaende",
               "anrechnung_2300_auf_3100", "auslagenpauschale", "umsatzsteuer")
_GKG_FELDER = ("verfahrenseinleitungsdatum", "streitwert", "positionen",
               "anrechnung_1100_auf_1210")


def _nur_erlaubte_felder(block: dict[str, Any], erlaubt: tuple[str, ...],
                         kontext: str) -> None:
    for feld in block:
        if feld not in erlaubt:
            raise WertgebuehrFehler(
                f"unbekanntes Feld {kontext}: '{feld}' (erlaubt: "
                f"{', '.join(repr(f) for f in erlaubt)})")


def _tabellenstand_kurz(stand: dict[str, Any]) -> dict[str, Any]:
    """Trimmt den vollen Tabellenstand (inkl. Stufen/Prüfpunkte) auf die für
    den Report relevanten Herkunftsangaben — die vollständigen Stufendaten
    stehen dauerhaft in gebuehrentabelle.json, nicht in jedem Report."""
    return {
        "id": stand["id"],
        "bezeichnung": stand["bezeichnung"],
        "gueltig_ab": stand["gueltig_ab"],
        "gueltig_bis": stand.get("gueltig_bis"),
        "fundstelle": stand["fundstelle"],
    }


def _baue_rvg_block(anfrage: dict[str, Any]) -> dict[str, Any]:
    _nur_erlaubte_felder(anfrage, _RVG_FELDER, "im Block 'rvg'")
    stichtag = parse_datum_strikt(_pflichtfeld(anfrage, "auftragsdatum"), "rvg.auftragsdatum")
    streitwert = _pflichtfeld(anfrage, "streitwert")

    # Zwei Eingabeformen: 'angelegenheiten' (Liste, je eigene tatbestaende —
    # die volle Form) ODER 'tatbestaende' (flach, Kurzform für genau EINE
    # Angelegenheit). Genau eine der beiden, nie beide.
    hat_angelegenheiten = anfrage.get("angelegenheiten") is not None
    hat_flach = anfrage.get("tatbestaende") is not None
    if hat_angelegenheiten and hat_flach:
        raise RVGEingabeFehler(
            "entweder 'rvg.angelegenheiten' (volle Form) ODER "
            "'rvg.tatbestaende' (Kurzform für eine Angelegenheit) angeben — "
            "nicht beides")
    if not hat_angelegenheiten and not hat_flach:
        raise RVGEingabeFehler(
            "es fehlt die Tatbestandsangabe: 'rvg.angelegenheiten' oder "
            "'rvg.tatbestaende'")
    if hat_angelegenheiten:
        angelegenheiten = anfrage["angelegenheiten"]
    else:
        angelegenheiten = [{"bezeichnung": "Angelegenheit 1",
                            "tatbestaende": anfrage["tatbestaende"]}]

    anrechnung = anfrage.get("anrechnung_2300_auf_3100", False)
    if not isinstance(anrechnung, bool):
        raise RVGEingabeFehler(
            f"'rvg.anrechnung_2300_auf_3100' muss ein JSON-Boolean sein, "
            f"nicht {anrechnung!r}")
    auslagenpauschale = anfrage.get("auslagenpauschale", True)
    umsatzsteuer = anfrage.get("umsatzsteuer", True)

    ergebnis = rvg_berechne(
        streitwert, stichtag, angelegenheiten,
        anrechnung_2300_auf_3100=anrechnung,
        auslagenpauschale=auslagenpauschale,
        umsatzsteuer=umsatzsteuer)

    return {
        "eingabe": {
            "auftragsdatum": stichtag.isoformat(),
            "streitwert": str(ergebnis.streitwert_eingabe),
            "angelegenheiten": angelegenheiten,
            "anrechnung_2300_auf_3100": anrechnung,
            "auslagenpauschale": bool(auslagenpauschale),
            "umsatzsteuer": bool(umsatzsteuer),
        },
        "tabellenstand": _tabellenstand_kurz(ergebnis.tabellenstand),
        "wertkappung": {
            "gekappt": ergebnis.wert_gekappt,
            "norm": "§ 22 Abs. 2 Satz 1 RVG",
            "streitwert_eingabe": str(ergebnis.streitwert_eingabe),
            "streitwert_angewendet": str(ergebnis.streitwert),
        } if ergebnis.wert_gekappt else None,
        "einfachgebuehr": str(ergebnis.einfachgebuehr),
        "angelegenheiten": [a.as_dict() for a in ergebnis.angelegenheiten],
        "anrechnung": ergebnis.anrechnung,
        "rechenkette": [s.as_dict() for s in ergebnis.rechenkette],
        "ergebnis": {
            "gesamt_verguetung": str(ergebnis.gesamt_verguetung),
            "gesamt_hinweis": ("Summe über alle Angelegenheiten (gleicher "
                               "Gläubiger) — die Angelegenheiten bleiben "
                               "gebührenrechtlich getrennt (je eigene "
                               "Auslagenpauschale Nr. 7002 und eigene USt-"
                               "Basis Nr. 7008)."),
            "quelle": "executor",
        },
        "warnungen": ergebnis.warnungen,
    }


def _baue_gkg_block(anfrage: dict[str, Any]) -> dict[str, Any]:
    _nur_erlaubte_felder(anfrage, _GKG_FELDER, "im Block 'gkg'")
    stichtag = parse_datum_strikt(
        _pflichtfeld(anfrage, "verfahrenseinleitungsdatum"),
        "gkg.verfahrenseinleitungsdatum")
    streitwert = _pflichtfeld(anfrage, "streitwert")
    positionen = _pflichtfeld(anfrage, "positionen")
    anrechnung = anfrage.get("anrechnung_1100_auf_1210", False)

    ergebnis = gkg_berechne(streitwert, stichtag, positionen,
                            anrechnung_1100_auf_1210=anrechnung)

    return {
        "eingabe": {
            "verfahrenseinleitungsdatum": stichtag.isoformat(),
            "streitwert": str(ergebnis.streitwert_eingabe),
            "positionen": positionen,
            "anrechnung_1100_auf_1210": bool(anrechnung),
        },
        "tabellenstand": _tabellenstand_kurz(ergebnis.tabellenstand),
        "wertkappung": {
            "gekappt": ergebnis.wert_gekappt,
            "norm": "§ 39 Abs. 2 GKG",
            "streitwert_eingabe": str(ergebnis.streitwert_eingabe),
            "streitwert_angewendet": str(ergebnis.streitwert),
        } if ergebnis.wert_gekappt else None,
        "einfachgebuehr": str(ergebnis.einfachgebuehr),
        "positionen": [p.as_dict() for p in ergebnis.positionen],
        "anrechnung": ergebnis.anrechnung,
        "rechenkette": [s.as_dict() for s in ergebnis.rechenkette],
        "ergebnis": {
            "gesamt": str(ergebnis.gesamt),
            "umsatzsteuerpflichtig": False,
            "quelle": "executor",
        },
        "warnungen": ergebnis.warnungen,
    }


def baue_report(eingabe: dict[str, Any], quelle_datei: str) -> dict[str, Any]:
    # Erst auf unbekannte Felder prüfen — ein Tippfehler wie {"rgv": ...}
    # soll als solcher gemeldet werden, nicht als "kein Block vorhanden".
    _nur_erlaubte_felder(eingabe, ("rvg", "gkg"), "auf oberster Ebene")
    hat_rvg = "rvg" in eingabe and eingabe["rvg"] is not None
    hat_gkg = "gkg" in eingabe and eingabe["gkg"] is not None
    if not hat_rvg and not hat_gkg:
        raise WertgebuehrFehler(
            "Anfrage muss mindestens einen Block enthalten: 'rvg' und/oder 'gkg'")

    report: dict[str, Any] = {
        "meta": {
            "erzeugt_von": "core/calc/rvg/executor.py",
            "quelle_datei": quelle_datei,
            "deterministik": ("Alle Geldbeträge in diesem Report sind "
                              "Executor-Ergebnisse (P3), nicht modellgeneriert."),
            "hinweis_getrennte_kostenarten": (
                "RVG-Anwaltsvergütung und GKG-Gerichtskosten werden "
                "absichtlich NICHT zu einer Gesamtsumme addiert — "
                "unterschiedliche Forderungen mit unterschiedlichen "
                "Kostenschuldnern."),
        },
    }
    if hat_rvg:
        if not isinstance(eingabe["rvg"], dict):
            raise WertgebuehrFehler("'rvg' muss ein JSON-Objekt sein")
        report["rvg"] = _baue_rvg_block(eingabe["rvg"])
    if hat_gkg:
        if not isinstance(eingabe["gkg"], dict):
            raise WertgebuehrFehler("'gkg' muss ein JSON-Objekt sein")
        report["gkg"] = _baue_gkg_block(eingabe["gkg"])
    return report


def main(argv: list[str] | None = None) -> int:
    args = standard_parser(__doc__,
                           "JSON-Eingabedatei (RVG-/GKG-Anfrage)").parse_args(argv)

    input_pfad = Path(args.input)
    try:
        eingabe = lese_json_objekt(input_pfad)
        report = baue_report(eingabe, quelle_datei=str(input_pfad))
        schreibe_report(report, args.output)
    except (CliFehler, WertgebuehrFehler, RVGEingabeFehler, GKGEingabeFehler,
            ValueError, ArithmeticError) as exc:
        # CliFehler/WertgebuehrFehler/RVGEingabeFehler/GKGEingabeFehler sind
        # der Regelfall; ValueError/ArithmeticError als Sicherheitsnetz
        # (u. a. decimal.InvalidOperation), damit nie ein Traceback statt
        # Exit 2 erscheint.
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
