"""Vergleich mit Mehrwert: Teilwerte je Position, Nr. 3101 VV RVG,
§ 15 Abs. 3 RVG, KV 1900 GKG mit § 36 Abs. 3 GKG (Anm. zu KV 1900).

Referenzfall (Praxistest): Klage 50.000 €, Teilrücknahme 10.000 €, Vergleich
in der mündlichen Verhandlung, der zusätzlich 20.000 € nicht rechtshängige
Ansprüche erledigt — EINE Angelegenheit. Erwartungswerte = web-verifizierter
Satz x 1,0-Gebühr aus den Repo-Tabellen (KostBRÄG 2025): RVG 1,0-Gebühr
20.000 = 872,00 · 40.000 = 1.185,00 · 50.000 = 1.357,00 · 60.000 = 1.456,50 ·
70.000 = 1.556,00; GKG 20.000 = 405,00 · 50.000 = 638,00 · 70.000 = 918,00.
"""
from __future__ import annotations

from conftest import CALC, lauf, report, schreibe  # noqa: E402

EXECUTOR = CALC / "rvg" / "executor.py"


def _rvg(tatbestaende, **extra):
    return {"auftragsdatum": "2026-03-01", "streitwert": "50000.00",
            "angelegenheiten": [{"bezeichnung": "Rechtsstreit",
                                 "tatbestaende": tatbestaende}], **extra}


REFERENZ = {
    "rvg": _rvg([
        {"nr": "3100", "gegenstandswert": "50000.00"},
        {"nr": "3101", "gegenstandswert": "20000.00"},
        {"nr": "3104", "gegenstandswert": "60000.00"},
        {"nr": "1003", "gegenstandswert": "40000.00"},
        {"nr": "1000", "gegenstandswert": "20000.00"},
    ]),
    "gkg": {"verfahrenseinleitungsdatum": "2026-03-01", "streitwert": "50000.00",
            "positionen": [{"nr": "1211"},
                           {"nr": "1900", "gegenstandswert": "20000.00"}]},
}


def _fehler(eingabe, tmp_path) -> str:
    ergebnis = lauf(EXECUTOR, "--input", schreibe(tmp_path / "a.json", eingabe))
    assert ergebnis.returncode == 2, ergebnis.stdout
    assert "Traceback" not in ergebnis.stderr
    return ergebnis.stderr


def test_referenzfall_end_to_end(tmp_path):
    r = report(EXECUTOR, "--input", schreibe(tmp_path / "a.json", REFERENZ))
    ang = r["rvg"]["angelegenheiten"]
    assert len(ang) == 1
    pos = {p["nr"]: p for p in ang[0]["positionen"]}
    assert {nr: p["betrag"] for nr, p in pos.items()} == {
        "3100": "1764.10", "3101": "697.60", "3104": "1747.80",
        "1003": "1185.00", "1000": "1308.00"}
    assert pos["3101"]["gegenstandswert"] == "20000.00"
    k = {x["gebuehrenart"]: x for x in ang[0]["kappungen_15_abs_3"]}
    assert (k["verfahrensgebuehr"]["summe_einzelgebuehren"],
            k["verfahrensgebuehr"]["betrag_nach_kappung"]) == ("2461.70", "2022.80")
    assert (k["einigungsgebuehr"]["summe_einzelgebuehren"],
            k["einigungsgebuehr"]["betrag_nach_kappung"]) == ("2493.00", "2184.75")
    assert all(x["gekappt"] for x in k.values())
    assert ang[0]["ergebnis"] == {
        "zwischensumme_gebuehren": "5955.35", "auslagenpauschale": "20.00",
        "netto": "5975.35", "ust_satz": "0.19", "ust": "1135.32",
        "gesamt": "7110.67", "quelle": "executor"}
    assert r["rvg"]["ergebnis"]["gesamt_verguetung"] == "7110.67"
    normen = [s["norm"] for s in r["rvg"]["rechenkette"]]
    assert normen.count("§ 15 Abs. 3 RVG") == 2

    gkg = r["gkg"]
    assert {p["nr"]: p["betrag"] for p in gkg["positionen"]} == {
        "1211": "638.00", "1900": "101.25"}
    # § 36 Abs. 3 GKG greift nicht (1,0 aus 70.000 = 918,00 > 739,25) —
    # trotzdem sichtbar ausgewiesen.
    assert gkg["kappung_36_abs_3"]["hoechstbetrag"] == "918.00"
    assert gkg["kappung_36_abs_3"]["gekappt"] is False
    assert gkg["ergebnis"]["gesamt"] == "739.25"


def test_15_abs_3_greift_nicht(tmp_path):
    # 1,3 x 652,00 + 0,8 x 51,50 = 888,80 < 1,3 x 707,00 (10.500) = 919,10
    r = report(EXECUTOR, "--input", schreibe(tmp_path / "a.json", {"rvg": _rvg([
        {"nr": "3100", "gegenstandswert": "10000"},
        {"nr": "3101", "gegenstandswert": "500"}])}))
    ang = r["rvg"]["angelegenheiten"][0]
    (k,) = ang["kappungen_15_abs_3"]
    assert (k["gekappt"], k["kuerzung"], k["hoechstbetrag"]) == (False, "0.00", "919.10")
    assert ang["ergebnis"]["zwischensumme_gebuehren"] == "888.80"
    assert any(s["norm"] == "§ 15 Abs. 3 RVG" and "greift nicht" in s["beschreibung"]
               for s in r["rvg"]["rechenkette"])


def test_gruppe_ohne_teilwert_fehler(tmp_path):
    assert "gegenstandswert" in _fehler({"rvg": _rvg([
        {"nr": "3100"}, {"nr": "3101", "gegenstandswert": "20000"}])}, tmp_path)


def test_anrechnung_ungleiche_werte_fehler(tmp_path):
    eingabe = {"rvg": {"auftragsdatum": "2026-03-01", "streitwert": "10000",
                       "anrechnung_2300_auf_3100": True, "angelegenheiten": [
        {"bezeichnung": "vorgerichtlich",
         "tatbestaende": [{"nr": "2300", "satz": "1.3", "gegenstandswert": "8000"}]},
        {"bezeichnung": "Rechtsstreit", "tatbestaende": [{"nr": "3100"}]}]}}
    assert "Teilanrechnung" in _fehler(eingabe, tmp_path)


def test_wert_hoechstgrenze_mit_teilwerten_fehler(tmp_path):
    # Position über 30 Mio.
    assert "§ 22 Abs. 2 RVG" in _fehler({"rvg": _rvg([
        {"nr": "3104", "gegenstandswert": "30000001"}])}, tmp_path)
    # je Wertteil darunter, Summe der Wertteile (§ 15 Abs. 3) darüber
    assert "§ 22 Abs. 2 RVG" in _fehler({"rvg": _rvg([
        {"nr": "3100", "gegenstandswert": "20000000"},
        {"nr": "3101", "gegenstandswert": "20000000"}])}, tmp_path)
    assert "§ 39 Abs. 2 GKG" in _fehler({"gkg": {
        "verfahrenseinleitungsdatum": "2026-03-01", "streitwert": "20000000",
        "positionen": [{"nr": "1211"},
                       {"nr": "1900", "gegenstandswert": "20000000"}]}}, tmp_path)


def test_kv_1900_ohne_wert_und_tippfehler_fehler(tmp_path):
    gkg = {"verfahrenseinleitungsdatum": "2026-03-01", "streitwert": "50000",
           "positionen": [{"nr": "1211"}, {"nr": "1900"}]}
    assert "gegenstandswert" in _fehler({"gkg": gkg}, tmp_path)
    assert "gegenstandwert" in _fehler({"rvg": _rvg([
        {"nr": "3104", "gegenstandwert": "60000"}])}, tmp_path)
