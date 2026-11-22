#!/usr/bin/env python3
"""rvg/gkg/famgkg — CLI-Executor (P2/P3): JSON-Eingabe rein, JSON-Report raus.

Wird vom Skill `rvg-gkg-rechner` aufgerufen. Das Modell (Claude) rechnet nie
selbst — es übergibt die Eingabedatei, liest den Report und stellt ihn dar.
Jeder Geldbetrag im Report stammt aus diesem Executor (Deterministik-Grenze,
CONVENTIONS.md P3).

Deckt drei Berechnungen ab, die über getrennte Blöcke angefordert werden
(mindestens einer ist Pflicht):

  * "rvg": Anwaltsvergütung nach § 13 RVG / VV RVG (core.calc.rvg.rechner).
  * "gkg": Gerichtskosten nach § 34 GKG / KV GKG (core.calc.gkg.rechner).
  * "famgkg": Gerichtskosten in Familiensachen nach § 28 FamGKG / KV FamGKG
    (core.calc.famgkg.rechner), Verfahrenswert entweder direkt
    ("verfahrenswert") oder ermittelt nach §§ 33 ff. FamGKG
    ("verfahrenswert_ermittlung", core.calc.famgkg.verfahrenswert).

"gkg" und "famgkg" schließen sich aus (ein Verfahren läuft entweder nach dem
GKG oder — Familiensache — nach dem FamGKG). Einzige Kopplung zwischen den
Blöcken: trägt "rvg.streitwert" den Literal-String "famgkg.verfahrenswert",
übernimmt der RVG-Block den Verfahrenswert des famgkg-Blocks (§ 23 Abs. 1
Satz 1 RVG) und weist das als eigenen Rechenketten-Schritt aus.

Anwaltsvergütung und Gerichtskosten werden **nicht** automatisch zu einer
Gesamtsumme addiert — es sind unterschiedliche Forderungen mit
unterschiedlichen Kostenschuldnern (Anwaltshonorar vs. Gerichtskasse); eine
stille Zusammenrechnung wäre irreführend.

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

Familiensache (statt "gkg"), Scheidung im Verbund mit Querverweis:

    {
      "rvg": {"auftragsdatum": "2026-03-01",
              "streitwert": "famgkg.verfahrenswert",
              "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]},
      "famgkg": {
        "verfahrenseinleitungsdatum": "2026-03-01",
        "verfahrenswert_ermittlung": {
          "ehesache": {"nettoeinkommen_monatlich": ["3000.00", "2000.00"]},
          "folgesachen": [{"art": "versorgungsausgleich", "anzahl_anrechte": 2}]
        },
        "positionen": [{"nr": "1110"}]
      }
    }

Optional trägt jeder RVG-Tatbestand bzw. jede GKG-Position einen eigenen
"gegenstandswert" (Teilwert, z. B. Mehrwert eines Vergleichs; KV 1900:
Pflicht) — Default ist der "streitwert" des Blocks.

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
from wertgebuehr_formel import D, WertgebuehrFehler, parse_datum_strikt  # noqa: E402
from rvg.rechner import RVGEingabeFehler, berechne as rvg_berechne  # noqa: E402
from gkg.rechner import GKGEingabeFehler, berechne as gkg_berechne  # noqa: E402
from famgkg.rechner import FamGKGEingabeFehler, berechne as famgkg_berechne  # noqa: E402
from famgkg.verfahrenswert import (  # noqa: E402
    ermittle as verfahrenswert_ermitteln,
    report_warnungen as verfahrenswert_warnungen,
)
from rechenschritt import RechenSchritt  # noqa: E402


_pflichtfeld = functools.partial(pflichtfeld, fehler=WertgebuehrFehler)

# Strikte Eingabe-Validierung (Geldpfad): ein unbekannter Key ist ein
# Eingabefehler mit Exit 2 und Nennung des Keys — nie stilles Ignorieren.
# Ein Tippfehler wie "anrechnung_1100_1210" würde sonst als *nicht*
# angeforderte Anrechnung durchlaufen und einen zu hohen Betrag ausweisen.
_RVG_FELDER = ("auftragsdatum", "streitwert", "angelegenheiten", "tatbestaende",
               "anrechnung_2300_auf_3100", "anrechnung_mahnverfahren_auf_3100",
               "auslagenpauschale", "umsatzsteuer")
_GKG_FELDER = ("verfahrenseinleitungsdatum", "streitwert", "positionen",
               "anrechnung_1100_auf_1210")
_FAMGKG_FELDER = ("verfahrenseinleitungsdatum", "verfahrenswert",
                  "verfahrenswert_ermittlung", "positionen")

# Querverweis: dieser Literal-String in rvg.streitwert übernimmt den
# Verfahrenswert des famgkg-Blocks (§ 23 Abs. 1 Satz 1 RVG).
QUERVERWEIS_FAMGKG = "famgkg.verfahrenswert"


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


def _renummeriere(kette: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, s in enumerate(kette, start=1):
        s["schritt"] = i
    return kette


def _baue_rvg_block(anfrage: dict[str, Any],
                    famgkg_wert: tuple[str, str] | None = None) -> dict[str, Any]:
    """`famgkg_wert` = (Verfahrenswert als String, Quelle) aus dem
    famgkg-Block — nur für den Querverweis 'famgkg.verfahrenswert'."""
    _nur_erlaubte_felder(anfrage, _RVG_FELDER, "im Block 'rvg'")
    stichtag = parse_datum_strikt(_pflichtfeld(anfrage, "auftragsdatum"), "rvg.auftragsdatum")
    streitwert = _pflichtfeld(anfrage, "streitwert")
    querverweis_schritt: dict[str, Any] | None = None
    if streitwert == QUERVERWEIS_FAMGKG:
        if famgkg_wert is None:
            raise WertgebuehrFehler(
                f"'rvg.streitwert' verweist auf '{QUERVERWEIS_FAMGKG}', aber die "
                f"Anfrage hat keinen Block 'famgkg' — den Block ergänzen oder "
                f"den Gegenstandswert direkt angeben")
        streitwert, wert_quelle = famgkg_wert
        querverweis_schritt = RechenSchritt(
            schritt=1, norm="§ 23 Abs. 1 Satz 1 RVG",
            beschreibung=(f"Gegenstandswert aus '{QUERVERWEIS_FAMGKG}' übernommen "
                          f"(im gerichtlichen Verfahren bestimmt sich der "
                          f"Gegenstandswert nach den für die Gerichtsgebühren "
                          f"geltenden Wertvorschriften, hier FamGKG): "
                          f"{streitwert} €."),
            ergebnis=streitwert, quelle=wert_quelle).as_dict()

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
    anrechnung_mahn = anfrage.get("anrechnung_mahnverfahren_auf_3100", False)
    if not isinstance(anrechnung_mahn, bool):
        raise RVGEingabeFehler(
            f"'rvg.anrechnung_mahnverfahren_auf_3100' muss ein JSON-Boolean "
            f"sein, nicht {anrechnung_mahn!r}")
    auslagenpauschale = anfrage.get("auslagenpauschale", True)
    umsatzsteuer = anfrage.get("umsatzsteuer", True)

    ergebnis = rvg_berechne(
        streitwert, stichtag, angelegenheiten,
        anrechnung_2300_auf_3100=anrechnung,
        anrechnung_mahnverfahren_auf_3100=anrechnung_mahn,
        auslagenpauschale=auslagenpauschale,
        umsatzsteuer=umsatzsteuer)

    eingabe_block: dict[str, Any] = {
        "auftragsdatum": stichtag.isoformat(),
        "streitwert": str(ergebnis.streitwert_eingabe),
    }
    if querverweis_schritt:
        eingabe_block["streitwert_herkunft"] = QUERVERWEIS_FAMGKG
    rechenkette = [s.as_dict() for s in ergebnis.rechenkette]
    if querverweis_schritt:
        rechenkette = _renummeriere([querverweis_schritt] + rechenkette)
    eingabe_normalisiert: dict[str, Any] = {
        **eingabe_block,
        "angelegenheiten": angelegenheiten,
        "anrechnung_2300_auf_3100": anrechnung,
    }
    # Nur ausgewiesen, wenn in der Anfrage gesetzt — ältere Reports behalten
    # ihr Schema unverändert (Rückwärtskompatibilität).
    if "anrechnung_mahnverfahren_auf_3100" in anfrage:
        eingabe_normalisiert["anrechnung_mahnverfahren_auf_3100"] = anrechnung_mahn
    eingabe_normalisiert["auslagenpauschale"] = bool(auslagenpauschale)
    eingabe_normalisiert["umsatzsteuer"] = bool(umsatzsteuer)
    block: dict[str, Any] = {
        "eingabe": eingabe_normalisiert,
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
        "rechenkette": rechenkette,
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
    # Zweite Anrechnung (Anm. zu Nr. 3305/3307 VV RVG) als eigener Block neben
    # 'anrechnung' (Geschäftsgebühr) — nur, wenn angefordert.
    if ergebnis.anrechnung_mahnverfahren is not None:
        block["anrechnung_mahnverfahren"] = ergebnis.anrechnung_mahnverfahren
    return block


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

    block = {
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
    if ergebnis.kappung:
        block["kappung_36_abs_3"] = ergebnis.kappung
    return block


def _baue_famgkg_block(anfrage: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, str]]:
    """Gibt (Report-Block, (Verfahrenswert als String, Quelle)) zurück."""
    _nur_erlaubte_felder(anfrage, _FAMGKG_FELDER, "im Block 'famgkg'")
    stichtag = parse_datum_strikt(
        _pflichtfeld(anfrage, "verfahrenseinleitungsdatum"),
        "famgkg.verfahrenseinleitungsdatum")
    positionen = _pflichtfeld(anfrage, "positionen")
    hat_wert = anfrage.get("verfahrenswert") is not None
    hat_ermittlung = anfrage.get("verfahrenswert_ermittlung") is not None
    if hat_wert and hat_ermittlung:
        raise FamGKGEingabeFehler(
            "entweder 'famgkg.verfahrenswert' (direkt) ODER "
            "'famgkg.verfahrenswert_ermittlung' (§§ 33 ff. FamGKG) angeben — "
            "nicht beides")
    if not hat_wert and not hat_ermittlung:
        raise FamGKGEingabeFehler(
            "es fehlt der Verfahrenswert: 'famgkg.verfahrenswert' oder "
            "'famgkg.verfahrenswert_ermittlung'")

    if hat_ermittlung:
        vw = verfahrenswert_ermitteln(anfrage["verfahrenswert_ermittlung"], stichtag)
        verfahrenswert = vw.gesamt
        vw_block = vw.as_dict()
        vw_quelle = vw.quelle
        herkunft = "verfahrenswert_ermittlung"
        vw_schritt_norm = "§§ 33 ff. FamGKG"
        vw_schritt_text = (f"Verfahrenswert aus der Verfahrenswert-Ermittlung "
                           f"(Block 'verfahrenswert'): {vw_block['gesamt']} €.")
    else:
        verfahrenswert = D(anfrage["verfahrenswert"])
        vw_quelle = "eingabe"
        herkunft = "eingabe"
        vw_block = {"gesamt": str(verfahrenswert), "quelle": "eingabe",
                    "form": "direkt",
                    "gegenstaende": [], "rechenkette": [],
                    "hinweise": ["Verfahrenswert direkt eingegeben, nicht nach "
                                 "§§ 33 ff. FamGKG ermittelt."]}
        vw_schritt_norm = "Eingabe"
        vw_schritt_text = (f"Verfahrenswert direkt eingegeben (nicht ermittelt): "
                           f"{verfahrenswert} €.")

    ergebnis = famgkg_berechne(verfahrenswert, stichtag, positionen)
    # § 41 FamGKG (Ausgangswert, Positions-Plausibilität) — leer ohne Ermittlung.
    vw_warnungen = verfahrenswert_warnungen(vw, positionen) if hat_ermittlung else []
    rechenkette = _renummeriere(
        [RechenSchritt(schritt=1, norm=vw_schritt_norm, beschreibung=vw_schritt_text,
                       ergebnis=vw_block["gesamt"], quelle=vw_quelle).as_dict()]
        + [s.as_dict() for s in ergebnis.rechenkette])

    block = {
        "eingabe": {
            "verfahrenseinleitungsdatum": stichtag.isoformat(),
            "verfahrenswert": str(ergebnis.verfahrenswert_eingabe),
            "verfahrenswert_herkunft": herkunft,
            "positionen": positionen,
        },
        "verfahrenswert": vw_block,
        "tabellenstand": _tabellenstand_kurz(ergebnis.tabellenstand),
        "wertkappung": {
            "gekappt": ergebnis.wert_gekappt,
            "norm": "§ 33 Abs. 2 FamGKG",
            "verfahrenswert_eingabe": str(ergebnis.verfahrenswert_eingabe),
            "verfahrenswert_angewendet": str(ergebnis.verfahrenswert),
        } if ergebnis.wert_gekappt else None,
        "einfachgebuehr": str(ergebnis.einfachgebuehr),
        "positionen": [p.as_dict() for p in ergebnis.positionen],
        "rechenkette": rechenkette,
        "ergebnis": {
            "gesamt": str(ergebnis.gesamt),
            "umsatzsteuerpflichtig": False,
            "quelle": "executor",
        },
        "warnungen": vw_warnungen + ergebnis.warnungen,
    }
    if ergebnis.kappung:
        block["kappung_30_abs_3"] = ergebnis.kappung
    return block, (vw_block["gesamt"], vw_quelle)


def baue_report(eingabe: dict[str, Any], quelle_datei: str) -> dict[str, Any]:
    # Erst auf unbekannte Felder prüfen — ein Tippfehler wie {"rgv": ...}
    # soll als solcher gemeldet werden, nicht als "kein Block vorhanden".
    _nur_erlaubte_felder(eingabe, ("rvg", "gkg", "famgkg"), "auf oberster Ebene")
    hat_rvg = "rvg" in eingabe and eingabe["rvg"] is not None
    hat_gkg = "gkg" in eingabe and eingabe["gkg"] is not None
    hat_famgkg = "famgkg" in eingabe and eingabe["famgkg"] is not None
    if not hat_rvg and not hat_gkg and not hat_famgkg:
        raise WertgebuehrFehler(
            "Anfrage muss mindestens einen Block enthalten: 'rvg', 'gkg' "
            "und/oder 'famgkg'")
    if hat_gkg and hat_famgkg:
        raise WertgebuehrFehler(
            "'gkg' und 'famgkg' in derselben Anfrage: Familiensachen laufen "
            "nach dem FamGKG, nicht nach dem GKG — ein Verfahren ist nie "
            "beides. Für eine Familiensache nur 'famgkg' angeben, für eine "
            "Zivilsache nur 'gkg'.")

    report: dict[str, Any] = {
        "meta": {
            "erzeugt_von": "core/calc/rvg/executor.py",
            "quelle_datei": quelle_datei,
            "deterministik": ("Alle Geldbeträge in diesem Report sind "
                              "Executor-Ergebnisse (P3), nicht modellgeneriert."),
            "hinweis_getrennte_kostenarten": (
                "RVG-Anwaltsvergütung und GKG- bzw. FamGKG-Gerichtskosten "
                "werden absichtlich NICHT zu einer Gesamtsumme addiert — "
                "unterschiedliche Forderungen mit unterschiedlichen "
                "Kostenschuldnern."),
        },
    }
    # Der famgkg-Block wird zuerst gerechnet (Querverweis aus rvg.streitwert),
    # erscheint im Report aber nach rvg — wie gkg.
    famgkg_block = famgkg_wert = None
    if hat_famgkg:
        if not isinstance(eingabe["famgkg"], dict):
            raise WertgebuehrFehler("'famgkg' muss ein JSON-Objekt sein")
        famgkg_block, famgkg_wert = _baue_famgkg_block(eingabe["famgkg"])
    if hat_rvg:
        if not isinstance(eingabe["rvg"], dict):
            raise WertgebuehrFehler("'rvg' muss ein JSON-Objekt sein")
        report["rvg"] = _baue_rvg_block(eingabe["rvg"], famgkg_wert)
    if hat_gkg:
        if not isinstance(eingabe["gkg"], dict):
            raise WertgebuehrFehler("'gkg' muss ein JSON-Objekt sein")
        report["gkg"] = _baue_gkg_block(eingabe["gkg"])
    if famgkg_block is not None:
        report["famgkg"] = famgkg_block
    return report


def main(argv: list[str] | None = None) -> int:
    args = standard_parser(__doc__,
                           "JSON-Eingabedatei (RVG-/GKG-/FamGKG-Anfrage)").parse_args(argv)

    input_pfad = Path(args.input)
    try:
        eingabe = lese_json_objekt(input_pfad)
        report = baue_report(eingabe, quelle_datei=str(input_pfad))
        schreibe_report(report, args.output)
    except (CliFehler, WertgebuehrFehler, RVGEingabeFehler, GKGEingabeFehler,
            FamGKGEingabeFehler, ValueError, ArithmeticError) as exc:
        # CliFehler/WertgebuehrFehler/RVGEingabeFehler/GKGEingabeFehler sind
        # der Regelfall; ValueError/ArithmeticError als Sicherheitsnetz
        # (u. a. decimal.InvalidOperation), damit nie ein Traceback statt
        # Exit 2 erscheint.
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
