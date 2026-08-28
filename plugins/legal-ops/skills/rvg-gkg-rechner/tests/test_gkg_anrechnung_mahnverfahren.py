"""Tests für die GKG-Anrechnung KV 1100 -> KV 1210 (Mahnbescheid ->
Widerspruch -> streitiges Verfahren) und für die strikte Key-Validierung der
Eingabeblöcke `rvg`/`gkg` im Executor.

Norm: Anmerkung Abs. 1 zu KV 1210 GKG (Anlage 1 GKG, Teil 1 Hauptabschnitt 2
Abschnitt 1 Unterabschnitt 1) — "… in diesem Fall wird eine Gebühr 1100 nach
dem Wert des Streitgegenstands angerechnet, der in das Prozessverfahren
übergegangen ist." Es ist eine ANRECHNUNG, keine Ermäßigung: der Satz 3,0 von
KV 1210 bleibt unverändert, abgezogen wird der Betrag der Gebühr KV 1100.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
import subprocess

import pytest

from conftest import CALC, lauf, report, schreibe  # noqa: E402

from gkg.rechner import GKGEingabeFehler, berechne  # noqa: E402

EXECUTOR = CALC / "rvg" / "executor.py"

STICHTAG_NEU = dt.date(2026, 1, 1)   # KostBRÄG 2025


def _lauf(eingabe, tmp_path: Path) -> subprocess.CompletedProcess:
    return lauf(EXECUTOR, "--input", schreibe(tmp_path / "anfrage.json", eingabe))


# --------------------------------------------------------------------------
# Anrechnung KV 1100 auf KV 1210
# --------------------------------------------------------------------------

def test_anrechnung_mahnverfahren_auf_streitverfahren():
    """Rechenweg (Streitwert 10.000 €, KostBRÄG 2025):
      1,0-Gebühr                       = 283,00 €
      KV 1100 (0,5 x 283,00)           = 141,50 €  (über dem Mindestbetrag 38 €)
      KV 1210 (3,0 x 283,00)           = 849,00 €
      Anrechnung KV 1100 auf KV 1210   = 849,00 - 141,50 = 707,50 €
      Gesamt                           = 141,50 + 707,50 = 849,00 €
    Wirtschaftlich bleibt bei vollständigem Übergang genau die 3,0-Gebühr
    stehen — die bereits gezahlte Mahnverfahrensgebühr wird angerechnet.
    """
    r = berechne("10000", STICHTAG_NEU, [{"nr": "1100"}, {"nr": "1210"}],
                 anrechnung_1100_auf_1210=True)
    assert r.einfachgebuehr == Decimal("283.00")
    betraege = {p.nr: p.betrag for p in r.positionen}
    assert betraege["1100"] == Decimal("141.50")
    assert betraege["1210"] == Decimal("707.50")
    assert r.gesamt == Decimal("849.00")

    # Satz von KV 1210 unverändert 3,0 — Anrechnung, keine Ermäßigung.
    satz_1210 = {p.nr: p.satz for p in r.positionen}["1210"]
    assert satz_1210 == Decimal("3.0")

    assert r.anrechnung is not None
    assert r.anrechnung["norm"] == "Anmerkung Abs. 1 zu KV 1210 GKG"
    assert r.anrechnung["anrechnungsbetrag"] == "141.50"
    assert r.anrechnung["gebuehr_1210_vor_anrechnung"] == "849.00"
    assert r.anrechnung["gebuehr_1210_nach_anrechnung"] == "707.50"

    # Rechenkette weist den Schritt mit Norm-Zitat aus (P3-Nachvollziehbarkeit).
    normen = [s.norm for s in r.rechenkette]
    assert "Anmerkung Abs. 1 zu KV 1210 GKG" in normen


def test_anrechnung_mit_greifendem_mindestbetrag_kv1100():
    """Kleiner Streitwert, Mindestbetrags-Floor bei KV 1100 greift.
    Rechenweg (Streitwert 797,84 €, Stichtag 05.07.2025 -> KostBRÄG 2025):
      1,0-Gebühr                       =  61,00 €
      KV 1100 (0,5 x 61,00 = 30,50 €)  ->  38,00 €  (Mindestbetrag KV 1100)
      KV 1210 (3,0 x 61,00)            = 183,00 €
      Anrechnung                       = 183,00 - 38,00 = 145,00 €
      Gesamt                           =  38,00 + 145,00 = 183,00 €
    Angerechnet wird der Betrag der Gebühr 1100 — also der auf den
    Mindestbetrag angehobene (38,00 €), nicht die rechnerischen 30,50 €.
    """
    r = berechne("797.84", dt.date(2025, 7, 5),
                 [{"nr": "1100"}, {"nr": "1210"}], anrechnung_1100_auf_1210=True)
    assert r.einfachgebuehr == Decimal("61.00")
    betraege = {p.nr: p.betrag for p in r.positionen}
    assert betraege["1100"] == Decimal("38.00")
    assert betraege["1210"] == Decimal("145.00")
    assert r.gesamt == Decimal("183.00")
    assert r.anrechnung["anrechnungsbetrag"] == "38.00"


@pytest.mark.parametrize("stichtag, einfach, kv1100", [
    (dt.date(2022, 1, 1), Decimal("38.00"), Decimal("36.00")),   # KostRÄG 2021
    (dt.date(2025, 7, 5), Decimal("40.00"), Decimal("38.00")),   # KostBRÄG 2025
])
def test_anrechnung_bleibt_am_kleinsten_streitwert_positiv(stichtag, einfach, kv1100):
    """Untere Grenze beider Tabellenstände: selbst wenn der Mindestbetrag von
    KV 1100 voll greift, liegt KV 1210 (3,0) deutlich darüber — die Anrechnung
    kann nie negativ werden. Der Test hält diese Invariante fest (deshalb hat
    `gkg/rechner.py` keinen Negativ-Zweig) und schlägt fehl, falls ein
    künftiger Tabellen-/Katalogstand den Floor über die 3,0-Gebühr hebt."""
    r = berechne("0.01", stichtag, [{"nr": "1100"}, {"nr": "1210"}],
                 anrechnung_1100_auf_1210=True)
    assert r.einfachgebuehr == einfach
    betraege = {p.nr: p.betrag for p in r.positionen}
    assert betraege["1100"] == kv1100                 # Mindestbetrag greift
    assert betraege["1210"] == 3 * einfach - kv1100
    assert betraege["1210"] > 0
    assert r.gesamt == 3 * einfach


def test_ohne_anrechnung_unveraendertes_verhalten():
    """Grenzfall: dieselben Positionen ohne angeforderte Anrechnung rechnen
    unverändert wie bisher (141,50 + 849,00 = 990,50 €)."""
    r = berechne("10000", STICHTAG_NEU, [{"nr": "1100"}, {"nr": "1210"}])
    assert {p.nr: p.betrag for p in r.positionen} == {
        "1100": Decimal("141.50"), "1210": Decimal("849.00")}
    assert r.gesamt == Decimal("990.50")
    assert r.anrechnung is None
    assert all(s.norm != "Anmerkung Abs. 1 zu KV 1210 GKG" for s in r.rechenkette)


def test_kein_mahnverfahren_kein_streitverfahren_wird_abgelehnt():
    """Anrechnung ohne KV 1100 bzw. ohne KV 1210 ist ein Eingabefehler —
    kein stilles Weiterrechnen."""
    with pytest.raises(GKGEingabeFehler, match="fehlt: KV 1100"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1210"}],
                 anrechnung_1100_auf_1210=True)
    with pytest.raises(GKGEingabeFehler, match="fehlt: KV 1210"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1100"}],
                 anrechnung_1100_auf_1210=True)


def test_ermaessigung_1211_ist_nicht_erfasst():
    """KV 1211 (Ermäßigung) ist von der Anmerkung zu KV 1210 nicht erfasst —
    gezielter Hinweis statt Rechnen auf gut Glück."""
    with pytest.raises(GKGEingabeFehler, match="KV 1211 ist von dieser Mechanik"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1100"}, {"nr": "1211"}],
                 anrechnung_1100_auf_1210=True)


def test_anrechnung_flag_muss_boolean_sein():
    with pytest.raises(GKGEingabeFehler, match="JSON-Boolean"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1100"}, {"nr": "1210"}],
                 anrechnung_1100_auf_1210="ja")


def test_anrechnung_ueber_cli(tmp_path):
    """Ende-zu-Ende über den Executor: Report trägt den `anrechnung`-Block."""
    r = report(EXECUTOR, "--input", schreibe(tmp_path / "a.json", {
        "gkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                "streitwert": "10000",
                "positionen": [{"nr": "1100"}, {"nr": "1210"}],
                "anrechnung_1100_auf_1210": True}}))
    assert r["gkg"]["ergebnis"]["gesamt"] == "849.00"
    assert r["gkg"]["anrechnung"]["gebuehr_1210_nach_anrechnung"] == "707.50"
    assert r["gkg"]["eingabe"]["anrechnung_1100_auf_1210"] is True


def test_gkg_anrechnung_default_false_im_report(tmp_path):
    r = report(EXECUTOR, "--input", schreibe(tmp_path / "a.json", {
        "gkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                "streitwert": "10000", "positionen": [{"nr": "1210"}]}}))
    assert r["gkg"]["anrechnung"] is None
    assert r["gkg"]["eingabe"]["anrechnung_1100_auf_1210"] is False


# --------------------------------------------------------------------------
# Strikte Key-Validierung der Eingabeblöcke (Geldpfad: kein stilles Ignorieren)
# --------------------------------------------------------------------------

def test_unbekannter_key_im_gkg_block(tmp_path):
    ergebnis = _lauf({"gkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "positionen": [{"nr": "1210"}],
                              "anrechnung_1100_1210": True}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld im Block 'gkg'" in ergebnis.stderr
    assert "anrechnung_1100_1210" in ergebnis.stderr


def test_unbekannter_key_im_rvg_block(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "tatbestaende": [{"nr": "3100"}],
                              "anrechnung_2300_auf_3200": True}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld im Block 'rvg'" in ergebnis.stderr
    assert "anrechnung_2300_auf_3200" in ergebnis.stderr
