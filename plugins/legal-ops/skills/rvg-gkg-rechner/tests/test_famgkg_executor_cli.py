"""Tests für den Block `famgkg` in core/calc/rvg/executor.py — CLI (P2/P3).

Deckt ab: famgkg allein (direkter Verfahrenswert und Ermittlung), mit `rvg`
und Querverweis "famgkg.verfahrenswert" (§ 23 Abs. 1 Satz 1 RVG),
Querverweis ohne famgkg-Block, gkg + famgkg zugleich, verfahrenswert und
verfahrenswert_ermittlung zugleich bzw. keines von beiden, strikte
Key-Prüfung, float-Ablehnung — jeweils Exit 2 ohne Traceback. Die
Synchronität des Schema-Beispiels prüft test_executor_cli.py.

Erwartete Beträge handgerechnet (Anlage 2 FamGKG/Anlage 2 RVG, Stand
KostBRÄG 2025): Verfahrenswert 15.000 € -> 1,0-Gebühr FamGKG 283,00 + 2 x
30,50 = 344,00 €; KV 1110 (2,0) = 688,00 €.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from conftest import CALC, lauf, report, schreibe  # noqa: E402

EXECUTOR = CALC / "rvg" / "executor.py"

FAMGKG = {"verfahrenseinleitungsdatum": "2026-01-01",
          "verfahrenswert_ermittlung": {
              "ehesache": {"nettoeinkommen_monatlich": ["3000.00", "2000.00"]}},
          "positionen": [{"nr": "1110"}]}


def _lauf(eingabe, tmp_path: Path) -> subprocess.CompletedProcess:
    return lauf(EXECUTOR, "--input", schreibe(tmp_path / "anfrage.json", eingabe))


def _report(eingabe: dict, tmp_path: Path) -> dict:
    return report(EXECUTOR, "--input", schreibe(tmp_path / "anfrage.json", eingabe))


def _exit2(eingabe, tmp_path, muster: str) -> None:
    ergebnis = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 2, ergebnis.stdout
    assert muster in ergebnis.stderr, ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_famgkg_allein_mit_ermittlung(tmp_path):
    r = _report({"famgkg": FAMGKG}, tmp_path)
    assert set(r) == {"meta", "famgkg"}
    f = r["famgkg"]
    assert f["verfahrenswert"]["gesamt"] == "15000.00"
    assert f["eingabe"]["verfahrenswert_herkunft"] == "verfahrenswert_ermittlung"
    assert f["einfachgebuehr"] == "344.00"
    assert f["ergebnis"] == {"gesamt": "688.00", "umsatzsteuerpflichtig": False,
                             "quelle": "executor"}
    assert f["wertkappung"] is None
    assert f["rechenkette"][0]["norm"] == "§§ 33 ff. FamGKG"
    assert [s["schritt"] for s in f["rechenkette"]] == list(range(1, len(f["rechenkette"]) + 1))
    assert "FamGKG" in r["meta"]["hinweis_getrennte_kostenarten"]


def test_famgkg_allein_direkter_verfahrenswert(tmp_path):
    r = _report({"famgkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                            "verfahrenswert": "15000.00",
                            "positionen": [{"nr": "1110"}]}}, tmp_path)
    f = r["famgkg"]
    assert f["verfahrenswert"]["form"] == "direkt"
    assert f["verfahrenswert"]["quelle"] == "eingabe"
    assert f["rechenkette"][0]["quelle"] == "eingabe"
    assert f["ergebnis"]["gesamt"] == "688.00"


def test_famgkg_wertkappung_block(tmp_path):
    r = _report({"famgkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                            "verfahrenswert": "40000000",
                            "positionen": [{"nr": "1220"}]}}, tmp_path)
    k = r["famgkg"]["wertkappung"]
    assert k["norm"] == "§ 33 Abs. 2 FamGKG"
    assert k["verfahrenswert_angewendet"] == "30000000.00"


def test_famgkg_kappung_30_abs_3_block(tmp_path):
    r = _report({"famgkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                            "verfahrenswert": "10000",
                            "positionen": [{"nr": "1310"},
                                           {"nr": "1500", "gegenstandswert": "5000"}]}},
                tmp_path)
    assert r["famgkg"]["kappung_30_abs_3"]["gekappt"] is True
    assert r["famgkg"]["ergebnis"]["gesamt"] == "172.00"


def test_rvg_mit_querverweis(tmp_path):
    """RVG-Gegenstandswert 15.000 € übernommen; 1,0-Gebühr RVG 15.000 € =
    Anlage 2 RVG (KostBRÄG 2025) — Vergleich gegen einen direkten Aufruf
    mit demselben Wert, damit nur der Querverweis geprüft wird."""
    mit = _report({"rvg": {"auftragsdatum": "2026-01-01",
                           "streitwert": "famgkg.verfahrenswert",
                           "tatbestaende": [{"nr": "3100"}]},
                   "famgkg": FAMGKG}, tmp_path)
    direkt = _report({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "15000.00",
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    assert mit["rvg"]["eingabe"]["streitwert"] == "15000.00"
    assert mit["rvg"]["eingabe"]["streitwert_herkunft"] == "famgkg.verfahrenswert"
    assert "streitwert_herkunft" not in direkt["rvg"]["eingabe"]
    erster = mit["rvg"]["rechenkette"][0]
    assert erster["norm"] == "§ 23 Abs. 1 Satz 1 RVG"
    assert erster["ergebnis"] == "15000.00"
    assert erster["quelle"] == "executor"
    assert mit["rvg"]["ergebnis"] == direkt["rvg"]["ergebnis"]
    assert [s["schritt"] for s in mit["rvg"]["rechenkette"]] == list(
        range(1, len(direkt["rvg"]["rechenkette"]) + 2))
    assert list(mit) == ["meta", "rvg", "famgkg"]


def test_querverweis_mit_festgesetztem_wert_ist_eingabe(tmp_path):
    r = _report({"rvg": {"auftragsdatum": "2026-01-01",
                         "streitwert": "famgkg.verfahrenswert",
                         "tatbestaende": [{"nr": "3100"}]},
                 "famgkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                            "verfahrenswert_ermittlung": {"verfahrenswert_festgesetzt": "8000"},
                            "positionen": [{"nr": "1220"}]}}, tmp_path)
    assert r["rvg"]["rechenkette"][0]["quelle"] == "eingabe"
    assert r["rvg"]["eingabe"]["streitwert"] == "8000.00"


def test_querverweis_ohne_famgkg_exit_2(tmp_path):
    _exit2({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "famgkg.verfahrenswert",
                    "tatbestaende": [{"nr": "3100"}]}}, tmp_path, "keinen Block 'famgkg'")


def test_querverweis_mit_gkg_statt_famgkg_exit_2(tmp_path):
    _exit2({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "famgkg.verfahrenswert",
                    "tatbestaende": [{"nr": "3100"}]},
            "gkg": {"verfahrenseinleitungsdatum": "2026-01-01", "streitwert": "1000",
                    "positionen": [{"nr": "1210"}]}}, tmp_path, "keinen Block 'famgkg'")


def test_gkg_und_famgkg_zugleich_exit_2(tmp_path):
    _exit2({"gkg": {"verfahrenseinleitungsdatum": "2026-01-01", "streitwert": "1000",
                    "positionen": [{"nr": "1210"}]},
            "famgkg": FAMGKG}, tmp_path, "nach dem FamGKG, nicht nach dem GKG")


def test_verfahrenswert_und_ermittlung_zugleich_exit_2(tmp_path):
    _exit2({"famgkg": dict(FAMGKG, verfahrenswert="1000")}, tmp_path, "nicht beides")


def test_weder_verfahrenswert_noch_ermittlung_exit_2(tmp_path):
    _exit2({"famgkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                       "positionen": [{"nr": "1110"}]}}, tmp_path,
           "es fehlt der Verfahrenswert")


@pytest.mark.parametrize("eingabe,muster", [
    ({"famgkg": dict(FAMGKG, streitwert="1000")}, "unbekanntes Feld im Block 'famgkg'"),
    ({"famgkg": dict(FAMGKG, verfahrenswert_ermittlung={"ehesache": {
        "nettoeinkommen_monatlich": ["1", "1"]}, "zusatz": 1})}, "unbekanntes Feld"),
    ({"famgkg": dict(FAMGKG, positionen=[{"nr": "1110", "x": 1}])}, "unbekanntes Feld"),
    ({"famkgk": FAMGKG}, "unbekanntes Feld auf oberster Ebene"),
    ({"famgkg": "kaputt"}, "JSON-Objekt"),
    ({"famgkg": dict(FAMGKG, positionen=[{"nr": "1130"}])}, "nicht unterstützt"),
    ({"famgkg": dict(FAMGKG, verfahrenseinleitungsdatum="2020-12-31")},
     "kein FamGKG-Tabellenstand"),
    ({"famgkg": dict(FAMGKG, verfahrenseinleitungsdatum="01.03.2026")}, "JJJJ-MM-TT"),
])
def test_eingabefehler_exit_2(eingabe, muster, tmp_path):
    _exit2(eingabe, tmp_path, muster)


def test_float_verfahrenswert_exit_2(tmp_path):
    _exit2('{"famgkg": {"verfahrenseinleitungsdatum": "2026-01-01", '
           '"verfahrenswert": ' + repr(0.1 + 0.2) + ', '
           '"positionen": [{"nr": "1110"}]}}', tmp_path, "float")


def test_float_einkommen_exit_2(tmp_path):
    _exit2({"famgkg": dict(FAMGKG, verfahrenswert_ermittlung={
        "ehesache": {"nettoeinkommen_monatlich": [3000.5, "2000"]}})}, tmp_path, "float")


def test_billigkeitsabweichung_nur_ueber_festgesetzt(tmp_path):
    # Ein "Billigkeits"-Feld gibt es nicht — Exit 2 statt stiller Annahme.
    _exit2({"famgkg": dict(FAMGKG, verfahrenswert_ermittlung={
        "gegenstaende": [{"art": "kindschaftssache", "gegenstand": "sorge",
                          "billigkeit": "7000"}]})}, tmp_path, "unbekanntes Feld")


def test_report_ist_json_mit_dezimalstrings(tmp_path):
    r = _report({"famgkg": FAMGKG}, tmp_path)
    text = json.dumps(r)
    assert '"gesamt": "688.00"' in text
