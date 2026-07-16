"""Tests für die Mandats-Zuordnung von posteingang-ocr-verteilung/executor.py
gegen core/context/beispiel-kontext/ (read-only) — delegiert vollständig an
core/calc/zuordnung/ (dieselbe Bibliothek wie email-akten-zuordnung).

Deckt ab: eindeutiger Treffer (Z0, eigenes Aktenzeichen im Scan-Text),
kein_treffer (kein Mandats-/Parteibezug) und einen echten
Mehrdeutigkeits-Grenzfall (der Absender "Zweite Beispiel KG" trifft sowohl
auf Mandat 2026-002 als auch — über das gemeinsame Wort "Beispiel" — auf
Mandat 2026-001), analog zum dokumentierten Grenzfall in
email-akten-zuordnung/tests/test_email_zuordnung_regeln.py.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"

_spec = importlib.util.spec_from_file_location("posteingang_ocr_verteilung_executor_z", EXECUTOR)
executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(executor)


def _zuordnung(fixture_name: str, absender: str, betreff: str) -> dict:
    text = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    mandate, warnungen = executor.lese_kontext_mandate(BEISPIEL_KONTEXT)
    assert warnungen == []
    eingang = {"eingang": {"absender": absender, "betreff": betreff}}
    return executor.baue_zuordnung(eingang, text, mandate, 0.85)


def test_eindeutiger_treffer_ueber_eigenes_aktenzeichen():
    z = _zuordnung("scan_eindeutig.txt", "Muster AG",
                   "Kündigung des Liefervertrags Nr. 4471")
    assert z["eindeutig"] is True
    assert z["az_fuer_routing"] == "2026-001"
    assert z["erfordert_rueckfrage"] is False
    assert z["kandidaten"][0]["stufe"] == "Z0"


def test_kein_treffer_ohne_mandatsbezug():
    z = _zuordnung("scan_kein_treffer.txt", "Werbe-Service GmbH",
                   "Sonderangebot fuer Kanzleibedarf")
    assert z["kein_treffer"] is True
    assert z["eindeutig"] is False
    assert z["az_fuer_routing"] is None
    assert z["erfordert_rueckfrage"] is False


def test_mehrdeutigkeit_erzwingt_rueckfrage_statt_automatischer_wahl():
    z = _zuordnung("scan_mehrdeutig.txt", "Zweite Beispiel KG",
                   "Mahnung wegen ausstehender Zahlung")
    assert len(z["kandidaten"]) == 2
    assert {k["az"] for k in z["kandidaten"]} == {"2026-001", "2026-002"}
    assert z["eindeutig"] is False
    assert z["az_fuer_routing"] is None
    assert z["erfordert_rueckfrage"] is True
    assert z["hinweis"] is not None and "Rückfrage" in z["hinweis"]


def test_mandat_ohne_aktenzeichen_wird_uebersprungen_und_gewarnt(tmp_path):
    kontext = tmp_path / "kontext"
    (kontext / "mandate").mkdir(parents=True)
    (kontext / "mandate" / "ohne-az.md").write_text(
        "---\nmandant: \"Ohne AZ GmbH\"\nstand: 2026-01-01\n---\n\n# Test\n",
        encoding="utf-8")
    mandate, warnungen = executor.lese_kontext_mandate(kontext)
    assert mandate == []
    assert warnungen and "kein Aktenzeichen" in warnungen[0]
