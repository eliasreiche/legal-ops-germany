"""Tests für den Routing-Plan von posteingang-ocr-verteilung/executor.py.

Deckt ab: Dry-Run-Default (kein Dateisystemzugriff auf das Ziel), fehlendes
Datum (`moeglich: false`, kein erfundener Zielordner), `--ausfuehren`
kopiert tatsächlich (Original bleibt erhalten), Kollisionserkennung
(bestehender Zielordner wird nie überschrieben/zusammengeführt), leere
`--scan-datei`-Liste bei `--ausfuehren`, und die Absender-Slug-Regel
(inkl. Fallback für leeren Absender).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"

_spec = importlib.util.spec_from_file_location("posteingang_ocr_verteilung_executor_r", EXECUTOR)
executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(executor)


def _eingang(absender: str = "Muster AG", datum: str | None = "2026-07-01") -> dict:
    return {"eingang": {"absender": absender, "datum_schreiben": datum,
                        "aktenzeichen_fremd": None, "aktenzeichen_eigen": None,
                        "betreff": "Test"}}


_ZUORDNUNG_EINDEUTIG = {"az_fuer_routing": "2026-001"}
_ZUORDNUNG_UNZUGEORDNET = {"az_fuer_routing": None}


def test_dry_run_baut_plan_ohne_dateisystemzugriff(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    plan = executor.baue_routing_plan(_eingang(), _ZUORDNUNG_EINDEUTIG, [], kontext,
                                      ausfuehren=False)
    assert plan["moeglich"] is True
    assert plan["ziel_ordner"] == "posteingang/2026-07-01_2026-001_muster-ag"
    assert plan["ausgefuehrt"] is False
    assert plan["fehler"] is None
    assert not (kontext / "posteingang").exists()


def test_ohne_datum_ist_kein_zielordner_erfunden(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    plan = executor.baue_routing_plan(_eingang(datum=None), _ZUORDNUNG_EINDEUTIG, [],
                                      kontext, ausfuehren=False)
    assert plan["moeglich"] is False
    assert plan["ziel_ordner"] is None
    assert plan["dateien"] == []
    assert "Datum" in plan["hinweis"]


def test_unzugeordnet_landet_im_unzugeordnet_ordner(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    plan = executor.baue_routing_plan(_eingang(), _ZUORDNUNG_UNZUGEORDNET, [], kontext,
                                      ausfuehren=False)
    assert plan["ziel_ordner"] == "posteingang/2026-07-01_unzugeordnet_muster-ag"


def test_ausfuehren_kopiert_dateien_original_bleibt_erhalten(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    scan = tmp_path / "scan.txt"
    scan.write_text("Inhalt des Scans", encoding="utf-8")

    plan = executor.baue_routing_plan(_eingang(), _ZUORDNUNG_EINDEUTIG, [scan], kontext,
                                      ausfuehren=True)

    assert plan["ausgefuehrt"] is True
    assert plan["fehler"] is None
    ziel = kontext / "posteingang" / "2026-07-01_2026-001_muster-ag" / "scan.txt"
    assert ziel.is_file()
    assert ziel.read_text(encoding="utf-8") == "Inhalt des Scans"
    assert scan.is_file()  # Original unverändert (kopiert, nicht verschoben)


def test_kollision_bei_bestehendem_zielordner_wird_nie_ueberschrieben(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    ziel_ordner = kontext / "posteingang" / "2026-07-01_2026-001_muster-ag"
    ziel_ordner.mkdir(parents=True)
    (ziel_ordner / "bestehende-datei.txt").write_text("bereits da", encoding="utf-8")

    scan = tmp_path / "scan.txt"
    scan.write_text("Neuer Inhalt", encoding="utf-8")

    plan = executor.baue_routing_plan(_eingang(), _ZUORDNUNG_EINDEUTIG, [scan], kontext,
                                      ausfuehren=True)

    assert plan["ausgefuehrt"] is False
    assert plan["fehler"] is not None and "Kollision" in plan["fehler"]
    # Bestehender Inhalt bleibt unangetastet.
    assert (ziel_ordner / "bestehende-datei.txt").read_text(encoding="utf-8") == "bereits da"
    assert not (ziel_ordner / "scan.txt").exists()


def test_ausfuehren_ohne_scan_dateien_bleibt_unausgefuehrt(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    plan = executor.baue_routing_plan(_eingang(), _ZUORDNUNG_EINDEUTIG, [], kontext,
                                      ausfuehren=True)
    assert plan["ausgefuehrt"] is False
    assert plan["fehler"] is None
    assert not (kontext / "posteingang").exists()


def test_absender_slug_transliteriert_und_kollabiert():
    assert executor._slug("Müller & Söhne GmbH", "x") == "mueller-soehne-gmbh"


def test_absender_slug_fallback_bei_leerem_absender():
    assert executor._slug("", "unbekannter-absender") == "unbekannter-absender"
    assert executor._slug("   ", "unbekannter-absender") == "unbekannter-absender"
