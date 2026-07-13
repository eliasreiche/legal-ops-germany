"""Tests für den Skill-Executor (CLI, P2) und die zitat-verifier-Integration.

Deckt ab: CLI über subprocess (Mandat rein → Report raus), Beispieldateien-
Round-Trip, adversariale Inputs (kaputtes JSON, unbekanntes Feld, unzulässiger
Wert) mit sauberem Exit 2 ohne Traceback, sowie den abschließenden
zitat-verifier-de-Lauf über die mitgelieferte quellen-registry.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"
SCHEMA = SKILL / "schema"
VERIFIER = REPO / "plugins" / "legal-ops" / "skills" / "zitat-verifier-de" / "executor.py"


def _lauf(eingabe, tmp_path: Path) -> subprocess.CompletedProcess:
    pfad = tmp_path / "mandat.json"
    if isinstance(eingabe, str):
        pfad.write_text(eingabe, encoding="utf-8")
    else:
        pfad.write_text(json.dumps(eingabe), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(EXECUTOR), "--mandat", str(pfad)],
        capture_output=True, text=True)


def _report(eingabe, tmp_path: Path) -> dict:
    ergebnis = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return json.loads(ergebnis.stdout)


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
    mandat = tmp_path / "mandat.json"
    mandat.write_text(json.dumps({"kataloggeschaeft": "keins"}), encoding="utf-8")
    ziel = tmp_path / "report.json"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--mandat", str(mandat),
         "--output", str(ziel)], capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["klassifikationsvorschlag"] in (
        "nicht_verpflichtet", "unvollstaendig", "niedrig", "mittel", "hoch")


# --------------------------------------------------------------------------
# Beispieldateien bleiben synchron
# --------------------------------------------------------------------------

def test_beispiel_report_synchron():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--mandat", str(SCHEMA / "beispiel-mandat.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
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

def test_fehler_kaputtes_json(tmp_path):
    ergebnis = _lauf("{kein json", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_datei_fehlt(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--mandat", str(tmp_path / "nix.json")],
        capture_output=True, text=True)
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


# --------------------------------------------------------------------------
# zitat-verifier-Integration (letzter Skill-Schritt)
# --------------------------------------------------------------------------

def test_zitat_verifier_verifiziert_gwg_normen(tmp_path):
    # Die gerenderte Doku zitiert die GwG-§§; mit der mitgelieferten Registry
    # müssen sie ✅ verifiziert (kein ❌ abweichend) sein.
    doku = tmp_path / "doku.md"
    doku.write_text(
        "GwG-Risiko-Dokumentation\n\n"
        "Anwendbarkeit nach § 2 GwG. Allgemeine Sorgfaltspflichten § 10 GwG, "
        "vereinfachte § 14 GwG, verstärkte § 15 GwG. Verdachtsmeldung § 43 GwG.\n",
        encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(VERIFIER), "--input", str(doku),
         "--registry", str(SCHEMA / "quellen-registry.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["zusammenfassung"]["abweichend"] == 0
    gwg_zitate = [z for z in report["zitate"]
                  if z["typ"] == "norm" and "GwG" in z["roh"]]
    assert gwg_zitate
    for z in gwg_zitate:
        assert z["zustand"] == "verifiziert", z


def test_quellen_registry_gueltiges_format():
    # Registry lädt fehlerfrei durch den Verifier (strukturell gültig).
    sys.path.insert(0, str(VERIFIER.parent))
    import executor as verifier_exec  # noqa: E402
    daten = verifier_exec.lade_registry(SCHEMA / "quellen-registry.json")
    assert {n["paragraph"] for n in daten["normen"]} >= {
        "2", "10", "14", "15", "43"}
