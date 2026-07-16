"""Tests für die zwei Befunde der händischen LG-Berlin-Abnahme (2026-07-15):

Befund 1 — Gerichts-PDF-Encoding-Reparatur ('$'→'§', 'SS'→'§§' nur im
           Normzitat-Kontext; nie blind; jede Ersetzung dokumentiert).
Befund 2 — Standard-Registries (BGB/ZPO/StGB) unter schema/standard-registries/,
           damit Norm-Zitate nicht pauschal `nicht_pruefbar` bleiben.

Getrennt von test_executor.py gehalten (eigene Datei, eindeutiger Name).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA_DIR = SKILL_DIR / "schema"
STD_REG_DIR = SCHEMA_DIR / "standard-registries"
sys.path.insert(0, str(SKILL_DIR))

import executor  # noqa: E402


def _kuerzel():
    return executor.lade_kuerzelliste(SCHEMA_DIR)


# ==========================================================================
# Befund 1 — Encoding-Reparatur
# ==========================================================================

def test_dollar_wird_im_normkontext_zu_paragraph():
    text, reps = executor.repariere_encoding("Anspruch auf $ 826 BGB gestützt.", _kuerzel())
    assert "§ 826 BGB" in text
    assert len(reps) == 1
    assert reps[0]["original"] == "$" and reps[0]["ersetzung"] == "§"


def test_SS_wird_im_normkontext_zu_doppelparagraph_inklusive_kette():
    text, reps = executor.repariere_encoding("(SS 37, 37b Abs. 1 StBerG)", _kuerzel())
    assert "§§ 37, 37b Abs. 1 StBerG" in text
    assert len(reps) == 1
    assert reps[0]["original"] == "SS" and reps[0]["ersetzung"] == "§§"


def test_geldbetrag_dollar_wird_nicht_angefasst():
    # '$ 50 Euro' und '$ 50.000' sind Geldangaben — 'Euro' ist kein Kürzel,
    # '.000' ist kein Kürzel. Kein Normzitat-Kontext → keine Reparatur.
    for probe in ("Betrag von $ 50 Euro offen.", "Streitwert $ 50.000 festgesetzt."):
        text, reps = executor.repariere_encoding(probe, _kuerzel())
        assert "$" in text and "§" not in text
        assert reps == []


def test_SS_in_wort_und_ohne_kuerzel_wird_nicht_angefasst():
    # 'PASSAU': auf 'SS' folgt keine Ziffer. 'SS 12 Personen': Ziffer, aber
    # 'Personen' ist kein bekanntes Gesetzeskürzel. Beides bleibt unberührt.
    text, reps = executor.repariere_encoding("In PASSAU tagen SS 12 Personen.", _kuerzel())
    assert text == "In PASSAU tagen SS 12 Personen."
    assert reps == []


def test_dollar_vor_ziffer_ohne_bekanntes_kuerzel_bleibt_unberuehrt():
    # Konservativ: '$ 5 Mio' — 'Mio' ist kein bekanntes Kürzel → keine Reparatur.
    text, reps = executor.repariere_encoding("rund $ 5 Mio. Schaden", _kuerzel())
    assert reps == []
    assert "$ 5 Mio" in text


def test_reparatur_liste_hat_position_zeile_original_ersetzung_kontext():
    text = "Zeile eins.\nAnspruch auf $ 826 BGB.\n"
    _, reps = executor.repariere_encoding(text, _kuerzel())
    r = reps[0]
    assert set(r) == {"position", "zeile", "original", "ersetzung", "kontext"}
    assert r["zeile"] == 2
    # Position zeigt exakt auf das Markerzeichen im Originaltext.
    assert text[r["position"]] == "$"
    assert r["kontext"] == "$ 826 BGB"


def test_reparatur_positionen_sind_laengenstabil():
    # '§' hat dieselbe Länge wie '$', '§§' dieselbe wie 'SS' → das Markerzeichen
    # steht im Reparat an derselben Position wie im Original.
    text = "x $ 826 BGB und (SS 37 StBerG)."
    repariert, reps = executor.repariere_encoding(text, _kuerzel())
    assert len(repariert) == len(text)
    for r in reps:
        assert repariert[r["position"]] == r["ersetzung"][0]


def test_baue_report_ohne_flag_repariert_nicht():
    text = "Anspruch auf $ 826 BGB gestützt."
    report = executor.baue_report(text, {"normen": [], "entscheidungen": [], "fundstellen": []},
                                  SCHEMA_DIR, quelle_datei="x", registry_datei=None,
                                  repariere=False)
    # '$ 826' ist ohne Reparatur kein erkennbares Normzitat und es gibt keine
    # Reparatur-Liste im Report.
    assert "encoding_reparaturen" not in report["meta"]
    assert all(z["typ"] != "norm" for z in report["zitate"])


def test_baue_report_meta_key_fehlt_wenn_nichts_repariert():
    # Sauberer Text + Flag an → keine Reparatur → kein encoding_reparaturen-Key
    # (hält u. a. das Golden-File beispiel-report.json stabil).
    report = executor.baue_report("§ 203 StGB.", {"normen": [], "entscheidungen": [], "fundstellen": []},
                                  SCHEMA_DIR, quelle_datei="x", registry_datei=None,
                                  repariere=True)
    assert "encoding_reparaturen" not in report["meta"]


def test_cli_repariere_encoding_flag_dokumentiert_reparaturen():
    eingabe = FIXTURES / "lg_berlin_encoding.md"
    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe),
         "--registry", str(STD_REG_DIR / "bgb.json"),
         "--repariere-encoding"],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    reps = report["meta"]["encoding_reparaturen"]
    # Genau zwei Reparaturen: '$ 826 BGB' und 'SS 37, 37b … StBerG'.
    assert len(reps) == 2
    marker = {r["original"] for r in reps}
    assert marker == {"$", "SS"}


# ==========================================================================
# Befund 1+2 gemeinsam — LG-Berlin-Beispiel gegen Standard-Registry
# ==========================================================================

def test_lg_berlin_beispiel_wird_mit_standard_registry_korrekt_klassifiziert():
    text = (FIXTURES / "lg_berlin_encoding.md").read_text(encoding="utf-8")
    registry = executor.lade_registry(STD_REG_DIR / "bgb.json")
    report = executor.baue_report(text, registry, SCHEMA_DIR,
                                  quelle_datei="lg_berlin_encoding.md",
                                  registry_datei="bgb.json", repariere=True)
    zustand = {z["roh"]: z["zustand"] for z in report["zitate"] if z["typ"] == "norm"}
    assert zustand["§ 826 BGB"] == "verifiziert"
    # StBerG ist nicht in der BGB-Registry → bleibt nicht_pruefbar (kein falsches ❌).
    stberg = next(r for k, r in zustand.items() if "StBerG" in k)
    assert stberg == "nicht_pruefbar"


# ==========================================================================
# Befund 2 — Standard-Registries
# ==========================================================================

def test_standard_registries_laden_ohne_fehler():
    for name in ("bgb.json", "zpo.json", "stgb.json"):
        reg = executor.lade_registry(STD_REG_DIR / name)
        assert reg["normen"], f"{name} hat keine Normen"


def test_standard_registry_traegt_provenienz_felder():
    reg = json.loads((STD_REG_DIR / "bgb.json").read_text(encoding="utf-8"))
    assert reg["quelle_url"].startswith("https://www.gesetze-im-internet.de/")
    assert reg["abgerufen_am"] == "2026-07-16"
    assert "frische" in reg["frische_hinweis"].lower()


def _pruefe_einzelnorm(zitat: str, registry_datei: str):
    registry = executor.lade_registry(STD_REG_DIR / registry_datei)
    t = executor.extrahiere_normzitate(zitat)[0]
    zustand, begruendung, _ = executor.pruefe_norm(t, registry, _kuerzel())
    return zustand, begruendung


def test_stichprobe_826_bgb_ist_verifiziert():
    zustand, _ = _pruefe_einzelnorm("§ 826 BGB", "bgb.json")
    assert zustand == executor.ZUSTAND_VERIFIZIERT


def test_stichprobe_222_zpo_ist_verifiziert():
    zustand, _ = _pruefe_einzelnorm("§ 222 ZPO", "zpo.json")
    assert zustand == executor.ZUSTAND_VERIFIZIERT


def test_37b_stberg_bleibt_nicht_pruefbar_gegen_bgb_registry():
    # § 37b StBerG steht in keiner der drei Registries → nicht_pruefbar,
    # nicht abweichend (StBerG-Kürzel kommt in bgb.json gar nicht vor).
    zustand, _ = _pruefe_einzelnorm("§ 37b StBerG", "bgb.json")
    assert zustand == executor.ZUSTAND_NICHT_PRUEFBAR


def test_erfundene_norm_9999_bgb_ist_abweichend():
    # BGB ist in der Registry vorhanden, § 9999 existiert nicht → abweichend.
    zustand, begruendung = _pruefe_einzelnorm("§ 9999 BGB", "bgb.json")
    assert zustand == executor.ZUSTAND_ABWEICHEND
    assert "9999" in begruendung


def test_aufgehobene_norm_ist_gekennzeichnet_und_bleibt_verifiziert():
    # Aufgehobene Paragraphen sind mit aufgehoben:true aufgenommen, damit ein
    # Zitat auf die historische Nummer nicht fälschlich als ❌ gemeldet wird.
    stgb = {n["paragraph"]: n for n in
            json.loads((STD_REG_DIR / "stgb.json").read_text(encoding="utf-8"))["normen"]}
    assert stgb["117"].get("aufgehoben") is True
    zustand, _ = _pruefe_einzelnorm("§ 117 StGB", "stgb.json")
    assert zustand == executor.ZUSTAND_VERIFIZIERT
