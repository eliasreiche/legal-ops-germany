"""Tests für core/calc/extf/parser.py — strikter EXTF-Leser (Format 700).

Kern-Zusicherung (Pflicht laut Auftrag): **Round-Trip gegen den eigenen
Writer** — Writer-Ausgabe → Parser → identische Werte. Dazu die
Reject-Matrix: jeder Formatverstoß ist ein ExtfParseFehler mit Zeilenangabe,
kein Traceback, keine stille Reparatur.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
CALC = REPO / "plugins" / "legal-ops" / "core" / "calc"
# Nur core/calc auf den Pfad — Importe strikt paket-qualifiziert (extf.executor,
# extf.parser), nie bare `import executor`/`import parser`: mehrere Skills
# tragen ein Modul namens `executor`, ein bare-Import würde sys.modules
# vergiften und fremde Tests (z. B. zitat-pruefer) im Vollauf brechen.
if str(CALC) not in sys.path:
    sys.path.insert(0, str(CALC))

from extf import executor as extf_executor  # core/calc/extf/executor.py (Writer = Orakel)
from extf.parser import (ExtfParseFehler, ExtfStapel, parse_extf,
                         parse_extf_datei)

GOLDEN = REPO / "plugins" / "legal-ops" / "skills" / "datev-export" / "tests" / "golden"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

GRUNDFALL = {
    "header": {
        "erzeugt_am": "2026-07-13T10:00:00",
        "exportiert_von": "Kanzlei Mustermann",
        "beraternummer": 12345,
        "mandantennummer": 100,
        "wirtschaftsjahresbeginn": "2026-01-01",
        "buchungszeitraum_von": "2026-01-01",
        "buchungszeitraum_bis": "2026-12-31",
        "bezeichnung": "Buchungsstapel Juli 2026",
    },
    "buchungen": [
        {"umsatz": "952.50", "soll_haben": "S", "konto": "1200",
         "gegenkonto": "8400", "belegdatum": "2026-03-15",
         "belegfeld1": "RE-2026-042", "buchungstext": "Honorar Müller ./. Schmidt"},
    ],
}


def _extf_bytes(eingabe: dict) -> bytes:
    inhalt, _ = extf_executor.baue_export(eingabe, "test")
    return inhalt.encode("cp1252")


# --------------------------------------------------------------------------
# Round-Trip: Writer -> Parser -> identische Werte (Pflicht)
# --------------------------------------------------------------------------

def _erwartete_buchung(roh: dict, jahr: int) -> dict:
    d = dt.date.fromisoformat(roh["belegdatum"])
    assert d.year == jahr
    return {
        "umsatz": Decimal(roh["umsatz"]),
        "soll_haben": roh["soll_haben"],
        "konto": roh["konto"],
        "gegenkonto": roh["gegenkonto"],
        "belegdatum": d,
        "belegfeld1": roh.get("belegfeld1"),
        "belegfeld2": roh.get("belegfeld2"),
        "buchungstext": roh.get("buchungstext"),
        "bu_schluessel": roh.get("bu_schluessel"),
        "skonto": Decimal(roh["skonto"]) if roh.get("skonto") else None,
    }


@pytest.mark.parametrize("eingabe_name", ["grundfall", "eingabe_2", "eingabe_3"])
def test_roundtrip_writer_parser_identische_werte(eingabe_name):
    if eingabe_name == "grundfall":
        eingabe = GRUNDFALL
    else:
        eingabe = json.loads((GOLDEN / f"{eingabe_name}.json").read_text(encoding="utf-8"))

    stapel = parse_extf(_extf_bytes(eingabe))
    assert isinstance(stapel, ExtfStapel)

    # Header-Werte identisch zur Eingabe
    h = stapel.header
    hi = eingabe["header"]
    assert h["beraternummer"] == hi["beraternummer"]
    assert h["mandantennummer"] == hi["mandantennummer"]
    assert h["exportiert_von"] == hi["exportiert_von"]
    assert h["bezeichnung"] == hi["bezeichnung"]
    assert h["buchungszeitraum_von"] == dt.date.fromisoformat(hi["buchungszeitraum_von"])
    assert h["buchungszeitraum_bis"] == dt.date.fromisoformat(hi["buchungszeitraum_bis"])
    assert h["wirtschaftsjahresbeginn"] == dt.date.fromisoformat(hi["wirtschaftsjahresbeginn"])
    assert h["sachkontenlaenge"] == hi.get("sachkontenlaenge", 4)

    # Buchungs-Werte identisch
    jahr = dt.date.fromisoformat(hi["buchungszeitraum_von"]).year
    assert len(stapel.buchungen) == len(eingabe["buchungen"])
    for gebucht, roh in zip(stapel.buchungen, eingabe["buchungen"]):
        erwartet = _erwartete_buchung(roh, jahr)
        assert gebucht.umsatz == erwartet["umsatz"]
        assert gebucht.soll_haben == erwartet["soll_haben"]
        assert gebucht.konto == erwartet["konto"]
        assert gebucht.gegenkonto == erwartet["gegenkonto"]
        assert gebucht.belegdatum == erwartet["belegdatum"]
        assert gebucht.belegfeld1 == erwartet["belegfeld1"]
        assert gebucht.belegfeld2 == erwartet["belegfeld2"]
        assert gebucht.buchungstext == erwartet["buchungstext"]
        assert gebucht.bu_schluessel == erwartet["bu_schluessel"]
        assert gebucht.skonto == erwartet["skonto"]


def test_roundtrip_erzeugt_am_millisekunden():
    eingabe = json.loads((GOLDEN / "eingabe_2.json").read_text(encoding="utf-8"))
    stapel = parse_extf(_extf_bytes(eingabe))
    assert stapel.header["erzeugt_am"] == dt.datetime(2026, 8, 1, 9, 30, 15, 500000)


def test_roundtrip_embedded_quotes_buchungstext():
    # eingabe_3 hat buchungstext mit eingebetteten Anführungszeichen.
    eingabe = json.loads((GOLDEN / "eingabe_3.json").read_text(encoding="utf-8"))
    stapel = parse_extf(_extf_bytes(eingabe))
    assert stapel.buchungen[0].buchungstext == 'Vorschuss "Projekt X"'


def test_parse_golden_fixture_bytes_direkt():
    stapel = parse_extf((GOLDEN / "erwartet_2.csv").read_bytes())
    assert len(stapel.buchungen) == 2
    assert stapel.buchungen[0].umsatz == Decimal("1500.00")
    assert stapel.buchungen[1].skonto == Decimal("5.00")


def test_parse_extf_datei_pfad():
    stapel = parse_extf_datei(FIXTURES / "beispiel-buchungsstapel.csv")
    assert len(stapel.buchungen) == 4


def test_belegdatum_none_bei_wj_ueber_jahresgrenze():
    eingabe = json.loads(json.dumps(GRUNDFALL))
    eingabe["header"]["wirtschaftsjahresbeginn"] = "2026-07-01"
    eingabe["header"]["buchungszeitraum_von"] = "2026-07-01"
    eingabe["header"]["buchungszeitraum_bis"] = "2027-06-30"
    eingabe["buchungen"][0]["belegdatum"] = "2026-09-15"
    stapel = parse_extf(_extf_bytes(eingabe))
    # Jahr nicht eindeutig -> belegdatum None, aber TTMM erhalten.
    assert stapel.buchungen[0].belegdatum is None
    assert stapel.buchungen[0].belegdatum_ttmm == "1509"


# --------------------------------------------------------------------------
# Reject-Matrix -> ExtfParseFehler mit Zeilenangabe, kein Traceback
# --------------------------------------------------------------------------

def test_reject_falsche_kennung():
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf('"CSV";1;1;"X";' + ";" * 27 + "\r\n" + '"a";' * 19 + '"b"\r\n')
    assert "Zeile 1" in str(exc.value)


def test_reject_zu_wenige_zeilen():
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf('"EXTF";700;21;"Buchungsstapel"' + ";" * 27 + "\r\n")
    assert "unvollständig" in str(exc.value) or "Header" in str(exc.value)


def test_reject_falsche_header_feldzahl():
    zeile1 = '"EXTF";700;21;"Buchungsstapel";5;20260101000000000\r\n'  # zu wenige Felder
    kopf = ";".join(f'"{k}"' for k in [
        "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz",
        "Kurs", "Basis-Umsatz", "WKZ Basis-Umsatz", "Konto",
        "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum",
        "Belegfeld 1", "Belegfeld 2", "Skonto", "Buchungstext", "Postensperre",
        "Diverse Adressnummer", "Geschäftspartnerbank", "Sachverhalt",
        "Zinssperre", "Beleglink"]) + "\r\n"
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf(zeile1 + kopf)
    assert "31 Felder" in str(exc.value)


def test_reject_falsche_spaltenkoepfe():
    eingabe = _extf_bytes(GRUNDFALL).decode("cp1252")
    kaputt = eingabe.replace('"Umsatz (ohne Soll/Haben-Kz)"', '"Falscher Kopf"')
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf(kaputt)
    assert "Zeile 2" in str(exc.value)


def test_reject_buchung_falsche_spaltenzahl():
    zeilen = _extf_bytes(GRUNDFALL).decode("cp1252").split("\r\n")
    zeilen[2] = zeilen[2] + ";extra"  # 21 Spalten
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf("\r\n".join(zeilen))
    assert "Zeile 3" in str(exc.value) and "Spalten" in str(exc.value)


def test_reject_umsatz_mit_punkt():
    zeilen = _extf_bytes(GRUNDFALL).decode("cp1252").split("\r\n")
    zeilen[2] = zeilen[2].replace("952,50", "952.50", 1)
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf("\r\n".join(zeilen))
    assert "Punkt" in str(exc.value)


def test_reject_umsatz_negativ():
    zeilen = _extf_bytes(GRUNDFALL).decode("cp1252").split("\r\n")
    zeilen[2] = zeilen[2].replace("952,50", "-1,00", 1)
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf("\r\n".join(zeilen))
    assert "> 0" in str(exc.value)


def test_reject_konto_nicht_numerisch():
    zeilen = _extf_bytes(GRUNDFALL).decode("cp1252").split("\r\n")
    zeilen[2] = zeilen[2].replace(";1200;8400;", ";ABCD;8400;", 1)
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf("\r\n".join(zeilen))
    assert "Konto" in str(exc.value)


def test_reject_befuellte_platzhalterspalte():
    zeilen = _extf_bytes(GRUNDFALL).decode("cp1252").split("\r\n")
    spalten = zeilen[2].split(";")
    spalten[14] = "1"  # Postensperre (v1 nicht unterstützt)
    zeilen[2] = ";".join(spalten)
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf("\r\n".join(zeilen))
    assert "nicht unterstützt" in str(exc.value) or "befüllt" in str(exc.value)


def test_reject_nicht_cp1252_bytes():
    # 0x81 ist in CP1252 undefiniert -> Decode-Fehler (CP1252 ist sonst sehr
    # permissiv und dekodiert fast jedes Byte).
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf(b'"EXTF";700;\x81')
    assert "CP1252" in str(exc.value)


def test_reject_datei_nicht_gefunden(tmp_path):
    with pytest.raises(ExtfParseFehler) as exc:
        parse_extf_datei(tmp_path / "gibtsnicht.csv")
    assert "nicht gefunden" in str(exc.value)
