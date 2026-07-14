"""Tests für executor.py — Regelwerk oberhalb der Zuordnungs-Bibliothek (P4).

Deckt ab: Fristverdacht-Wortliste (positiv/negativ), Priorität-Regel,
Slug-/Dateinamen-Bildung und das Kommunikations-Zeilen-Format nach
`core/context/README.md`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = REPO / "plugins" / "legal-ops" / "skills" / "email-akten-zuordnung"

_SPEC = importlib.util.spec_from_file_location(
    "email_akten_zuordnung_executor", SKILL_DIR / "executor.py")
executor = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = executor
_SPEC.loader.exec_module(executor)


# --------------------------------------------------------------------------
# Fristverdacht — Wortliste (positiv/negativ)
# --------------------------------------------------------------------------

def test_fristverdacht_positiv_frist_im_betreff():
    assert executor.fristverdacht("Fristsetzung zur Stellungnahme", "") is True


def test_fristverdacht_positiv_kuendigung_zusammengesetztes_wort():
    # Substring-Suche erkennt auch zusammengesetzte Wörter.
    assert executor.fristverdacht("Kündigungsschreiben", "") is True


def test_fristverdacht_positiv_je_signalwort():
    for wort in ("Urteil", "Beschluss", "Bescheid", "Zustellung", "Mahnung",
                 "Klage", "einstweilige Verfügung"):
        assert executor.fristverdacht(wort, "") is True, wort


def test_fristverdacht_positiv_in_textauszug_statt_betreff():
    assert executor.fristverdacht("Kurzmitteilung", "bitte Frist beachten") is True


def test_fristverdacht_negativ_ohne_signalwort():
    assert executor.fristverdacht("Terminabstimmung", "Wie wäre es mit Dienstag?") is False


def test_fristverdacht_case_insensitiv():
    assert executor.fristverdacht("FRISTVERLÄNGERUNG", "") is True


# --------------------------------------------------------------------------
# Priorität
# --------------------------------------------------------------------------

def test_prioritaet_hoch_bei_fristverdacht_ohne_kandidat():
    assert executor.prioritaet(True, []) == "hoch"


def test_prioritaet_hoch_bei_treffer_ohne_fristverdacht():
    k = executor.Kandidat(az="2026-001", stufe="Z0", kategorie="treffer",
                           score=1.0, begruendung="x")
    assert executor.prioritaet(False, [k]) == "hoch"


def test_prioritaet_normal_ohne_fristverdacht_und_ohne_treffer():
    k = executor.Kandidat(az="2026-001", stufe="Z4", kategorie="moeglicher_treffer",
                           score=0.9, begruendung="x")
    assert executor.prioritaet(False, [k]) == "normal"


def test_prioritaet_normal_ohne_alles():
    assert executor.prioritaet(False, []) == "normal"


# --------------------------------------------------------------------------
# Slug-Regel
# --------------------------------------------------------------------------

def test_slug_umlaute_und_leerzeichen():
    assert executor.betreff_slug("Fristsetzung in Sachen Müller / Az. 2026-001") == \
        "fristsetzung-in-sachen-mueller-az-2026-001"


def test_slug_leerer_betreff():
    assert executor.betreff_slug("") == "ohne-betreff"
    assert executor.betreff_slug(None) == "ohne-betreff"  # type: ignore[arg-type]


def test_slug_wird_gekuerzt():
    langer_betreff = "Wort " * 30
    slug = executor.betreff_slug(langer_betreff)
    assert len(slug) <= executor.SLUG_MAX_LEN
    assert not slug.endswith("-")


def test_slug_nur_sonderzeichen_ergibt_ohne_betreff():
    assert executor.betreff_slug("!!!???...") == "ohne-betreff"


# --------------------------------------------------------------------------
# Ablage-Vorschlag / Kommunikations-Zeile
# --------------------------------------------------------------------------

def test_ablage_vorschlag_dateiname_und_kommunikationszeile():
    vorschlag = executor.baue_ablage_vorschlag("2026-06-20", "Fristsetzung Az. 2026-001")
    assert vorschlag["moeglich"] is True
    assert vorschlag["dateiname"] == "posteingang/2026-06-20-fristsetzung-az-2026-001.eml"
    assert vorschlag["kommunikations_zeile"] == (
        "2026-06-20 — Fristsetzung Az. 2026-001 — "
        "[Datei](../posteingang/2026-06-20-fristsetzung-az-2026-001.eml)")


def test_ablage_vorschlag_ohne_datum_ist_luecke_kein_erfundenes_datum():
    vorschlag = executor.baue_ablage_vorschlag(None, "Betreff ohne Datum")
    assert vorschlag["moeglich"] is False
    assert vorschlag["dateiname"] is None
    assert vorschlag["kommunikations_zeile"] is None
    assert "Datum" in vorschlag["hinweis"]


def test_ablage_vorschlag_ungueltiges_datumsformat_ist_luecke():
    vorschlag = executor.baue_ablage_vorschlag("20.06.2026", "Betreff")
    assert vorschlag["moeglich"] is False


def test_ablage_vorschlag_ohne_betreff_nutzt_platzhalter_anzeige():
    vorschlag = executor.baue_ablage_vorschlag("2026-06-20", "")
    assert vorschlag["kommunikations_zeile"].split(" — ")[1] == "(ohne Betreff)"
    assert vorschlag["dateiname"] == "posteingang/2026-06-20-ohne-betreff.eml"
