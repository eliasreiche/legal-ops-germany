"""Tests für plugins/legal-ops/skills/taetigkeitstext-rvg/executor.py (CLI).

Deckt ab: Modus 1 (rechnen) — Validierung, Dauer-Berechnung, Taktung,
Aggregation je Aktenzeichen/(Aktenzeichen, Datum), `ohne_az`-Lücke; Modus 2
(Provenienz-Gate) — grüner und roter Lauf (erfundene Zahl, falsches Datum,
fremdes Aktenzeichen, 1,5h/90min-Äquivalenz); CLI-Fehlerfälle (Exit 2, kein
Traceback); Beispieldateien-Round-Trip (Golden Files).

Eindeutiger Testdateiname (`test_taetigkeitstext_executor_cli.py`), damit er
im selben pytest-Lauf nicht mit gleichnamigen Tests anderer Skills
kollidiert (mehrere Skills heißen `executor.py`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"
SCHEMA = SKILL / "schema"


def _schreibe_json(pfad: Path, daten) -> None:
    if isinstance(daten, str):
        pfad.write_text(daten, encoding="utf-8")
    else:
        pfad.write_text(json.dumps(daten), encoding="utf-8")


def _rechne(daten, tmp_path: Path) -> subprocess.CompletedProcess:
    eingabe = tmp_path / "leistungen.json"
    _schreibe_json(eingabe, daten)
    return subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe)],
        capture_output=True, text=True)


def _report(daten, tmp_path: Path) -> dict:
    ergebnis = _rechne(daten, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return json.loads(ergebnis.stdout)


def _pruefe(text: str, report: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    text_pfad = tmp_path / "entwurf.md"
    text_pfad.write_text(text, encoding="utf-8")
    report_pfad = tmp_path / "report.json"
    report_pfad.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(EXECUTOR), "--pruefe-text", str(text_pfad),
         "--report", str(report_pfad)],
        capture_output=True, text=True)


def _minimal_eintrag(**overrides) -> dict:
    basis = {
        "datum": "2026-07-01", "az": "12/2026", "minuten": 30,
        "start": None, "ende": None,
        "stichworte": ["Telefonat mit Mandant"], "quelle": "manuell",
    }
    basis.update(overrides)
    return basis


# --------------------------------------------------------------------------
# Modus 1 — Erfolgsfälle
# --------------------------------------------------------------------------

def test_rechnen_direkte_minuten(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(minuten=45)]}, tmp_path)
    assert report["eintraege"][0]["minuten"] == 45
    assert report["eintraege"][0]["minuten_getaktet"] == 45
    assert report["eintraege"][0]["quelle_zeit"] == "minuten"
    assert report["eintraege"][0]["stichworte"] == ["Telefonat mit Mandant"]
    assert report["meta"]["erzeugt_von"].endswith("taetigkeitstext-rvg/executor.py")


def test_rechnen_start_ende(tmp_path):
    eintrag = _minimal_eintrag(minuten=None,
                               start="2026-07-01T09:00:00", ende="2026-07-01T09:47:00")
    report = _report({"eintraege": [eintrag]}, tmp_path)
    assert report["eintraege"][0]["minuten"] == 47
    assert report["eintraege"][0]["quelle_zeit"] == "start_ende"


def test_rechnen_taktung_rundet_immer_auf(tmp_path):
    report = _report(
        {"eintraege": [_minimal_eintrag(minuten=47)], "config": {"takt_minuten": 6}},
        tmp_path)
    assert report["eintraege"][0]["minuten"] == 47
    assert report["eintraege"][0]["minuten_getaktet"] == 48
    assert report["meta"]["config"] == {"takt_minuten": 6}


def test_rechnen_ohne_config_keine_taktung(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(minuten=47)]}, tmp_path)
    assert report["eintraege"][0]["minuten_getaktet"] == 47
    assert report["meta"]["config"] == {"takt_minuten": None}


def test_rechnen_aggregation_je_az_und_je_az_datum(tmp_path):
    eintraege = [
        _minimal_eintrag(datum="2026-07-01", az="12/2026", minuten=30),
        _minimal_eintrag(datum="2026-07-01", az="12/2026", minuten=20),
        _minimal_eintrag(datum="2026-07-02", az="12/2026", minuten=10),
        _minimal_eintrag(datum="2026-07-02", az="34/2026", minuten=15),
    ]
    report = _report({"eintraege": eintraege}, tmp_path)
    assert report["summen"]["je_az"] == {"12/2026": 60, "34/2026": 15}
    je_az_datum = {(e["az"], e["datum"]): e["minuten"] for e in report["summen"]["je_az_und_datum"]}
    assert je_az_datum == {
        ("12/2026", "2026-07-01"): 50,
        ("12/2026", "2026-07-02"): 10,
        ("34/2026", "2026-07-02"): 15,
    }


def test_rechnen_ohne_az_luecke(tmp_path):
    eintraege = [
        _minimal_eintrag(az=None, minuten=20),
        _minimal_eintrag(az="12/2026", minuten=30),
    ]
    report = _report({"eintraege": eintraege}, tmp_path)
    assert len(report["ohne_az"]) == 1
    assert report["ohne_az"][0]["az"] is None
    assert len(report["eintraege"]) == 1
    assert report["zusammenfassung"]["anzahl_ohne_az"] == 1
    assert report["zusammenfassung"]["anzahl_mit_az"] == 1
    # Lücke fließt nicht in die az-Summen ein.
    assert "null" not in report["summen"]["je_az"]


def test_rechnen_leeres_az_wird_wie_null_behandelt(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(az="   ")]}, tmp_path)
    assert report["ohne_az"][0]["az"] is None
    assert report["eintraege"] == []


def test_rechnen_zusammenfassung_summen(tmp_path):
    eintraege = [
        _minimal_eintrag(az="12/2026", minuten=47),
        _minimal_eintrag(az=None, minuten=10),
    ]
    report = _report({"eintraege": eintraege, "config": {"takt_minuten": 6}}, tmp_path)
    z = report["zusammenfassung"]
    assert z["anzahl_eintraege"] == 2
    assert z["minuten_gesamt"] == 57
    assert z["minuten_gesamt_getaktet"] == 48 + 12


def test_rechnen_output_datei(tmp_path):
    eingabe = tmp_path / "leistungen.json"
    _schreibe_json(eingabe, {"eintraege": [_minimal_eintrag()]})
    ziel = tmp_path / "report.json"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe), "--output", str(ziel)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["zusammenfassung"]["anzahl_eintraege"] == 1


# --------------------------------------------------------------------------
# Modus 1 — Eingabefehler (Exit 2, kein Traceback)
# --------------------------------------------------------------------------

def test_rechnen_fehler_kaputtes_json(tmp_path):
    ergebnis = _rechne("{kein json", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_rechnen_fehler_datei_fehlt(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(tmp_path / "nix.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_rechnen_fehler_wurzel_kein_objekt(tmp_path):
    ergebnis = _rechne([1, 2, 3], tmp_path)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_rechnen_fehler_unbekanntes_wurzelfeld(tmp_path):
    ergebnis = _rechne({"eintraege": [], "tippfehler": 1}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr


def test_rechnen_fehler_eintraege_fehlt(tmp_path):
    ergebnis = _rechne({}, tmp_path)
    assert ergebnis.returncode == 2
    assert "eintraege" in ergebnis.stderr


def test_rechnen_fehler_unbekanntes_eintragsfeld(tmp_path):
    eintrag = _minimal_eintrag()
    eintrag["tippfehler"] = "x"
    ergebnis = _rechne({"eintraege": [eintrag]}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_rechnen_fehler_pflichtfeld_fehlt(tmp_path):
    eintrag = _minimal_eintrag()
    del eintrag["quelle"]
    ergebnis = _rechne({"eintraege": [eintrag]}, tmp_path)
    assert ergebnis.returncode == 2
    assert "Pflichtfeld" in ergebnis.stderr


def test_rechnen_fehler_unzulaessige_quelle(tmp_path):
    ergebnis = _rechne({"eintraege": [_minimal_eintrag(quelle="telefon")]}, tmp_path)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_rechnen_fehler_beide_zeitangaben(tmp_path):
    eintrag = _minimal_eintrag(minuten=30, start="2026-07-01T09:00:00",
                               ende="2026-07-01T09:30:00")
    ergebnis = _rechne({"eintraege": [eintrag]}, tmp_path)
    assert ergebnis.returncode == 2
    assert "beides" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_rechnen_fehler_nur_start_ohne_ende(tmp_path):
    eintrag = _minimal_eintrag(minuten=None, start="2026-07-01T09:00:00", ende=None)
    ergebnis = _rechne({"eintraege": [eintrag]}, tmp_path)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_rechnen_fehler_keine_zeitangabe(tmp_path):
    eintrag = _minimal_eintrag(minuten=None)
    ergebnis = _rechne({"eintraege": [eintrag]}, tmp_path)
    assert ergebnis.returncode == 2


def test_rechnen_fehler_ungueltiges_datum(tmp_path):
    ergebnis = _rechne({"eintraege": [_minimal_eintrag(datum="01.07.2026")]}, tmp_path)
    assert ergebnis.returncode == 2
    assert "datum" in ergebnis.stderr


def test_rechnen_fehler_leere_stichworte(tmp_path):
    ergebnis = _rechne({"eintraege": [_minimal_eintrag(stichworte=[])]}, tmp_path)
    # Leere Liste ist erlaubt (kein Stichwort != ungültiges Stichwort); nur
    # nicht-leere Strings sind Pflicht innerhalb der Liste.
    assert ergebnis.returncode == 0, ergebnis.stderr


def test_rechnen_fehler_leerstring_in_stichworten(tmp_path):
    ergebnis = _rechne({"eintraege": [_minimal_eintrag(stichworte=["gut", "  "])]}, tmp_path)
    assert ergebnis.returncode == 2


def test_rechnen_fehler_unbekanntes_configfeld(tmp_path):
    ergebnis = _rechne(
        {"eintraege": [_minimal_eintrag()], "config": {"takt": 6}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr


def test_rechnen_fehler_takt_minuten_nicht_positiv(tmp_path):
    ergebnis = _rechne(
        {"eintraege": [_minimal_eintrag()], "config": {"takt_minuten": 0}}, tmp_path)
    assert ergebnis.returncode == 2


# --------------------------------------------------------------------------
# Modus 2 — Provenienz-Gate: grüner Lauf
# --------------------------------------------------------------------------

def test_pruefe_sauber_bei_belegten_werten(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(minuten=45)]}, tmp_path)
    ergebnis = _pruefe(
        "Am 01.07.2026 wurde ein Telefonat mit dem Mandanten geführt (45 Minuten) "
        "für das Aktenzeichen 12/2026.", report, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    pruef = json.loads(ergebnis.stdout)
    assert pruef["ergebnis"] == "sauber"
    assert pruef["befunde"] == []


def test_pruefe_stunden_minuten_aequivalenz(tmp_path):
    # 90 Minuten ≡ 1,5 Stunden.
    report = _report({"eintraege": [_minimal_eintrag(minuten=90)]}, tmp_path)
    ergebnis = _pruefe("Aufwand am 01.07.2026 für 12/2026: 1,5 Stunden.", report, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    pruef = json.loads(ergebnis.stdout)
    assert pruef["ergebnis"] == "sauber"
    stunden_funde = [g for g in pruef["gefundene_werte"]["minuten"] if g["typ"] == "stunden"]
    assert stunden_funde and stunden_funde[0]["normalisiert"] == 90
    assert stunden_funde[0]["status"] == "belegt"


def test_pruefe_deutsches_und_iso_datum_gleichwertig(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(datum="2026-07-01", minuten=30)]},
                     tmp_path)
    ergebnis = _pruefe("Eintrag vom 2026-07-01 über 30 Minuten, Az. 12/2026.",
                       report, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr


# --------------------------------------------------------------------------
# Modus 2 — Provenienz-Gate: roter Lauf
# --------------------------------------------------------------------------

def test_pruefe_erfundene_zahl_wird_abgefangen(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(minuten=45)]}, tmp_path)
    ergebnis = _pruefe(
        "Am 01.07.2026 wurden 50 Minuten für 12/2026 aufgewendet.", report, tmp_path)
    assert ergebnis.returncode == 1
    pruef = json.loads(ergebnis.stdout)
    assert pruef["ergebnis"] == "abweichend"
    assert any(b["typ"] == "fremde_zahl" and b["normalisiert"] == 50 for b in pruef["befunde"])


def test_pruefe_falsches_datum_wird_abgefangen(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(datum="2026-07-01", minuten=45)]},
                     tmp_path)
    ergebnis = _pruefe(
        "Am 05.07.2026 wurden 45 Minuten für 12/2026 aufgewendet.", report, tmp_path)
    assert ergebnis.returncode == 1
    pruef = json.loads(ergebnis.stdout)
    assert any(b["typ"] == "fremdes_datum" and b["normalisiert"] == "2026-07-05"
              for b in pruef["befunde"])


def test_pruefe_fremdes_aktenzeichen_wird_abgefangen(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(az="12/2026", minuten=45)]}, tmp_path)
    ergebnis = _pruefe(
        "Am 01.07.2026 wurden 45 Minuten für 99/2099 aufgewendet.", report, tmp_path)
    assert ergebnis.returncode == 1
    pruef = json.loads(ergebnis.stdout)
    assert any(b["typ"] == "fremdes_aktenzeichen" and b["roh"] == "99/2099"
              for b in pruef["befunde"])


def test_pruefe_nicht_normalisierbare_stunden(tmp_path):
    report = _report({"eintraege": [_minimal_eintrag(minuten=45)]}, tmp_path)
    # 1,33 Stunden = 79,8 Minuten -> keine ganze Minutenzahl.
    ergebnis = _pruefe("Aufwand: 1,33 Stunden für 12/2026 am 01.07.2026.", report, tmp_path)
    assert ergebnis.returncode == 1
    pruef = json.loads(ergebnis.stdout)
    assert any(b["typ"] == "fremde_zahl" and b["normalisiert"] is None for b in pruef["befunde"])


# --------------------------------------------------------------------------
# Modus 2 — CLI-Fehlerfälle
# --------------------------------------------------------------------------

def test_pruefe_fehler_report_datei_fehlt(tmp_path):
    text_pfad = tmp_path / "entwurf.md"
    text_pfad.write_text("Text", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--pruefe-text", str(text_pfad),
         "--report", str(tmp_path / "nix.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_pruefe_fehler_text_datei_fehlt(tmp_path):
    report_pfad = tmp_path / "report.json"
    report_pfad.write_text("{}", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--pruefe-text", str(tmp_path / "nix.md"),
         "--report", str(report_pfad)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_pruefe_fehler_fremder_report_wird_abgelehnt(tmp_path):
    text_pfad = tmp_path / "entwurf.md"
    text_pfad.write_text("Text ohne Belang.", encoding="utf-8")
    report_pfad = tmp_path / "report.json"
    report_pfad.write_text(json.dumps({"meta": {"erzeugt_von": "modell"}}), encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--pruefe-text", str(text_pfad),
         "--report", str(report_pfad)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_pruefe_fehler_kaputtes_report_json(tmp_path):
    text_pfad = tmp_path / "entwurf.md"
    text_pfad.write_text("Text", encoding="utf-8")
    report_pfad = tmp_path / "report.json"
    report_pfad.write_text("{kein json", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--pruefe-text", str(text_pfad),
         "--report", str(report_pfad)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr


# --------------------------------------------------------------------------
# CLI — Modus-Auswahl
# --------------------------------------------------------------------------

def test_cli_ohne_modus_argument_exit_2(tmp_path):
    ergebnis = subprocess.run([sys.executable, str(EXECUTOR)], capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_beide_modi_gleichzeitig_exit_2(tmp_path):
    eingabe = tmp_path / "leistungen.json"
    _schreibe_json(eingabe, {"eintraege": []})
    text_pfad = tmp_path / "entwurf.md"
    text_pfad.write_text("Text", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe),
         "--pruefe-text", str(text_pfad), "--report", str(eingabe)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2


def test_cli_pruefe_text_ohne_report_exit_2(tmp_path):
    text_pfad = tmp_path / "entwurf.md"
    text_pfad.write_text("Text", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--pruefe-text", str(text_pfad)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2


# --------------------------------------------------------------------------
# Beispieldateien bleiben synchron (Golden Files, nie handeditiert)
# --------------------------------------------------------------------------

def test_beispiel_report_synchron():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(SCHEMA / "beispiel-leistungen.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
    gespeichert = json.loads((SCHEMA / "beispiel-report.json").read_text("utf-8"))
    erzeugt["meta"].pop("eingabe_datei")
    gespeichert["meta"].pop("eingabe_datei")
    assert erzeugt == gespeichert


def test_beispiel_pruef_report_synchron():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--pruefe-text", str(SCHEMA / "beispiel-entwurf.md"),
         "--report", str(SCHEMA / "beispiel-report.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
    gespeichert = json.loads((SCHEMA / "beispiel-pruef-report.json").read_text("utf-8"))
    for d in (erzeugt, gespeichert):
        d["meta"].pop("text_datei")
        d["meta"].pop("report_datei")
    assert erzeugt == gespeichert
    assert erzeugt["ergebnis"] == "sauber"


def test_beispiel_leistungen_round_trip_kernwerte():
    report = json.loads(subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(SCHEMA / "beispiel-leistungen.json")],
        capture_output=True, text=True).stdout)
    assert report["zusammenfassung"]["anzahl_eintraege"] == 5
    assert report["zusammenfassung"]["anzahl_ohne_az"] == 1
    assert report["summen"]["je_az"] == {"12/2026": 78, "34/2026": 42}
