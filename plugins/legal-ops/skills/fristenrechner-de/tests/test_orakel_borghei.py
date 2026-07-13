"""Orakel-Tests gegen borghei/AI-Skills-German-Law (P4).

Quelle der erwarteten Werte: https://github.com/borghei/AI-Skills-German-Law,
`scripts/legal_calc/tests.py` (Klassen TestFeiertage und TestFristen) sowie
die dort dokumentierten Fixtures. Es wurde KEIN borghei-Code ausgeführt oder
importiert — die handgerechneten Erwartungswerte der borghei-Testfälle sind
hier als unabhängiges Orakel gegen unsere eigene Implementierung übertragen
(Attribution: siehe NOTICE im Repo-Root).

Übertragungs-Anpassungen (API-Unterschiede, keine inhaltlichen Abweichungen):

* borghei kennt ein Pseudo-Land "BUND" (nur bundeseinheitliche Feiertage);
  unsere API verlangt ein echtes Bundesland (§ 193 BGB stellt auf den
  Fristende-Ort ab). BUND-Fälle wurden auf ein konkretes Land übertragen,
  bei dem im jeweiligen Zeitfenster kein landesspezifischer Feiertag liegt —
  das Orakel-Ergebnis bleibt dadurch identisch.
* borghei liefert Feiertage als dict {datum: name} und verschmilzt
  zusammenfallende Namen; wir führen getrennte Einträge je Feiertag.
* borghei parametriert `rollover=False`, wir `paragraf_193_anwenden=False`.
* borgheis `gemeinde_hinweis`/`gemeinde_konflikt`-Warnlogik bilden wir durch
  die datumsgenaue Doppel-Ausweisung (`fristende_bei_teilgebietlichem_
  feiertag`) ab — geprüft wird dieselbe Aussage: BY-Warnung nur, wenn der
  15.08. das Fristfenster berührt.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

import feiertage  # noqa: E402
from fristen import (  # noqa: E402
    FristEingabeFehler,
    berechne_frist,
    naechster_werktag,
)


def _daten(jahr, land):
    return {f.datum for f in feiertage.feiertage(jahr, land)}


# --------------------------------------------------------------------------
# Orakel: TestFeiertage (borghei tests.py)
# --------------------------------------------------------------------------

def test_orakel_ostersonntag():
    # borghei: test_ostersonntag
    assert feiertage.ostersonntag(2024) == dt.date(2024, 3, 31)
    assert feiertage.ostersonntag(2025) == dt.date(2025, 4, 20)
    assert feiertage.ostersonntag(2026) == dt.date(2026, 4, 5)


def test_orakel_bundeseinheitlich_2026():
    # borghei: test_bundeseinheitlich (BUND) — hier: in jedem Land enthalten.
    for land in feiertage.BUNDESLAENDER:
        d = _daten(2026, land)
        assert dt.date(2026, 1, 1) in d      # Neujahr
        assert dt.date(2026, 4, 3) in d      # Karfreitag (Ostern - 2)
        assert dt.date(2026, 10, 3) in d     # Tag der Deutschen Einheit
        assert dt.date(2026, 12, 26) in d    # 2. Weihnachtstag


def test_orakel_laenderspezifisch_2026():
    # borghei: test_laenderspezifisch
    by = _daten(2026, "BY")
    be = _daten(2026, "BE")
    assert dt.date(2026, 1, 6) in by         # Heilige Drei Könige: BY ja
    assert dt.date(2026, 1, 6) not in be     # ... BE nein
    assert dt.date(2026, 6, 4) in by         # Fronleichnam (Ostern + 60): BY ja
    assert dt.date(2026, 6, 4) not in be     # ... BE nein


def test_orakel_reformationstag_yeargate():
    # borghei: test_reformationstag_yeargate
    assert dt.date(2018, 10, 31) in _daten(2018, "HH")   # HH ab 2018
    assert dt.date(2018, 10, 31) not in _daten(2018, "NW")


def test_orakel_reformationstag_2017_bundesweit():
    # borghei: test_reformationstag_2017_bundesweit (ohne Pseudo-Land BUND)
    for land in ("NW", "BY", "BE", "HH"):
        assert dt.date(2017, 10, 31) in _daten(2017, land), land


def test_orakel_zusammenfallende_feiertage_2008():
    # borghei: test_zusammenfallende_feiertage_namen — 2008 fällt Christi
    # Himmelfahrt auf den 01.05.; beide Namen müssen erhalten bleiben.
    namen = {f.name for f in feiertage.feiertage(2008, "BE")
             if f.datum == dt.date(2008, 5, 1)}
    assert "Tag der Arbeit" in namen
    assert "Christi Himmelfahrt" in namen


def test_orakel_gemeinde_warnung_datumsabhaengig():
    # borghei: test_gemeinde_konflikt_datumsabhaengig — BY-Hinweis nur, wenn
    # der 15.08. das Fristfenster berührt; bei uns über die Doppel-Ausweisung.
    fern = berechne_frist(dt.date(2026, 1, 2), 3, "tage", bundesland="BY")
    assert fern.fristende_bei_teilgebietlichem_feiertag is None
    nah = berechne_frist(dt.date(2025, 8, 1), 2, "wochen", bundesland="BY")
    assert nah.fristende_bei_teilgebietlichem_feiertag is not None
    be = berechne_frist(dt.date(2025, 8, 1), 2, "wochen", bundesland="BE")
    assert be.fristende_bei_teilgebietlichem_feiertag is None


def test_orakel_unbekanntes_land():
    # borghei: test_unbekanntes_land
    with pytest.raises(ValueError):
        feiertage.feiertage(2026, "XX")


# --------------------------------------------------------------------------
# Orakel: TestFristen (borghei tests.py)
# --------------------------------------------------------------------------

def test_orakel_klagefrist_kschg_3_wochen():
    # borghei: test_klagefrist_kschg_3_wochen — § 4 KSchG: Zugang Do
    # 15.01.2026, 3 Wochen, Ereignisfrist (borghei: BUND; hier NW — am
    # 05.02. liegt in keinem Land ein Feiertag, Ergebnis identisch).
    r = berechne_frist(dt.date(2026, 1, 15), 3, "wochen", bundesland="NW")
    assert r.fristbeginn == dt.date(2026, 1, 16)
    assert r.fristende == dt.date(2026, 2, 5)    # Do, Werktag
    assert not r.verschoben


def test_orakel_monatsfrist_overflow_und_193():
    # borghei: test_monatsfrist_overflow_und_193 — 1 Monat ab 31.01.2026
    # -> 28.02.2026 (§ 188 III), Sa -> 02.03.2026 (§ 193).
    r = berechne_frist(dt.date(2026, 1, 31), 1, "monate", bundesland="NW")
    assert r.fristende_rechnerisch == dt.date(2026, 2, 28)
    assert r.fristende == dt.date(2026, 3, 2)
    assert r.verschoben
    # ohne Verschiebung bleibt es der 28.02.:
    r2 = berechne_frist(dt.date(2026, 1, 31), 1, "monate", bundesland="NW",
                        paragraf_193_anwenden=False)
    assert r2.fristende == dt.date(2026, 2, 28)


def test_orakel_tagesfrist_ereignis_vs_beginn():
    # borghei: test_tagesfrist_ereignis_vs_beginn
    r = berechne_frist(dt.date(2026, 6, 1), 10, "tage", bundesland="NW",
                       paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 6, 11)
    rb = berechne_frist(dt.date(2026, 6, 1), 10, "tage", "beginn",
                        bundesland="NW", paragraf_193_anwenden=False)
    assert rb.fristende == dt.date(2026, 6, 10)


def test_orakel_lebensalter_beginnfrist():
    # borghei: test_lebensalter_beginnfrist — § 187 II / § 188 II Alt. 2:
    # geb. 01.01.2008 wird mit Ablauf des 31.12.2025 volljährig.
    r = berechne_frist(dt.date(2008, 1, 1), 18, "jahre", "beginn",
                       bundesland="NW", paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2025, 12, 31)


def test_orakel_beginnfrist_schaltjahr():
    # borghei: test_beginnfrist_schaltjahr — geb. 29.02.2008 wird mit Ablauf
    # des 28.02.2026 achtzehn (kein 29.02.2026 -> letzter Tag des Monats,
    # NICHT der 27.02.).
    r = berechne_frist(dt.date(2008, 2, 29), 18, "jahre", "beginn",
                       bundesland="NW", paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 2, 28)


def test_orakel_beginnfrist_monatsende_overflow():
    # borghei: test_beginnfrist_monatsende_overflow — Beginnfrist 1 Monat ab
    # 31.03.2026: April hat keinen 31. -> Ablauf 30.04.2026 (nicht 29.04.).
    r = berechne_frist(dt.date(2026, 3, 31), 1, "monate", "beginn",
                       bundesland="NW", paragraf_193_anwenden=False)
    assert r.fristende == dt.date(2026, 4, 30)


def test_orakel_feiertag_rollover_land():
    # borghei: test_feiertag_rollover_land — Ereignisfrist 5 Tage ab
    # 01.01.2026 -> 06.01.2026 (Di): in BY Feiertag -> 07.01., in BE nicht.
    r_by = berechne_frist(dt.date(2026, 1, 1), 5, "tage", bundesland="BY")
    r_be = berechne_frist(dt.date(2026, 1, 1), 5, "tage", bundesland="BE")
    assert r_by.fristende_rechnerisch == dt.date(2026, 1, 6)
    assert r_by.verschoben
    assert r_by.fristende == dt.date(2026, 1, 7)
    assert not r_be.verschoben
    assert r_be.fristende == dt.date(2026, 1, 6)


def test_orakel_naechster_werktag():
    # borghei: test_naechster_werktag — Sa 03.01.2026 -> Mo 05.01.2026
    # (borghei: BUND; hier NW — 4./5. Januar sind nirgends Feiertag).
    assert naechster_werktag(dt.date(2026, 1, 3), "NW") == dt.date(2026, 1, 5)


def test_orakel_invalid_inputs():
    # borghei: test_invalid_inputs
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 1), 0, "tage", bundesland="NW")
    with pytest.raises(FristEingabeFehler):
        berechne_frist(dt.date(2026, 1, 1), 1, "stunden", bundesland="NW")
