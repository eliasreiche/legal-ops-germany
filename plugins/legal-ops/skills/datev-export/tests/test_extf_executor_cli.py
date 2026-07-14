"""Tests für core/calc/extf/executor.py — CLI: JSON rein, EXTF-Datei +
JSON-Report raus (P2).

Deckt ab: Header-Feldpositionen (Zeile 1), CP1252/Umlaute, Komma-Dezimal,
TTMM-Belegdatum, DATEV-Quoting, Golden-File-Vergleich (byte-identisch),
Idempotenz (2x gleicher Input -> byte-identische Datei), sowie die
Reject-Matrix (unbestätigte Modell-Extraktion, Belegdatum außerhalb des
Buchungszeitraums, nicht-numerisches Konto, nicht-CP1252-Zeichen,
Betrag <= 0, Buchungstext > 60 Zeichen, u. a.) — jeweils Exit 2, kein
Traceback, KEINE Datei.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
EXECUTOR = REPO / "plugins" / "legal-ops" / "core" / "calc" / "extf" / "executor.py"
SCHEMA = Path(__file__).resolve().parents[1] / "schema"
GOLDEN = Path(__file__).resolve().parent / "golden"

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
        {
            "umsatz": "952.50",
            "soll_haben": "S",
            "konto": "1200",
            "gegenkonto": "8400",
            "belegdatum": "2026-03-15",
            "belegfeld1": "RE-2026-042",
            "buchungstext": "Honorar Müller ./. Schmidt",
        }
    ],
}


def _lauf(eingabe, tmp_path: Path, *, output: str = "stapel.csv",
          output_report: str | None = "report.json") -> tuple[subprocess.CompletedProcess, Path, Path | None]:
    eingabe_pfad = tmp_path / "eingabe.json"
    if isinstance(eingabe, str):
        eingabe_pfad.write_text(eingabe, encoding="utf-8")
    else:
        eingabe_pfad.write_text(json.dumps(eingabe), encoding="utf-8")
    ausgabe_pfad = tmp_path / output
    args = [sys.executable, str(EXECUTOR), "--input", str(eingabe_pfad),
            "--output", str(ausgabe_pfad)]
    report_pfad = None
    if output_report:
        report_pfad = tmp_path / output_report
        args += ["--output-report", str(report_pfad)]
    ergebnis = subprocess.run(args, capture_output=True, text=True)
    return ergebnis, ausgabe_pfad, report_pfad


def _erfolg(eingabe, tmp_path: Path):
    ergebnis, ausgabe_pfad, report_pfad = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    inhalt = ausgabe_pfad.read_bytes().decode("cp1252")
    report = json.loads(report_pfad.read_text(encoding="utf-8"))
    return inhalt, report


# --------------------------------------------------------------------------
# Erfolgsfall & Header-Feldpositionen (Zeile 1)
# --------------------------------------------------------------------------

def test_grundfall_erzeugt_datei_und_report(tmp_path):
    inhalt, report = _erfolg(GRUNDFALL, tmp_path)
    zeilen = inhalt.split("\r\n")
    assert zeilen[0].startswith('"EXTF";700;21;"Buchungsstapel";')
    assert report["header"]["quelle"] == "executor"
    assert report["buchungen"][0]["quelle"] == "executor"
    assert report["buchungen_anzahl"] == 1


def test_header_feldpositionen_zeile_1(tmp_path):
    inhalt, _ = _erfolg(GRUNDFALL, tmp_path)
    felder = inhalt.split("\r\n")[0].split(";")
    assert len(felder) == 31
    assert felder[0] == '"EXTF"'
    assert felder[1] == "700"
    assert felder[2] == "21"
    assert felder[3] == '"Buchungsstapel"'
    assert felder[7] == '"RE"'                       # Herkunft
    assert felder[8] == '"Kanzlei Mustermann"'        # Exportiert von
    assert felder[10] == "12345"                      # Beraternummer
    assert felder[11] == "100"                         # Mandantennummer
    assert felder[12] == "20260101"                    # WJ-Beginn
    assert felder[13] == "4"                            # Sachkontenlaenge (Default)
    assert felder[14] == "20260101"                    # Buchungszeitraum von
    assert felder[15] == "20261231"                    # Buchungszeitraum bis
    assert felder[16] == '"Buchungsstapel Juli 2026"'  # Bezeichnung
    assert felder[21] == '"EUR"'                        # Waehrung


def test_spaltenkopf_zeile_20_spalten(tmp_path):
    inhalt, _ = _erfolg(GRUNDFALL, tmp_path)
    zeilen = inhalt.split("\r\n")
    kopf = zeilen[1].split(";")
    assert len(kopf) == 20
    assert kopf[0] == '"Umsatz (ohne Soll/Haben-Kz)"'
    assert kopf[9] == '"Belegdatum"'
    assert kopf[13] == '"Buchungstext"'


def test_buchungszeile_komma_dezimal_und_ttmm(tmp_path):
    inhalt, _ = _erfolg(GRUNDFALL, tmp_path)
    zeile = inhalt.split("\r\n")[2].split(";")
    assert len(zeile) == 20
    assert zeile[0] == "952,50"       # Komma statt Punkt, nie float
    assert zeile[1] == '"S"'
    assert zeile[6] == "1200"          # Konto unquotiert
    assert zeile[7] == "8400"
    assert zeile[9] == "1503"          # Belegdatum 2026-03-15 -> TTMM


def test_belegdatum_ttmm_exakt(tmp_path):
    inhalt, _ = _erfolg(GRUNDFALL, tmp_path)
    zeile = inhalt.split("\r\n")[2].split(";")
    assert zeile[9] == "1503"  # 15.03. -> TTMM


def test_umlaute_cp1252_kodiert(tmp_path):
    _, ausgabe_pfad, _ = _lauf(GRUNDFALL, tmp_path)
    roh = ausgabe_pfad.read_bytes()
    # "Müller" in CP1252: ü = 0xFC (ein Byte) — NICHT die UTF-8-Zweibyte-
    # Folge 0xC3 0xBC, die bei einem versehentlichen UTF-8-Export entstünde.
    assert "Müller".encode("cp1252") in roh
    assert b"Honorar M\xfcller" in roh
    assert "Müller".encode("utf-8") not in roh


# --------------------------------------------------------------------------
# Golden-File-Tests: byte-identische EXTF-Ausgabe
# --------------------------------------------------------------------------

@pytest.mark.parametrize("nr", [2, 3])
def test_golden_file_byte_identisch(nr, tmp_path):
    eingabe = json.loads((GOLDEN / f"eingabe_{nr}.json").read_text(encoding="utf-8"))
    _, ausgabe_pfad, _ = _lauf(eingabe, tmp_path, output_report=None)
    erzeugt = ausgabe_pfad.read_bytes()
    erwartet = (GOLDEN / f"erwartet_{nr}.csv").read_bytes()
    assert erzeugt == erwartet


def test_beispiel_stapel_synchron(tmp_path):
    """schema/beispiel-stapel.csv muss exakt dem aktuellen Executor-Output
    aus schema/beispiel-eingabe.json entsprechen (Golden-File im Skill).
    Schreibt bewusst in ein tmp_path-Ziel, nie in die Schema-Fixture selbst."""
    ziel = tmp_path / "stapel.csv"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(SCHEMA / "beispiel-eingabe.json"),
         "--output", str(ziel)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ziel.read_bytes() == (SCHEMA / "beispiel-stapel.csv").read_bytes()


def test_beispiel_report_synchron(tmp_path):
    ziel = tmp_path / "stapel.csv"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(SCHEMA / "beispiel-eingabe.json"),
         "--output", str(ziel)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
    gespeichert = json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8"))
    erzeugt["meta"].pop("quelle_datei")
    gespeichert["meta"].pop("quelle_datei")
    assert erzeugt == gespeichert


# --------------------------------------------------------------------------
# Idempotenz: 2x gleicher Input -> byte-identische Ausgabe
# --------------------------------------------------------------------------

def test_idempotenz_zwei_laeufe_byte_identisch(tmp_path):
    ergebnis1, pfad1, _ = _lauf(GRUNDFALL, tmp_path, output="lauf1.csv", output_report=None)
    ergebnis2, pfad2, _ = _lauf(GRUNDFALL, tmp_path, output="lauf2.csv", output_report=None)
    assert ergebnis1.returncode == 0 and ergebnis2.returncode == 0
    assert pfad1.read_bytes() == pfad2.read_bytes()


def test_idempotenz_erzeugt_am_kommt_nicht_von_wall_clock(tmp_path):
    # Zwei Läufe mit fixem 'erzeugt_am' (Vergangenheit) müssen exakt
    # dieselbe Kopfzeile liefern, unabhängig vom tatsächlichen Systemdatum.
    inhalt1, _ = _erfolg(GRUNDFALL, tmp_path)
    inhalt2, _ = _erfolg(GRUNDFALL, tmp_path)
    assert inhalt1.split("\r\n")[0] == inhalt2.split("\r\n")[0]
    assert "20260713100000000" in inhalt1.split("\r\n")[0]


# --------------------------------------------------------------------------
# Reject-Matrix -> Exit 2, keine Datei
# --------------------------------------------------------------------------

def _erwarte_reject(eingabe, tmp_path, *, enthaelt: str):
    ergebnis, ausgabe_pfad, report_pfad = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 2
    assert enthaelt in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
    assert not ausgabe_pfad.exists(), "bei Exit 2 darf keine EXTF-Datei entstehen"
    assert not report_pfad.exists(), "bei Exit 2 darf kein Report entstehen"


def test_reject_modell_extraktion_unbestaetigt(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["quelle"] = "modell-extraktion"
    _erwarte_reject(eingabe, tmp_path, enthaelt="bestaetigt")


def test_akzeptiert_modell_extraktion_bestaetigt(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["quelle"] = "modell-extraktion"
    eingabe["buchungen"][0]["bestaetigt"] = True
    ergebnis, ausgabe_pfad, _ = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ausgabe_pfad.exists()


def test_reject_unbekannter_quelle_wert(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["quelle"] = "irgendwas"
    _erwarte_reject(eingabe, tmp_path, enthaelt="unbekannter Wert")


def test_reject_belegdatum_ausserhalb_buchungszeitraum(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["belegdatum"] = "2027-01-01"
    _erwarte_reject(eingabe, tmp_path, enthaelt="Buchungszeitraum")


def test_reject_belegdatum_vor_buchungszeitraum(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["belegdatum"] = "2025-12-31"
    _erwarte_reject(eingabe, tmp_path, enthaelt="Buchungszeitraum")


@pytest.mark.parametrize("konto", ["ABCD", "12,00", "12.5", ""])
def test_reject_konto_nicht_numerisch(konto, tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["konto"] = konto
    _erwarte_reject(eingabe, tmp_path, enthaelt="konto")


def test_reject_konto_falsche_laenge(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["konto"] = "12"  # Sachkontenlaenge Default 4
    _erwarte_reject(eingabe, tmp_path, enthaelt="Stellen")


def test_reject_nicht_cp1252_zeichen(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["buchungstext"] = "Honorar 🎉"
    _erwarte_reject(eingabe, tmp_path, enthaelt="CP1252")


def test_reject_betrag_negativ(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["umsatz"] = "-10.00"
    _erwarte_reject(eingabe, tmp_path, enthaelt="größer als 0")


def test_reject_betrag_null(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["umsatz"] = "0"
    _erwarte_reject(eingabe, tmp_path, enthaelt="größer als 0")


def test_reject_betrag_float(tmp_path):
    eingabe_str = json.dumps(GRUNDFALL).replace('"952.50"', str(0.1 + 0.2))
    ergebnis, ausgabe_pfad, report_pfad = _lauf(eingabe_str, tmp_path)
    assert ergebnis.returncode == 2
    assert "float" in ergebnis.stderr
    assert not ausgabe_pfad.exists()


def test_reject_buchungstext_zu_lang(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["buchungstext"] = "X" * 61
    _erwarte_reject(eingabe, tmp_path, enthaelt="zu lang")


def test_reject_soll_haben_ungueltig(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["soll_haben"] = "X"
    _erwarte_reject(eingabe, tmp_path, enthaelt="soll_haben")


def test_reject_kurs_null(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["kurs"] = "0"
    _erwarte_reject(eingabe, tmp_path, enthaelt="kurs")


def test_reject_basisumsatz_ohne_wkz(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["basisumsatz"] = "100.00"
    _erwarte_reject(eingabe, tmp_path, enthaelt="basisumsatz")


def test_reject_belegfeld1_unzulaessiges_zeichen(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["belegfeld1"] = "RE 2026#42"
    _erwarte_reject(eingabe, tmp_path, enthaelt="unzulässige Zeichen")


def test_reject_belegfeld1_numerisch(tmp_path):
    # Regressionstest D12-Review-Blocker: Rechnungsnummern kommen im JSON
    # oft als bare Zahl ("belegfeld1": 42) — vor dem Fix lief len() vor dem
    # Typ-Check -> ungefangener TypeError, Traceback, Exit 1. Jetzt: Exit 2,
    # klare Meldung mit Korrekturhinweis, keine Datei.
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["belegfeld1"] = 42
    _erwarte_reject(eingabe, tmp_path, enthaelt="muss ein Text (String) sein")


def test_reject_belegfeld2_numerisch(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["belegfeld2"] = 42
    _erwarte_reject(eingabe, tmp_path, enthaelt="muss ein Text (String) sein")


def test_reject_leere_buchungsliste(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"] = []
    _erwarte_reject(eingabe, tmp_path, enthaelt="nicht-leere Liste")


def test_reject_fehlendes_pflichtfeld_header(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    del eingabe["header"]["bezeichnung"]
    _erwarte_reject(eingabe, tmp_path, enthaelt="bezeichnung")


def test_reject_unbekanntes_feld_header(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["header"]["unsinn"] = "x"
    _erwarte_reject(eingabe, tmp_path, enthaelt="unbekanntes Feld")


def test_reject_unbekanntes_feld_buchung(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["buchungen"][0]["unsinn"] = "x"
    _erwarte_reject(eingabe, tmp_path, enthaelt="unbekanntes Feld")


def test_reject_buchungszeitraum_von_nach_bis(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["header"]["buchungszeitraum_von"] = "2026-12-31"
    eingabe["header"]["buchungszeitraum_bis"] = "2026-01-01"
    _erwarte_reject(eingabe, tmp_path, enthaelt="liegt nach")


def test_reject_kaputtes_json(tmp_path):
    ergebnis, ausgabe_pfad, report_pfad = _lauf("{kein json", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert not ausgabe_pfad.exists()


def test_reject_eingabedatei_fehlt(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(tmp_path / "nix.json"),
         "--output", str(tmp_path / "out.csv")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_reject_sachkontenlaenge_ausserhalb_bereich(tmp_path):
    eingabe = copy.deepcopy(GRUNDFALL)
    eingabe["header"]["sachkontenlaenge"] = 3
    _erwarte_reject(eingabe, tmp_path, enthaelt="sachkontenlaenge")


# --------------------------------------------------------------------------
# Typ-Fuzz (D12-Review-Nachtrag): KEIN Feld darf bei falschem JSON-Typ einen
# Traceback statt Exit 2 produzieren. Kontrakt je Fall: Exit ist 0 oder 2,
# stderr ist traceback-frei, bei Exit 2 entsteht keine Datei. (Der konkrete
# Blocker — numerisches belegfeld1 — hat oben zusätzlich seinen eigenen
# Meldungs-Test.)
# --------------------------------------------------------------------------

_BOESE_WERTE = [42, 4.2, True, False, None, [1, 2], {"a": 1}]

_HEADER_FUZZ_FELDER = sorted(GRUNDFALL["header"]) + [
    "sachkontenlaenge", "diktatkuerzel", "buchungstyp", "waehrung",
    "formatversion", "herkunft"]
_BUCHUNG_FUZZ_FELDER = sorted(GRUNDFALL["buchungen"][0]) + [
    "wkz_umsatz", "kurs", "basisumsatz", "wkz_basisumsatz", "bu_schluessel",
    "belegfeld2", "skonto", "quelle", "bestaetigt"]


def _pruefe_typfuzz_kontrakt(eingabe, tmp_path, fall_nr, kontext, *,
                             erwarte_exit=(0, 2)):
    # Eigenes Unterverzeichnis je Fuzz-Fall: ein früherer Exit-0-Fall darf
    # keine stapel.csv hinterlassen, die die "keine Datei bei Exit 2"-
    # Prüfung des nächsten Falls verfälscht.
    fall_dir = tmp_path / f"fall-{fall_nr}"
    fall_dir.mkdir()
    ergebnis, ausgabe_pfad, report_pfad = _lauf(eingabe, fall_dir)
    assert ergebnis.returncode in erwarte_exit, (kontext, ergebnis.stderr)
    assert "Traceback" not in ergebnis.stderr, (kontext, ergebnis.stderr)
    if ergebnis.returncode == 2:
        assert not ausgabe_pfad.exists(), kontext
        assert not report_pfad.exists(), kontext


@pytest.mark.parametrize("feld", _HEADER_FUZZ_FELDER)
def test_typfuzz_header_feld_nie_traceback(feld, tmp_path):
    for nr, wert in enumerate(_BOESE_WERTE):
        eingabe = copy.deepcopy(GRUNDFALL)
        eingabe["header"][feld] = wert
        _pruefe_typfuzz_kontrakt(eingabe, tmp_path, nr, f"header.{feld}={wert!r}")


@pytest.mark.parametrize("feld", _BUCHUNG_FUZZ_FELDER)
def test_typfuzz_buchung_feld_nie_traceback(feld, tmp_path):
    for nr, wert in enumerate(_BOESE_WERTE):
        eingabe = copy.deepcopy(GRUNDFALL)
        eingabe["buchungen"][0][feld] = wert
        _pruefe_typfuzz_kontrakt(eingabe, tmp_path, nr, f"buchung.{feld}={wert!r}")


def test_typfuzz_strukturebene_nie_traceback(tmp_path):
    nr = 0
    for wert in _BOESE_WERTE + ["x"]:
        for mutation in ("header", "buchungen", "buchungen[0]", "top-level"):
            if mutation == "header":
                eingabe = copy.deepcopy(GRUNDFALL)
                eingabe["header"] = wert
            elif mutation == "buchungen":
                eingabe = copy.deepcopy(GRUNDFALL)
                eingabe["buchungen"] = wert
            elif mutation == "buchungen[0]":
                eingabe = copy.deepcopy(GRUNDFALL)
                eingabe["buchungen"] = [wert]
            else:
                eingabe = wert  # gesamte Eingabe ist kein Objekt
            _pruefe_typfuzz_kontrakt(eingabe, tmp_path, nr,
                                     f"{mutation}={wert!r}", erwarte_exit=(2,))
            nr += 1
