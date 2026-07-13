#!/usr/bin/env python3
"""fristen — CLI-Executor (P2/P3): JSON-Eingabe rein, JSON-Report raus.

Wird vom Skill `fristenrechner` aufgerufen. Das Modell (Claude) rechnet
nie selbst — es übergibt die Eingabedatei, liest den Report und stellt ihn
dar. Jeder Datums-/Zahlenwert im Report stammt aus diesem Executor
(Deterministik-Grenze, CONVENTIONS.md P3).

Eingabe (JSON-Datei, Schema siehe plugins/legal-ops/skills/
fristenrechner/schema/README.md):

    {
      "ereignis_datum": "2026-01-15",
      "fristart": "berufung",              // ODER dauer + einheit:
      "dauer": 3, "einheit": "wochen",
      "fristtyp": "ereignis",              // optional (Default: Katalog bzw. "ereignis")
      "bundesland": "NW",                  // Pflicht (§ 193 BGB: Fristende-Ort)
      "paragraf_193_anwenden": true        // optional, Default true
    }

CLI:
    python3 core/calc/fristen/executor.py --input ANFRAGE.json [--output REPORT.json]

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fristen.rechner import (  # noqa: E402
    FRISTTYP_EREIGNIS,
    FristEingabeFehler,
    berechne_frist,
    fristart_nach_id,
    lade_katalog,
)
from feiertage import STAND as FEIERTAGE_STAND  # noqa: E402


def _pflichtfeld(eingabe: dict[str, Any], feld: str) -> Any:
    if feld not in eingabe or eingabe[feld] in (None, ""):
        raise FristEingabeFehler(f"Pflichtfeld '{feld}' fehlt oder ist leer")
    return eingabe[feld]


_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _datum(wert: Any, feld: str) -> _dt.date:
    # Strikt JJJJ-MM-TT (Datei-Kontrakt): fromisoformat() allein würde über
    # den str()-Umweg auch JSON-Zahlen (20260115) oder die Wochen-Notation
    # ("2026-W03-4") schlucken — beides liegt außerhalb des Kontrakts.
    if not isinstance(wert, str) or not _DATUM_RE.match(wert):
        raise FristEingabeFehler(
            f"'{feld}' muss ein ISO-Datum als String im Format JJJJ-MM-TT "
            f"sein, nicht {wert!r}")
    try:
        return _dt.date.fromisoformat(wert)
    except ValueError as exc:
        raise FristEingabeFehler(
            f"'{feld}' ist kein gültiges ISO-Datum (JJJJ-MM-TT): {wert!r} ({exc})")


def baue_report(eingabe: dict[str, Any], quelle_datei: str) -> dict[str, Any]:
    ereignis = _datum(_pflichtfeld(eingabe, "ereignis_datum"), "ereignis_datum")
    bundesland = str(_pflichtfeld(eingabe, "bundesland"))

    katalog = lade_katalog()
    fristart: dict[str, Any] | None = None
    hinweise: list[str] = []

    hat_fristart = bool(eingabe.get("fristart"))
    hat_frei = eingabe.get("dauer") is not None or bool(eingabe.get("einheit"))
    if hat_fristart and hat_frei:
        raise FristEingabeFehler(
            "entweder 'fristart' (Katalog) ODER 'dauer'+'einheit' (freie Frist) "
            "angeben — nicht beides")
    if not hat_fristart and not hat_frei:
        raise FristEingabeFehler(
            "es fehlt die Fristangabe: 'fristart' (Katalog) oder 'dauer'+'einheit'")

    if hat_fristart:
        fristart = fristart_nach_id(str(eingabe["fristart"]), katalog)
        dauer = int(fristart["dauer"])
        einheit = str(fristart["einheit"])
        fristtyp = str(fristart.get("fristtyp", FRISTTYP_EREIGNIS))
        # Der Fristtyp einer Katalog-Fristart ist gesetzlich festgelegt —
        # ein abweichender Override wäre eine stille Falschberechnung und
        # wird abgelehnt (konservativ, Haftungs-Tool).
        if eingabe.get("fristtyp") and str(eingabe["fristtyp"]) != fristtyp:
            raise FristEingabeFehler(
                f"'fristtyp' der Katalog-Fristart '{fristart['id']}' ist "
                f"gesetzlich festgelegt ({fristtyp!r}, {fristart['norm']}) und "
                f"kann nicht auf {eingabe['fristtyp']!r} überschrieben werden — "
                f"für abweichende Fälle die freie Fristangabe (dauer/einheit/"
                f"fristtyp) verwenden")
        hinweise.extend(fristart.get("hinweise", []))
        if fristart.get("notfrist"):
            hinweise.append(
                f"{fristart['bezeichnung']} ist eine Notfrist "
                f"(§ 224 Abs. 1 Satz 2 ZPO); sie kann nicht verlängert werden "
                f"(§ 224 Abs. 2 ZPO) — bei Versäumung kommt nur "
                f"Wiedereinsetzung in Betracht (§§ 233 ff. ZPO).")
        elif fristart.get("verlaengerbar"):
            hinweise.append(
                f"{fristart['bezeichnung']} ist auf rechtzeitigen Antrag "
                f"verlängerbar ({fristart['norm']}) — Verlängerung ist eine "
                f"anwaltliche Entscheidung, nicht Teil dieser Berechnung.")
    else:
        dauer_roh = _pflichtfeld(eingabe, "dauer")
        if not isinstance(dauer_roh, int) or isinstance(dauer_roh, bool):
            raise FristEingabeFehler(
                f"'dauer' muss eine ganze Zahl sein, nicht {dauer_roh!r}")
        dauer = dauer_roh
        einheit = str(_pflichtfeld(eingabe, "einheit"))
        fristtyp = str(eingabe.get("fristtyp") or FRISTTYP_EREIGNIS)

    paragraf_193 = eingabe.get("paragraf_193_anwenden", True)
    if not isinstance(paragraf_193, bool):
        # Strenge Typprüfung: der JSON-String "false" wäre truthy — eine
        # stille Fehlinterpretation bei einem Haftungs-Tool.
        raise FristEingabeFehler(
            f"'paragraf_193_anwenden' muss ein JSON-Boolean (true/false) "
            f"sein, nicht {paragraf_193!r}")

    ergebnis = berechne_frist(
        ereignis, dauer, einheit, fristtyp,
        bundesland=bundesland,
        paragraf_193_anwenden=paragraf_193)

    warnungen = list(ergebnis.warnungen)
    if fristart and fristart.get("kein_technisches_fristende"):
        warnungen.insert(0, (
            f"'{fristart['bezeichnung']}' hat kein Fristende im technischen "
            f"Sinn — das berechnete Datum ist nur der Ablauf der in der "
            f"Belehrung genannten Frist (Details siehe hinweise)."))

    report = {
        "meta": {
            "erzeugt_von": "core/calc/fristen/executor.py",
            "quelle_datei": quelle_datei,
            "katalog_stand": katalog["stand"],
            "feiertagsregeln_stand": FEIERTAGE_STAND,
            "deterministik": ("Alle Datums-/Zahlenwerte in diesem Report sind "
                              "Executor-Ergebnisse (P3), nicht modellgeneriert."),
        },
        "eingabe": {
            "ereignis_datum": ereignis.isoformat(),
            "fristart": fristart["id"] if fristart else None,
            "dauer": dauer,
            "einheit": einheit,
            "fristtyp": fristtyp,
            "bundesland": ergebnis.bundesland,
            "paragraf_193_anwenden": paragraf_193,
        },
        "fristart": fristart,
        "rechenkette": [s.as_dict() for s in ergebnis.rechenkette],
        "ergebnis": {
            "fristbeginn": ergebnis.fristbeginn.isoformat(),
            "fristende_rechnerisch": ergebnis.fristende_rechnerisch.isoformat(),
            "fristende": ergebnis.fristende.isoformat(),
            "verschoben": ergebnis.verschoben,
            "verschiebungen": [v.as_dict() for v in ergebnis.verschiebungen],
            "fristende_bei_teilgebietlichem_feiertag": (
                ergebnis.fristende_bei_teilgebietlichem_feiertag.isoformat()
                if ergebnis.fristende_bei_teilgebietlichem_feiertag else None),
            "kein_technisches_fristende": bool(
                fristart and fristart.get("kein_technisches_fristende")),
            "quelle": "executor",
        },
        "warnungen": warnungen,
        "hinweise": hinweise,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True,
                        help="JSON-Eingabedatei (Fristanfrage)")
    parser.add_argument("--output",
                        help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    input_pfad = Path(args.input)
    if not input_pfad.is_file():
        print(f"Fehler: Eingabedatei nicht gefunden: {input_pfad}", file=sys.stderr)
        return 2

    try:
        eingabe = json.loads(input_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Fehler: Eingabedatei ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(eingabe, dict):
        print("Fehler: Eingabe muss ein JSON-Objekt sein", file=sys.stderr)
        return 2

    try:
        report = baue_report(eingabe, quelle_datei=str(input_pfad))
    except (FristEingabeFehler, ValueError, OverflowError) as exc:
        # FristEingabeFehler ist der Regelfall; ValueError/OverflowError als
        # Sicherheitsnetz, damit nie ein Traceback statt Exit 2 erscheint.
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
