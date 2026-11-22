"""Tests für das Mahnverfahren im RVG-Rechner (Teil 3 Abschnitt 3
Unterabschnitt 2 VV RVG, Nr. 3305–3308).

Normtext (web-verifiziert am 2026-11-22 gegen
gesetze-im-internet.de/rvg/anlage_1.html, Fundstellen im Katalog
`vv-katalog.json`, Feld `quelle_hinweis`):
  Nr. 3305 Antragsteller 1,0 (Anm.: Anrechnung auf nachfolgenden Rechtsstreit),
  Nr. 3306 vorzeitige Beendigung „Die Gebühr 3305 beträgt" 0,5,
  Nr. 3307 Antragsgegner 0,5 (Anm. wie 3305),
  Nr. 3308 Vollstreckungsbescheid 0,5 (Anm. Satz 2: Nr. 1008 nicht, wenn sich
  bereits die Gebühr 3305 erhöht); Vorbem. 3.3.2 (Terminsgebühr nach
  Abschnitt 1, nicht modelliert); § 17 Nr. 2 RVG (Mahnverfahren und
  streitiges Verfahren = verschiedene Angelegenheiten).

Orakel-Werte aus der gesetzlichen Stufenformel (tabelle.py), nie frei gesetzt.
1,0-Gebühr KostBRÄG 2025 für 40.000 € (Stufen aus gebuehrentabelle.json):
  51,50 (bis 500) + 3 x 41,50 (bis 2.000) + 8 x 59,50 (bis 10.000)
  + 5 x 55,00 (bis 25.000) + 3 x 86,00 (bis 40.000) = 1.185,00 €.
"""
from __future__ import annotations

import datetime as dt
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import CALC, lauf, report, schreibe  # noqa: E402

from rvg.rechner import RVGEingabeFehler, berechne  # noqa: E402
from rvg.tabelle import einfachgebuehr  # noqa: E402
from wertgebuehr_formel import rundung_cent  # noqa: E402

EXECUTOR = CALC / "rvg" / "executor.py"
STICHTAG = dt.date(2026, 11, 22)        # KostBRÄG 2025
STICHTAG_ALT = dt.date(2024, 1, 1)      # KostRÄG 2021
WERT = "40000"

EG_40000 = (Decimal("51.50") + 3 * Decimal("41.50") + 8 * Decimal("59.50")
            + 5 * Decimal("55.00") + 3 * Decimal("86.00"))


def _eg(wert, stichtag=STICHTAG) -> Decimal:
    return einfachgebuehr(wert, stichtag)[0].einfachgebuehr


def _b(tatbestaende, **kwargs):
    """Eine einzelne Angelegenheit."""
    return berechne(kwargs.pop("streitwert", WERT),
                    kwargs.pop("stichtag", STICHTAG),
                    [{"bezeichnung": "Mahnverfahren",
                      "tatbestaende": tatbestaende}], **kwargs)


def _zwei(mahn, rechtsstreit, **kwargs):
    return berechne(kwargs.pop("streitwert", WERT), STICHTAG, [
        {"bezeichnung": "Mahnverfahren", "tatbestaende": mahn},
        {"bezeichnung": "Rechtsstreit", "tatbestaende": rechtsstreit},
    ], **kwargs)


def _pos(angelegenheit):
    return {p.nr: p for p in angelegenheit.positionen}


def _lauf(eingabe, tmp_path: Path) -> subprocess.CompletedProcess:
    return lauf(EXECUTOR, "--input", schreibe(tmp_path / "anfrage.json", eingabe))


# --------------------------------------------------------------------------
# Grundfälle
# --------------------------------------------------------------------------

def test_einfachgebuehr_40000_aus_stufenformel():
    assert EG_40000 == Decimal("1185.00")
    assert _eg(WERT) == EG_40000


def test_antragsteller_grundfall_3305():
    r = _b([{"nr": "3305"}])
    a = r.angelegenheiten[0]
    p = _pos(a)["3305"]
    assert p.satz == Decimal("1.0")
    assert p.betrag == EG_40000 == Decimal("1185.00")
    assert a.auslagenpauschale == Decimal("20.00")          # min(20 %, 20 €)
    ust = rundung_cent((EG_40000 + Decimal("20.00")) * Decimal("0.19"))
    assert ust == Decimal("228.95")
    assert a.ust == ust
    assert a.gesamt == Decimal("1433.95")
    assert r.anrechnung is None and r.anrechnung_mahnverfahren is None


def test_3305_und_3308_eine_angelegenheit_eine_pauschale():
    r = _b([{"nr": "3305"}, {"nr": "3308"}])
    a = r.angelegenheiten[0]
    pos = _pos(a)
    assert pos["3308"].betrag == rundung_cent(Decimal("0.5") * EG_40000) \
        == Decimal("592.50")
    summe = EG_40000 + Decimal("592.50")
    assert a.zwischensumme_gebuehren == summe
    assert a.auslagenpauschale == Decimal("20.00")           # genau eine 7002
    netto = summe + Decimal("20.00")
    assert a.gesamt == rundung_cent(netto + rundung_cent(netto * Decimal("0.19")))
    assert any("Anm. Satz 1 zu Nr. 3308" in h for h in pos["3308"].hinweise)


def test_3308_allein_zulaessig():
    r = _b([{"nr": "3308"}])
    assert _pos(r.angelegenheiten[0])["3308"].betrag == Decimal("592.50")


def test_3306_ermaessigt():
    r = _b([{"nr": "3306"}])
    p = _pos(r.angelegenheiten[0])["3306"]
    assert p.satz == Decimal("0.5")
    assert p.betrag == rundung_cent(Decimal("0.5") * EG_40000)
    assert any("prüft der Executor nicht" in h for h in p.hinweise)


def test_3307_antragsgegner():
    r = _b([{"nr": "3307"}])
    p = _pos(r.angelegenheiten[0])["3307"]
    assert p.satz == Decimal("0.5")
    assert p.betrag == Decimal("592.50")


def test_1008_auf_3305():
    r = _b([{"nr": "3305"},
            {"nr": "1008", "erhoeht_position": "3305", "weitere_auftraggeber": 1}])
    pos = {p.nr: p for p in r.angelegenheiten[0].positionen}
    assert pos["1008"].satz == Decimal("0.3")
    assert pos["1008"].betrag == rundung_cent(Decimal("0.3") * EG_40000) \
        == Decimal("355.50")


def test_1008_auf_3307_allein_zulaessig():
    r = _b([{"nr": "3307"},
            {"nr": "1008", "erhoeht_position": "3307", "weitere_auftraggeber": 1}])
    pos = {p.nr: p for p in r.angelegenheiten[0].positionen}
    assert pos["1008"].betrag == Decimal("355.50")


def test_1008_auf_3308_ohne_erhoehte_3305_zulaessig():
    r = _b([{"nr": "3305"}, {"nr": "3308"},
            {"nr": "1008", "erhoeht_position": "3308", "weitere_auftraggeber": 1}])
    pos = {p.nr: p for p in r.angelegenheiten[0].positionen}
    assert pos["1008"].betrag == Decimal("355.50")


@pytest.mark.parametrize("stichtag", [STICHTAG, STICHTAG_ALT])
def test_mindestbetrag_floor_greift_beim_kleinsten_wert_nicht(stichtag):
    """Kleinster Wert (bis 500 €): 0,5 x 51,50 = 25,75 € (KostBRÄG 2025) bzw.
    0,5 x 49,00 = 24,50 € (KostRÄG 2021) — beide über dem Mindestbetrag
    15,00 € (§ 13 Abs. 3 RVG). Bei den Mahnverfahrens-Sätzen (>= 0,5) kann
    der Floor rechnerisch nicht greifen; der Report weist das korrekt aus."""
    r = _b([{"nr": "3307"}], streitwert="100", stichtag=stichtag)
    p = _pos(r.angelegenheiten[0])["3307"]
    assert p.betrag == rundung_cent(Decimal("0.5") * _eg("100", stichtag))
    assert p.betrag > Decimal("15.00")
    assert p.mindestbetrag_gegriffen is False


# --------------------------------------------------------------------------
# Exit-2-Fälle innerhalb einer Angelegenheit
# --------------------------------------------------------------------------

def test_3305_und_3306_kumulativ_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="alternativ, nie kumulativ"):
        _b([{"nr": "3305"}, {"nr": "3306"}])


@pytest.mark.parametrize("andere", ["3305", "3306", "3308"])
def test_3307_mit_antragsteller_abgelehnt(andere):
    with pytest.raises(RVGEingabeFehler, match="Antragsgegners"):
        _b([{"nr": "3307"}, {"nr": andere}])


@pytest.mark.parametrize("basis", ["3305", "3306"])
def test_1008_auf_3308_bei_erhoehter_3305_abgelehnt(basis):
    with pytest.raises(RVGEingabeFehler, match="Anm. Satz 2 zu Nr. 3308"):
        _b([{"nr": basis}, {"nr": "3308"},
            {"nr": "1008", "erhoeht_position": basis, "weitere_auftraggeber": 1},
            {"nr": "1008", "erhoeht_position": "3308", "weitere_auftraggeber": 1}])


@pytest.mark.parametrize("reihenfolge", [["3104", "3305"], ["3305", "3104"]])
def test_terminsgebuehr_im_mahnverfahren_gezielt_abgelehnt(reihenfolge):
    with pytest.raises(RVGEingabeFehler) as exc:
        _b([{"nr": nr} for nr in reihenfolge])
    assert "Vorbem. 3.3.2" in str(exc.value)
    assert "Anwaltlich prüfen" in str(exc.value)
    assert "§ 17 Nr. 1" not in str(exc.value)    # nicht die generische Meldung


@pytest.mark.parametrize("streitig", ["3100", "3200"])
def test_mahnverfahren_und_streitiges_verfahren_eine_angelegenheit(streitig):
    with pytest.raises(RVGEingabeFehler, match="§ 17 Nr. 2 RVG"):
        _b([{"nr": "3305"}, {"nr": streitig}])


def test_mahnverfahren_und_2300_eine_angelegenheit():
    with pytest.raises(RVGEingabeFehler, match="Teil 2"):
        _b([{"nr": "3305"}, {"nr": "2300", "satz": "1.3"}])


# --------------------------------------------------------------------------
# Anrechnung Mahnverfahren -> Nr. 3100 (Anm. zu Nr. 3305 / 3307)
# --------------------------------------------------------------------------

def test_anrechnung_3305_auf_3100():
    r = _zwei([{"nr": "3305"}], [{"nr": "3100"}, {"nr": "3104"}],
              anrechnung_mahnverfahren_auf_3100=True)
    vor = rundung_cent(Decimal("1.3") * EG_40000)            # 1.540,50 €
    nach = vor - EG_40000                                    #   355,50 €
    anr = r.anrechnung_mahnverfahren
    assert anr["norm"] == "Anm. zu Nr. 3305 VV RVG"
    assert anr["angerechnete_nr"] == "3305"
    assert anr["anrechnungsbetrag"] == str(EG_40000)
    assert anr["verfahrensgebuehr_vor_anrechnung"] == str(vor) == "1540.50"
    assert anr["verfahrensgebuehr_nach_anrechnung"] == str(nach) == "355.50"
    assert _pos(r.angelegenheiten[1])["3100"].betrag == nach
    # Mahnverfahrens-Angelegenheit selbst bleibt ungekürzt.
    assert _pos(r.angelegenheiten[0])["3305"].betrag == EG_40000
    assert r.anrechnung is None
    assert any("Kein Teilübergang" in w for w in r.warnungen)


def test_anrechnung_3307_auf_3100():
    r = _zwei([{"nr": "3307"}], [{"nr": "3100"}],
              anrechnung_mahnverfahren_auf_3100=True)
    assert r.anrechnung_mahnverfahren["norm"] == "Anm. zu Nr. 3307 VV RVG"
    assert _pos(r.angelegenheiten[1])["3100"].betrag == \
        rundung_cent(Decimal("1.3") * EG_40000) - Decimal("592.50")


def test_anrechnung_ohne_3308():
    r = _zwei([{"nr": "3305"}, {"nr": "3308"}],
              [{"nr": "3100"}], anrechnung_mahnverfahren_auf_3100=True)
    # nur die Gebühr 3305 (1.185,00 €), nie Nr. 3308.
    assert r.anrechnung_mahnverfahren["anrechnungsbetrag"] == "1185.00"
    assert r.anrechnung_mahnverfahren["angerechnete_nr"] == "3305"


def test_anrechnung_erhoehte_mahnverfahrensgebuehr_abgelehnt():
    """Nr. 1008 erhöht die Verfahrensgebühr selbst; angerechnet würde die
    erhöhte Gebühr — nicht modelliert, Exit 2."""
    with pytest.raises(RVGEingabeFehler, match="nach Nr. 1008 erhöhten"):
        _zwei([{"nr": "3305"},
               {"nr": "1008", "erhoeht_position": "3305",
                "weitere_auftraggeber": 1}],
              [{"nr": "3100"},
               {"nr": "1008", "erhoeht_position": "3100",
                "weitere_auftraggeber": 1}],
              streitwert="10000", anrechnung_mahnverfahren_auf_3100=True)


def test_mahnverfahren_und_3100_ohne_flag_warnt():
    r = _zwei([{"nr": "3307"}], [{"nr": "3100"}])
    assert r.anrechnung_mahnverfahren is None
    assert _pos(r.angelegenheiten[1])["3100"].betrag == \
        rundung_cent(Decimal("1.3") * EG_40000)
    assert any("zwingend" in w for w in r.warnungen)


def test_nur_3308_und_3100_ohne_flag_keine_warnung():
    r = _zwei([{"nr": "3308"}], [{"nr": "3100"}])
    assert not any("zwingend" in w for w in r.warnungen)


@pytest.mark.parametrize("mahn,streit", [
    ([{"nr": "3308"}], [{"nr": "3100"}]),           # 3308 nie angerechnet
    ([{"nr": "3305"}], [{"nr": "3200"}]),           # keine 3100
])
def test_anrechnung_fehlende_seite_abgelehnt(mahn, streit):
    with pytest.raises(RVGEingabeFehler, match="genau eine"):
        _zwei(mahn, streit, anrechnung_mahnverfahren_auf_3100=True)


def test_anrechnung_verschiedene_werte_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="Teilübergang"):
        _zwei([{"nr": "3305", "gegenstandswert": "30000"}],
              [{"nr": "3100"}], anrechnung_mahnverfahren_auf_3100=True)


def test_anrechnung_flag_kein_bool():
    with pytest.raises(RVGEingabeFehler, match="JSON-Boolean"):
        _zwei([{"nr": "3305"}], [{"nr": "3100"}],
              anrechnung_mahnverfahren_auf_3100="ja")


# --------------------------------------------------------------------------
# Geschäftsgebühr + Mahnverfahren
# --------------------------------------------------------------------------

def _drei(**kwargs):
    return berechne(WERT, STICHTAG, [
        {"bezeichnung": "Außergerichtlich",
         "tatbestaende": [{"nr": "2300", "satz": "1.3"}]},
        {"bezeichnung": "Mahnverfahren", "tatbestaende": [{"nr": "3305"}]},
        {"bezeichnung": "Rechtsstreit", "tatbestaende": [{"nr": "3100"}]},
    ], **kwargs)


@pytest.mark.parametrize("flag", ["anrechnung_2300_auf_3100",
                                  "anrechnung_mahnverfahren_auf_3100"])
def test_2300_plus_mahnverfahren_mit_anrechnung_abgelehnt(flag):
    with pytest.raises(RVGEingabeFehler, match="Kettenanrechnung"):
        _drei(**{flag: True})


def test_2300_plus_mahnverfahren_ohne_anrechnung_rechnet_mit_hinweis():
    r = _drei()
    assert r.anrechnung is None and r.anrechnung_mahnverfahren is None
    assert _pos(r.angelegenheiten[2])["3100"].betrag == \
        rundung_cent(Decimal("1.3") * EG_40000)
    assert any("nicht angefordert" in w for w in r.warnungen)


# --------------------------------------------------------------------------
# Executor-CLI: strikte Keys, Report-Block, Rückwärtskompatibilität
# --------------------------------------------------------------------------

def _anfrage(**rvg_extra):
    return {"rvg": {"auftragsdatum": "2026-11-22", "streitwert": "40000.00",
                    "angelegenheiten": [
                        {"bezeichnung": "Mahnverfahren",
                         "tatbestaende": [{"nr": "3305"}]},
                        {"bezeichnung": "Rechtsstreit",
                         "tatbestaende": [{"nr": "3100"}]}],
                    **rvg_extra}}


def test_cli_anrechnung_block(tmp_path):
    r = report(EXECUTOR, "--input", schreibe(
        tmp_path / "a.json", _anfrage(anrechnung_mahnverfahren_auf_3100=True)))
    rvg = r["rvg"]
    assert rvg["anrechnung"] is None
    assert rvg["anrechnung_mahnverfahren"]["verfahrensgebuehr_nach_anrechnung"] \
        == "355.50"
    assert rvg["eingabe"]["anrechnung_mahnverfahren_auf_3100"] is True


def test_cli_ohne_flag_kein_neuer_block(tmp_path):
    r = report(EXECUTOR, "--input", schreibe(tmp_path / "a.json", _anfrage()))
    assert "anrechnung_mahnverfahren" not in r["rvg"]
    assert "anrechnung_mahnverfahren_auf_3100" not in r["rvg"]["eingabe"]


def test_cli_unbekannter_key_abgelehnt(tmp_path):
    erg = _lauf(_anfrage(anrechnung_mahnverfahren_3100=True), tmp_path)
    assert erg.returncode == 2
    assert "anrechnung_mahnverfahren_3100" in erg.stderr
    assert "Traceback" not in erg.stderr


def test_cli_flag_kein_bool(tmp_path):
    erg = _lauf(_anfrage(anrechnung_mahnverfahren_auf_3100="true"), tmp_path)
    assert erg.returncode == 2
    assert "JSON-Boolean" in erg.stderr


def test_cli_terminsgebuehr_mahnverfahren_exit2(tmp_path):
    erg = _lauf({"rvg": {"auftragsdatum": "2026-11-22", "streitwert": "40000",
                         "tatbestaende": [{"nr": "3305"}, {"nr": "3104"}]}},
                tmp_path)
    assert erg.returncode == 2
    assert "Vorbem. 3.3.2" in erg.stderr
