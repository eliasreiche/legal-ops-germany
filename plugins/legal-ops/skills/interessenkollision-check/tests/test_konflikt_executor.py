"""Tests für executor.py — Unit-Ebene (Matching-Stufen, CSV-/JSON-Einlesen).

Deckt ab: je mindestens ein Fall für S1-S4, die geforderten False-Positive-
Grenzfälle (Rechtsform allein reicht nie; kurze Namen), CSV-/JSON-Parsing
(Semikolon, BOM, fehlende Pflichtspalte(n), ungültige rolle/typ-Werte) sowie
den Report-Aufbau (Zusammenfassung, Sortierung, kein_treffer erscheint
nicht im Report). CLI-Verhalten (subprocess) steht in
test_konflikt_executor_cli.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = REPO / "plugins" / "legal-ops" / "skills" / "interessenkollision-check"

# Modul unter eindeutigem Namen laden (nicht "executor"): mehrere Skills in
# diesem Repo haben je ein eigenes executor.py und importieren es unter dem
# generischen Namen "executor" — ein schlichtes `sys.path.insert` + `import
# executor` würde in derselben pytest-Session das zuerst geladene Modul aus
# sys.modules cachen und in allen anderen Testdateien (z. B.
# plugins/legal-ops/skills/zitat-pruefer/tests/test_executor.py) fälschlich
# wiederverwenden.
_SPEC = importlib.util.spec_from_file_location(
    "interessenkollision_check_executor", SKILL_DIR / "executor.py")
executor = importlib.util.module_from_spec(_SPEC)
# Vor exec_module in sys.modules eintragen: dataclasses löst
# `cls.__module__` in Python 3.14 über sys.modules auf (u. a. für
# ClassVar/InitVar-Erkennung) — ohne Eintrag schlägt @dataclass fehl.
sys.modules[_SPEC.name] = executor
_SPEC.loader.exec_module(executor)


def _partei(name, rolle=None, typ=None, az=None, notiz=None) -> executor.Partei:
    return executor.Partei(name=name, rolle=rolle, typ=typ, az=az, notiz=notiz)


# --------------------------------------------------------------------------
# Match-Stufen S1-S4 (je mindestens ein Fall)
# --------------------------------------------------------------------------

def test_s1_exakter_treffer_nach_normalisierung():
    kandidat = executor.vergleiche(
        _partei("Dr. Max Mustermann"), _partei("Max Mustermann GmbH"), 0.85)
    assert kandidat is not None
    assert kandidat.regel == "S1"
    assert kandidat.stufe == executor.STUFE_TREFFER
    assert kandidat.score == 1.0


def test_s2_token_mengen_gleichheit_wortreihenfolge():
    kandidat = executor.vergleiche(
        _partei("Bau Mustermann GmbH"), _partei("Mustermann Bau GmbH"), 0.85)
    assert kandidat.regel == "S2"
    assert kandidat.stufe == executor.STUFE_TREFFER
    assert kandidat.score == 1.0


def test_s2_token_teilmenge_niedrigerer_score():
    kandidat = executor.vergleiche(
        _partei("Mustermann"), _partei("Auto Mustermann GmbH"), 0.85)
    assert kandidat.regel == "S2"
    assert kandidat.stufe == executor.STUFE_TREFFER
    assert kandidat.score == pytest.approx(0.5)


def test_s3_phonetisch_meyer_maier():
    kandidat = executor.vergleiche(_partei("Maier"), _partei("Meyer"), 0.85)
    assert kandidat.regel == "S3"
    assert kandidat.stufe == executor.STUFE_MOEGLICH
    assert kandidat.score == 1.0
    assert "Kölner Phonetik" in kandidat.begruendung


def test_s3_phonetisch_schmidt_schmitt():
    kandidat = executor.vergleiche(_partei("Schmitt"), _partei("Schmidt"), 0.85)
    assert kandidat.regel == "S3"
    assert kandidat.stufe == executor.STUFE_MOEGLICH


def test_s4_fuzzy_ueber_schwelle():
    kandidat = executor.vergleiche(
        _partei("Beispiel Handels GmbH"),
        _partei("Beispiel Handel GmbH & Co. KG"), 0.85)
    assert kandidat.regel == "S4"
    assert kandidat.stufe == executor.STUFE_MOEGLICH
    assert kandidat.score >= 0.85


def test_s4_unter_schwelle_ist_kein_treffer():
    kandidat = executor.vergleiche(
        _partei("Beispiel Handels GmbH"),
        _partei("Beispiel Handel GmbH & Co. KG"), 0.99)
    assert kandidat is None


# --------------------------------------------------------------------------
# False-Positive-Grenzfälle (dürfen NICHT matchen)
# --------------------------------------------------------------------------

def test_rechtsform_allein_reicht_nie():
    kandidat = executor.vergleiche(_partei("Müller GmbH"), _partei("Schulze GmbH"), 0.85)
    assert kandidat is None


def test_kurze_namen_fuehren_nicht_zu_falschem_treffer():
    kandidat = executor.vergleiche(_partei("AB GmbH"), _partei("AC GmbH"), 0.85)
    assert kandidat is None


def test_voellig_unterschiedliche_namen_kein_treffer():
    kandidat = executor.vergleiche(
        _partei("Voellig Unbeteiligte Partei GmbH"), _partei("Erika Mustermann"), 0.85)
    assert kandidat is None


# --------------------------------------------------------------------------
# Schwellen-Override
# --------------------------------------------------------------------------

def test_schwellen_override_macht_treffer_aus_nicht_treffer():
    neue = _partei("Beispiel Handels GmbH")
    liste = _partei("Beispiel Handel GmbH & Co. KG")
    assert executor.vergleiche(neue, liste, 0.99) is None
    kandidat = executor.vergleiche(neue, liste, 0.90)
    assert kandidat is not None
    assert kandidat.regel == "S4"


# --------------------------------------------------------------------------
# CSV-Parsing: Mandantenliste
# --------------------------------------------------------------------------

def test_csv_semikolon_wird_korrekt_geparst(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_text(
        "name;rolle;typ;az;notiz\nErika Mustermann;mandant;natuerlich;12/2024;Notiz\n",
        encoding="utf-8")
    parteien = executor.lese_mandantenliste(pfad)
    assert len(parteien) == 1
    assert parteien[0].name == "Erika Mustermann"
    assert parteien[0].rolle == "mandant"
    assert parteien[0].typ == "natuerlich"
    assert parteien[0].az == "12/2024"
    assert parteien[0].notiz == "Notiz"


def test_csv_bom_wird_toleriert(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_bytes(
        "﻿name;rolle;typ\nErika Mustermann;mandant;natuerlich\n".encode("utf-8"))
    parteien = executor.lese_mandantenliste(pfad)
    assert len(parteien) == 1
    assert parteien[0].name == "Erika Mustermann"


def test_csv_fehlende_pflichtspalte_wirft_fehler(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_text("name;rolle\nErika Mustermann;mandant\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="Pflichtspalte"):
        executor.lese_mandantenliste(pfad)


def test_csv_fehlender_name_in_zeile_wirft_fehler(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_text("name;rolle;typ\n;mandant;natuerlich\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="'name'"):
        executor.lese_mandantenliste(pfad)


def test_csv_ungueltige_rolle_wirft_fehler(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_text("name;rolle;typ\nErika;unsinn;natuerlich\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="rolle"):
        executor.lese_mandantenliste(pfad)


def test_csv_ungueltiger_typ_wirft_fehler(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_text("name;rolle;typ\nErika;mandant;unsinn\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="typ"):
        executor.lese_mandantenliste(pfad)


def test_csv_nur_kopfzeile_wirft_fehler(tmp_path):
    pfad = tmp_path / "liste.csv"
    pfad.write_text("name;rolle;typ\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="keine Einträge"):
        executor.lese_mandantenliste(pfad)


# --------------------------------------------------------------------------
# CSV-/JSON-Parsing: neue Parteien
# --------------------------------------------------------------------------

def test_neue_parteien_csv_nur_name_pflicht(tmp_path):
    pfad = tmp_path / "parteien.csv"
    pfad.write_text("name\nErika Mustermann\n", encoding="utf-8")
    parteien = executor.lese_neue_parteien(pfad)
    assert len(parteien) == 1
    assert parteien[0].rolle is None
    assert parteien[0].typ is None


def test_neue_parteien_csv_fehlender_name_wirft_fehler(tmp_path):
    pfad = tmp_path / "parteien.csv"
    pfad.write_text("rolle\nmandant\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="Pflichtspalte 'name'"):
        executor.lese_neue_parteien(pfad)


def test_neue_parteien_json_liste_von_objekten(tmp_path):
    pfad = tmp_path / "parteien.json"
    pfad.write_text(
        '[{"name": "Erika Mustermann", "rolle": "mandant"}, {"name": "Beispiel GmbH"}]',
        encoding="utf-8")
    parteien = executor.lese_neue_parteien(pfad)
    assert len(parteien) == 2
    assert parteien[0].rolle == "mandant"
    assert parteien[1].rolle is None


def test_neue_parteien_json_kein_array_wirft_fehler(tmp_path):
    pfad = tmp_path / "parteien.json"
    pfad.write_text('{"name": "Erika"}', encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="Liste"):
        executor.lese_neue_parteien(pfad)


def test_neue_parteien_json_kaputtes_json_wirft_fehler(tmp_path):
    pfad = tmp_path / "parteien.json"
    pfad.write_text('[{kein json]', encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="JSON"):
        executor.lese_neue_parteien(pfad)


def test_neue_parteien_unbekannte_dateiendung_wirft_fehler(tmp_path):
    pfad = tmp_path / "parteien.txt"
    pfad.write_text("name\nErika\n", encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="Dateiendung"):
        executor.lese_neue_parteien(pfad)


def test_neue_parteien_json_leere_liste_wirft_fehler(tmp_path):
    pfad = tmp_path / "parteien.json"
    pfad.write_text('[]', encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="leere Liste"):
        executor.lese_neue_parteien(pfad)


def test_neue_parteien_json_ungueltige_rolle_wirft_fehler(tmp_path):
    pfad = tmp_path / "parteien.json"
    pfad.write_text('[{"name": "Erika", "rolle": "unsinn"}]', encoding="utf-8")
    with pytest.raises(executor.EingabeFehler, match="rolle"):
        executor.lese_neue_parteien(pfad)


# --------------------------------------------------------------------------
# Report-Aufbau
# --------------------------------------------------------------------------

def test_baue_report_zaehlt_kein_treffer_nur_in_zusammenfassung():
    neue = [_partei("Voellig Unbeteiligte Partei")]
    liste = [_partei("Erika Mustermann", "mandant", "natuerlich")]
    report = executor.baue_report(neue, liste, 0.85, "liste.csv", "parteien.json")
    assert report["kandidaten"] == []
    assert report["zusammenfassung"]["anzahl_geprueft_paare"] == 1
    assert report["zusammenfassung"]["anzahl_treffer"] == 0
    assert report["zusammenfassung"]["anzahl_moegliche_treffer"] == 0


def test_baue_report_sortiert_treffer_vor_moeglichen_treffern():
    neue = [_partei("Maier"), _partei("Erika Mustermann")]
    liste = [_partei("Meyer", "gegner", "natuerlich"),
             _partei("Erika Mustermann", "mandant", "natuerlich")]
    report = executor.baue_report(neue, liste, 0.85, "liste.csv", "parteien.json")
    stufen = [k["stufe"] for k in report["kandidaten"]]
    assert stufen[0] == executor.STUFE_TREFFER
    assert stufen[-1] == executor.STUFE_MOEGLICH
