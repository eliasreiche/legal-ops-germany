#!/usr/bin/env python3
"""taetigkeitstext-rvg — CLI-Executor (P2/P3), zwei Modi.

Zeitwerte stammen ausschließlich aus dem Input, nie vom Modell (P3). Das
Modell (Claude) formuliert Tätigkeitsbeschreibungen nur aus den `stichworte`n
des Reports; Minuten und Daten übernimmt es unverändert. Dieser Executor
erzwingt das maschinell in zwei Schritten:

  Modus 1 (rechnen) — `--input leistungen.json [--output report.json]`
      Validiert die Leistungs-Einträge streng (siehe schema/README.md),
      berechnet je Eintrag die Minuten (aus `minuten` ODER `start`+`ende`,
      Bibliothek core/calc/zeit) und optional die Taktung, aggregiert Summen
      je Aktenzeichen (`az`) und je (`az`, `datum`), und echot `stichworte`
      wörtlich. Einträge ohne `az` landen in `ohne_az[]` (Lücke, nie geraten).

  Modus 2 (Provenienz-Gate) — `--pruefe-text entwurf.md --report report.json
      [--output pruef-report.json]`
      Prüft einen vom Modell formulierten Leistungsnachweis-Text maschinell:
      jede Zahl (Minuten/Stunden, inkl. „1,5 Stunden" ≡ 90 Minuten) und jedes
      Datum im Text muss einem Executor-Wert aus dem Report entsprechen;
      jedes Aktenzeichen im Text muss im Report vorkommen. Eine fremde Zahl/
      ein fremdes Datum/Aktenzeichen ist ein Befund (Exit 1).

Nur Standardbibliothek. Kein Netzwerkzugriff. Liest ausschließlich lokale
Dateien.

Exit-Codes:
    Modus 1: 0 = Report erzeugt, 2 = Eingabefehler.
    Modus 2: 0 = sauber (keine Befunde), 1 = mindestens ein Befund,
             2 = Eingabefehler (Datei fehlt, kaputtes JSON, Report ist kein
             gültiger Executor-Report).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

# core/calc auf den Importpfad legen (zeit-Paket liegt dort, nicht im Skill).
# Self-relativ innerhalb des Plugins: skill -> skills -> <plugin-root>/core/calc.
_SKILL_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SKILL_DIR.parents[1]
_CALC_DIR = _PLUGIN_ROOT / "core" / "calc"
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from zeit.rechner import (  # noqa: E402
    ZeitEingabeFehler,
    ZeitEintrag,
    dauer_minuten,
    runde_auf_takt,
    summe_je_az,
    summe_je_az_und_datum,
)

ERZEUGT_VON = "plugins/legal-ops/skills/taetigkeitstext-rvg/executor.py"

EINTRAG_FELDER = {"datum", "az", "minuten", "start", "ende", "stichworte", "quelle"}
EINTRAG_PFLICHTFELDER = {"datum", "stichworte", "quelle"}
QUELLEN_WERTE = {"kalender", "mail", "manuell"}


class EingabeFehler(ValueError):
    """Eingabefehler im Leistungen-JSON (Modus 1) — führt zu Exit 2."""


# --------------------------------------------------------------------------
# Modus 1 — Validierung + Berechnung
# --------------------------------------------------------------------------

def _pruefe_datum(wert: Any, pfad: str) -> str:
    if not isinstance(wert, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", wert):
        raise EingabeFehler(f"{pfad}.datum: muss ISO-Format JJJJ-MM-TT sein, ist: {wert!r}")
    try:
        _dt.date.fromisoformat(wert)
    except ValueError as exc:
        raise EingabeFehler(f"{pfad}.datum: kein gültiges Kalenderdatum: {wert!r}") from exc
    return wert


def _pruefe_eintrag(roh: Any, index: int) -> dict[str, Any]:
    pfad = f"eintraege[{index}]"
    if not isinstance(roh, dict):
        raise EingabeFehler(f"{pfad}: muss ein JSON-Objekt sein")

    unbekannt = set(roh) - EINTRAG_FELDER
    if unbekannt:
        raise EingabeFehler(f"{pfad}: unbekanntes Feld {sorted(unbekannt)!r}")
    fehlend = EINTRAG_PFLICHTFELDER - set(roh)
    if fehlend:
        raise EingabeFehler(f"{pfad}: Pflichtfeld(er) fehlen: {sorted(fehlend)!r}")

    datum = _pruefe_datum(roh["datum"], pfad)

    az_roh = roh.get("az")
    if az_roh is not None and not isinstance(az_roh, str):
        raise EingabeFehler(f"{pfad}.az: muss Text oder null sein, ist: {az_roh!r}")
    az = az_roh.strip() if isinstance(az_roh, str) else None
    if az == "":
        az = None

    stichworte = roh.get("stichworte")
    if not isinstance(stichworte, list) or not all(
            isinstance(s, str) and s.strip() for s in stichworte):
        raise EingabeFehler(f"{pfad}.stichworte: muss eine Liste nicht-leerer Texte sein, "
                            f"ist: {stichworte!r}")

    quelle = roh.get("quelle")
    if quelle not in QUELLEN_WERTE:
        raise EingabeFehler(f"{pfad}.quelle: muss eine von {sorted(QUELLEN_WERTE)} sein, "
                            f"ist: {quelle!r}")

    minuten_roh = roh.get("minuten")
    if minuten_roh is not None and (isinstance(minuten_roh, bool)
                                    or not isinstance(minuten_roh, int)):
        raise EingabeFehler(f"{pfad}.minuten: muss eine ganze Zahl oder null sein, "
                            f"ist: {minuten_roh!r}")

    start = roh.get("start")
    ende = roh.get("ende")
    if start is not None and not isinstance(start, str):
        raise EingabeFehler(f"{pfad}.start: muss Text oder null sein, ist: {start!r}")
    if ende is not None and not isinstance(ende, str):
        raise EingabeFehler(f"{pfad}.ende: muss Text oder null sein, ist: {ende!r}")

    try:
        minuten = dauer_minuten(start=start, ende=ende, minuten=minuten_roh)
    except ZeitEingabeFehler as exc:
        raise EingabeFehler(f"{pfad}: {exc}") from exc

    quelle_zeit = "minuten" if minuten_roh is not None else "start_ende"

    return {
        "datum": datum, "az": az, "minuten": minuten, "quelle_zeit": quelle_zeit,
        "stichworte": list(stichworte), "quelle": quelle,
    }


def _pruefe_config(roh: Any) -> dict[str, Any]:
    if roh is None:
        return {"takt_minuten": None}
    if not isinstance(roh, dict):
        raise EingabeFehler(f"config: muss ein JSON-Objekt sein, ist: {roh!r}")
    unbekannt = set(roh) - {"takt_minuten"}
    if unbekannt:
        raise EingabeFehler(f"config: unbekanntes Feld {sorted(unbekannt)!r}")
    takt = roh.get("takt_minuten")
    if takt is not None and (isinstance(takt, bool) or not isinstance(takt, int) or takt <= 0):
        raise EingabeFehler(f"config.takt_minuten: muss eine ganze Zahl > 0 oder null sein, "
                            f"ist: {takt!r}")
    return {"takt_minuten": takt}


def baue_report(daten: Any, eingabe_datei: str) -> dict[str, Any]:
    if not isinstance(daten, dict):
        raise EingabeFehler(f"Wurzel: muss ein JSON-Objekt sein, ist: {type(daten).__name__}")
    unbekannt = set(daten) - {"eintraege", "config"}
    if unbekannt:
        raise EingabeFehler(f"Wurzel: unbekanntes Feld {sorted(unbekannt)!r}")
    if "eintraege" not in daten:
        raise EingabeFehler("Wurzel: Pflichtfeld `eintraege` fehlt")
    eintraege_roh = daten["eintraege"]
    if not isinstance(eintraege_roh, list):
        raise EingabeFehler(f"`eintraege`: muss eine Liste sein, ist: {type(eintraege_roh).__name__}")

    config = _pruefe_config(daten.get("config"))
    takt = config["takt_minuten"]

    mit_az: list[dict[str, Any]] = []
    ohne_az: list[dict[str, Any]] = []
    for i, roh in enumerate(eintraege_roh):
        e = _pruefe_eintrag(roh, i)
        try:
            minuten_getaktet = runde_auf_takt(e["minuten"], takt)
        except ZeitEingabeFehler as exc:
            raise EingabeFehler(f"eintraege[{i}]: {exc}") from exc
        eintrag_report = {
            "index": i,
            "datum": e["datum"],
            "az": e["az"],
            "minuten": e["minuten"],
            "minuten_getaktet": minuten_getaktet,
            "quelle_zeit": e["quelle_zeit"],
            "stichworte": e["stichworte"],
            "quelle": e["quelle"],
        }
        (mit_az if e["az"] is not None else ohne_az).append(eintrag_report)

    zeit_eintraege = [ZeitEintrag(az=e["az"], datum=e["datum"], minuten=e["minuten_getaktet"])
                      for e in mit_az]
    je_az = summe_je_az(zeit_eintraege)
    je_az_datum = summe_je_az_und_datum(zeit_eintraege)
    je_az_datum_liste = [
        {"az": az, "datum": datum, "minuten": minuten}
        for (az, datum), minuten in sorted(je_az_datum.items())
    ]

    alle = mit_az + ohne_az
    minuten_gesamt = sum(e["minuten"] for e in alle)
    minuten_gesamt_getaktet = sum(e["minuten_getaktet"] for e in alle)

    return {
        "meta": {
            "erzeugt_von": ERZEUGT_VON,
            "eingabe_datei": eingabe_datei,
            "config": config,
            "deterministik": ("Alle Minuten-, Datums- und Summenwerte in diesem "
                              "Report sind Executor-Ergebnisse (P3), nicht "
                              "modellgeneriert."),
        },
        "eintraege": mit_az,
        "ohne_az": ohne_az,
        "summen": {
            "je_az": dict(sorted(je_az.items())),
            "je_az_und_datum": je_az_datum_liste,
        },
        "zusammenfassung": {
            "anzahl_eintraege": len(alle),
            "anzahl_mit_az": len(mit_az),
            "anzahl_ohne_az": len(ohne_az),
            "minuten_gesamt": minuten_gesamt,
            "minuten_gesamt_getaktet": minuten_gesamt_getaktet,
        },
    }


# --------------------------------------------------------------------------
# Modus 2 — Provenienz-Gate (Text gegen Report)
# --------------------------------------------------------------------------

_MINUTEN_RE = re.compile(r"(\d+)\s*(?:Minuten|Minute|Min\.)")
_STUNDEN_RE = re.compile(r"(\d+(?:,\d+)?)\s*(?:Stunden|Stunde|Std\.)")
_DATUM_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATUM_DE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?!\d)")
# Aktenzeichen-Heuristik dieses Skills: Ziffern/Jahr (z. B. „12/2026"), die
# Repo-Konvention für das interne `az`-Feld (siehe schema/README.md). Andere
# Kanzlei-Formate (Gerichts-Aktenzeichen wie „12 O 345/26") erkennt dieses
# Muster nicht — dokumentierte Grenze, siehe SKILL.md „Grenzen".
_AZ_RE = re.compile(r"\b\d{1,5}/\d{4}\b")


def _kanon_datum(jahr: str, monat: str, tag: str) -> str | None:
    j = jahr
    if len(j) == 2:
        jj = int(j)
        j = ("20" if jj <= 69 else "19") + j
    try:
        _dt.date(int(j), int(monat), int(tag))
    except ValueError:
        return None
    return f"{int(j):04d}-{int(monat):02d}-{int(tag):02d}"


def _sammle_report_werte(report: dict[str, Any]) -> tuple[set[int], set[str], set[str]]:
    minuten_erlaubt: set[int] = set()
    daten_erlaubt: set[str] = set()
    az_erlaubt: set[str] = set()

    def erfasse_eintrag(e: dict[str, Any]) -> None:
        if isinstance(e.get("minuten"), int):
            minuten_erlaubt.add(e["minuten"])
        if isinstance(e.get("minuten_getaktet"), int):
            minuten_erlaubt.add(e["minuten_getaktet"])
        if isinstance(e.get("datum"), str):
            daten_erlaubt.add(e["datum"])
        if e.get("az"):
            az_erlaubt.add(e["az"])

    for e in report.get("eintraege", []) or []:
        if isinstance(e, dict):
            erfasse_eintrag(e)
    for e in report.get("ohne_az", []) or []:
        if isinstance(e, dict):
            erfasse_eintrag(e)

    summen = report.get("summen", {}) or {}
    for wert in (summen.get("je_az", {}) or {}).values():
        if isinstance(wert, int):
            minuten_erlaubt.add(wert)
    for eintrag in summen.get("je_az_und_datum", []) or []:
        if isinstance(eintrag, dict):
            if isinstance(eintrag.get("minuten"), int):
                minuten_erlaubt.add(eintrag["minuten"])
            if isinstance(eintrag.get("datum"), str):
                daten_erlaubt.add(eintrag["datum"])

    zusammenfassung = report.get("zusammenfassung", {}) or {}
    for feld in ("minuten_gesamt", "minuten_gesamt_getaktet"):
        if isinstance(zusammenfassung.get(feld), int):
            minuten_erlaubt.add(zusammenfassung[feld])

    return minuten_erlaubt, daten_erlaubt, az_erlaubt


def _erfasse_datumsfund(roh: str, kanon: str | None, daten_erlaubt: set[str],
                        sammlung: list[dict[str, Any]], befunde: list[dict[str, Any]]) -> None:
    if kanon is None:
        sammlung.append({"roh": roh, "normalisiert": None, "status": "fremd"})
        befunde.append({"typ": "fremdes_datum", "roh": roh, "normalisiert": None,
                        "hinweis": "kein gültiges Kalenderdatum"})
        return
    status = "belegt" if kanon in daten_erlaubt else "fremd"
    sammlung.append({"roh": roh, "normalisiert": kanon, "status": status})
    if status == "fremd":
        befunde.append({"typ": "fremdes_datum", "roh": roh, "normalisiert": kanon,
                        "hinweis": "kein Executor-Datum im Report"})


def pruefe_text(text: str, report: dict[str, Any], text_datei: str,
                report_datei: str) -> dict[str, Any]:
    minuten_erlaubt, daten_erlaubt, az_erlaubt = _sammle_report_werte(report)

    gefundene_minuten: list[dict[str, Any]] = []
    befunde: list[dict[str, Any]] = []

    for m in _MINUTEN_RE.finditer(text):
        wert = int(m.group(1))
        status = "belegt" if wert in minuten_erlaubt else "fremd"
        gefundene_minuten.append({"roh": m.group(0), "normalisiert": wert,
                                  "typ": "minuten", "status": status})
        if status == "fremd":
            befunde.append({"typ": "fremde_zahl", "roh": m.group(0), "normalisiert": wert,
                            "hinweis": "kein Executor-Wert im Report (Minuten)"})

    for m in _STUNDEN_RE.finditer(text):
        stunden = Decimal(m.group(1).replace(",", "."))
        minuten_dec = stunden * 60
        if minuten_dec == minuten_dec.to_integral_value():
            wert = int(minuten_dec)
            status = "belegt" if wert in minuten_erlaubt else "fremd"
            gefundene_minuten.append({"roh": m.group(0), "normalisiert": wert,
                                      "typ": "stunden", "status": status})
            if status == "fremd":
                befunde.append({"typ": "fremde_zahl", "roh": m.group(0), "normalisiert": wert,
                                "hinweis": "kein Executor-Wert im Report (Stunden → Minuten)"})
        else:
            gefundene_minuten.append({"roh": m.group(0), "normalisiert": None,
                                      "typ": "stunden", "status": "fremd"})
            befunde.append({"typ": "fremde_zahl", "roh": m.group(0), "normalisiert": None,
                            "hinweis": "Stundenwert ergibt keine ganze Minutenzahl — "
                                      "nicht normalisierbar"})

    gefundene_daten: list[dict[str, Any]] = []
    for m in _DATUM_ISO_RE.finditer(text):
        kanon = _kanon_datum(m.group(1), m.group(2), m.group(3))
        _erfasse_datumsfund(m.group(0), kanon, daten_erlaubt, gefundene_daten, befunde)
    for m in _DATUM_DE_RE.finditer(text):
        kanon = _kanon_datum(m.group(3), m.group(2), m.group(1))
        _erfasse_datumsfund(m.group(0), kanon, daten_erlaubt, gefundene_daten, befunde)

    gefundene_az: list[dict[str, Any]] = []
    for m in _AZ_RE.finditer(text):
        wert = m.group(0)
        status = "belegt" if wert in az_erlaubt else "fremd"
        gefundene_az.append({"roh": wert, "status": status})
        if status == "fremd":
            befunde.append({"typ": "fremdes_aktenzeichen", "roh": wert,
                            "hinweis": "kein Aktenzeichen im Report"})

    ergebnis = "sauber" if not befunde else "abweichend"
    return {
        "meta": {
            "erzeugt_von": ERZEUGT_VON,
            "text_datei": text_datei,
            "report_datei": report_datei,
            "deterministik": ("Jeder Beleg-Zustand (belegt/fremd) in diesem "
                              "Prüf-Report ist ein Executor-Ergebnis (P3), "
                              "nicht modellgeneriert."),
        },
        "gefundene_werte": {
            "minuten": gefundene_minuten,
            "daten": gefundene_daten,
            "aktenzeichen": gefundene_az,
        },
        "befunde": befunde,
        "zusammenfassung": {
            "anzahl_gefunden": len(gefundene_minuten) + len(gefundene_daten) + len(gefundene_az),
            "anzahl_befunde": len(befunde),
        },
        "ergebnis": ergebnis,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _ausgabe(report: dict[str, Any], output: str | None) -> bool:
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        try:
            Path(output).write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Fehler: Datei konnte nicht geschrieben werden: {exc}", file=sys.stderr)
            return False
    else:
        print(text)
    return True


def _modus_rechnen(args: argparse.Namespace) -> int:
    pfad = Path(args.input)
    if not pfad.is_file():
        print(f"Fehler: Eingabedatei nicht gefunden: {pfad}", file=sys.stderr)
        return 2
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Fehler: Eingabedatei ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 2
    try:
        report = baue_report(daten, eingabe_datei=str(pfad))
    except EingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0 if _ausgabe(report, args.output) else 2


def _modus_pruefe(args: argparse.Namespace) -> int:
    text_pfad = Path(args.pruefe_text)
    report_pfad = Path(args.report)
    if not text_pfad.is_file():
        print(f"Fehler: Text-Datei nicht gefunden: {text_pfad}", file=sys.stderr)
        return 2
    if not report_pfad.is_file():
        print(f"Fehler: Report-Datei nicht gefunden: {report_pfad}", file=sys.stderr)
        return 2
    try:
        report = json.loads(report_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Fehler: Report-Datei ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 2
    erzeugt_von = report.get("meta", {}).get("erzeugt_von", "") if isinstance(report, dict) else ""
    if not erzeugt_von.endswith("taetigkeitstext-rvg/executor.py"):
        print("Fehler: Report ist kein gültiger taetigkeitstext-rvg-Executor-Report "
              "(meta.erzeugt_von fehlt/abweichend) — modellgenerierte Reports werden "
              "abgelehnt (P3)", file=sys.stderr)
        return 2

    text = text_pfad.read_text(encoding="utf-8")
    pruef_report = pruefe_text(text, report, text_datei=str(text_pfad),
                               report_datei=str(report_pfad))
    if not _ausgabe(pruef_report, args.output):
        return 2
    return 0 if pruef_report["ergebnis"] == "sauber" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="Leistungen-JSON (Modus 1: rechnen)")
    parser.add_argument("--pruefe-text", help="Entwurfs-Text (Modus 2: Provenienz-Gate)")
    parser.add_argument("--report", help="Report-JSON aus Modus 1 (Pflicht mit --pruefe-text)")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    if args.input and args.pruefe_text:
        print("Fehler: --input und --pruefe-text schließen sich aus (zwei getrennte Modi)",
              file=sys.stderr)
        return 2
    if args.pruefe_text:
        if not args.report:
            print("Fehler: --pruefe-text verlangt --report", file=sys.stderr)
            return 2
        return _modus_pruefe(args)
    if args.input:
        return _modus_rechnen(args)
    print("Fehler: --input (Modus 1) oder --pruefe-text/--report (Modus 2) erforderlich",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
