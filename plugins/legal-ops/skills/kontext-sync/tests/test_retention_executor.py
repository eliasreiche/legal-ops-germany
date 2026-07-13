"""Tests für core/calc/retention/executor.py — Retention-Hinweis, KEIN Delete (P3/P4).

Deckt ab: die Fristberechnung (Fristbeginn Schluss des Kalenderjahres der
Mandatsbeendigung + 6 Jahre, § 50 Abs. 1 BRAO), Einordnung
überfällig/noch-nicht-löschbar/nicht-anwendbar, dass der Executor
nachweislich keine Datei löscht, sowie die CLI (Exit-Codes, JSON+Markdown-
Output) gegen `beispiel-kontext/`.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EXECUTOR = REPO / "plugins" / "legal-ops" / "core" / "calc" / "retention" / "executor.py"
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"

# Bewusst NICHT `sys.path.insert(...); import executor` — der Modulname
# "executor" ist im Repo mehrfach vergeben (jeder Skill hat sein eigenes
# executor.py); ein bare `import executor` würde global in sys.modules
# landen und je nach Testreihenfolge das FALSCHE Modul für andere Tests
# liefern (beobachteter Kollisions-Bug beim ersten Durchlauf: zitat-pruefer-
# Tests liefen versehentlich gegen dieses retention/executor.py). Stattdessen
# per importlib unter einem eindeutigen Namen laden.
_spec = importlib.util.spec_from_file_location(
    "kontext_sync_test_retention_executor", EXECUTOR)
retention = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(retention)


# --------------------------------------------------------------------------
# Reine Berechnung (P3)
# --------------------------------------------------------------------------

def test_berechne_retention_fristbeginn_schluss_des_kalenderjahres():
    retention_bis, loeschbar_ab = retention.berechne_retention(date(2026, 3, 31))
    assert retention_bis == date(2032, 12, 31)
    assert loeschbar_ab == date(2033, 1, 1)


def test_berechne_retention_mandatsende_am_jahresanfang_gleiches_ergebnis():
    # Egal ob das Mandat am 01.01. oder 31.12. endet: Fristbeginn ist der
    # Schluss DES JAHRES, also unabhängig vom Monat innerhalb des Jahres.
    a = retention.berechne_retention(date(2026, 1, 1))
    b = retention.berechne_retention(date(2026, 12, 31))
    assert a == b == (date(2032, 12, 31), date(2033, 1, 1))


# --------------------------------------------------------------------------
# Report-Erzeugung
# --------------------------------------------------------------------------

def test_beispiel_kontext_ein_ueberfaellig_ein_nicht_anwendbar():
    report = retention.baue_report(BEISPIEL_KONTEXT, stichtag=date(2033, 6, 1))
    z = report["zusammenfassung"]
    assert z["anzahl_mandate"] == 2
    assert z["loeschbar_ueberfaellig"] == 1
    assert z["nicht_anwendbar"] == 1
    assert z["noch_nicht_loeschbar"] == 0
    assert report["meta"]["loescht_nie"] is True
    assert report["meta"]["quelle"] == "executor"
    assert "§ 50 Abs. 1 BRAO" in report["meta"]["norm_hinweis"]


def test_beispiel_kontext_noch_nicht_loeschbar_bei_frueherem_stichtag():
    report = retention.baue_report(BEISPIEL_KONTEXT, stichtag=date(2026, 7, 13))
    z = report["zusammenfassung"]
    assert z["loeschbar_ueberfaellig"] == 0
    assert z["noch_nicht_loeschbar"] == 1
    assert z["nicht_anwendbar"] == 1


def test_aktives_mandat_ohne_mandatsende_ist_nicht_anwendbar():
    report = retention.baue_report(BEISPIEL_KONTEXT, stichtag=date(2026, 7, 13))
    eintrag = next(e for e in report["mandate"] if e["az"] == "2026-001")
    assert eintrag["einordnung"] == "nicht_anwendbar"


def test_beendetes_mandat_liefert_retention_bis_und_loeschbar_ab():
    report = retention.baue_report(BEISPIEL_KONTEXT, stichtag=date(2026, 7, 13))
    eintrag = next(e for e in report["mandate"] if e["az"] == "2026-002")
    assert eintrag["retention_bis"] == "2032-12-31"
    assert eintrag["loeschbar_ab"] == "2033-01-01"
    assert eintrag["quelle"] == "executor"


def test_markdown_report_enthaelt_loescht_nichts_hinweis():
    report = retention.baue_report(BEISPIEL_KONTEXT, stichtag=date(2026, 7, 13))
    md = retention.baue_markdown(report)
    assert "löscht nichts" in md
    assert "2026-002" in md


# --------------------------------------------------------------------------
# Nachweis: keine Datei wird gelöscht/verändert
# --------------------------------------------------------------------------

def test_executor_veraendert_keine_dateien_im_kontext(tmp_path):
    import shutil
    kopie = tmp_path / "kontext-kopie"
    shutil.copytree(BEISPIEL_KONTEXT, kopie)
    vorher = {p: p.read_bytes() for p in sorted(kopie.rglob("*")) if p.is_file()}

    retention.baue_report(kopie, stichtag=date(2033, 1, 1))

    nachher = {p: p.read_bytes() for p in sorted(kopie.rglob("*")) if p.is_file()}
    assert vorher.keys() == nachher.keys()  # keine gelöschte/neue Datei
    assert vorher == nachher                # kein Inhalt verändert


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _lauf(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(EXECUTOR), *args],
                          capture_output=True, text=True)


def test_cli_gegen_beispiel_kontext_exit_0():
    res = _lauf("--kontext", str(BEISPIEL_KONTEXT), "--stichtag", "2026-07-13")
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    assert report["meta"]["stichtag"] == "2026-07-13"


def test_cli_kontext_verzeichnis_fehlt_exit_2(tmp_path):
    res = _lauf("--kontext", str(tmp_path / "fehlt"))
    assert res.returncode == 2


def test_cli_ungueltiger_stichtag_exit_2():
    res = _lauf("--kontext", str(BEISPIEL_KONTEXT), "--stichtag", "13.07.2026")
    assert res.returncode == 2


def test_cli_output_dateien(tmp_path):
    json_ziel = tmp_path / "report.json"
    md_ziel = tmp_path / "report.md"
    res = _lauf("--kontext", str(BEISPIEL_KONTEXT), "--stichtag", "2026-07-13",
               "--output-json", str(json_ziel), "--output-md", str(md_ziel))
    assert res.returncode == 0, res.stderr
    assert json.loads(json_ziel.read_text(encoding="utf-8"))["meta"]["quelle"] == "executor"
    assert "Retention-Hinweis-Report" in md_ziel.read_text(encoding="utf-8")


def test_cli_ohne_stichtag_nutzt_heute():
    res = _lauf("--kontext", str(BEISPIEL_KONTEXT))
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    assert report["meta"]["stichtag"] == date.today().isoformat()
