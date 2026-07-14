"""Tests für plugins/legal-ops/skills/passive-zeiterfassung/executor.py (CLI).

Deckt ab: Dauer/Datum aus Zeitstempeln, Akten-Zuordnung (eindeutig /
mehrdeutig / kein Treffer), Mail-Pauschale aus Config vs. ohne_zeitwert-Lücke
ohne Config, Termin-Überlappungswarnung, ende<=start als Eingabefehler,
CLI-Fehlerfälle (jeweils Exit 2 ohne Traceback), Summen nur über eindeutige
Vorschläge.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"


def _schreibe(pfad: Path, daten) -> None:
    if isinstance(daten, str):
        pfad.write_text(daten, encoding="utf-8")
    else:
        pfad.write_text(json.dumps(daten), encoding="utf-8")


def _lauf(tmp_path: Path, *, termine=None, mails=None, config=None,
          kontext=BEISPIEL_KONTEXT) -> subprocess.CompletedProcess:
    args = [sys.executable, str(EXECUTOR), "--kontext", str(kontext)]
    if termine is not None:
        p = tmp_path / "termine.json"
        _schreibe(p, termine)
        args += ["--termine", str(p)]
    if mails is not None:
        p = tmp_path / "mails.json"
        _schreibe(p, mails)
        args += ["--mails", str(p)]
    if config is not None:
        p = tmp_path / "config.json"
        _schreibe(p, config)
        args += ["--config", str(p)]
    return subprocess.run(args, capture_output=True, text=True)


def _report(tmp_path: Path, **kwargs) -> dict:
    ergebnis = _lauf(tmp_path, **kwargs)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return json.loads(ergebnis.stdout)


def _termin(**overrides) -> dict:
    basis = {"betreff": "Az. 2026-001 Besprechung", "start": "2026-07-06T09:00:00",
             "ende": "2026-07-06T09:45:00", "teilnehmer": [], "ort": None}
    basis.update(overrides)
    return basis


def _mail(**overrides) -> dict:
    basis = {"zeitstempel": "2026-07-06T13:15:00", "betreff": "Az. 2026-001 Rückfrage",
             "absender": "Kanzlei", "empfaenger": [], "richtung": "ausgehend"}
    basis.update(overrides)
    return basis


# --------------------------------------------------------------------------
# Dauer / Datum aus Zeitstempeln
# --------------------------------------------------------------------------

def test_termin_dauer_und_datum_aus_start_ende(tmp_path):
    report = _report(tmp_path, termine={"termine": [
        _termin(start="2026-07-06T09:00:00", ende="2026-07-06T09:47:00")]})
    v = report["vorschlaege"][0]
    assert v["leistung"]["datum"] == "2026-07-06"
    assert v["leistung"]["start"] == "2026-07-06T09:00:00"
    assert v["leistung"]["ende"] == "2026-07-06T09:47:00"
    assert v["leistung"]["minuten"] is None
    # 47 Minuten fließen über core/calc/zeit in die Summe.
    assert report["summen"]["je_az"]["2026-001"] == 47


def test_termin_dauer_wird_aufgerundet(tmp_path):
    report = _report(tmp_path, termine={"termine": [
        _termin(start="2026-07-06T09:00:00", ende="2026-07-06T09:00:30")]})
    assert report["summen"]["je_az"]["2026-001"] == 1


def test_mail_datum_aus_zeitstempel(tmp_path):
    report = _report(tmp_path, mails={"mails": [_mail(zeitstempel="2026-07-06T13:15:00")]},
                     config={"mail_pauschale_minuten": 6})
    assert report["vorschlaege"][0]["leistung"]["datum"] == "2026-07-06"


# --------------------------------------------------------------------------
# Zuordnung: eindeutig / mehrdeutig / kein Treffer
# --------------------------------------------------------------------------

def test_zuordnung_eindeutig_via_az(tmp_path):
    report = _report(tmp_path, termine={"termine": [_termin(betreff="Az. 2026-001 Termin")]})
    assert len(report["vorschlaege"]) == 1
    v = report["vorschlaege"][0]
    assert v["leistung"]["az"] == "2026-001"
    assert v["zuordnung"]["stufe"] == "Z0"
    assert v["status"] == "zu_bestaetigen"
    assert report["mehrdeutig"] == [] and report["nicht_zuordenbar"] == []


def test_zuordnung_mehrdeutig_bei_zwei_treffern(tmp_path):
    report = _report(tmp_path, termine={"termine": [
        _termin(betreff="Sammeltermin Az. 2026-001 und Az. 2026-002")]})
    assert report["vorschlaege"] == []
    assert len(report["mehrdeutig"]) == 1
    az_kandidaten = {k["az"] for k in report["mehrdeutig"][0]["kandidaten"]}
    assert az_kandidaten == {"2026-001", "2026-002"}


def test_zuordnung_nicht_zuordenbar(tmp_path):
    report = _report(tmp_path, termine={"termine": [
        _termin(betreff="Interne Fortbildung", teilnehmer=["Dr. Schmitt"], ort="Raum 1")]})
    assert report["vorschlaege"] == []
    assert len(report["nicht_zuordenbar"]) == 1
    assert "kein" in report["nicht_zuordenbar"][0]["hinweis"].lower()


# --------------------------------------------------------------------------
# Mail-Pauschale aus Config vs. ohne_zeitwert-Lücke ohne Config
# --------------------------------------------------------------------------

def test_mail_pauschale_aus_config_wird_zu_minuten(tmp_path):
    report = _report(tmp_path, mails={"mails": [_mail()]}, config={"mail_pauschale_minuten": 6})
    v = report["vorschlaege"][0]
    assert v["leistung"]["minuten"] == 6
    assert v["leistung"]["quelle"] == "mail"
    assert report["summen"]["je_az"]["2026-001"] == 6


def test_mail_ohne_config_landet_in_ohne_zeitwert(tmp_path):
    report = _report(tmp_path, mails={"mails": [_mail()]})
    assert report["vorschlaege"] == []
    assert len(report["ohne_zeitwert"]) == 1
    o = report["ohne_zeitwert"][0]
    assert o["zuordnung_status"] == "eindeutig"
    assert o["az"] == "2026-001"
    assert "manuell" in o["hinweis"].lower()
    assert report["summen"]["je_az"] == {}


def test_mail_config_null_wie_keine_config(tmp_path):
    report = _report(tmp_path, mails={"mails": [_mail()]},
                     config={"mail_pauschale_minuten": None})
    assert report["vorschlaege"] == []
    assert len(report["ohne_zeitwert"]) == 1


# --------------------------------------------------------------------------
# Termin-Überlappung
# --------------------------------------------------------------------------

def test_ueberlappende_termine_warnung(tmp_path):
    report = _report(tmp_path, termine={"termine": [
        _termin(betreff="Az. 2026-001 A", start="2026-07-08T10:00:00", ende="2026-07-08T11:00:00"),
        _termin(betreff="Az. 2026-002 B", start="2026-07-08T10:30:00", ende="2026-07-08T11:30:00"),
    ]})
    assert len(report["warnungen"]) == 1
    w = report["warnungen"][0]
    assert w["typ"] == "termin_ueberlappung"
    assert {w["termin_a"]["betreff"], w["termin_b"]["betreff"]} == {"Az. 2026-001 A", "Az. 2026-002 B"}


def test_nicht_ueberlappende_termine_keine_warnung(tmp_path):
    report = _report(tmp_path, termine={"termine": [
        _termin(start="2026-07-08T10:00:00", ende="2026-07-08T11:00:00"),
        _termin(start="2026-07-08T11:00:00", ende="2026-07-08T12:00:00"),
    ]})
    assert report["warnungen"] == []


# --------------------------------------------------------------------------
# Eingabefehler (Exit 2, kein Traceback)
# --------------------------------------------------------------------------

def test_fehler_ende_vor_start(tmp_path):
    ergebnis = _lauf(tmp_path, termine={"termine": [
        _termin(start="2026-07-06T10:00:00", ende="2026-07-06T09:00:00")]})
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_fehler_ende_gleich_start(tmp_path):
    ergebnis = _lauf(tmp_path, termine={"termine": [
        _termin(start="2026-07-06T09:00:00", ende="2026-07-06T09:00:00")]})
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_fehler_keine_quelle(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--kontext", str(BEISPIEL_KONTEXT)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "termine" in ergebnis.stderr and "mails" in ergebnis.stderr


def test_fehler_kontext_fehlt(tmp_path):
    ergebnis = _lauf(tmp_path, termine={"termine": [_termin()]},
                     kontext=tmp_path / "gibtsnicht")
    assert ergebnis.returncode == 2
    assert "kontext" in ergebnis.stderr.lower()


def test_fehler_kaputtes_json(tmp_path):
    ergebnis = _lauf(tmp_path, termine="{kein json")
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_unbekanntes_termin_feld(tmp_path):
    ergebnis = _lauf(tmp_path, termine={"termine": [dict(_termin(), tippfehler="x")]})
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr


def test_fehler_fehlendes_termin_pflichtfeld(tmp_path):
    t = _termin()
    del t["start"]
    ergebnis = _lauf(tmp_path, termine={"termine": [t]})
    assert ergebnis.returncode == 2
    assert "Pflichtfeld" in ergebnis.stderr


def test_fehler_ungueltige_mail_richtung(tmp_path):
    ergebnis = _lauf(tmp_path, mails={"mails": [_mail(richtung="intern")]})
    assert ergebnis.returncode == 2
    assert "richtung" in ergebnis.stderr


def test_fehler_ungueltiger_zeitstempel(tmp_path):
    ergebnis = _lauf(tmp_path, mails={"mails": [_mail(zeitstempel="06.07.2026")]},
                     config={"mail_pauschale_minuten": 6})
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_fehler_unbekanntes_config_feld(tmp_path):
    ergebnis = _lauf(tmp_path, mails={"mails": [_mail()]}, config={"pauschale": 6})
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr


def test_fehler_config_pauschale_nicht_positiv(tmp_path):
    ergebnis = _lauf(tmp_path, mails={"mails": [_mail()]}, config={"mail_pauschale_minuten": 0})
    assert ergebnis.returncode == 2


def test_fehler_wurzel_falsches_feld(tmp_path):
    ergebnis = _lauf(tmp_path, termine={"eintraege": []})
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr or "termine" in ergebnis.stderr


# --------------------------------------------------------------------------
# Output-Datei
# --------------------------------------------------------------------------

def test_output_datei(tmp_path):
    t = tmp_path / "termine.json"
    _schreibe(t, {"termine": [_termin()]})
    ziel = tmp_path / "report.json"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--termine", str(t),
         "--kontext", str(BEISPIEL_KONTEXT), "--output", str(ziel)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["meta"]["erzeugt_von"].endswith("passive-zeiterfassung/executor.py")
