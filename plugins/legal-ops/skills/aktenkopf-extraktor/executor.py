#!/usr/bin/env python3
"""aktenkopf-extraktor — deterministischer Provenienz- und Schema-Validator (P2/P3).

Die inhaltliche Extraktion aus dem Mandats-Dokument macht das Modell (Claude):
es liest das/die Quelldokument(e) und schreibt einen strukturierten `aktenkopf.json`
nach dem Schema in schema/README.md. Dieser Executor erfindet nichts und
extrahiert nichts — er ist die maschinelle Absicherung der Anti-Halluzinations-
Disziplin des Repos:

  (a) Schema-Konformität  — der aktenkopf.json hat die Pflichtstruktur, gültige
                            Datumsformate (ISO JJJJ-MM-TT) und wohlgeformte Einträge.
  (b) Provenienz          — jeder kritische Wert (Datum, Geldbetrag, Aktenzeichen,
                            IBAN, E-Mail, Telefonnummer) muss — nach definierter
                            Normalisierung — wörtlich in mindestens einer
                            Quelldatei vorkommen. Belegte Werte tragen ihre
                            Fundstelle (Datei + Zeile); nicht belegte Werte werden
                            als `nicht_belegt` ausgewiesen.
  (c) Lücken-Disziplin    — fehlende Pflichtangaben müssen explizit im `luecken`-
                            Array stehen. Ein leeres Pflichtfeld ohne passenden
                            Lücken-Eintrag ist ein Schema-Fehler.

WICHTIG (Deterministik-Grenze, P3): Dieses Modul vergibt die Zustände `belegt`/
`nicht_belegt`/`schema_fehler`. Das Modell orchestriert und stellt den Report dar,
darf aber keinen Beleg-Zustand selbst setzen oder überschreiben. Die erkannten
Datumsnennungen sind KEINE Fristberechnung — dafür ist der Skill `fristenrechner`
zuständig (Zweitkontrolle).

Nur Standardbibliothek. Kein Netzwerkzugriff. Liest ausschließlich lokale Dateien.

Exit-Codes:
    0 — Schema in Ordnung UND alle kritischen Werte belegt
    1 — mindestens ein `nicht_belegt`-Wert und/oder mindestens ein Schema-Fehler
    2 — Eingabefehler (Datei fehlt, kaputtes JSON, nicht schreibbares Ziel)

CLI:
    python3 executor.py --aktenkopf aktenkopf.json --quelle dokument.md
                        [--quelle weitere.txt ...] [--output report.json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ERZEUGT_VON = "aktenkopf-extraktor/executor.py"

STATUS_BELEGT = "belegt"
STATUS_NICHT_BELEGT = "nicht_belegt"

ROLLEN = {"mandant", "gegner", "sonstige"}
PARTEI_TYPEN = {"natuerlich", "juristisch"}

# Kontakt-Unterfelder, die als kritische Werte auf Provenienz geprüft werden,
# mit ihrem Normalisierungstyp.
KONTAKT_KRITISCH = {"email": "email", "telefon": "telefon", "iban": "iban"}


# --------------------------------------------------------------------------
# Normalisierung — Datum
# --------------------------------------------------------------------------

_ISO_RAW = r"(\d{4})-(\d{1,2})-(\d{1,2})"
_DE_RAW = r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})"
_DATUM_ISO = re.compile(r"\b" + _ISO_RAW + r"\b")
_DATUM_DE = re.compile(r"(?<!\d)" + _DE_RAW + r"(?!\d)")


def _norm_jahr(j: str) -> str:
    if len(j) == 2:
        jj = int(j)
        return ("20" if jj <= 69 else "19") + j
    return j.zfill(4)


def _kanon_datum(jahr: str, monat: str, tag: str) -> str | None:
    """Kanonisiert ein Datum auf `JJJJ-MM-TT`; None, wenn kein gültiges Kalenderdatum."""
    j = _norm_jahr(jahr)
    try:
        datetime.date(int(j), int(monat), int(tag))
    except ValueError:
        return None
    return f"{int(j):04d}-{int(monat):02d}-{int(tag):02d}"


def _datum_kanon_wert(wert: str) -> str | None:
    """Kanonform eines einzelnen Datumswerts (ISO `01.03.2026` ↔ `2026-03-01`)."""
    wert = wert.strip()
    mi = re.fullmatch(_ISO_RAW, wert)
    if mi:
        return _kanon_datum(mi.group(1), mi.group(2), mi.group(3))
    md = re.fullmatch(_DE_RAW, wert)
    if md:
        return _kanon_datum(md.group(3), md.group(2), md.group(1))
    return None


def _datum_kanons_in_zeile(zeile: str) -> set[str]:
    res: set[str] = set()
    for m in _DATUM_ISO.finditer(zeile):
        k = _kanon_datum(m.group(1), m.group(2), m.group(3))
        if k:
            res.add(k)
    for m in _DATUM_DE.finditer(zeile):
        k = _kanon_datum(m.group(3), m.group(2), m.group(1))
        if k:
            res.add(k)
    return res


# --------------------------------------------------------------------------
# Normalisierung — Geldbetrag
# --------------------------------------------------------------------------

# Entweder Betrag mit Tausenderpunkten (1.234[,56]) oder schlichte Zahl (1234[,56]).
_GELD_TOKEN = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")


def _geld_kanon(text: str) -> str | None:
    """Kanonisiert einen Geldbetrag auf `<ganzzahl>.<cent>` (deutsches Format:
    `.` = Tausendertrennung, `,` = Dezimaltrenner). Währung (€, EUR, Euro) wird
    entfernt, sodass `1.234,56 €` und `1234,56 EUR` denselben Wert ergeben."""
    ohne_waehrung = re.sub(r"(?i)eur\b|euro\b|€", "", text).strip()
    m = _GELD_TOKEN.search(ohne_waehrung)
    if not m:
        return None
    zahl = m.group(0).replace(".", "").replace(",", ".")
    try:
        return str(Decimal(zahl).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return None


def _geld_kanons_in_zeile(zeile: str) -> set[str]:
    res: set[str] = set()
    for m in _GELD_TOKEN.finditer(zeile):
        zahl = m.group(0).replace(".", "").replace(",", ".")
        try:
            res.add(str(Decimal(zahl).quantize(Decimal("0.01"))))
        except (InvalidOperation, ValueError):
            continue
    return res


# --------------------------------------------------------------------------
# Normalisierung — Aktenzeichen / IBAN / E-Mail / Telefon
# --------------------------------------------------------------------------

def _ws_collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _iban_norm(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


def _tel_norm(s: str) -> str:
    # Trennzeichen entfernen; Buchstaben/Wortgrenzen bleiben als Trenner erhalten.
    return re.sub(r"[\s/().\-]", "", s)


def _kanon_ziel(wert: str, typ: str) -> str | None:
    if typ == "datum":
        return _datum_kanon_wert(wert)
    if typ == "geld":
        return _geld_kanon(wert)
    if typ == "email":
        return wert.strip().lower() or None
    if typ == "telefon":
        return _tel_norm(wert) or None
    if typ == "iban":
        return _iban_norm(wert) or None
    if typ == "aktenzeichen":
        return _ws_collapse(wert) or None
    return None


def _zeile_belegt(zeile: str, typ: str, ziel: str) -> bool:
    if typ == "datum":
        return ziel in _datum_kanons_in_zeile(zeile)
    if typ == "geld":
        return ziel in _geld_kanons_in_zeile(zeile)
    if typ == "email":
        return ziel in zeile.lower()
    if typ == "telefon":
        return ziel in _tel_norm(zeile)
    if typ == "iban":
        return ziel in _iban_norm(zeile)
    if typ == "aktenzeichen":
        return ziel in _ws_collapse(zeile)
    return False


# --------------------------------------------------------------------------
# Provenienz-Prüfung
# --------------------------------------------------------------------------

def finde_beleg(wert: str, typ: str,
                quellen: list[tuple[str, list[str]]]) -> dict[str, Any] | None:
    """Sucht den ersten Beleg für `wert` in den Quelldateien. Rückgabe:
    Fundstelle `{datei, zeile, zitat}` oder None (nicht belegt)."""
    ziel = _kanon_ziel(wert, typ)
    if not ziel:
        return None
    for datei, zeilen in quellen:
        for i, zeile in enumerate(zeilen, start=1):
            if _zeile_belegt(zeile, typ, ziel):
                return {"datei": datei, "zeile": i, "zitat": zeile.strip()}
    return None


def sammle_kritische_werte(aktenkopf: dict[str, Any]) -> list[dict[str, str]]:
    """Läuft die bekannten Fundorte kritischer Werte defensiv ab (überspringt
    fehlerhaft getypte Strukturen, damit auch bei Schema-Fehlern kein Traceback
    entsteht) und liefert `[{pfad, typ, wert}]`."""
    werte: list[dict[str, str]] = []

    def nichtleer(v: Any) -> bool:
        return isinstance(v, str) and v.strip() != ""

    ak = aktenkopf.get("aktenkopf")
    if isinstance(ak, dict) and nichtleer(ak.get("eingangsdatum")):
        werte.append({"pfad": "aktenkopf.eingangsdatum", "typ": "datum",
                      "wert": ak["eingangsdatum"]})

    parteien = aktenkopf.get("parteien")
    if isinstance(parteien, list):
        for i, p in enumerate(parteien):
            if not isinstance(p, dict):
                continue
            kontakt = p.get("kontakt")
            if isinstance(kontakt, dict):
                for feld, typ in KONTAKT_KRITISCH.items():
                    if nichtleer(kontakt.get(feld)):
                        werte.append({"pfad": f"parteien[{i}].kontakt.{feld}",
                                      "typ": typ, "wert": kontakt[feld]})

    fristen = aktenkopf.get("fristen_hinweise")
    if isinstance(fristen, list):
        for i, f in enumerate(fristen):
            if isinstance(f, dict) and nichtleer(f.get("datum_im_text")):
                werte.append({"pfad": f"fristen_hinweise[{i}].datum_im_text",
                              "typ": "datum", "wert": f["datum_im_text"]})

    betraege = aktenkopf.get("betraege")
    if isinstance(betraege, list):
        for i, b in enumerate(betraege):
            if isinstance(b, dict) and nichtleer(b.get("betrag")):
                werte.append({"pfad": f"betraege[{i}].betrag", "typ": "geld",
                              "wert": b["betrag"]})

    azs = aktenkopf.get("aktenzeichen_fremd")
    if isinstance(azs, list):
        for i, a in enumerate(azs):
            if isinstance(a, dict) and nichtleer(a.get("aktenzeichen")):
                werte.append({"pfad": f"aktenzeichen_fremd[{i}].aktenzeichen",
                              "typ": "aktenzeichen", "wert": a["aktenzeichen"]})

    return werte


def pruefe_provenienz(aktenkopf: dict[str, Any],
                      quellen: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    ergebnisse: list[dict[str, Any]] = []
    for kw in sammle_kritische_werte(aktenkopf):
        beleg = finde_beleg(kw["wert"], kw["typ"], quellen)
        if beleg is not None:
            ergebnisse.append({
                "pfad": kw["pfad"], "typ": kw["typ"], "wert": kw["wert"],
                "status": STATUS_BELEGT, "fundstelle": beleg,
                "begruendung": f"wörtlich in Quelle gefunden (Normalisierung: {kw['typ']})",
            })
        else:
            ergebnisse.append({
                "pfad": kw["pfad"], "typ": kw["typ"], "wert": kw["wert"],
                "status": STATUS_NICHT_BELEGT, "fundstelle": None,
                "begruendung": ("kein Vorkommen in den Quelldateien "
                                f"(Normalisierung: {kw['typ']}) — Wert streichen "
                                "oder als Lücke ausweisen"),
            })
    return ergebnisse


# --------------------------------------------------------------------------
# Schema-Prüfung
# --------------------------------------------------------------------------

# Pflichtfelder, die leer sein DÜRFEN, sofern sie explizit als Lücke geführt
# werden (Lücken-Disziplin). Pfad -> None wird zur Laufzeit für Parteien ergänzt.
LUECKE_PFLICHT_AKTENKOPF = ["kurzrubrum", "sachverhalt_kurz", "eingangsdatum"]
LUECKE_PFLICHT_PARTEI = ["name", "anschrift"]


def _ist_iso(s: Any) -> bool:
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _leer(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _luecken_felder(aktenkopf: dict[str, Any]) -> set[str]:
    felder: set[str] = set()
    luecken = aktenkopf.get("luecken")
    if isinstance(luecken, list):
        for l in luecken:
            if isinstance(l, dict) and isinstance(l.get("feld"), str):
                felder.add(l["feld"].strip())
    return felder


def pruefe_schema(aktenkopf: dict[str, Any]) -> list[str]:
    fehler: list[str] = []

    if not isinstance(aktenkopf, dict):
        return ["Wurzel: aktenkopf.json muss ein JSON-Objekt sein"]

    for schluessel, typ in (("aktenkopf", dict), ("parteien", list),
                            ("fristen_hinweise", list), ("betraege", list),
                            ("aktenzeichen_fremd", list), ("luecken", list)):
        if schluessel not in aktenkopf:
            fehler.append(f"Wurzel: Pflichtschlüssel `{schluessel}` fehlt")
        elif not isinstance(aktenkopf[schluessel], typ):
            fehler.append(f"Wurzel: `{schluessel}` muss vom Typ {typ.__name__} sein")

    gedeckt = _luecken_felder(aktenkopf)

    # aktenkopf-Block
    ak = aktenkopf.get("aktenkopf")
    if isinstance(ak, dict):
        for feld in LUECKE_PFLICHT_AKTENKOPF:
            if feld not in ak:
                fehler.append(f"aktenkopf.{feld}: Pflichtfeld fehlt")
            elif _leer(ak[feld]):
                if f"aktenkopf.{feld}" not in gedeckt:
                    fehler.append(f"aktenkopf.{feld}: leer und nicht als Lücke "
                                  f"ausgewiesen (Lücken-Disziplin)")
        if not _leer(ak.get("eingangsdatum")) and not _ist_iso(ak.get("eingangsdatum")):
            fehler.append(f"aktenkopf.eingangsdatum: kein gültiges ISO-Datum "
                          f"JJJJ-MM-TT ({ak.get('eingangsdatum')!r})")

    # parteien
    parteien = aktenkopf.get("parteien")
    if isinstance(parteien, list):
        if not parteien:
            fehler.append("parteien: mindestens eine Partei (Mandant) erforderlich")
        for i, p in enumerate(parteien):
            if not isinstance(p, dict):
                fehler.append(f"parteien[{i}]: muss ein Objekt sein")
                continue
            for feld in ("rolle", "name", "typ", "anschrift", "kontakt",
                         "vertreten_durch"):
                if feld not in p:
                    fehler.append(f"parteien[{i}].{feld}: Pflichtfeld fehlt")
            if p.get("rolle") not in ROLLEN:
                fehler.append(f"parteien[{i}].rolle: muss eine von "
                              f"{sorted(ROLLEN)} sein ({p.get('rolle')!r})")
            if p.get("typ") not in PARTEI_TYPEN:
                fehler.append(f"parteien[{i}].typ: muss eine von "
                              f"{sorted(PARTEI_TYPEN)} sein ({p.get('typ')!r})")
            for feld in LUECKE_PFLICHT_PARTEI:
                if feld in p and _leer(p[feld]):
                    if f"parteien[{i}].{feld}" not in gedeckt:
                        fehler.append(f"parteien[{i}].{feld}: leer und nicht als "
                                      f"Lücke ausgewiesen (Lücken-Disziplin)")

    # fristen_hinweise
    fristen = aktenkopf.get("fristen_hinweise")
    if isinstance(fristen, list):
        for i, f in enumerate(fristen):
            if not isinstance(f, dict):
                fehler.append(f"fristen_hinweise[{i}]: muss ein Objekt sein")
                continue
            for feld in ("datum_im_text", "originalschreibweise", "quelle_zitat",
                         "vermutete_bedeutung"):
                if _leer(f.get(feld)):
                    fehler.append(f"fristen_hinweise[{i}].{feld}: fehlt oder leer "
                                  f"(erkannte Datumsnennungen sind vollständig "
                                  f"anzugeben, keine Lücke)")
            if not _leer(f.get("datum_im_text")) and not _ist_iso(f.get("datum_im_text")):
                fehler.append(f"fristen_hinweise[{i}].datum_im_text: kein gültiges "
                              f"ISO-Datum JJJJ-MM-TT ({f.get('datum_im_text')!r})")

    # betraege
    betraege = aktenkopf.get("betraege")
    if isinstance(betraege, list):
        for i, b in enumerate(betraege):
            if not isinstance(b, dict):
                fehler.append(f"betraege[{i}]: muss ein Objekt sein")
                continue
            for feld in ("betrag", "kontext", "quelle_zitat"):
                if _leer(b.get(feld)):
                    fehler.append(f"betraege[{i}].{feld}: fehlt oder leer")

    # aktenzeichen_fremd
    azs = aktenkopf.get("aktenzeichen_fremd")
    if isinstance(azs, list):
        for i, a in enumerate(azs):
            if not isinstance(a, dict):
                fehler.append(f"aktenzeichen_fremd[{i}]: muss ein Objekt sein")
                continue
            for feld in ("aktenzeichen", "stelle", "quelle_zitat"):
                if _leer(a.get(feld)):
                    fehler.append(f"aktenzeichen_fremd[{i}].{feld}: fehlt oder leer")

    # luecken
    luecken = aktenkopf.get("luecken")
    if isinstance(luecken, list):
        for i, l in enumerate(luecken):
            if not isinstance(l, dict):
                fehler.append(f"luecken[{i}]: muss ein Objekt sein")
                continue
            for feld in ("feld", "grund"):
                if _leer(l.get(feld)):
                    fehler.append(f"luecken[{i}].{feld}: fehlt oder leer")

    return fehler


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def baue_report(aktenkopf: dict[str, Any], quellen: list[tuple[str, list[str]]],
                aktenkopf_datei: str) -> dict[str, Any]:
    schema_fehler = pruefe_schema(aktenkopf)
    provenienz = pruefe_provenienz(aktenkopf, quellen)

    belegt = sum(1 for p in provenienz if p["status"] == STATUS_BELEGT)
    nicht_belegt = sum(1 for p in provenienz if p["status"] == STATUS_NICHT_BELEGT)

    luecken = aktenkopf.get("luecken") if isinstance(aktenkopf.get("luecken"), list) else []

    return {
        "meta": {
            "erzeugt_von": ERZEUGT_VON,
            "aktenkopf_datei": aktenkopf_datei,
            "quelldateien": [datei for datei, _ in quellen],
            "anzahl_kritische_werte": len(provenienz),
            "hinweis": ("Erkannte Datumsnennungen sind KEINE Fristberechnung — "
                        "Fristen nur über den Skill fristenrechner (Zweitkontrolle)."),
        },
        "schema_ok": not schema_fehler,
        "schema_fehler": schema_fehler,
        "provenienz": provenienz,
        "luecken": luecken,
        "zusammenfassung": {
            "belegt": belegt,
            "nicht_belegt": nicht_belegt,
            "schema_fehler": len(schema_fehler),
        },
    }


def report_ist_sauber(report: dict[str, Any]) -> bool:
    z = report["zusammenfassung"]
    return z["nicht_belegt"] == 0 and z["schema_fehler"] == 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aktenkopf", required=True,
                        help="Strukturierter Aktenkopf (JSON), vom Modell erzeugt")
    parser.add_argument("--quelle", action="append", required=True,
                        help="Quelldokument (.txt/.md). Mehrfach angebbar.")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    aktenkopf_pfad = Path(args.aktenkopf)
    if not aktenkopf_pfad.is_file():
        print(f"Fehler: Aktenkopf-Datei nicht gefunden: {aktenkopf_pfad}", file=sys.stderr)
        return 2

    quellen: list[tuple[str, list[str]]] = []
    for q in args.quelle:
        qp = Path(q)
        if not qp.is_file():
            print(f"Fehler: Quelldatei nicht gefunden: {qp}", file=sys.stderr)
            return 2
        quellen.append((str(qp), qp.read_text(encoding="utf-8").splitlines()))

    try:
        aktenkopf = json.loads(aktenkopf_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Fehler: Aktenkopf-Datei ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 2

    report = baue_report(aktenkopf, quellen, aktenkopf_datei=str(aktenkopf_pfad))

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Fehler: Report konnte nicht geschrieben werden: {exc}", file=sys.stderr)
            return 2
    else:
        print(ausgabe)

    return 0 if report_ist_sauber(report) else 1


if __name__ == "__main__":
    sys.exit(main())
