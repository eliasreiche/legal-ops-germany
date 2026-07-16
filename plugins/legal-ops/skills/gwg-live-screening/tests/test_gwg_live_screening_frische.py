"""Tests für das Frische-Gate (D19-Muster) des Screening-Executors (P4).

Deckt: harter Fehler bei fehlendem abgerufen_am / fehlender abruf-meta.json /
fehlendem XML-Generierungsdatum, die 7-Tage-Warnschwelle (Grenzfälle) und die
korrekte Alter-Berechnung — über ein injiziertes Bezugsdatum, nicht die
Systemzeit. Kein Netzwerkzugriff.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = Path(__file__).resolve().parents[1]

# Executor als Modul laden (liegt nicht auf dem Importpfad).
_spec = importlib.util.spec_from_file_location(
    "gwg_live_screening_executor", SKILL_DIR / "executor.py")
executor = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = executor
_spec.loader.exec_module(executor)

FIXTURES = SKILL_DIR / "tests" / "fixtures"
HEUTE = _dt.date(2026, 7, 16)


def _kopiere_listen(tmp_path: Path, mit_meta: bool = True,
                    abgerufen_am: str | None = "2026-07-15") -> Path:
    """Legt ein Listen-Verzeichnis mit den Fixtures an, optional mit meta."""
    ziel = tmp_path / "listen"
    ziel.mkdir()
    for name in ("eu-fsf-mini.xml", "un-consolidated-mini.xml"):
        (ziel / name).write_bytes((FIXTURES / name).read_bytes())
    if mit_meta:
        import json
        meta = {}
        for name in ("eu-fsf-mini.xml", "un-consolidated-mini.xml"):
            eintrag = {"url": "https://example.invalid"}
            if abgerufen_am is not None:
                eintrag["abgerufen_am"] = abgerufen_am
            meta[name] = eintrag
        (ziel / "abruf-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return ziel


def test_frisch_keine_warnung(tmp_path):
    ziel = _kopiere_listen(tmp_path, abgerufen_am="2026-07-15")
    geladen = executor.lade_listen_verzeichnis(ziel, HEUTE)
    assert len(geladen) == 2
    assert all(not gl.warnung for gl in geladen)
    assert all(gl.alter_tage == 1 for gl in geladen)


def test_warnung_ab_8_tagen(tmp_path):
    ziel = _kopiere_listen(tmp_path, abgerufen_am="2026-07-08")  # 8 Tage
    geladen = executor.lade_listen_verzeichnis(ziel, HEUTE)
    assert all(gl.warnung for gl in geladen)
    assert all(gl.alter_tage == 8 for gl in geladen)


def test_keine_warnung_genau_7_tage(tmp_path):
    ziel = _kopiere_listen(tmp_path, abgerufen_am="2026-07-09")  # 7 Tage
    geladen = executor.lade_listen_verzeichnis(ziel, HEUTE)
    assert all(not gl.warnung for gl in geladen)
    assert all(gl.alter_tage == 7 for gl in geladen)


def test_fehlende_meta_ist_frische_fehler(tmp_path):
    ziel = _kopiere_listen(tmp_path, mit_meta=False)
    with pytest.raises(executor.FrischeFehler):
        executor.lade_listen_verzeichnis(ziel, HEUTE)


def test_fehlendes_abgerufen_am_ist_frische_fehler(tmp_path):
    ziel = _kopiere_listen(tmp_path, abgerufen_am=None)
    with pytest.raises(executor.FrischeFehler):
        executor.lade_listen_verzeichnis(ziel, HEUTE)


def test_ungueltiges_abgerufen_am_ist_frische_fehler(tmp_path):
    ziel = _kopiere_listen(tmp_path, abgerufen_am="letzte Woche")
    with pytest.raises(executor.FrischeFehler):
        executor.lade_listen_verzeichnis(ziel, HEUTE)


def test_fehlendes_generierungsdatum_ist_frische_fehler(tmp_path):
    ziel = _kopiere_listen(tmp_path)
    # XML ohne generationDate an der Wurzel überschreiben.
    (ziel / "eu-fsf-mini.xml").write_text(
        '<export xmlns="http://eu.europa.ec/fpi/fsd/export">'
        '<sanctionEntity euReferenceNumber="EU.1"><subjectType code="person"/>'
        '<nameAlias wholeName="Test Person"/></sanctionEntity></export>',
        encoding="utf-8")
    with pytest.raises(executor.FrischeFehler):
        executor.lade_listen_verzeichnis(ziel, HEUTE)


def test_leeres_verzeichnis_ohne_xml_ist_eingabefehler(tmp_path):
    import json
    ziel = tmp_path / "leer"
    ziel.mkdir()
    (ziel / "abruf-meta.json").write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(executor.EingabeFehler):
        executor.lade_listen_verzeichnis(ziel, HEUTE)
