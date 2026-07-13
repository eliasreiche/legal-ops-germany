"""Tests für core/calc/fristen/kalender_executor.py — Report rein, Kalender raus (P2/P3).

Deckt ab: iCal- und CSV-Erzeugung aus dem Fristen-Report, die Determinismus-
und Idempotenz-Zusage („Re-Export nur bei Korrektur" = stabile UID, byte-
stabiler Export), die Kennzeichnungen (Notfrist, kein technisches Fristende,
teilgebietlicher Feiertag), die Vorfrist-Ableitung sowie saubere Eingabefehler
(Exit 2, kein Traceback). Der Report wird jeweils frisch aus dem
Fristberechnungs-Executor erzeugt (End-to-End: calc → export).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
CALC = REPO / "plugins" / "legal-ops" / "core" / "calc" / "fristen" / "executor.py"
EXPORT = REPO / "plugins" / "legal-ops" / "core" / "calc" / "fristen" / "kalender_executor.py"
SCHEMA = Path(__file__).resolve().parents[1] / "schema"


def _report(eingabe: dict, tmp_path: Path, name: str = "report") -> Path:
    """Erzeugt einen echten Executor-Report als Datei (P3-Quelle)."""
    anfrage = tmp_path / f"anfrage-{name}.json"
    anfrage.write_text(json.dumps(eingabe), encoding="utf-8")
    ziel = tmp_path / f"{name}.json"
    res = subprocess.run(
        [sys.executable, str(CALC), "--input", str(anfrage), "--output", str(ziel)],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return ziel


def _export(report: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXPORT), "--report", str(report), *extra],
        capture_output=True, text=True)


def _stdout_ics(report: Path, *extra: str) -> str:
    res = _export(report, *extra)
    assert res.returncode == 0, res.stderr
    return res.stdout


def _unfold(ics: str) -> str:
    """RFC-5545-Content-Line-Unfolding: entfernt die Faltung (Zeilenumbruch +
    ein Leerzeichen). Im subprocess-Textmodus ist das CRLF bereits zu \\n
    normalisiert, die Faltung also '\\n '."""
    return ics.replace("\n ", "")


# --------------------------------------------------------------------------
# iCal-Grundstruktur & Korrektheit
# --------------------------------------------------------------------------

def test_ics_grundstruktur_ganztags_event(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    # In Datei schreiben, um echte CRLF-Enden zu prüfen (subprocess-Textmodus
    # würde \r\n normalisieren).
    ziel = tmp_path / "frist.ics"
    res = _export(report, "--format", "ics", "--output", str(ziel))
    assert res.returncode == 0, res.stderr
    roh = ziel.read_bytes()
    assert roh.startswith(b"BEGIN:VCALENDAR\r\n")
    assert roh.rstrip().endswith(b"END:VCALENDAR")
    # RFC 5545: ausschließlich CRLF-Zeilenenden.
    assert roh.count(b"\n") == roh.count(b"\r\n")
    text = roh.decode("utf-8")
    assert "DTSTART;VALUE=DATE:20260216" in text          # Fristende
    assert "DTEND;VALUE=DATE:20260217" in text            # exklusiv +1 Tag
    assert "BEGIN:VALARM" in text and "TRIGGER:-P3D" in text  # Default-Vorfrist


def test_ics_notfrist_und_verschiebung_markiert(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    text = _unfold(_stdout_ics(report, "--format", "ics"))
    assert "Frist: Berufungsfrist [NOTFRIST]" in text
    assert "193 BGB verschoben" in text
    assert "Zweitkontrolle bleibt zwingend" in text       # P5-Disclaimer


def test_ics_aktenzeichen_und_vorlauftage(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    text = _unfold(_stdout_ics(report, "--format", "ics",
                               "--aktenzeichen", "12/2026", "--vorlauftage", "7"))
    assert "Az. 12/2026" in text
    assert "TRIGGER:-P7D" in text
    assert "Vorfrist (7 Tage vorher): 09.02.2026" in text  # 16.02. - 7 Tage


# --------------------------------------------------------------------------
# Determinismus / Idempotenz — „Re-Export nur bei Korrektur"
# --------------------------------------------------------------------------

def test_unveraenderter_report_byte_identisch(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    a = _export(report, "--format", "ics")
    b = _export(report, "--format", "ics")
    assert a.returncode == 0 and b.returncode == 0
    assert a.stdout == b.stdout        # kein Wall-Clock im Export


def _uid(ics: str) -> str:
    return next(z for z in ics.split("\n") if z.startswith("UID:"))


def test_korrektur_erzeugt_neue_uid(tmp_path):
    r1 = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                  "bundesland": "NW"}, tmp_path, name="vor")
    # Korrektur des fristauslösenden Ereignisses → anderes Fristende → neue UID.
    r2 = _report({"ereignis_datum": "2026-01-20", "fristart": "berufung",
                  "bundesland": "NW"}, tmp_path, name="nach")
    assert _uid(_stdout_ics(r1)) != _uid(_stdout_ics(r2))


def test_gleiche_frist_unterschiedliche_akten_verschiedene_uid(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    u1 = _uid(_stdout_ics(report, "--aktenzeichen", "12/2026"))
    u2 = _uid(_stdout_ics(report, "--aktenzeichen", "99/2026"))
    assert u1 != u2


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

def test_csv_kopf_und_werte(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    res = _export(report, "--format", "csv", "--aktenzeichen", "12/2026")
    assert res.returncode == 0, res.stderr
    zeilen = res.stdout.strip().split("\n")
    kopf = zeilen[0].strip().split(";")
    werte = dict(zip(kopf, zeilen[1].strip().split(";")))
    assert werte["fristende"] == "2026-02-16"
    assert werte["vorfrist"] == "2026-02-13"
    assert werte["notfrist"] == "ja"
    assert werte["verschoben"] == "ja"
    assert werte["aktenzeichen"] == "12/2026"
    assert werte["quelle"] == "executor"


def test_csv_semikolon_im_feld_wird_gequotet(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    res = _export(report, "--format", "csv", "--bezeichnung", "Mandat A; B")
    assert res.returncode == 0, res.stderr
    assert '"Frist: Mandat A; B [NOTFRIST]"' in res.stdout


# --------------------------------------------------------------------------
# Ehrlichkeits-Kennzeichnungen
# --------------------------------------------------------------------------

def test_kein_technisches_fristende_als_kontrolltermin(tmp_path):
    report = _report({"ereignis_datum": "2026-03-02",
                      "fristart": "widerspruch_mahnbescheid",
                      "bundesland": "HE"}, tmp_path)
    text = _unfold(_stdout_ics(report, "--format", "ics"))
    assert "Kontrolltermin (kein technisches Fristende)" in text
    summary = text.split("SUMMARY:")[1].split("\n")[0]
    assert not summary.startswith("Frist: ")
    assert "§ 694 ZPO" in text


def test_teilgebietlicher_feiertag_alternativende_notiert(tmp_path):
    report = _report({"ereignis_datum": "2025-08-01", "dauer": 2,
                      "einheit": "wochen", "bundesland": "BY"}, tmp_path)
    text = _unfold(_stdout_ics(report, "--format", "ics"))
    assert "DTSTART;VALUE=DATE:20250815" in text          # früheres, sicheres Ende
    assert "Teilgebietlicher Feiertag" in text
    assert "18.08.2025" in text                           # alternatives Ende
    res = _export(report, "--format", "csv")
    assert "2025-08-18" in res.stdout                     # Spalte alternativ_ende


# --------------------------------------------------------------------------
# Eingabefehler → Exit 2, kein Traceback
# --------------------------------------------------------------------------

def test_fehler_report_fehlt(tmp_path):
    res = _export(tmp_path / "nix.json")
    assert res.returncode == 2
    assert "nicht gefunden" in res.stderr
    assert "Traceback" not in res.stderr


def test_fehler_kein_executor_report(tmp_path):
    # Modellgenerierter „Report" ohne Executor-Marke wird abgelehnt (P3).
    fake = tmp_path / "fake.json"
    fake.write_text(json.dumps({"ergebnis": {"fristende": "2026-02-16"}}),
                    encoding="utf-8")
    res = _export(fake)
    assert res.returncode == 2
    assert "quelle" in res.stderr
    assert "Traceback" not in res.stderr


def test_fehler_kaputtes_json(tmp_path):
    fake = tmp_path / "kaputt.json"
    fake.write_text("{kein json", encoding="utf-8")
    res = _export(fake)
    assert res.returncode == 2
    assert "JSON" in res.stderr


def test_fehler_negative_vorlauftage(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    res = _export(report, "--vorlauftage", "-1")
    assert res.returncode == 2
    assert "negativ" in res.stderr
    assert "Traceback" not in res.stderr


def test_fehler_format_beide_ohne_output_dir(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    res = _export(report, "--format", "beide")
    assert res.returncode == 2
    assert "output-dir" in res.stderr


def test_beispiel_exporte_synchron(tmp_path):
    # Die abgelegten Beispiel-Exporte müssen aus dem Beispiel-Report
    # reproduzierbar sein (Determinismus-Nachweis + Doku bleibt aktuell).
    for fmt, datei in (("ics", "beispiel-export.ics"), ("csv", "beispiel-export.csv")):
        ziel = tmp_path / datei
        res = _export(SCHEMA / "beispiel-report.json", "--format", fmt,
                      "--aktenzeichen", "12/2026", "--output", str(ziel))
        assert res.returncode == 0, res.stderr
        assert ziel.read_bytes() == (SCHEMA / datei).read_bytes(), (
            f"{datei} nicht synchron — neu erzeugen")


def test_format_beide_schreibt_zwei_dateien(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15", "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    ziel = tmp_path / "out"
    res = _export(report, "--format", "beide", "--output-dir", str(ziel),
                  "--aktenzeichen", "12/2026")
    assert res.returncode == 0, res.stderr
    dateien = sorted(p.suffix for p in ziel.iterdir())
    assert dateien == [".csv", ".ics"]
