#!/usr/bin/env python3
"""extf — CLI-Executor (P2/P3): JSON-Buchungsdaten rein, DATEV-EXTF-Datei +
JSON-Report raus.

Wird vom Skill `datev-export` aufgerufen. Erzeugt **ausschließlich einen
Buchungsstapel** (EXTF-CSV, Kategorie 21, Format 700) zum Import in DATEV
Rechnungswesen — kein Parser, keine Stammdaten (Kategorie 16), kein Import
(Scope-Grenze, Maintainer-Entscheidung D20). Das Modell rechnet/formatiert
nie selbst: jeder Betrag, jedes Datum und jede Kontonummer im Export wird
hier deterministisch validiert und formatiert (P3).

⚠️ Formatversion 700 ist NICHT primärquellen-verifiziert (developer.datev.de
blockt automatisierten Zugriff) — vor dem ersten echten Import gegen die
aktuelle DATEV-Dokumentation prüfen (siehe header_format_700.json,
buchungssatz_spalten_700.json, README.md).

Eingabe (JSON-Datei, Schema siehe plugins/legal-ops/skills/datev-export/
schema/README.md):

    {
      "header": {
        "erzeugt_am": "2026-07-13T10:00:00",
        "exportiert_von": "Kanzlei Mustermann",
        "beraternummer": 12345,
        "mandantennummer": 100,
        "wirtschaftsjahresbeginn": "2026-01-01",
        "buchungszeitraum_von": "2026-01-01",
        "buchungszeitraum_bis": "2026-12-31",
        "bezeichnung": "Buchungsstapel Juli 2026"
      },
      "buchungen": [
        {"umsatz": "952.50", "soll_haben": "S", "konto": "1200",
         "gegenkonto": "8400", "belegdatum": "2026-03-15",
         "belegfeld1": "RE-2026-042", "buchungstext": "Honorar ./. Muster"}
      ]
    }

Modell-extrahierte Zahlen (z. B. aus einer Rechnung von Claude ausgelesen)
müssen je Buchung als `"quelle": "modell-extraktion"` markiert UND
`"bestaetigt": true` gesetzt sein (Nutzer-Bestätigung) — sonst Exit 2. Direkt
strukturiert gelieferte Buchungen brauchen kein `quelle`-Feld (P3).

CLI:
    python3 core/calc/extf/executor.py --input BUCHUNGEN.json \\
      --output STAPEL.csv [--output-report REPORT.json]

Exit-Codes: 0 = EXTF-Datei + Report erzeugt, 2 = Eingabe-/Formatfehler
(dann wird KEINE Datei geschrieben — weder EXTF noch Report).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_EXTF_DIR = Path(__file__).resolve().parent
if str(_EXTF_DIR) not in sys.path:
    sys.path.insert(0, str(_EXTF_DIR))

from formate import (  # noqa: E402
    D, ExtfFormatFehler, WertgebuehrFehler, bare_zahl, datum_jjjjmmtt,
    datum_ttmm, datumzeit_kompakt, dezimal_komma, leer, parse_datum_strikt,
    parse_datumzeit_strikt, pruefe_belegfeld, pruefe_cp1252, pruefe_konto,
    quote_text,
)

HEADER_SPEC = json.loads((_EXTF_DIR / "header_format_700.json").read_text(encoding="utf-8"))
SPALTEN_SPEC = json.loads((_EXTF_DIR / "buchungssatz_spalten_700.json").read_text(encoding="utf-8"))

_HEADER_ERLAUBTE_FELDER = {
    "erzeugt_am", "exportiert_von", "beraternummer", "mandantennummer",
    "wirtschaftsjahresbeginn", "sachkontenlaenge", "buchungszeitraum_von",
    "buchungszeitraum_bis", "bezeichnung", "diktatkuerzel", "buchungstyp",
    "waehrung", "formatversion", "herkunft",
}
_BUCHUNG_ERLAUBTE_FELDER = {
    "umsatz", "soll_haben", "wkz_umsatz", "kurs", "basisumsatz",
    "wkz_basisumsatz", "konto", "gegenkonto", "bu_schluessel", "belegdatum",
    "belegfeld1", "belegfeld2", "skonto", "buchungstext", "quelle",
    "bestaetigt",
}


def _pflichtfeld(eingabe: dict[str, Any], feld: str, kontext: str) -> Any:
    if feld not in eingabe or eingabe[feld] in (None, ""):
        raise ExtfFormatFehler(f"Pflichtfeld '{kontext}.{feld}' fehlt oder ist leer")
    return eingabe[feld]


def _nur_erlaubte_felder(eingabe: dict[str, Any], erlaubt: set[str], kontext: str) -> None:
    for feld in eingabe:
        if feld not in erlaubt:
            raise ExtfFormatFehler(f"unbekanntes Feld '{kontext}.{feld}'")


def _ganzzahl(wert: Any, feld: str, *, min_laenge: int | None = None,
              max_laenge: int | None = None, erlaubt: list[int] | None = None) -> int:
    if isinstance(wert, bool) or not isinstance(wert, int):
        raise ExtfFormatFehler(f"'{feld}' muss eine ganze Zahl sein, nicht {wert!r}")
    if erlaubt is not None and wert not in erlaubt:
        raise ExtfFormatFehler(f"'{feld}' muss einer von {erlaubt} sein, ist: {wert}")
    if (min_laenge is not None or max_laenge is not None) and wert < 0:
        raise ExtfFormatFehler(f"'{feld}' darf nicht negativ sein: {wert}")
    laenge = len(str(wert))
    if min_laenge is not None and laenge < min_laenge:
        raise ExtfFormatFehler(f"'{feld}' hat zu wenig Stellen ({laenge}, min {min_laenge}): {wert}")
    if max_laenge is not None and laenge > max_laenge:
        raise ExtfFormatFehler(f"'{feld}' hat zu viele Stellen ({laenge}, max {max_laenge}): {wert}")
    return wert


def _text(wert: Any, feld: str, *, laenge: int) -> str:
    if not isinstance(wert, str):
        raise ExtfFormatFehler(f"'{feld}' muss ein Text (String) sein, nicht {wert!r}")
    if len(wert) > laenge:
        raise ExtfFormatFehler(f"'{feld}' ist zu lang ({len(wert)} Zeichen, max {laenge}): {wert!r}")
    pruefe_cp1252(wert, feld)
    return wert


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

def _baue_header(eingabe: dict[str, Any]) -> dict[str, Any]:
    _nur_erlaubte_felder(eingabe, _HEADER_ERLAUBTE_FELDER, "header")

    erzeugt_am = parse_datumzeit_strikt(_pflichtfeld(eingabe, "erzeugt_am", "header"), "header.erzeugt_am")
    exportiert_von = _text(_pflichtfeld(eingabe, "exportiert_von", "header"), "header.exportiert_von", laenge=25)
    beraternummer = _ganzzahl(_pflichtfeld(eingabe, "beraternummer", "header"), "header.beraternummer",
                               min_laenge=1, max_laenge=7)
    mandantennummer = _ganzzahl(_pflichtfeld(eingabe, "mandantennummer", "header"), "header.mandantennummer",
                                 min_laenge=1, max_laenge=5)
    wj_beginn = parse_datum_strikt(_pflichtfeld(eingabe, "wirtschaftsjahresbeginn", "header"),
                                    "header.wirtschaftsjahresbeginn")
    sachkontenlaenge = eingabe.get("sachkontenlaenge", 4)
    if isinstance(sachkontenlaenge, bool) or not isinstance(sachkontenlaenge, int) or not (4 <= sachkontenlaenge <= 8):
        raise ExtfFormatFehler(
            f"'header.sachkontenlaenge' muss eine ganze Zahl zwischen 4 und 8 sein, "
            f"nicht {sachkontenlaenge!r}")

    von = parse_datum_strikt(_pflichtfeld(eingabe, "buchungszeitraum_von", "header"), "header.buchungszeitraum_von")
    bis = parse_datum_strikt(_pflichtfeld(eingabe, "buchungszeitraum_bis", "header"), "header.buchungszeitraum_bis")
    if von > bis:
        raise ExtfFormatFehler(
            f"'header.buchungszeitraum_von' ({von.isoformat()}) liegt nach "
            f"'header.buchungszeitraum_bis' ({bis.isoformat()})")

    bezeichnung = _text(_pflichtfeld(eingabe, "bezeichnung", "header"), "header.bezeichnung", laenge=30)
    diktatkuerzel = eingabe.get("diktatkuerzel")
    if diktatkuerzel is not None:
        diktatkuerzel = _text(diktatkuerzel, "header.diktatkuerzel", laenge=2)
    buchungstyp = _ganzzahl(eingabe.get("buchungstyp", 1), "header.buchungstyp", erlaubt=[1, 2])
    waehrung = _text(eingabe.get("waehrung", "EUR"), "header.waehrung", laenge=3)
    formatversion = _ganzzahl(eingabe.get("formatversion", 5), "header.formatversion", min_laenge=1, max_laenge=3)
    herkunft = _text(eingabe.get("herkunft", "RE"), "header.herkunft", laenge=2)

    return {
        "erzeugt_am": erzeugt_am,
        "exportiert_von": exportiert_von,
        "beraternummer": beraternummer,
        "mandantennummer": mandantennummer,
        "wirtschaftsjahresbeginn": wj_beginn,
        "sachkontenlaenge": sachkontenlaenge,
        "buchungszeitraum_von": von,
        "buchungszeitraum_bis": bis,
        "bezeichnung": bezeichnung,
        "diktatkuerzel": diktatkuerzel,
        "buchungstyp": buchungstyp,
        "waehrung": waehrung,
        "formatversion": formatversion,
        "herkunft": herkunft,
    }


def _header_zeile(h: dict[str, Any]) -> list[str]:
    """Baut die 31 Header-Token in der Reihenfolge von header_format_700.json."""
    werte_nach_pos = {
        1: quote_text("EXTF", "Kennzeichen"),
        2: bare_zahl(700),
        3: bare_zahl(21),
        4: quote_text("Buchungsstapel", "Formatname"),
        5: bare_zahl(h["formatversion"]),
        6: bare_zahl(datumzeit_kompakt(h["erzeugt_am"])),
        7: leer(),
        8: quote_text(h["herkunft"], "Herkunft"),
        9: quote_text(h["exportiert_von"], "Exportiert von"),
        10: leer(),
        11: bare_zahl(h["beraternummer"]),
        12: bare_zahl(h["mandantennummer"]),
        13: bare_zahl(datum_jjjjmmtt(h["wirtschaftsjahresbeginn"])),
        14: bare_zahl(h["sachkontenlaenge"]),
        15: bare_zahl(datum_jjjjmmtt(h["buchungszeitraum_von"])),
        16: bare_zahl(datum_jjjjmmtt(h["buchungszeitraum_bis"])),
        17: quote_text(h["bezeichnung"], "Bezeichnung"),
        18: quote_text(h["diktatkuerzel"], "Diktatkuerzel") if h["diktatkuerzel"] else leer(),
        19: bare_zahl(h["buchungstyp"]),
        20: leer(),
        21: leer(),
        22: quote_text(h["waehrung"], "Waehrungskennzeichen"),
        23: leer(), 24: leer(), 25: leer(), 26: leer(), 27: leer(),
        28: leer(), 29: leer(), 30: leer(), 31: leer(),
    }
    return [werte_nach_pos[f["pos"]] for f in HEADER_SPEC["felder"]]


def _spaltenkopf_zeile() -> list[str]:
    return [quote_text(s["feld"], "Spaltenkopf") for s in SPALTEN_SPEC["spalten"]]


# --------------------------------------------------------------------------
# Buchungszeilen
# --------------------------------------------------------------------------

def _pruefe_modell_extraktion(buchung: dict[str, Any], index: int) -> None:
    """P3-Wahrung: modell-extrahierte Buchungen brauchen eine explizite
    Nutzer-Bestätigung. Granularität ist die gesamte Buchungszeile (nicht
    das einzelne Zahlenfeld) — alle Beträge/Daten einer Zeile stammen aus
    demselben Beleg und werden gemeinsam bestätigt (Design-Entscheidung,
    siehe schema/README.md). Direkt strukturiert gelieferte Buchungen (ohne
    'quelle' oder mit einem anderen Wert) brauchen keine Bestätigung."""
    quelle = buchung.get("quelle")
    if quelle is None:
        return
    if quelle != "modell-extraktion":
        raise ExtfFormatFehler(
            f"Buchung {index}: unbekannter Wert für 'quelle': {quelle!r} — "
            f"erlaubt ist nur 'modell-extraktion' oder das Feld ganz wegzulassen")
    if buchung.get("bestaetigt") is not True:
        raise ExtfFormatFehler(
            f"Buchung {index}: als 'quelle': 'modell-extraktion' markiert, "
            f"aber nicht 'bestaetigt': true — modellgenerierte Zahlenfelder "
            f"dürfen erst nach Nutzer-Bestätigung exportiert werden (P3)")


def _baue_buchungszeile(buchung: dict[str, Any], index: int,
                         header: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    _nur_erlaubte_felder(buchung, _BUCHUNG_ERLAUBTE_FELDER, f"buchungen[{index}]")
    _pruefe_modell_extraktion(buchung, index)
    kontext = f"buchungen[{index}]"
    sachkontenlaenge = header["sachkontenlaenge"]

    umsatz = D(_pflichtfeld(buchung, "umsatz", kontext))
    if umsatz <= 0:
        raise ExtfFormatFehler(f"'{kontext}.umsatz' muss größer als 0 sein, ist: {umsatz}")

    soll_haben = _pflichtfeld(buchung, "soll_haben", kontext)
    if soll_haben not in ("S", "H"):
        raise ExtfFormatFehler(f"'{kontext}.soll_haben' muss 'S' oder 'H' sein, nicht {soll_haben!r}")

    wkz_umsatz = buchung.get("wkz_umsatz")
    if wkz_umsatz is not None:
        wkz_umsatz = _text(wkz_umsatz, f"{kontext}.wkz_umsatz", laenge=3)

    kurs = buchung.get("kurs")
    if kurs is not None:
        kurs = D(kurs)
        if kurs == 0:
            raise ExtfFormatFehler(f"'{kontext}.kurs' darf nicht 0 sein, falls angegeben")

    basisumsatz = buchung.get("basisumsatz")
    wkz_basisumsatz = buchung.get("wkz_basisumsatz")
    if (basisumsatz is None) != (wkz_basisumsatz is None):
        raise ExtfFormatFehler(
            f"'{kontext}.basisumsatz' und '{kontext}.wkz_basisumsatz' müssen "
            f"beide oder keines von beiden gesetzt sein")
    if basisumsatz is not None:
        basisumsatz = D(basisumsatz)
        wkz_basisumsatz = _text(wkz_basisumsatz, f"{kontext}.wkz_basisumsatz", laenge=3)

    konto = pruefe_konto(_pflichtfeld(buchung, "konto", kontext), f"{kontext}.konto", sachkontenlaenge)
    gegenkonto = pruefe_konto(_pflichtfeld(buchung, "gegenkonto", kontext), f"{kontext}.gegenkonto", sachkontenlaenge)

    bu_schluessel = buchung.get("bu_schluessel")
    if bu_schluessel is not None:
        bu_schluessel = _text(bu_schluessel, f"{kontext}.bu_schluessel", laenge=4)

    belegdatum = parse_datum_strikt(_pflichtfeld(buchung, "belegdatum", kontext), f"{kontext}.belegdatum")
    if not (header["buchungszeitraum_von"] <= belegdatum <= header["buchungszeitraum_bis"]):
        raise ExtfFormatFehler(
            f"'{kontext}.belegdatum' ({belegdatum.isoformat()}) liegt außerhalb "
            f"des Header-Buchungszeitraums "
            f"({header['buchungszeitraum_von'].isoformat()} – "
            f"{header['buchungszeitraum_bis'].isoformat()})")

    belegfeld1 = buchung.get("belegfeld1")
    if belegfeld1 is not None:
        belegfeld1 = pruefe_belegfeld(belegfeld1, f"{kontext}.belegfeld1", 36)
    belegfeld2 = buchung.get("belegfeld2")
    if belegfeld2 is not None:
        belegfeld2 = pruefe_belegfeld(belegfeld2, f"{kontext}.belegfeld2", 12)

    skonto = buchung.get("skonto")
    if skonto is not None:
        skonto = D(skonto)
        if skonto == 0:
            raise ExtfFormatFehler(f"'{kontext}.skonto' darf nicht 0 sein, falls angegeben")

    buchungstext = buchung.get("buchungstext")
    if buchungstext is not None:
        buchungstext = _text(buchungstext, f"{kontext}.buchungstext", laenge=60)

    tokens = [
        bare_zahl(dezimal_komma(umsatz, 2)),
        quote_text(soll_haben, f"{kontext}.soll_haben"),
        quote_text(wkz_umsatz, f"{kontext}.wkz_umsatz") if wkz_umsatz else leer(),
        bare_zahl(dezimal_komma(kurs, 6)) if kurs is not None else leer(),
        bare_zahl(dezimal_komma(basisumsatz, 2)) if basisumsatz is not None else leer(),
        quote_text(wkz_basisumsatz, f"{kontext}.wkz_basisumsatz") if wkz_basisumsatz else leer(),
        bare_zahl(konto),
        bare_zahl(gegenkonto),
        quote_text(bu_schluessel, f"{kontext}.bu_schluessel") if bu_schluessel else leer(),
        bare_zahl(datum_ttmm(belegdatum)),
        quote_text(belegfeld1, f"{kontext}.belegfeld1") if belegfeld1 else leer(),
        quote_text(belegfeld2, f"{kontext}.belegfeld2") if belegfeld2 else leer(),
        bare_zahl(dezimal_komma(skonto, 2)) if skonto is not None else leer(),
        quote_text(buchungstext, f"{kontext}.buchungstext") if buchungstext else leer(),
        leer(), leer(), leer(), leer(), leer(), leer(),  # Spalten 15-20: v1 nicht unterstützt
    ]
    assert len(tokens) == len(SPALTEN_SPEC["spalten"]) == 20

    return tokens, {
        "index": index,
        "umsatz": dezimal_komma(umsatz, 2).replace(",", "."),
        "soll_haben": soll_haben,
        "konto": konto,
        "gegenkonto": gegenkonto,
        "belegdatum_ttmm": datum_ttmm(belegdatum),
        "belegdatum_iso": belegdatum.isoformat(),
        "belegfeld1": belegfeld1,
        "buchungstext": buchungstext,
        "quelle": "executor",
    }


# --------------------------------------------------------------------------
# Gesamter Export
# --------------------------------------------------------------------------

def baue_export(eingabe: dict[str, Any], quelle_datei: str) -> tuple[str, dict[str, Any]]:
    if not isinstance(eingabe, dict):
        raise ExtfFormatFehler("Eingabe muss ein JSON-Objekt sein")
    _nur_erlaubte_felder(eingabe, {"header", "buchungen"}, "$")

    header_roh = _pflichtfeld(eingabe, "header", "$")
    if not isinstance(header_roh, dict):
        raise ExtfFormatFehler("'header' muss ein JSON-Objekt sein")
    header = _baue_header(header_roh)

    buchungen_roh = _pflichtfeld(eingabe, "buchungen", "$")
    if not isinstance(buchungen_roh, list) or not buchungen_roh:
        raise ExtfFormatFehler("'buchungen' muss eine nicht-leere Liste sein")

    zeilen = [_header_zeile(header), _spaltenkopf_zeile()]
    report_buchungen = []
    for i, buchung in enumerate(buchungen_roh, start=1):
        if not isinstance(buchung, dict):
            raise ExtfFormatFehler(f"'buchungen[{i}]' muss ein JSON-Objekt sein")
        tokens, report_zeile = _baue_buchungszeile(buchung, i, header)
        zeilen.append(tokens)
        report_buchungen.append(report_zeile)

    inhalt = "\r\n".join(";".join(zeile) for zeile in zeilen) + "\r\n"
    try:
        inhalt.encode("cp1252")
    except UnicodeEncodeError as exc:  # Sicherheitsnetz — jedes Feld wurde
        # bereits einzeln geprüft (pruefe_cp1252); dieser Zweig sollte nie
        # greifen, verhindert aber einen Traceback statt Exit 2.
        raise ExtfFormatFehler(f"Export ist nicht vollständig CP1252-kodierbar: {exc}")

    report = {
        "meta": {
            "erzeugt_von": "core/calc/extf/executor.py",
            "quelle_datei": quelle_datei,
            "deterministik": ("Alle Beträge/Daten/Kontonummern in diesem "
                              "Report und der EXTF-Datei sind Executor-"
                              "Ergebnisse (P3), nicht modellgeneriert."),
            "formatversion_hinweis": ("⚠️ Formatversion 700 / Feldliste "
                                       "NICHT primärquellen-verifiziert — vor "
                                       "erstem Echt-Import gegen aktuelle "
                                       "DATEV-Dokumentation prüfen."),
            "scope_hinweis": ("Nur Buchungsstapel-Export — kein Parser, "
                               "keine Stammdaten (Kategorie 16), kein Import."),
        },
        "header": {
            "erzeugt_am": header["erzeugt_am"].isoformat(),
            "beraternummer": header["beraternummer"],
            "mandantennummer": header["mandantennummer"],
            "wirtschaftsjahresbeginn": header["wirtschaftsjahresbeginn"].isoformat(),
            "sachkontenlaenge": header["sachkontenlaenge"],
            "buchungszeitraum_von": header["buchungszeitraum_von"].isoformat(),
            "buchungszeitraum_bis": header["buchungszeitraum_bis"].isoformat(),
            "bezeichnung": header["bezeichnung"],
            "formatversion": header["formatversion"],
            "waehrung": header["waehrung"],
            "quelle": "executor",
        },
        "buchungen_anzahl": len(report_buchungen),
        "buchungen": report_buchungen,
        "warnungen": [],
    }
    return inhalt, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="JSON-Eingabedatei (header + buchungen)")
    parser.add_argument("--output", required=True, help="Zieldatei für die EXTF-CSV")
    parser.add_argument("--output-report", help="Zieldatei für den JSON-Report (Default: stdout)")
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

    try:
        inhalt, report = baue_export(eingabe, quelle_datei=str(input_pfad))
    except (ExtfFormatFehler, WertgebuehrFehler, ValueError, ArithmeticError,
            OverflowError) as exc:
        # Fail-fast VOR jedem Dateizugriff: bei einem Formatfehler wird
        # weder die EXTF-Datei noch der Report geschrieben (Maintainer-
        # Entscheidung D20: kein defektes EXTF beim Steuerberater).
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    try:
        Path(args.output).write_bytes(inhalt.encode("cp1252"))
    except OSError as exc:
        print(f"Fehler: EXTF-Datei kann nicht geschrieben werden: {exc}", file=sys.stderr)
        return 2

    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_report:
        try:
            Path(args.output_report).write_text(report_json + "\n", encoding="utf-8")
        except OSError as exc:
            # Kein Teil-Ergebnis stehen lassen: die EXTF-Datei wurde bereits
            # geschrieben, aber ohne Report ist Exit 2 kein sauberer Zustand
            # (D20: entweder beide Artefakte oder keins).
            Path(args.output).unlink(missing_ok=True)
            print(f"Fehler: Report-Datei kann nicht geschrieben werden: {exc}", file=sys.stderr)
            return 2
    else:
        print(report_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
