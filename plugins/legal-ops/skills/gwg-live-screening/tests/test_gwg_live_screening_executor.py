"""Tests für executor.py — CLI (subprocess): Dateien rein, JSON-Report raus (P2).

Deckt: erfolgreiche Screenings (Treffer/möglicher Treffer/kein Treffer =
negative clearance), Match gegen Primärname UND Alias, Frische-Warnung im
Report, Determinismus, Schwellen-Override, Round-Trip gegen
schema/beispiel-report.json, Frische-Gate (Exit 3) und Eingabefehler (Exit 2),
jeweils ohne Traceback. Kein Netzwerkzugriff.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
SCHEMA = SKILL_DIR / "schema"
FIXTURES = SKILL_DIR / "tests" / "fixtures"


def _lauf(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXECUTOR), *args], capture_output=True, text=True)


def _listen_dir(tmp_path: Path, abgerufen_am: str = "2026-07-15") -> Path:
    ziel = tmp_path / "listen"
    ziel.mkdir()
    for name in ("eu-fsf-mini.xml", "un-consolidated-mini.xml"):
        shutil.copy(FIXTURES / name, ziel / name)
    meta = {name: {"url": "https://example.invalid", "abgerufen_am": abgerufen_am}
            for name in ("eu-fsf-mini.xml", "un-consolidated-mini.xml")}
    (ziel / "abruf-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return ziel


def _parteien(tmp_path: Path, *namen: str) -> Path:
    pfad = tmp_path / "parteien.json"
    pfad.write_text(json.dumps([{"name": n} for n in namen]), encoding="utf-8")
    return pfad


# --------------------------------------------------------------------------
# Erfolgsfälle
# --------------------------------------------------------------------------

def test_exakter_treffer_s1(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 0, e.stderr
    report = json.loads(e.stdout)
    partei = report["parteien"][0]
    assert partei["ergebnis"] == "treffer"
    s1 = [t for t in partei["treffer"] if t["regel"] == "S1"]
    assert s1 and s1[0]["namensfeld"] == "primaername"
    assert s1[0]["listen_referenz"] == "EU.9001.99"


def test_alias_treffer(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Musterbau AG")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 0, e.stderr
    treffer = json.loads(e.stdout)["parteien"][0]["treffer"]
    assert any(t["namensfeld"] == "alias" and t["stufe"] == "treffer" for t in treffer)


def test_kein_treffer_ist_negative_clearance(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Johanna Sauber")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 0, e.stderr
    report = json.loads(e.stdout)
    partei = report["parteien"][0]
    assert partei["ergebnis"] == "kein_treffer"
    assert partei["treffer"] == []
    assert report["zusammenfassung"]["parteien_ohne_treffer"] == 1


def test_phonetischer_moeglicher_treffer_s3(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Maximilian Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    report = json.loads(e.stdout)
    partei = report["parteien"][0]
    assert partei["ergebnis"] == "moeglicher_treffer"
    assert any(t["regel"] == "S3" for t in partei["treffer"])


def test_frische_im_report_ausgewiesen(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    frische = json.loads(e.stdout)["listen_frische"]
    assert len(frische) == 2
    for f in frische:
        assert f["generierungsdatum"]
        assert f["abgerufen_am"] == "2026-07-15"
        assert f["warnung_veraltet"] is False


def test_warnung_bei_alter_liste(tmp_path):
    listen = _listen_dir(tmp_path, abgerufen_am="2026-06-01")
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 0, e.stderr
    report = json.loads(e.stdout)
    assert report["warnungen"]
    assert all(f["warnung_veraltet"] for f in report["listen_frische"])
    assert "Warnung" in e.stderr


def test_output_datei(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann")
    ziel = tmp_path / "report.json"
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16", "--output", str(ziel))
    assert e.returncode == 0, e.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["zusammenfassung"]["anzahl_parteien"] == 1


def test_schwelle_override_unterdrueckt_fuzzy(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann")
    streng = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
                   "--heute", "2026-07-16", "--schwelle-moeglich", "0.99")
    report = json.loads(streng.stdout)
    partei = report["parteien"][0]
    # S1-Treffer bleibt, der S4-Fuzzy-Kandidat (0.83) fällt bei 0.99 weg.
    assert partei["ergebnis"] == "treffer"
    assert all(t["regel"] != "S4" for t in partei["treffer"])


def test_determinismus(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann", "Musterbau AG", "Johanna Sauber")
    args = ("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
            "--heute", "2026-07-16")
    r1 = json.loads(_lauf(*args).stdout)
    r2 = json.loads(_lauf(*args).stdout)
    assert json.dumps(r1["parteien"], sort_keys=True) == \
        json.dumps(r2["parteien"], sort_keys=True)


def test_csv_parteien(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name;typ\nMax Mustermann;natuerlich\n", encoding="utf-8")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 0, e.stderr
    assert json.loads(e.stdout)["parteien"][0]["ergebnis"] == "treffer"


# --------------------------------------------------------------------------
# Beispiel-Round-Trip
# --------------------------------------------------------------------------

def test_beispiel_report_synchron():
    e = _lauf("--parteien", str(SCHEMA / "beispiel-parteien.json"),
              "--listen-verzeichnis", str(FIXTURES), "--heute", "2026-07-16")
    assert e.returncode == 0, e.stderr
    erzeugt = json.loads(e.stdout)
    gespeichert = json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8"))
    for r in (erzeugt, gespeichert):
        r["meta"].pop("parteien_datei")
        r["meta"].pop("listen_verzeichnis")
    assert erzeugt == gespeichert


# --------------------------------------------------------------------------
# Frische-Gate -> Exit 3
# --------------------------------------------------------------------------

def test_exit3_ohne_meta(tmp_path):
    listen = _listen_dir(tmp_path)
    (listen / "abruf-meta.json").unlink()
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 3
    assert "Frische-Gate" in e.stderr
    assert "Traceback" not in e.stderr
    assert e.stdout.strip() == ""  # kein Report


# --------------------------------------------------------------------------
# Eingabefehler -> Exit 2, klare Meldung, kein Traceback
# --------------------------------------------------------------------------

def test_exit2_parteien_fehlt(tmp_path):
    listen = _listen_dir(tmp_path)
    e = _lauf("--parteien", str(tmp_path / "nix.json"),
              "--listen-verzeichnis", str(listen))
    assert e.returncode == 2
    assert "nicht gefunden" in e.stderr


def test_exit2_verzeichnis_fehlt(tmp_path):
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien),
              "--listen-verzeichnis", str(tmp_path / "gibtsnicht"))
    assert e.returncode == 2
    assert "Traceback" not in e.stderr


def test_exit2_schwelle_ausserhalb(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--schwelle-moeglich", "1.5")
    assert e.returncode == 2
    assert "0.0 und 1.0" in e.stderr


def test_exit2_kaputtes_xml(tmp_path):
    listen = _listen_dir(tmp_path)
    (listen / "eu-fsf-mini.xml").write_text("<nichtgeschlossen>", encoding="utf-8")
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "2026-07-16")
    assert e.returncode == 2
    assert "Traceback" not in e.stderr


def test_exit2_ungueltiges_heute(tmp_path):
    listen = _listen_dir(tmp_path)
    parteien = _parteien(tmp_path, "Max Mustermann")
    e = _lauf("--parteien", str(parteien), "--listen-verzeichnis", str(listen),
              "--heute", "kaputt")
    assert e.returncode == 2
