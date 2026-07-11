"""Tests für core/calc/fristen — Fristen-Rechner (P3/P4).

Deckt ab: Ereignis- vs. Beginnfrist (§ 187 BGB), Fristende für Tages-,
Wochen-, Monats- und Jahresfristen (§ 188 BGB) inkl. Monatsende-Fall
(§ 188 Abs. 3) und Schaltjahr, die Verschiebung nach § 193 BGB /
§ 222 Abs. 2 ZPO (einzeln, als Kaskade, bundeslandabhängig, Buß- und
Bettag nur SN), die ehrliche Doppel-Ausweisung bei teilgebietlichen
Feiertagen, die nachvollziehbare Rechenkette (P3) und die Validierung.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "core" / "calc"))

from fristen import (  # noqa: E402
    FristEingabeFehler,
    berechne_frist,
    fristart_nach_id,
    lade_katalog,
    naechster_werktag,
)


# --------------------------------------------------------------------------
# § 187 BGB — Fristbeginn
# --------------------------------------------------------------------------

def test_ereignisfrist_beginn_am_folgetag():
    r = berechne_frist(dt.date(2026, 6, 1), 10, "tage", bundesland="NW")
    assert r.fristbeginn == dt.date(2026, 6, 2)


def test_beginnfrist_anfangstag_zaehlt_mit():
    r = berechne_frist(dt.date(2026, 6, 1), 10, "tage", "beginn", bundesland="NW")
    assert r.fristbeginn == dt.date(2026, 6, 1)


# --------------------------------------------------------------------------
# § 188 BGB — Fristende (Tage / Wochen / Monate / Jahre)
# --------------------------------------------------------------------------

def test_tagesfrist_ereignis():
    r = berechne_frist(dt.date(2026, 6, 1), 10, "tage", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 6, 11)


def test_tagesfrist_beginn():
    r = berechne_frist(dt.date(2026, 6, 1), 10, "tage", "beginn",
                       bundesland="NW", paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 6, 10)


def test_wochenfrist_endet_am_entsprechenden_wochentag():
    # Zustellung Do 15.01.2026 + 3 Wochen -> Do 05.02.2026
    r = berechne_frist(dt.date(2026, 1, 15), 3, "wochen", bundesland="NW")
    assert r.fristende_rechnerisch == dt.date(2026, 2, 5)
    assert r.fristende_rechnerisch.weekday() == dt.date(2026, 1, 15).weekday()


def test_wochenfrist_beginnfrist():
    # § 188 Abs. 2 Alt. 2: Vortag des dem Anfangstag entsprechenden Tages.
    r = berechne_frist(dt.date(2026, 6, 1), 2, "wochen", "beginn",
                       bundesland="NW", paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 6, 14)


def test_monatsfrist_regulaer():
    r = berechne_frist(dt.date(2026, 3, 10), 1, "monate", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 4, 10)


def test_monatsende_paragraf_188_abs_3():
    # 31.01.2026 + 1 Monat: kein 31.02. -> letzter Tag des Februar (28.02.).
    r = berechne_frist(dt.date(2026, 1, 31), 1, "monate", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 2, 28)
    assert any("§ 188 Abs. 3 BGB" == s.norm for s in r.rechenkette)


def test_monatsende_schaltjahr():
    # 31.01.2024 + 1 Monat -> 29.02.2024 (Schaltjahr!)
    r = berechne_frist(dt.date(2024, 1, 31), 1, "monate", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2024, 2, 29)


def test_jahresfrist_schalttag():
    # 29.02.2024 + 1 Jahr: kein 29.02.2025 -> 28.02.2025 (§ 188 Abs. 3).
    r = berechne_frist(dt.date(2024, 2, 29), 1, "jahre", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2025, 2, 28)
    assert any("§ 188 Abs. 3 BGB" == s.norm for s in r.rechenkette)


def test_beginnfrist_monatsueberlauf_endet_mit_monatsletztem():
    # Beginnfrist 1 Monat ab 31.03.2026: April hat keinen 31. ->
    # Ablauf mit dem letzten Tag des Monats (30.04.), NICHT 29.04.
    r = berechne_frist(dt.date(2026, 3, 31), 1, "monate", "beginn",
                       bundesland="NW", paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 4, 30)


def test_silvester_ist_werktag():
    # 31.12.2026 ist ein Donnerstag und kein gesetzlicher Feiertag -> bleibt.
    r = berechne_frist(dt.date(2026, 12, 21), 10, "tage", bundesland="NW")
    assert r.fristende == dt.date(2026, 12, 31)
    assert not r.verschoben


def test_neujahr_verschiebt():
    # Fristende 01.01.2027 (Freitag, Neujahr) -> Montag 04.01.2027.
    r = berechne_frist(dt.date(2026, 12, 22), 10, "tage", bundesland="NW")
    assert r.fristende_rechnerisch == dt.date(2027, 1, 1)
    assert r.fristende == dt.date(2027, 1, 4)
    assert len(r.verschiebungen) == 3   # Fr (Feiertag), Sa, So


# --------------------------------------------------------------------------
# § 193 BGB / § 222 Abs. 2 ZPO — Verschiebung
# --------------------------------------------------------------------------

def test_verschiebung_sonntag():
    # 1 Monat ab 15.01.2026 -> 15.02.2026 (So) -> 16.02.2026 (Mo).
    r = berechne_frist(dt.date(2026, 1, 15), 1, "monate", bundesland="NW")
    assert r.fristende_rechnerisch == dt.date(2026, 2, 15)
    assert r.fristende == dt.date(2026, 2, 16)
    assert r.verschoben
    assert r.verschiebungen[0].grund == "Sonntag"


def test_feiertagskaskade_karfreitag_bis_dienstag():
    # 2 Wochen ab Fr 20.03.2026 -> Karfreitag 03.04. -> Sa -> So ->
    # Ostermontag -> Di 07.04.2026. Jede Station einzeln ausgewiesen.
    r = berechne_frist(dt.date(2026, 3, 20), 2, "wochen", bundesland="NW")
    assert r.fristende_rechnerisch == dt.date(2026, 4, 3)
    assert r.fristende == dt.date(2026, 4, 7)
    gruende = [v.grund for v in r.verschiebungen]
    assert len(gruende) == 4
    assert "Karfreitag" in gruende[0]
    assert "Sonnabend" in gruende[1]
    assert gruende[2] == "Sonntag"
    assert "Ostermontag" in gruende[3]
    for v in r.verschiebungen:
        assert v.norm == "§ 193 BGB / § 222 Abs. 2 ZPO"


def test_samstag_und_feiertag_zugleich():
    # 03.10.2026 ist Samstag UND Tag der Deutschen Einheit — beide Gründe.
    r = berechne_frist(dt.date(2026, 10, 1), 2, "tage", bundesland="NW")
    assert r.fristende_rechnerisch == dt.date(2026, 10, 3)
    assert r.fristende == dt.date(2026, 10, 5)
    assert "Sonnabend" in r.verschiebungen[0].grund
    assert "Tag der Deutschen Einheit" in r.verschiebungen[0].grund


def test_feiertag_bundeslandabhaengig():
    # Fristende 06.01.2026 (Di): Heilige Drei Könige in BY, nicht in BE.
    r_by = berechne_frist(dt.date(2026, 1, 1), 5, "tage", bundesland="BY")
    r_be = berechne_frist(dt.date(2026, 1, 1), 5, "tage", bundesland="BE")
    assert r_by.fristende_rechnerisch == dt.date(2026, 1, 6)
    assert r_by.fristende == dt.date(2026, 1, 7) and r_by.verschoben
    assert r_be.fristende == dt.date(2026, 1, 6) and not r_be.verschoben


def test_buss_und_bettag_nur_sachsen():
    # Fristende 18.11.2026 (Mi, Buß- und Bettag): nur in SN verschoben.
    r_sn = berechne_frist(dt.date(2026, 11, 16), 2, "tage", bundesland="SN")
    r_by = berechne_frist(dt.date(2026, 11, 16), 2, "tage", bundesland="BY")
    assert r_sn.fristende_rechnerisch == dt.date(2026, 11, 18)
    assert r_sn.fristende == dt.date(2026, 11, 19) and r_sn.verschoben
    assert r_by.fristende == dt.date(2026, 11, 18) and not r_by.verschoben


def test_paragraf_193_abschaltbar():
    r = berechne_frist(dt.date(2026, 1, 31), 1, "monate", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 2, 28)   # Samstag, bleibt
    assert not r.verschoben


# --------------------------------------------------------------------------
# Teilgebietliche Feiertage — beide Enden, nie stillschweigend
# --------------------------------------------------------------------------

def test_teilgebietlich_beide_enden_bayern():
    # Ende 15.08.2025 (Fr) = Mariä Himmelfahrt, in BY nur teilgebietlich.
    r = berechne_frist(dt.date(2025, 8, 1), 2, "wochen", bundesland="BY")
    assert r.fristende == dt.date(2025, 8, 15)                      # landesweit
    assert r.fristende_bei_teilgebietlichem_feiertag == dt.date(2025, 8, 18)
    assert any("Mariä Himmelfahrt" in w for w in r.warnungen)
    assert any("teilgebietlich" in s.norm for s in r.rechenkette)


def test_teilgebietlich_saarland_landesweit_kein_doppel():
    # In SL ist Mariä Himmelfahrt landesweit -> normale Verschiebung, kein
    # Alternativ-Ende.
    r = berechne_frist(dt.date(2025, 8, 1), 2, "wochen", bundesland="SL")
    assert r.fristende == dt.date(2025, 8, 18)
    assert r.fristende_bei_teilgebietlichem_feiertag is None


def test_teilgebietlich_unbeteiligtes_land_keine_warnung():
    r = berechne_frist(dt.date(2025, 8, 1), 2, "wochen", bundesland="BW")
    assert r.fristende == dt.date(2025, 8, 15)
    assert r.fristende_bei_teilgebietlichem_feiertag is None
    assert not any("teilgebietlich" in w.lower() for w in r.warnungen)


def test_teilgebietlich_irrelevant_wenn_fern():
    # Frist im Januar in BY: kein teilgebietlicher Feiertag betroffen.
    r = berechne_frist(dt.date(2026, 1, 7), 1, "wochen", bundesland="BY")
    assert r.fristende_bei_teilgebietlichem_feiertag is None
    assert not r.warnungen


# --------------------------------------------------------------------------
# Rechenkette (P3)
# --------------------------------------------------------------------------

def test_rechenkette_nachvollziehbar_und_markiert():
    r = berechne_frist(dt.date(2026, 1, 15), 1, "monate", bundesland="NW")
    assert [s.schritt for s in r.rechenkette] == list(range(1, len(r.rechenkette) + 1))
    for s in r.rechenkette:
        assert s.quelle == "executor"
        assert s.norm.startswith("§")
    # Fristbeginn und rechnerisches Ende tauchen als Zwischenergebnisse auf:
    ergebnisse = [s.ergebnis for s in r.rechenkette]
    assert r.fristbeginn.isoformat() in ergebnisse
    assert r.fristende_rechnerisch.isoformat() in ergebnisse
    assert r.fristende.isoformat() in ergebnisse


def test_as_dict_serialisierbar():
    import json
    r = berechne_frist(dt.date(2025, 8, 1), 2, "wochen", bundesland="BY")
    d = r.as_dict()
    json.dumps(d)   # darf nicht werfen
    assert d["quelle"] == "executor"
    assert d["fristende"] == "2025-08-15"
    assert d["fristende_bei_teilgebietlichem_feiertag"] == "2025-08-18"


# --------------------------------------------------------------------------
# Katalog & Hilfsfunktionen
# --------------------------------------------------------------------------

def test_katalog_konsistent():
    katalog = lade_katalog()
    ids = [f["id"] for f in katalog["fristarten"]]
    assert len(ids) == len(set(ids))
    for f in katalog["fristarten"]:
        for feld in ("id", "bezeichnung", "norm", "dauer", "einheit",
                     "fristtyp", "ausloeser", "notfrist", "verlaengerbar"):
            assert feld in f, (f["id"], feld)
        assert f["einheit"] in ("tage", "wochen", "monate", "jahre")
        assert isinstance(f["dauer"], int) and f["dauer"] >= 1
    # Die im Auftrag geforderten Fristarten sind alle da:
    for pflicht in ("berufung", "berufungsbegruendung",
                    "einspruch_versaeumnisurteil", "widerspruch_mahnbescheid",
                    "revision", "revisionsbegruendung", "anhoerungsruege",
                    "wiedereinsetzung"):
        assert pflicht in ids, pflicht


def test_fristbeginn_wird_nicht_verschoben():
    # Befund 7a: § 193 BGB gilt nur für das FristENDE — ein Fristbeginn auf
    # Sonntag oder Feiertag bleibt unverändert.
    r = berechne_frist(dt.date(2026, 1, 3), 1, "wochen", bundesland="NW")
    assert r.fristbeginn == dt.date(2026, 1, 4)          # Sonntag, bleibt
    assert r.fristende_rechnerisch == dt.date(2026, 1, 10)
    assert r.fristende == dt.date(2026, 1, 12)           # nur das Ende wandert
    r2 = berechne_frist(dt.date(2026, 12, 31), 5, "tage", bundesland="NW")
    assert r2.fristbeginn == dt.date(2027, 1, 1)         # Neujahr, bleibt


def test_bereichsgrenzen_sauberer_eingabefehler():
    # Befund 1 / 7c: Datumsbereich-Überschreitungen sind Eingabefehler
    # (FristEingabeFehler), nie nackte ValueError/OverflowError-Tracebacks.
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(1500, 1, 15), 1, "monate", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(4099, 12, 15), 1, "monate", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 15), 2100, "jahre", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 15), 100_000_000_000, "tage",
                       bundesland="NW")
    # Innerhalb der Grenzen rechnet er normal:
    r = berechne_frist(dt.date(1583, 1, 15), 1, "monate", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(1583, 2, 15)


def test_fristart_nach_id_unbekannt():
    with pytest.raises(FristEingabeFehler):
        fristart_nach_id("gibt_es_nicht")


def test_widerspruch_mahnbescheid_gekennzeichnet():
    f = fristart_nach_id("widerspruch_mahnbescheid")
    assert f.get("kein_technisches_fristende") is True


def test_naechster_werktag():
    assert naechster_werktag(dt.date(2026, 1, 3), "NW") == dt.date(2026, 1, 5)
    assert naechster_werktag(dt.date(2026, 1, 5), "NW") == dt.date(2026, 1, 5)


# --------------------------------------------------------------------------
# Validierung
# --------------------------------------------------------------------------

def test_ungueltige_eingaben():
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 1), 0, "tage", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 1), 1, "stunden", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 1), 1, "tage", "sofort", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 1), 1, "tage", bundesland="Bayern")
