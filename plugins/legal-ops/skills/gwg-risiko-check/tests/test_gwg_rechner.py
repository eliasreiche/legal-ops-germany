"""Tests für core/calc/gwg/rechner.py — regelbasierte GwG-Klassifikation (P4).

Deckt die fünf Klassifikationspfade (nicht_verpflichtet, unvollstaendig,
niedrig, mittel, hoch/PEP, hoch/Hochrisiko-Drittstaat), die Katalog-Integrität
(Fragebogen-Felder, Fundstellen-Format, Stand), den Determinismus und die
Vorbehalts-Kennzeichnung bei Länder-Treffern ab.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from gwg import rechner  # noqa: E402
from gwg.rechner import (  # noqa: E402
    FRAGEBOGEN_FELDER,
    KLASSIFIKATIONEN,
    GwGEingabeFehler,
    frische_status,
    klassifiziere,
    lade_kataloge,
)

SCHEMA = Path(__file__).resolve().parents[1] / "schema"

# Ein vollständig ausgefülltes, unauffälliges Basis-Mandat (verpflichtet, alle
# kritischen Felder belastbar, keine Anlage-2-Faktoren). Einzelne Tests
# variieren gezielt.
BASIS = {
    "kataloggeschaeft": "vermoegensverwaltung",
    "mandant_typ": "juristische_person",
    "sitz_land": "DE",
    "pep": "nein",
    "wirtschaftlich_berechtigter_geklaert": "ja",
    "bargeldintensiv": "nein",
    "komplexe_eigentumsstruktur": "nein",
    "distanzgeschaeft": "nein",
    "herkunft_der_mittel_klar": "ja",
    "boersennotiert_reguliert": "nein",
    "oeffentliche_stelle": "nein",
    "nominee_inhaberaktien": "nein",
    "private_vermoegensstruktur": "nein",
    "anonymitaets_produkt": "nein",
    "zahlung_unbekannte_dritte": "nein",
}


def _m(**overrides):
    m = copy.deepcopy(BASIS)
    m.update(overrides)
    return m


# --------------------------------------------------------------------------
# Die fünf/​sechs Klassifikationspfade
# --------------------------------------------------------------------------

def test_nicht_verpflichtet():
    r = klassifiziere(_m(kataloggeschaeft="keins"))
    assert r["klassifikationsvorschlag"] == "nicht_verpflichtet"
    assert r["anwendbarkeit"]["status"] == "nicht_verpflichtet"
    assert "vorbehalt" in r["anwendbarkeit"]
    assert r["angewandte_faktoren"] == []


def test_unvollstaendig_kritische_luecke_pep():
    r = klassifiziere(_m(pep="unklar"))
    assert r["klassifikationsvorschlag"] == "unvollstaendig"
    assert r["anwendbarkeit"]["status"] == "verpflichtet"
    assert any(l["feld"] == "pep" and l["kritisch"] for l in r["luecken"])


def test_unvollstaendig_wb_nicht_geklaert():
    r = klassifiziere(_m(wirtschaftlich_berechtigter_geklaert="nein"))
    assert r["klassifikationsvorschlag"] == "unvollstaendig"
    assert any(l["feld"] == "wirtschaftlich_berechtigter_geklaert"
               and l["kritisch"] for l in r["luecken"])


def test_unvollstaendig_kataloggeschaeft_unklar():
    r = klassifiziere(_m(kataloggeschaeft="unklar"))
    assert r["klassifikationsvorschlag"] == "unvollstaendig"
    assert r["anwendbarkeit"]["status"] == "unklar"


def test_niedrig_nur_anlage1():
    # boersennotiert (Anlage 1) + EU-Sitz (Anlage 1), kein Anlage-2-Faktor.
    r = klassifiziere(_m(boersennotiert_reguliert="ja"))
    assert r["klassifikationsvorschlag"] == "niedrig"
    assert any(f["anlage"] == 1 for f in r["angewandte_faktoren"])
    assert not any(f.get("anlage") == 2 for f in r["angewandte_faktoren"])
    assert any(p["norm"] == "§ 14 GwG" for p in r["pflichten_hinweise"])


def test_mittel_anlage2_ohne_paragraph15():
    r = klassifiziere(_m(bargeldintensiv="ja"))
    assert r["klassifikationsvorschlag"] == "mittel"
    assert any(f.get("anlage") == 2 for f in r["angewandte_faktoren"])
    assert any(p["norm"] == "§ 10 GwG" for p in r["pflichten_hinweise"])


def test_hoch_pep():
    r = klassifiziere(_m(pep="ja"))
    assert r["klassifikationsvorschlag"] == "hoch"
    assert any(f["fundstelle"] == "§ 15 Abs. 3 Nr. 1 GwG"
               for f in r["angewandte_faktoren"])
    assert any(p["norm"] == "§ 15 GwG" for p in r["pflichten_hinweise"])


def test_hoch_hochrisiko_drittstaat():
    # Iran: EU-Hochrisiko + FATF-Schwarzliste -> gesetzlicher Trigger.
    r = klassifiziere(_m(sitz_land="IR"))
    assert r["klassifikationsvorschlag"] == "hoch"
    geo = [f for f in r["angewandte_faktoren"]
           if f["fundstelle"] == "Anlage 2 Nr. 3 Buchst. a GwG"]
    assert len(geo) == 1
    # Vorbehalts-Kennzeichnung beim Länder-Treffer (im Faktor-Detail).
    assert "ändern sich laufend" in geo[0]["detail"]
    treffer = r["laender_listen_treffer"]
    assert treffer["iso2"] == "IR"
    assert set(treffer["listen"]) == {"eu-hochrisiko", "fatf-blacklist"}
    # BaFin-Allgemeinverfügung-Hinweis nur für KP/IR.
    assert any("BaFin-Allgemeinverfügung" in p["norm"]
               for p in r["pflichten_hinweise"])


def test_pep_und_land_gleichzeitig_bleibt_hoch():
    r = klassifiziere(_m(pep="ja", sitz_land="IR"))
    assert r["klassifikationsvorschlag"] == "hoch"


# --------------------------------------------------------------------------
# Vorbehalts-Kennzeichnung bei Länder-Treffern
# --------------------------------------------------------------------------

def test_laender_vorbehalt_immer_bei_bekanntem_sitzland():
    # Auch ohne Treffer wird die Länder-Konsultation als Vorbehalt vermerkt.
    r = klassifiziere(_m(sitz_land="DE"))
    assert any("Länder-Einordnung" in v for v in r["vorbehalte"])


def test_grundvorbehalte_immer_vorhanden():
    r = klassifiziere(_m())
    assert any("risikobasierter Ansatz" in v for v in r["vorbehalte"])
    assert any("nicht gegen den Gesetzestext geprüft" in v for v in r["vorbehalte"])


# --------------------------------------------------------------------------
# 3-Zustands-Marker auf jeder Fundstelle
# --------------------------------------------------------------------------

def test_jede_fundstelle_traegt_marker():
    r = klassifiziere(_m(bargeldintensiv="ja", boersennotiert_reguliert="ja"))
    for f in r["angewandte_faktoren"]:
        assert f["marker"] == "⚠️"
        assert f["marker_begruendung"]
    for p in r["pflichten_hinweise"]:
        assert p["marker"] == "⚠️"
    assert r["anwendbarkeit"]["marker"] == "⚠️"


def test_klassifikation_ist_gueltiger_wert():
    for kg in ("keins", "unklar", "vermoegensverwaltung"):
        r = klassifiziere(_m(kataloggeschaeft=kg))
        assert r["klassifikationsvorschlag"] in KLASSIFIKATIONEN


# --------------------------------------------------------------------------
# Katalog-Integrität
# --------------------------------------------------------------------------

def test_katalog_fragebogen_felder_existieren_im_schema():
    anlage1, anlage2, _ = lade_kataloge()
    beispiel = json.loads((SCHEMA / "beispiel-mandat.json").read_text("utf-8"))
    for katalog in (anlage1, anlage2):
        for fk in katalog["faktoren"]:
            feld = fk["fragebogen_feld"]
            assert feld in FRAGEBOGEN_FELDER, feld
            assert feld in beispiel, f"{feld} fehlt in beispiel-mandat.json"


def test_katalog_fundstellen_format():
    anlage1, anlage2, _ = lade_kataloge()
    muster = re.compile(r"^Anlage [12] Nr\. \d+ Buchst\. [a-z] GwG$")
    for katalog in (anlage1, anlage2):
        for fk in katalog["faktoren"]:
            assert muster.match(fk["fundstelle"]), fk["fundstelle"]
            assert fk["paraphrase"].strip()
            assert fk["kategorie"] in (
                "kundenrisiko", "produkt-transaktionsrisiko", "geografisch")


def test_katalog_stand_vorhanden():
    anlage1, anlage2, hochrisiko = lade_kataloge()
    for datei in (anlage1, anlage2, hochrisiko):
        assert datei.get("stand"), "stand-Feld fehlt"
        assert datei.get("pruefhinweis") or datei.get("vorbehalt")


def test_hochrisiko_liste_hat_vorbehalt_und_iso():
    _, _, hochrisiko = lade_kataloge()
    assert "ändern sich laufend" in hochrisiko["vorbehalt"]
    zulaessige_listen = {"eu-hochrisiko", "fatf-blacklist", "fatf-greylist"}
    for eintrag in hochrisiko["laender"]:
        assert re.match(r"^[A-Z]{2}$", eintrag["iso2"]), eintrag
        assert eintrag["land"].strip()
        assert eintrag["listen"], eintrag
        assert set(eintrag["listen"]) <= zulaessige_listen, eintrag


# --------------------------------------------------------------------------
# Listen-Treffer-Logik (Aufgabe: Länderliste verifiziert, 3 Listen)
# --------------------------------------------------------------------------

def test_listen_konsistenz_gegen_vorgabe():
    """JSON enthält exakt die vorgegebenen Länder je Liste (Anzahl +
    Stichproben) — verifizierte Daten vom 2026-07-13."""
    _, _, hochrisiko = lade_kataloge()
    laender = {e["iso2"]: set(e["listen"]) for e in hochrisiko["laender"]}

    eu_only = {"AF", "DZ", "NA", "TT", "VU", "RU"}
    eu_und_schwarz = {"IR", "KP", "MM"}
    eu_und_grau = {"AO", "BO", "VG", "CM", "CI", "CD", "HT", "KE", "LA", "LB",
                   "MC", "NP", "SS", "SY", "VE", "VN", "YE"}
    nur_grau = {"BA", "BG", "IQ", "KW", "PG"}

    assert len(laender) == 31
    for iso in eu_only:
        assert laender[iso] == {"eu-hochrisiko"}, iso
    for iso in eu_und_schwarz:
        assert laender[iso] == {"eu-hochrisiko", "fatf-blacklist"}, iso
    for iso in eu_und_grau:
        assert laender[iso] == {"eu-hochrisiko", "fatf-greylist"}, iso
    for iso in nur_grau:
        assert laender[iso] == {"fatf-greylist"}, iso

    alle_eu = eu_only | eu_und_schwarz | eu_und_grau
    assert len(alle_eu) == 26  # 23 (Abschnitt I) + 1 + 1 + 1
    eu_abschnitte = hochrisiko["eu_abschnitte"]
    assert len(eu_abschnitte["I"]) == 23
    assert eu_abschnitte["II"] == ["IR"]
    assert eu_abschnitte["III"] == ["KP"]
    assert eu_abschnitte["IV"] == ["RU"]


def test_eu_treffer_pro_liste_hoch():
    # (a) je Liste ein Beispiel-Land -> hoch + korrekte Listen-Ausweisung.
    r = klassifiziere(_m(sitz_land="DZ"))  # nur EU
    assert r["klassifikationsvorschlag"] == "hoch"
    assert r["laender_listen_treffer"]["listen"] == ["eu-hochrisiko"]
    assert any(f["fundstelle"] == "Anlage 2 Nr. 3 Buchst. a GwG"
               for f in r["angewandte_faktoren"])


def test_fatf_schwarzliste_treffer_hoch():
    r = klassifiziere(_m(sitz_land="KP"))  # EU + FATF-schwarz
    assert r["klassifikationsvorschlag"] == "hoch"
    assert set(r["laender_listen_treffer"]["listen"]) == {
        "eu-hochrisiko", "fatf-blacklist"}
    assert any("BaFin-Allgemeinverfügung" in p["norm"]
               for p in r["pflichten_hinweise"])


def test_fatf_grauliste_mit_eu_treffer_hoch():
    r = klassifiziere(_m(sitz_land="AO"))  # EU + FATF-grau
    assert r["klassifikationsvorschlag"] == "hoch"
    assert set(r["laender_listen_treffer"]["listen"]) == {
        "eu-hochrisiko", "fatf-greylist"}


def test_nur_fatf_grau_hoch_als_hauseinstufung():
    # (b) nur-FATF-grau-Land (Kuwait) -> hoch, aber als konservative
    # Haus-Einstufung ohne Gesetzespflicht, nicht als § 15-Zitat.
    r = klassifiziere(_m(sitz_land="KW"))
    assert r["klassifikationsvorschlag"] == "hoch"
    treffer = r["laender_listen_treffer"]
    assert treffer["listen"] == ["fatf-greylist"]
    # Kein statutorischer Anlage-2-Faktor für einen reinen Grauliste-Treffer.
    assert not any(f["fundstelle"] == "Anlage 2 Nr. 3 Buchst. a GwG"
                   for f in r["angewandte_faktoren"])
    haus_faktor = [f for f in r["angewandte_faktoren"]
                   if f["id"] == "haus_fatf_listen_treffer"]
    assert len(haus_faktor) == 1
    assert haus_faktor[0]["anlage"] is None
    hinweis = [p for p in r["pflichten_hinweise"]
               if p["norm"] == "Hausrichtlinie (keine GwG-Norm)"]
    assert len(hinweis) == 1
    assert "konservative Haus-Einstufung" in hinweis[0]["hinweis"]
    assert "KEINE unmittelbare Gesetzespflicht" in hinweis[0]["hinweis"]
    assert not any(p["norm"] == "§ 15 GwG" for p in r["pflichten_hinweise"])


def test_bulgarien_eu_mitgliedstaat_sonderfall():
    # Bulgarien: nur FATF-grau, aber EU-Mitgliedstaat -> Sonderhinweis im
    # Begründungstext (kann begrifflich kein Drittstaat sein).
    r = klassifiziere(_m(sitz_land="BG"))
    assert r["klassifikationsvorschlag"] == "hoch"
    assert any("EU-Mitgliedstaat" in v and "Drittstaat" in v
               for v in r["vorbehalte"])


def test_kein_listen_treffer_fuer_nicht_gelistetes_land():
    # (c) Nicht-Listen-Land (Frankreich) -> kein Hochrisiko-Treffer.
    r = klassifiziere(_m(sitz_land="FR"))
    assert r["laender_listen_treffer"] is None
    assert not any(f["id"] == "a2_g_hochrisiko_drittstaat"
                   for f in r["angewandte_faktoren"])
    assert not any(f["id"] == "haus_fatf_listen_treffer"
                   for f in r["angewandte_faktoren"])


# --------------------------------------------------------------------------
# Determinismus
# --------------------------------------------------------------------------

def test_determinismus_identischer_report():
    m = _m(bargeldintensiv="ja", sitz_land="IR", pep="nein")
    r1 = klassifiziere(m)
    r2 = klassifiziere(copy.deepcopy(m))
    assert json.dumps(r1, sort_keys=True, ensure_ascii=False) == \
        json.dumps(r2, sort_keys=True, ensure_ascii=False)


# --------------------------------------------------------------------------
# Eingabefehler
# --------------------------------------------------------------------------

def test_unbekanntes_feld_fehler():
    with pytest.raises(GwGEingabeFehler):
        klassifiziere({"kataloggeschaeft": "keins", "unsinn": "x"})


def test_unzulaessiger_wert_fehler():
    with pytest.raises(GwGEingabeFehler):
        klassifiziere(_m(pep="vielleicht"))


def test_ungueltiges_sitzland_fehler():
    with pytest.raises(GwGEingabeFehler):
        klassifiziere(_m(sitz_land="Deutschland"))


def test_fehlende_felder_werden_unklar():
    # Nur Kataloggeschäft gesetzt — alle anderen Felder unklar, kritische
    # Lücken -> unvollstaendig, nichts wird geraten.
    r = klassifiziere({"kataloggeschaeft": "vermoegensverwaltung"})
    assert r["klassifikationsvorschlag"] == "unvollstaendig"
    assert r["eingabe_normalisiert"]["pep"] == "unklar"


# --------------------------------------------------------------------------
# CI-Frische-Warnung (Aufgabe 3): abgerufen_am der Hochrisiko-Länderliste.
# (d) Frische-Logik über Monkeypatch des Datums, nicht der echten Systemzeit.
# --------------------------------------------------------------------------

def test_frische_frisch_kein_warnung():
    hr = {"abgerufen_am": "2026-07-13"}
    status = frische_status(hr, heute=date(2026, 7, 13))
    assert status["warnung"] is False
    assert status["fehler"] is False


def test_frische_warnung_ab_4_monaten():
    hr = {"abgerufen_am": "2026-01-01"}
    status = frische_status(hr, heute=date(2026, 7, 13))  # ~6,3 Monate
    assert status["warnung"] is True
    assert status["fehler"] is False


def test_frische_kein_warnung_knapp_unter_4_monaten():
    hr = {"abgerufen_am": "2026-05-01"}
    status = frische_status(hr, heute=date(2026, 7, 13))  # ~2,4 Monate
    assert status["warnung"] is False


def test_frische_fehler_ab_12_monaten():
    hr = {"abgerufen_am": "2025-06-01"}
    status = frische_status(hr, heute=date(2026, 7, 13))  # ~13,5 Monate
    assert status["warnung"] is True
    assert status["fehler"] is True


def test_frische_fehlendes_datum_ist_fehler():
    status = frische_status({}, heute=date(2026, 7, 13))
    assert status["fehler"] is True


def test_frische_ueber_monkeypatch_heute(monkeypatch):
    # Monkeypatch der internen _heute()-Funktion statt der echten Systemzeit —
    # simuliert, dass seit dem Abruf ein Jahr vergangen ist.
    hr = {"abgerufen_am": "2026-07-13"}
    monkeypatch.setattr(rechner, "_heute", lambda: date(2027, 8, 1))
    status = frische_status(hr)
    assert status["fehler"] is True


def test_gwg_hochrisiko_liste_ist_nicht_ueberfaellig():
    # Harter CI-Test (kein Monkeypatch): schlägt erst fehl, wenn die
    # hinterlegte Liste seit >= 12 Monaten nicht aktualisiert wurde
    # (erzwingt spätestens einen Jahres-Refresh, siehe rechner.py).
    _, _, hochrisiko = lade_kataloge()
    status = frische_status(hochrisiko)
    assert not status["fehler"], status["hinweis"]
