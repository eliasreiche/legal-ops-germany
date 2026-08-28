"""Tests für den Skill-Executor (CLI, P2).

Deckt ab: CLI über subprocess (Mandat rein → Report raus), Beispieldateien-
Round-Trip, adversariale Inputs (kaputtes JSON, unbekanntes Feld, unzulässiger
Wert) mit sauberem Exit 2 ohne Traceback.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import lauf, report, schreibe  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"
SCHEMA = SKILL / "schema"


def _lauf(eingabe, tmp_path: Path) -> subprocess.CompletedProcess:
    return lauf(EXECUTOR, "--mandat", schreibe(tmp_path / "mandat.json", eingabe))


def _report(eingabe, tmp_path: Path) -> dict:
    return report(EXECUTOR, "--mandat", schreibe(tmp_path / "mandat.json", eingabe))


# --------------------------------------------------------------------------
# Erfolgsfälle
# --------------------------------------------------------------------------

def test_cli_liefert_report(tmp_path):
    report = _report({"kataloggeschaeft": "keins"}, tmp_path)
    assert report["klassifikationsvorschlag"] == "nicht_verpflichtet"
    assert report["meta"]["erzeugt_von"].endswith("executor.py")


def test_cli_alle_werte_aus_executor(tmp_path):
    report = _report(json.loads(
        (SCHEMA / "beispiel-mandat.json").read_text("utf-8")), tmp_path)
    for f in report["angewandte_faktoren"]:
        assert f["quelle"] == "executor"
    for p in report["pflichten_hinweise"]:
        assert p["quelle"] == "executor"


def test_cli_output_datei(tmp_path):
    mandat = schreibe(tmp_path / "mandat.json", {"kataloggeschaeft": "keins"})
    ziel = tmp_path / "report.json"
    ergebnis = lauf(EXECUTOR, "--mandat", mandat, "--output", ziel)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["klassifikationsvorschlag"] in (
        "nicht_verpflichtet", "unvollstaendig", "niedrig", "mittel", "hoch")


# --------------------------------------------------------------------------
# Beispieldateien bleiben synchron
# --------------------------------------------------------------------------

def test_beispiel_report_synchron():
    # Festes Bezugsdatum (Muster gwg-live-screening): sonst wandert das
    # Frische-Gate der Länderliste täglich durch den Beispiel-Report.
    erzeugt = report(EXECUTOR, "--mandat", SCHEMA / "beispiel-mandat.json",
                     "--heute", "2026-07-16")
    gespeichert = json.loads((SCHEMA / "beispiel-report.json").read_text("utf-8"))
    erzeugt["meta"].pop("quelle_datei")
    gespeichert["meta"].pop("quelle_datei")
    assert erzeugt == gespeichert


def test_beispiel_mandat_round_trip(tmp_path):
    # Report aus dem Beispiel-Mandat erzeugen und Kernfelder gegenprüfen.
    report = _report(json.loads(
        (SCHEMA / "beispiel-mandat.json").read_text("utf-8")), tmp_path)
    assert report["klassifikationsvorschlag"] == "mittel"
    assert report["anwendbarkeit"]["status"] == "verpflichtet"


# --------------------------------------------------------------------------
# Eingabefehler → Exit 2, klare Meldung, kein Traceback
# --------------------------------------------------------------------------

def test_frische_warnung_auf_stderr_report_bleibt(tmp_path):
    # Veraltete Länderliste: Report wird trotzdem erzeugt (Exit 0), die
    # Warnung steht im Report UND auf stderr.
    mandat = schreibe(tmp_path / "mandat.json", {"kataloggeschaeft": "keins"})
    ergebnis = lauf(EXECUTOR, "--mandat", mandat, "--heute", "2027-08-01")
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "überfällig" in ergebnis.stderr
    assert json.loads(ergebnis.stdout)["warnungen"]


def test_fehler_ungueltiges_heute(tmp_path):
    mandat = schreibe(tmp_path / "mandat.json", {"kataloggeschaeft": "keins"})
    ergebnis = lauf(EXECUTOR, "--mandat", mandat, "--heute", "16.07.2026")
    assert ergebnis.returncode == 2
    assert "JJJJ-MM-TT" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_kaputtes_json(tmp_path):
    ergebnis = _lauf("{kein json", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_datei_fehlt(tmp_path):
    ergebnis = lauf(EXECUTOR, "--mandat", tmp_path / "nix.json")
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_fehler_unbekanntes_feld(tmp_path):
    ergebnis = _lauf({"kataloggeschaeft": "keins", "tippfehler": "x"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_unzulaessiger_wert(tmp_path):
    ergebnis = _lauf({"kataloggeschaeft": "keins", "pep": "vielleicht"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_fehler_kein_objekt(tmp_path):
    ergebnis = _lauf("[1, 2, 3]", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON-Objekt" in ergebnis.stderr


def test_quellen_registry_deckt_die_zitierten_gwg_normen():
    """Die Registry ist die Belegliste für die händische Normprüfung — sie muss
    parsebar sein und die vom Executor zitierten §§ GwG führen."""
    registry = json.loads((SCHEMA / "quellen-registry.json").read_text(encoding="utf-8"))
    gefuehrt = {(n["kuerzel"], n["paragraph"]) for n in registry["normen"]}
    assert {("GwG", p) for p in ("2", "10", "14", "15", "43")} <= gefuehrt
