#!/usr/bin/env python3
"""fristen/kalender — CLI-Executor (P2/P3): Fristen-Report rein, Kalender raus.

Zweiter Executor des Skills `fristenrechner`. Er nimmt **ausschließlich**
den JSON-Report von `executor.py` (die Fristberechnung) und erzeugt daraus
einen Kalender-/Docketing-Export (iCal `.ics` oder CSV) zum Import in
Fristenkalender oder Kanzleisoftware.

Deterministik-Grenze (P3): Jeder Datumswert im Export stammt **unverändert**
aus dem Report bzw. wird hier aus Report-Daten deterministisch abgeleitet
(Vorfrist = Fristende − Vorlauftage, iCal-DTEND = Fristende + 1 Tag). Das
Modell rechnet nie selbst — es übergibt den Report und liest den Export.

„Re-Export nur bei Korrektur" (Datei-Ebene): Die VEVENT-`UID` ist ein
deterministischer Hash der Fristidentität (Ereignis, Fristart/Dauer, Fristtyp,
Bundesland, Fristende, Aktenzeichen). Unveränderte Frist → identische Bytes →
Re-Import aktualisiert dasselbe Ereignis (kein Duplikat). Eine **korrigierte**
Frist ändert die Identität → neue UID → neues Ereignis. Wall-Clock-Werte
(DTSTAMP) werden aus dem Report abgeleitet, damit der Export byte-stabil ist.

Eingabe (JSON-Report, Schema: plugins/legal-ops/skills/fristenrechner/
schema/README.md → Abschnitt „Kalender-Export"):

    python3 core/calc/fristen/kalender_executor.py \
      --report REPORT.json [--format ics|csv|beide] \
      [--output DATEI | --output-dir ORDNER] \
      [--aktenzeichen AZ] [--bezeichnung TEXT] [--vorlauftage N]

Exit-Codes: 0 = Export erzeugt, 2 = Eingabefehler (kein Traceback).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PRODID = "-//claude-for-legal-non-billable-germany//fristenrechner//DE"
UID_DOMAIN = "fristenrechner.legal-ops"
# Zweitkontroll-Klausel (P5) — steht immer in Beschreibung und CSV.
ZWEITKONTROLLE = ("Zweitkontrolle bleibt zwingend: Dieser Export ersetzt keinen "
                  "Fristenkalender mit Vier-Augen-Prinzip. Import und Kontrolle "
                  "im Zielsystem verantwortet die Kanzlei.")

# Statische Norm-Belehrungen dieses Moduls (Notfrist-/Einspruchs-Hinweis in
# der Kalender-Beschreibung) — als benannte Konstanten, damit der
# CI-Marker-Konsistenz-Test (tests/test_zitiermarker_statisch.py) sie ohne
# fragiles Quelltext-Grep über STATISCHE_NORM_BELEHRUNGEN abgreifen kann.
# Rein additiv/Umbenennung — _beschreibungszeilen() nutzt dieselben Texte
# unverändert weiter.
NOTFRIST_BELEHRUNG = ("✅ Notfrist — nicht verlängerbar (§ 224 Abs. 2 ZPO); bei "
                     "Versäumung nur Wiedereinsetzung (§§ 233 ff. ZPO).")
KEIN_TECHNISCHES_FRISTENDE_BELEHRUNG = (
    "✅ Kein Fristende im technischen Sinn — das Datum ist nur der "
    "Ablauf der Belehrungsfrist; verspäteter Widerspruch gilt als "
    "Einspruch (§ 694 ZPO). Nicht als harte Frist behandeln.")

STATISCHE_NORM_BELEHRUNGEN: list[dict[str, str]] = [
    {"marker": "✅", "text": NOTFRIST_BELEHRUNG},
    {"marker": "✅", "text": KEIN_TECHNISCHES_FRISTENDE_BELEHRUNG},
]


class ExportEingabeFehler(ValueError):
    """Eingabefehler → Exit 2 mit klarer Meldung, nie Traceback."""


# --------------------------------------------------------------------------
# Report lesen & prüfen
# --------------------------------------------------------------------------

def _lade_report(pfad: Path) -> dict[str, Any]:
    if not pfad.is_file():
        raise ExportEingabeFehler(f"Report-Datei nicht gefunden: {pfad}")
    try:
        report = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExportEingabeFehler(f"Report-Datei ist kein gültiges JSON: {exc}")
    if not isinstance(report, dict):
        raise ExportEingabeFehler("Report muss ein JSON-Objekt sein")
    ergebnis = report.get("ergebnis")
    if not isinstance(ergebnis, dict) or not ergebnis.get("fristende"):
        raise ExportEingabeFehler(
            "kein gültiger Fristen-Report: 'ergebnis.fristende' fehlt — erwartet "
            "wird die Ausgabe von core/calc/fristen/executor.py")
    if ergebnis.get("quelle") != "executor":
        # Schutz gegen modellgenerierte Fantasie-Reports (P3): nur echte
        # Executor-Reports exportieren.
        raise ExportEingabeFehler(
            "Report ist nicht als Executor-Ergebnis markiert "
            "('ergebnis.quelle' != 'executor') — es werden nur Reports aus "
            "der Fristberechnung exportiert, keine modellgenerierten Werte (P3)")
    return report


def _datum(iso: str, feld: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(iso)
    except (ValueError, TypeError):
        raise ExportEingabeFehler(f"'{feld}' ist kein ISO-Datum: {iso!r}")


# --------------------------------------------------------------------------
# Abgeleitete Werte (P3: hier, nicht im Modell)
# --------------------------------------------------------------------------

def _vorlauftage(wert: int | str | None) -> int:
    if wert is None:
        return 3
    try:
        n = int(wert)
    except (ValueError, TypeError):
        raise ExportEingabeFehler(f"'vorlauftage' muss eine ganze Zahl ≥ 0 sein, "
                                  f"nicht {wert!r}")
    if n < 0:
        raise ExportEingabeFehler(f"'vorlauftage' darf nicht negativ sein: {n}")
    return n


def _fristidentitaet(report: dict[str, Any], aktenzeichen: str | None) -> str:
    """Stabile, korrektur-empfindliche Identität der Frist für die UID."""
    e = report.get("eingabe", {})
    erg = report["ergebnis"]
    teile = [
        str(e.get("ereignis_datum")), str(e.get("fristart")),
        str(e.get("dauer")), str(e.get("einheit")), str(e.get("fristtyp")),
        str(e.get("bundesland")), str(e.get("paragraf_193_anwenden")),
        str(erg.get("fristende")), str(erg.get("kein_technisches_fristende")),
        (aktenzeichen or "").strip(),
    ]
    roh = "|".join(teile)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


def _uid(report: dict[str, Any], aktenzeichen: str | None) -> str:
    return f"{_fristidentitaet(report, aktenzeichen)}@{UID_DOMAIN}"


# --------------------------------------------------------------------------
# Gemeinsame Feldaufbereitung
# --------------------------------------------------------------------------

def _kontext(report: dict[str, Any], aktenzeichen: str | None,
             bezeichnung: str | None, vorlauftage: int) -> dict[str, Any]:
    erg = report["ergebnis"]
    fristart = report.get("fristart") or {}
    fristende = _datum(erg["fristende"], "ergebnis.fristende")
    vorfrist = fristende - _dt.timedelta(days=vorlauftage)

    label = (bezeichnung or fristart.get("bezeichnung") or "Frist").strip()
    kein_tech = bool(erg.get("kein_technisches_fristende"))
    notfrist = bool(fristart.get("notfrist"))

    if kein_tech:
        titel = f"Kontrolltermin (kein technisches Fristende): {label}"
    else:
        titel = f"Frist: {label}"
    if notfrist:
        titel += " [NOTFRIST]"
    if aktenzeichen:
        titel += f" — Az. {aktenzeichen.strip()}"

    teil_ende = erg.get("fristende_bei_teilgebietlichem_feiertag")
    return {
        "fristende": fristende,
        "vorfrist": vorfrist,
        "vorlauftage": vorlauftage,
        "titel": titel,
        "label": label,
        "norm": fristart.get("norm"),
        "notfrist": notfrist,
        "kein_technisches_fristende": kein_tech,
        "verschoben": bool(erg.get("verschoben")),
        "teilgebietliches_ende": teil_ende,
        "bundesland": report.get("eingabe", {}).get("bundesland"),
        "warnungen": list(report.get("warnungen", [])),
        "hinweise": list(report.get("hinweise", [])),
        "fristbeginn": erg.get("fristbeginn"),
    }


def _beschreibungszeilen(k: dict[str, Any]) -> list[str]:
    z: list[str] = []
    if k["norm"]:
        z.append(f"Fristart: {k['label']} — {k['norm']} ✅ (verifiziert: aus "
                 f"Fristberechnungs-Report)")
    else:
        z.append(f"Fristart: {k['label']} (freie Frist)")
    z.append(f"Fristende: {k['fristende'].strftime('%d.%m.%Y')}"
             + (" (nach § 193 BGB verschoben)" if k["verschoben"] else ""))
    z.append(f"Vorfrist ({k['vorlauftage']} Tage vorher): "
             f"{k['vorfrist'].strftime('%d.%m.%Y')}")
    if k["notfrist"]:
        z.append(NOTFRIST_BELEHRUNG)
    if k["kein_technisches_fristende"]:
        z.append(KEIN_TECHNISCHES_FRISTENDE_BELEHRUNG)
    if k["teilgebietliches_ende"]:
        z.append(f"⚠️ Teilgebietlicher Feiertag möglich: Fällt am Fristende-Ort "
                 f"ein nur örtlich geltender Feiertag an, verschiebt sich das "
                 f"Ende auf {_datum(k['teilgebietliches_ende'], 'teil').strftime('%d.%m.%Y')}. "
                 f"Das frühere Ende ist vorsorglich notiert — konkrete Gemeinde prüfen.")
    for w in k["warnungen"]:
        z.append(f"Warnung: {w}")
    for h in k["hinweise"]:
        z.append(f"Hinweis: {h}")
    z.append(ZWEITKONTROLLE)
    return z


# --------------------------------------------------------------------------
# iCal (RFC 5545)
# --------------------------------------------------------------------------

def _ical_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold(zeile: str) -> str:
    """Content-Line-Folding auf ≤75 Oktetts (RFC 5545 §3.1)."""
    roh = zeile.encode("utf-8")
    if len(roh) <= 75:
        return zeile
    teile: list[bytes] = []
    rest = roh
    grenze = 75
    while len(rest) > grenze:
        schnitt = grenze
        # nicht mitten in einem UTF-8-Mehrbyte-Zeichen trennen
        while schnitt > 0 and (rest[schnitt] & 0xC0) == 0x80:
            schnitt -= 1
        teile.append(rest[:schnitt])
        rest = rest[schnitt:]
        grenze = 74  # Folgezeilen beginnen mit einem Leerzeichen
    teile.append(rest)
    return "\r\n ".join(t.decode("utf-8") for t in teile)


def _dt_compact(datum: _dt.date) -> str:
    return datum.strftime("%Y%m%d")


def baue_ical(report: dict[str, Any], *, aktenzeichen: str | None,
              bezeichnung: str | None, vorlauftage: int) -> str:
    k = _kontext(report, aktenzeichen, bezeichnung, vorlauftage)
    uid = _uid(report, aktenzeichen)
    # DTSTAMP deterministisch aus dem Report (Fristbeginn) → byte-stabil.
    stamp_datum = _datum(k["fristbeginn"], "ergebnis.fristbeginn")
    dtstamp = f"{_dt_compact(stamp_datum)}T000000Z"
    dtstart = _dt_compact(k["fristende"])                     # Ganztags
    dtend = _dt_compact(k["fristende"] + _dt.timedelta(days=1))  # exklusiv

    beschreibung = _ical_escape("\n".join(_beschreibungszeilen(k)))

    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{_ical_escape(k['titel'])}",
        f"DESCRIPTION:{beschreibung}",
        "SEQUENCE:0",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ical_escape('Vorfrist: ' + k['titel'])}",
        f"TRIGGER:-P{vorlauftage}D",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(z) for z in zeilen) + "\r\n"


# --------------------------------------------------------------------------
# CSV (semikolon-getrennt, DE-Kanzleisoftware-freundlich)
# --------------------------------------------------------------------------

CSV_SPALTEN = [
    "fristende", "vorfrist", "vorlauftage", "titel", "fristart", "norm",
    "aktenzeichen", "bundesland", "notfrist", "verschoben",
    "kein_technisches_fristende", "alternativ_ende_teilgebietlich",
    "uid", "quelle",
]


def _csv_feld(wert: Any) -> str:
    s = "" if wert is None else str(wert)
    if any(c in s for c in ';"\r\n'):
        s = '"' + s.replace('"', '""') + '"'
    return s


def baue_csv(report: dict[str, Any], *, aktenzeichen: str | None,
             bezeichnung: str | None, vorlauftage: int) -> str:
    k = _kontext(report, aktenzeichen, bezeichnung, vorlauftage)
    zeile = {
        "fristende": k["fristende"].isoformat(),
        "vorfrist": k["vorfrist"].isoformat(),
        "vorlauftage": k["vorlauftage"],
        "titel": k["titel"],
        "fristart": k["label"],
        "norm": k["norm"] or "",
        "aktenzeichen": (aktenzeichen or "").strip(),
        "bundesland": k["bundesland"] or "",
        "notfrist": "ja" if k["notfrist"] else "nein",
        "verschoben": "ja" if k["verschoben"] else "nein",
        "kein_technisches_fristende": "ja" if k["kein_technisches_fristende"] else "nein",
        "alternativ_ende_teilgebietlich": k["teilgebietliches_ende"] or "",
        "uid": _uid(report, aktenzeichen),
        "quelle": "executor",
    }
    kopf = ";".join(CSV_SPALTEN)
    werte = ";".join(_csv_feld(zeile[s]) for s in CSV_SPALTEN)
    return kopf + "\r\n" + werte + "\r\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _schreibe(pfad: Path, inhalt: str) -> None:
    try:
        pfad.write_text(inhalt, encoding="utf-8", newline="")
    except OSError as exc:
        raise ExportEingabeFehler(f"Datei kann nicht geschrieben werden: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True,
                        help="JSON-Report aus core/calc/fristen/executor.py")
    parser.add_argument("--format", choices=["ics", "csv", "beide"],
                        default="ics", help="Exportformat (Default: ics)")
    parser.add_argument("--output", help="Zieldatei (nur für ein Format)")
    parser.add_argument("--output-dir",
                        help="Zielordner für --format beide (Dateiname aus UID)")
    parser.add_argument("--aktenzeichen", help="Aktenzeichen (Label, kein Rechenwert)")
    parser.add_argument("--bezeichnung", help="Freie Terminbezeichnung (Label)")
    parser.add_argument("--vorlauftage", default=3,
                        help="Vorfrist-Vorlauf in Tagen (Default: 3)")
    args = parser.parse_args(argv)

    try:
        report = _lade_report(Path(args.report))
        vorlauftage = _vorlauftage(args.vorlauftage)
        opts = dict(aktenzeichen=args.aktenzeichen,
                    bezeichnung=args.bezeichnung, vorlauftage=vorlauftage)

        if args.format == "beide":
            if not args.output_dir:
                raise ExportEingabeFehler(
                    "--format beide verlangt --output-dir (zwei Dateien)")
            ziel = Path(args.output_dir)
            try:
                ziel.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ExportEingabeFehler(f"Zielordner nicht anlegbar: {exc}")
            uid8 = _fristidentitaet(report, args.aktenzeichen)[:8]
            ics_pfad = ziel / f"frist-{uid8}.ics"
            csv_pfad = ziel / f"frist-{uid8}.csv"
            _schreibe(ics_pfad, baue_ical(report, **opts))
            _schreibe(csv_pfad, baue_csv(report, **opts))
            print(f"{ics_pfad}\n{csv_pfad}")
            return 0

        inhalt = (baue_ical(report, **opts) if args.format == "ics"
                  else baue_csv(report, **opts))
        if args.output:
            _schreibe(Path(args.output), inhalt)
        else:
            # stdout ohne zusätzliche Zeilenenden-Normalisierung
            sys.stdout.write(inhalt)
        return 0
    except ExportEingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
