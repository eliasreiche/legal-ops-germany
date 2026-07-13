"""Tests für plugins/legal-ops/skills/zitat-verifier-de/executor.py.

Deckt ab: Extraktion aller drei Zitattypen, den 3-Zustands-Marker gegen eine
Quellen-Registry, die quellenfreien Formatprüfungen sowie die CLI (Datei rein
→ JSON-Report raus, P2).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SKILL_DIR))

import executor  # noqa: E402


SCHEMA_DIR = SKILL_DIR / "schema"


def _leere_registry():
    return {"normen": [], "entscheidungen": [], "fundstellen": []}


# --------------------------------------------------------------------------
# Normzitate — Extraktion
# --------------------------------------------------------------------------

def test_extrahiert_einfaches_normzitat():
    treffer = executor.extrahiere_normzitate("Vgl. § 203 StGB.")
    assert len(treffer) == 1
    t = treffer[0]
    assert t["gesetz"] == "StGB"
    assert t["paragraphen"] == ["203"]
    assert t["marker_zeichen"] == "§"


def test_extrahiert_norm_mit_abs_satz_nr_lit():
    treffer = executor.extrahiere_normzitate(
        "Nach § 312c Abs. 1 Satz 1 Nr. 3 lit. a BGB gilt Folgendes.")
    assert len(treffer) == 1
    t = treffer[0]
    assert t["paragraphen"] == ["312c"]
    assert t["abs"] == "Abs. 1"
    assert t["satz"] == "Satz 1"
    assert t["nr"] == "Nr. 3"
    assert t["lit"] == "lit. a"


def test_extrahiert_paragraphenkette():
    treffer = executor.extrahiere_normzitate("Es gelten §§ 53, 97 StPO.")
    assert len(treffer) == 1
    assert treffer[0]["paragraphen"] == ["53", "97"]
    assert treffer[0]["marker_zeichen"] == "§§"


def test_extrahiert_artikel_zitat():
    treffer = executor.extrahiere_normzitate("Art. 44 DSGVO ist zu beachten.")
    assert len(treffer) == 1
    assert treffer[0]["gesetz"] == "DSGVO"
    assert treffer[0]["paragraphen"] == ["44"]


def test_extrahiert_klammerzusatz():
    treffer = executor.extrahiere_normzitate("§ 312c BGB (n.F.) regelt dies.")
    assert treffer[0]["klammer"] == "(n.F.)"


def test_extrahiert_norm_im_fussnotenstil():
    text = "Haupttext ohne Zitat.\n\n12 Vgl. § 203 StGB.\n13 Vgl. § 5 UnbekanntesKuerzel.\n"
    treffer = executor.extrahiere_normzitate(text)
    assert [t["gesetz"] for t in treffer] == ["StGB", "UnbekanntesKuerzel"]
    # Fußnote 13 steht auf Zeile 4.
    assert treffer[1]["zeile"] == 4


def test_zeilennummer_wird_korrekt_berechnet():
    text = "Zeile eins.\nZeile zwei mit § 1 BGB.\nZeile drei.\n"
    treffer = executor.extrahiere_normzitate(text)
    assert treffer[0]["zeile"] == 2


# --------------------------------------------------------------------------
# Normzitate — Prüfzustand
# --------------------------------------------------------------------------

def test_norm_verifiziert_bei_registry_treffer():
    kuerzel = {"StGB"}
    registry = {"normen": [{"kuerzel": "StGB", "paragraph": "203"}],
                "entscheidungen": [], "fundstellen": []}
    t = executor.extrahiere_normzitate("§ 203 StGB")[0]
    zustand, begruendung, warnungen = executor.pruefe_norm(t, registry, kuerzel)
    assert zustand == executor.ZUSTAND_VERIFIZIERT
    assert "StGB" in begruendung


def test_norm_nicht_pruefbar_ohne_registry_eintrag_fuer_gesetz():
    kuerzel = {"StGB"}
    t = executor.extrahiere_normzitate("§ 203 StGB")[0]
    zustand, _, _ = executor.pruefe_norm(t, _leere_registry(), kuerzel)
    assert zustand == executor.ZUSTAND_NICHT_PRUEFBAR


def test_norm_abweichend_wenn_gesetz_bekannt_aber_paragraph_fehlt():
    kuerzel = {"BRAO"}
    registry = {"normen": [{"kuerzel": "BRAO", "paragraph": "43a"}],
                "entscheidungen": [], "fundstellen": []}
    t = executor.extrahiere_normzitate("§ 999 BRAO")[0]
    zustand, begruendung, _ = executor.pruefe_norm(t, registry, kuerzel)
    assert zustand == executor.ZUSTAND_ABWEICHEND
    assert "999" in begruendung


def test_norm_kette_aggregiert_schlechtesten_zustand():
    kuerzel = {"StPO"}
    registry = {"normen": [{"kuerzel": "StPO", "paragraph": "53"}],
                "entscheidungen": [], "fundstellen": []}
    t = executor.extrahiere_normzitate("§§ 53, 97 StPO")[0]
    zustand, begruendung, _ = executor.pruefe_norm(t, registry, kuerzel)
    assert zustand == executor.ZUSTAND_ABWEICHEND
    assert "97" in begruendung


def test_norm_formatwarnung_unbekanntes_kuerzel():
    kuerzel = {"StGB"}
    t = executor.extrahiere_normzitate("§ 5 UnbekanntesGesetz")[0]
    _, _, warnungen = executor.pruefe_norm(t, _leere_registry(), kuerzel)
    assert any("unbekanntes Gesetzeskürzel" in w for w in warnungen)


def test_norm_formatwarnung_plural_mit_einer_nummer():
    kuerzel = {"StGB"}
    t = executor.extrahiere_normzitate("§§ 5 StGB")[0]
    _, _, warnungen = executor.pruefe_norm(t, _leere_registry(), kuerzel)
    assert any("vermutlich '§' gemeint" in w for w in warnungen)


def test_norm_formatwarnung_singular_mit_kette():
    kuerzel = {"StGB"}
    t = executor.extrahiere_normzitate("§ 5, 6 StGB")[0]
    _, _, warnungen = executor.pruefe_norm(t, _leere_registry(), kuerzel)
    assert any("vermutlich '§§' gemeint" in w for w in warnungen)


def test_norm_formatwarnung_absatz_null():
    kuerzel = {"StGB"}
    t = executor.extrahiere_normzitate("§ 5 Abs. 0 StGB")[0]
    _, _, warnungen = executor.pruefe_norm(t, _leere_registry(), kuerzel)
    assert any("Abs. 0" in w for w in warnungen)


# --------------------------------------------------------------------------
# Gerichtsentscheidungen
# --------------------------------------------------------------------------

def _gerichte():
    return executor.lade_gerichte(SCHEMA_DIR)


def test_extrahiert_gerichtsentscheidung_mit_datum_und_az():
    treffer = executor.extrahiere_gerichtsentscheidungen(
        "BGH, Urt. v. 12.01.2023 – IX ZR 15/22.", _gerichte())
    assert len(treffer) == 1
    t = treffer[0]
    assert t["gericht"] == "BGH"
    assert t["datum"] == "12.01.2023"
    assert t["aktenzeichen"] == "IX ZR 15/22"


def test_extrahiert_gerichtsentscheidung_mit_ortszusatz():
    treffer = executor.extrahiere_gerichtsentscheidungen(
        "OLG München, Beschl. v. 03.04.2019 – 7 U 12/18.", _gerichte())
    assert len(treffer) == 1
    assert treffer[0]["gericht"] == "OLG München"
    assert treffer[0]["aktenzeichen"] == "7 U 12/18"


def test_entscheidung_verifiziert_bei_exaktem_registry_treffer():
    registry = {"normen": [], "fundstellen": [],
                "entscheidungen": [{"gericht": "BGH", "aktenzeichen": "IX ZR 15/22",
                                     "datum": "2023-01-12"}]}
    t = executor.extrahiere_gerichtsentscheidungen(
        "BGH, Urt. v. 12.01.2023 – IX ZR 15/22.", _gerichte())[0]
    zustand, _, _ = executor.pruefe_entscheidung(t, registry)
    assert zustand == executor.ZUSTAND_VERIFIZIERT


def test_entscheidung_abweichend_bei_falschem_datum():
    registry = {"normen": [], "fundstellen": [],
                "entscheidungen": [{"gericht": "BGH", "aktenzeichen": "IX ZR 15/22",
                                     "datum": "2023-01-12"}]}
    t = executor.extrahiere_gerichtsentscheidungen(
        "BGH, Urt. v. 01.01.2020 – IX ZR 15/22.", _gerichte())[0]
    zustand, begruendung, _ = executor.pruefe_entscheidung(t, registry)
    assert zustand == executor.ZUSTAND_ABWEICHEND
    assert "Datum" in begruendung


def test_entscheidung_nicht_pruefbar_ohne_registry_treffer():
    t = executor.extrahiere_gerichtsentscheidungen(
        "BGH, Urt. v. 12.01.2023 – IX ZR 15/22.", _gerichte())[0]
    zustand, _, _ = executor.pruefe_entscheidung(t, _leere_registry())
    assert zustand == executor.ZUSTAND_NICHT_PRUEFBAR


def test_entscheidung_formatwarnung_az_jahr_nach_entscheidungsdatum():
    t = executor.extrahiere_gerichtsentscheidungen(
        "BGH, Urt. v. 01.01.2020 – IX ZR 15/22.", _gerichte())[0]
    _, _, warnungen = executor.pruefe_entscheidung(t, _leere_registry())
    assert any("Aktenzeichen-Jahr" in w for w in warnungen)


# --------------------------------------------------------------------------
# Fundstellen
# --------------------------------------------------------------------------

def _zeitschriften():
    return executor.lade_zeitschriften(SCHEMA_DIR)


def test_extrahiert_fundstelle_mit_gericht():
    treffer = executor.extrahiere_fundstellen(
        "Siehe BVerfG NJW 2020, 300.", _gerichte(), _zeitschriften(), [])
    assert len(treffer) == 1
    t = treffer[0]
    assert t["gericht"] == "BVerfG"
    assert t["zeitschrift"] == "NJW"
    assert t["jahr"] == 2020
    assert t["seite"] == 300


def test_extrahiert_fundstelle_ohne_gericht():
    treffer = executor.extrahiere_fundstellen(
        "Siehe NJW 2020, 300.", _gerichte(), _zeitschriften(), [])
    assert treffer[0]["gericht"] is None


def test_fundstelle_wird_bei_ueberlappung_mit_entscheidung_unterdrueckt():
    text = "BGH, Urt. v. 12.01.2023 – IX ZR 15/22."
    entscheidungen = executor.extrahiere_gerichtsentscheidungen(text, _gerichte())
    belegt = [t["span"] for t in entscheidungen]
    treffer = executor.extrahiere_fundstellen(text, _gerichte(), _zeitschriften(), belegt)
    assert treffer == []


def test_fundstelle_verifiziert_bei_registry_treffer():
    registry = {"normen": [], "entscheidungen": [],
                "fundstellen": [{"zeitschrift": "NJW", "jahr": 2020, "seite": 300,
                                  "gericht": "BVerfG"}]}
    t = executor.extrahiere_fundstellen(
        "BVerfG NJW 2020, 300.", _gerichte(), _zeitschriften(), [])[0]
    zustand, _, _ = executor.pruefe_fundstelle(t, registry)
    assert zustand == executor.ZUSTAND_VERIFIZIERT


def test_fundstelle_abweichend_bei_falschem_gericht():
    registry = {"normen": [], "entscheidungen": [],
                "fundstellen": [{"zeitschrift": "NJW", "jahr": 2020, "seite": 300,
                                  "gericht": "BVerfG"}]}
    t = executor.extrahiere_fundstellen(
        "BGH NJW 2020, 300.", _gerichte(), _zeitschriften(), [])[0]
    zustand, begruendung, _ = executor.pruefe_fundstelle(t, registry)
    assert zustand == executor.ZUSTAND_ABWEICHEND
    assert "Gericht" in begruendung


def test_fundstelle_nicht_pruefbar_ohne_registry_treffer():
    t = executor.extrahiere_fundstellen(
        "BVerfG NJW 2020, 300.", _gerichte(), _zeitschriften(), [])[0]
    zustand, _, _ = executor.pruefe_fundstelle(t, _leere_registry())
    assert zustand == executor.ZUSTAND_NICHT_PRUEFBAR


# --------------------------------------------------------------------------
# Gesamtreport (baue_report)
# --------------------------------------------------------------------------

def test_baue_report_end_to_end_mit_fixture():
    text = (FIXTURES / "text_gemischt.md").read_text(encoding="utf-8")
    registry = json.loads((FIXTURES / "registry_gemischt.json").read_text(encoding="utf-8"))
    report = executor.baue_report(text, registry, SCHEMA_DIR,
                                   quelle_datei="text_gemischt.md",
                                   registry_datei="registry_gemischt.json")
    assert report["meta"]["anzahl_zitate"] == len(report["zitate"])
    zustaende = {z["zustand"] for z in report["zitate"]}
    # Alle drei Zustände müssen im gemischten Fixture-Fall vorkommen.
    assert zustaende == {"verifiziert", "nicht_pruefbar", "abweichend"}
    summe = sum(report["zusammenfassung"].values())
    assert summe == report["meta"]["anzahl_zitate"]
    # IDs sind lückenlos und nach Zeile sortiert.
    assert [z["id"] for z in report["zitate"]] == list(range(1, len(report["zitate"]) + 1))
    zeilen = [z["zeile"] for z in report["zitate"]]
    assert zeilen == sorted(zeilen)


def test_baue_report_ohne_registry_ist_alles_nicht_pruefbar_ausser_formatwarnungen():
    text = "§ 203 StGB und BGH, Urt. v. 12.01.2023 – IX ZR 15/22."
    report = executor.baue_report(text, _leere_registry(), SCHEMA_DIR,
                                   quelle_datei="x", registry_datei=None)
    assert all(z["zustand"] == "nicht_pruefbar" for z in report["zitate"])
    assert report["zusammenfassung"]["verifiziert"] == 0
    assert report["zusammenfassung"]["abweichend"] == 0


# --------------------------------------------------------------------------
# CLI (P2: Datei rein → JSON-Report raus)
# --------------------------------------------------------------------------

def test_cli_erzeugt_gueltigen_json_report(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 203 StGB und § 999 BRAO.\n", encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "normen": [{"kuerzel": "StGB", "paragraph": "203"},
                   {"kuerzel": "BRAO", "paragraph": "43a"}],
        "entscheidungen": [], "fundstellen": []}), encoding="utf-8")
    ausgabe = tmp_path / "report.json"

    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe), "--registry", str(registry),
         "--output", str(ausgabe)],
        capture_output=True, text=True)

    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ausgabe.read_text(encoding="utf-8"))
    zustaende = {z["roh"]: z["zustand"] for z in report["zitate"]}
    assert zustaende["§ 203 StGB"] == "verifiziert"
    assert zustaende["§ 999 BRAO"] == "abweichend"


def test_cli_ohne_registry_funktioniert(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 203 StGB.\n", encoding="utf-8")

    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"), "--input", str(eingabe)],
        capture_output=True, text=True)

    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["zitate"][0]["zustand"] == "nicht_pruefbar"


def test_cli_fehlende_eingabedatei_gibt_exitcode_2(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(tmp_path / "existiert-nicht.md")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_cli_fehlende_registry_datei_gibt_exitcode_2(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 1 BGB.\n", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe), "--registry", str(tmp_path / "fehlt.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2


def test_schema_dateien_sind_gueltiges_json():
    for name in ("gesetzeskuerzel.json", "gerichte.json", "zeitschriften.json",
                 "beispiel-registry.json", "beispiel-report.json"):
        json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Review-Nacharbeit — KRITISCH: falsche ✅ (F1-F3)
# --------------------------------------------------------------------------

def test_f1_abs_ueber_registry_hinaus_bleibt_maximal_verifiziert_mit_warnung():
    # "§ 203 Abs. 99 StGB" — die Registry kennt nur Paragraphen-Granularität
    # (§ 203), Abs. 99 ist erfunden. Zustand darf trotzdem nicht heimlich als
    # vollständig geprüft durchgehen: verifiziert bleibt (Paragraph stimmt),
    # aber mit expliziter Formatwarnung und Begründung, die den geprüften
    # Umfang exakt benennt.
    kuerzel = {"StGB"}
    registry = {"normen": [{"kuerzel": "StGB", "paragraph": "203"}],
                "entscheidungen": [], "fundstellen": []}
    t = executor.extrahiere_normzitate("§ 203 Abs. 99 StGB")[0]
    zustand, begruendung, warnungen = executor.pruefe_norm(t, registry, kuerzel)
    assert zustand == executor.ZUSTAND_VERIFIZIERT
    assert "Abs./Satz/Nr./lit. nicht gegen Registry prüfbar" in warnungen
    assert "nur Paragraph 203 geprüft" in begruendung


def test_f1_readme_dokumentiert_abs_satz_nr_lit_blindstelle():
    inhalt = (SKILL_DIR / "schema" / "README.md").read_text(encoding="utf-8")
    grenzen_abschnitt = inhalt[inhalt.index("## Bewusst nicht erkannt"):]
    assert "Abs." in grenzen_abschnitt and "Satz" in grenzen_abschnitt
    assert "nicht" in grenzen_abschnitt.lower()


def test_f2_entscheidung_ohne_registry_datum_bleibt_verifiziert_mit_warnung():
    # "BGH, Urt. v. 01.01.1850 – IX ZR 15/22" — Registry-Eintrag hat kein
    # datum-Feld, das zitierte Datum wird also gar nicht geprüft.
    registry = {"normen": [], "fundstellen": [],
                "entscheidungen": [{"gericht": "BGH", "aktenzeichen": "IX ZR 15/22"}]}
    t = executor.extrahiere_gerichtsentscheidungen(
        "BGH, Urt. v. 01.01.1850 – IX ZR 15/22.", _gerichte())[0]
    zustand, begruendung, warnungen = executor.pruefe_entscheidung(t, registry)
    assert zustand == executor.ZUSTAND_VERIFIZIERT
    assert "Datum nicht in Registry hinterlegt, nicht geprüft" in warnungen
    assert "nur Gericht und Aktenzeichen geprüft" in begruendung


def test_f3_offener_ff_bereich_bleibt_maximal_verifiziert_mit_warnung():
    # "§§ 249 ff. BGB" — nur § 249 selbst ist gegen die Registry prüfbar, der
    # offene ff.-Bereich nicht.
    kuerzel = {"BGB"}
    registry = {"normen": [{"kuerzel": "BGB", "paragraph": "249"}],
                "entscheidungen": [], "fundstellen": []}
    t = executor.extrahiere_normzitate("§§ 249 ff. BGB")[0]
    zustand, begruendung, warnungen = executor.pruefe_norm(t, registry, kuerzel)
    assert zustand == executor.ZUSTAND_VERIFIZIERT
    assert "offener ff.-Bereich nicht prüfbar" in warnungen
    assert "nur Paragraph 249 geprüft" in begruendung


# --------------------------------------------------------------------------
# Review-Nacharbeit — HOCH: verschluckte/fehlgeparste Zitate (B1-B4)
# --------------------------------------------------------------------------

def test_b1_roemische_absatz_kurzschreibweise_erkennt_gesetz():
    # "§ 823 I BGB" durfte bisher gesetz="I" parsen und BGB verwerfen.
    kuerzel = {"BGB"}
    registry = {"normen": [{"kuerzel": "BGB", "paragraph": "823"}],
                "entscheidungen": [], "fundstellen": []}
    treffer = executor.extrahiere_normzitate("§ 823 I BGB")
    assert len(treffer) == 1
    t = treffer[0]
    assert t["gesetz"] == "BGB"
    assert t["paragraphen"] == ["823"]
    assert t["abs"] == "Abs. I"
    zustand, _, warnungen = executor.pruefe_norm(t, registry, kuerzel)
    assert zustand == executor.ZUSTAND_VERIFIZIERT
    assert "Abs./Satz/Nr./lit. nicht gegen Registry prüfbar" in warnungen


def test_b1_explizites_abs_roemisch_wird_ebenfalls_erkannt():
    treffer = executor.extrahiere_normzitate("§ 823 Abs. I BGB")
    assert len(treffer) == 1
    assert treffer[0]["gesetz"] == "BGB"
    assert treffer[0]["abs"] == "Abs. I"


def test_b1_roemische_sgb_buch_erkennung_bleibt_unveraendert():
    # Regressionsschutz: die B1-Änderung darf die bestehende SGB-Bücher-
    # Erkennung (Kürzel + römische Zahl, z. B. "SGB II") nicht brechen.
    treffer = executor.extrahiere_normzitate("§ 7 SGB II regelt dies.")
    assert len(treffer) == 1
    assert treffer[0]["gesetz"] == "SGB II"
    assert treffer[0]["abs"] is None


def test_b2_ivm_kette_erste_norm_wird_nicht_verschluckt():
    # "§ 823 i.V.m. § 249 BGB" — § 823 hat kein eigenes Kürzel und verschwand
    # bisher spurlos, weil das Gesetz-Segment mandatorisch war.
    kuerzel = {"BGB"}
    registry = {"normen": [{"kuerzel": "BGB", "paragraph": "823"},
                            {"kuerzel": "BGB", "paragraph": "249"}],
                "entscheidungen": [], "fundstellen": []}
    treffer = executor.extrahiere_normzitate("§ 823 i.V.m. § 249 BGB")
    rohe = {t["roh"] for t in treffer}
    assert "§ 823" in rohe
    assert "§ 249 BGB" in rohe
    erste = next(t for t in treffer if t["roh"] == "§ 823")
    assert erste["gesetz"] == "BGB"
    zustand, _, warnungen = executor.pruefe_norm(erste, registry, kuerzel)
    assert zustand == executor.ZUSTAND_VERIFIZIERT
    assert any("i.V.m.-Kette übernommen" in w for w in warnungen)


def test_b2_ivm_kette_ohne_registry_treffer_fuer_ererbtes_gesetz_wird_nicht_pruefbar():
    kuerzel = {"BGB"}
    treffer = executor.extrahiere_normzitate("§ 823 i.V.m. § 249 BGB")
    erste = next(t for t in treffer if t["roh"] == "§ 823")
    zustand, _, _ = executor.pruefe_norm(erste, _leere_registry(), kuerzel)
    assert zustand == executor.ZUSTAND_NICHT_PRUEFBAR


def test_b3_gericht_mit_mehrwortigem_ortsnamen_frankfurt_am_main():
    treffer = executor.extrahiere_gerichtsentscheidungen(
        "OLG Frankfurt am Main, Urt. v. 12.01.2023 – 7 U 12/18.", _gerichte())
    assert len(treffer) == 1
    assert treffer[0]["gericht"] == "OLG Frankfurt am Main"
    assert treffer[0]["aktenzeichen"] == "7 U 12/18"


def test_b3_gericht_mit_bindestrich_ortsnamen_baden_baden():
    treffer = executor.extrahiere_gerichtsentscheidungen(
        "OLG Baden-Baden, Urt. v. 12.01.2023 – 7 U 12/18.", _gerichte())
    assert len(treffer) == 1
    assert treffer[0]["gericht"] == "OLG Baden-Baden"


def test_b3_einfacher_ortsname_bleibt_unveraendert():
    treffer = executor.extrahiere_gerichtsentscheidungen(
        "OLG München, Beschl. v. 03.04.2019 – 7 U 12/18.", _gerichte())
    assert treffer[0]["gericht"] == "OLG München"


def test_b4_nbsp_zwischen_paragraph_und_zahl_wird_erkannt():
    text = "§ 203 StGB"
    treffer = executor.extrahiere_normzitate(text)
    assert len(treffer) == 1
    assert treffer[0]["gesetz"] == "StGB"
    assert treffer[0]["paragraphen"] == ["203"]


def test_b4_schmales_leerzeichen_zwischen_paragraph_und_zahl_wird_erkannt():
    text = "§ 203 StGB"
    treffer = executor.extrahiere_normzitate(text)
    assert len(treffer) == 1
    assert treffer[0]["gesetz"] == "StGB"


# --------------------------------------------------------------------------
# Review-Nacharbeit — MEDIUM: Robustheit (R1-R3)
# --------------------------------------------------------------------------

def test_r1_redos_lange_leerzeichenlaeufe_nach_gericht_bleibt_schnell():
    # Repro aus dem Review: "Siehe BGH" + 2000 Leerzeichen + "kein Az hier."
    # hing mit der alten Regex >20s. Härterer Fall laut Review-Vorgabe:
    # 50.000 Leerzeichen müssen in < 2s durchlaufen.
    text = "Siehe BGH" + " " * 50_000 + "kein Az hier."
    gerichte = _gerichte()
    start = time.perf_counter()
    treffer = executor.extrahiere_gerichtsentscheidungen(text, gerichte)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"ReDoS-Regression: {elapsed:.2f}s für 50.000 Leerzeichen"
    assert treffer == []


def test_r2_kaputtes_registry_json_gibt_exitcode_2_statt_traceback(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 1 BGB.\n", encoding="utf-8")
    registry = tmp_path / "kaputt.json"
    registry.write_text("{nicht valides json", encoding="utf-8")

    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe), "--registry", str(registry)],
        capture_output=True, text=True)

    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
    assert "JSON" in ergebnis.stderr


def test_r3_registry_norm_ohne_kuerzel_gibt_exitcode_2_statt_traceback(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 1 BGB.\n", encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "normen": [{"paragraph": "1"}], "entscheidungen": [], "fundstellen": []}),
        encoding="utf-8")

    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe), "--registry", str(registry)],
        capture_output=True, text=True)

    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
    assert "kuerzel" in ergebnis.stderr


def test_r3_registry_norm_ohne_paragraph_gibt_exitcode_2_statt_traceback(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 1 BGB.\n", encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "normen": [{"kuerzel": "BGB"}], "entscheidungen": [], "fundstellen": []}),
        encoding="utf-8")

    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe), "--registry", str(registry)],
        capture_output=True, text=True)

    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
    assert "paragraph" in ergebnis.stderr


def test_r3_registry_entscheidung_ohne_aktenzeichen_gibt_exitcode_2(tmp_path):
    eingabe = tmp_path / "eingabe.md"
    eingabe.write_text("§ 1 BGB.\n", encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "normen": [], "entscheidungen": [{"gericht": "BGH"}], "fundstellen": []}),
        encoding="utf-8")

    ergebnis = subprocess.run(
        [sys.executable, str(SKILL_DIR / "executor.py"),
         "--input", str(eingabe), "--registry", str(registry)],
        capture_output=True, text=True)

    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


# --------------------------------------------------------------------------
# Zusätzliche Tests aus dem Review: Golden-File & Usability-Warnung
# --------------------------------------------------------------------------

def test_beispiel_report_ist_golden_file_gegen_frischen_executor_lauf():
    """schema/beispiel-report.json inhaltlich (nicht nur als gültiges JSON)
    gegen eine frische Executor-Ausgabe aus beispiel-eingabe.md +
    beispiel-registry.json prüfen. Muss bei jeder Verhaltensänderung des
    Executors neu generiert werden (mit dem Executor, nicht von Hand)."""
    text = (SCHEMA_DIR / "beispiel-eingabe.md").read_text(encoding="utf-8")
    registry = json.loads((SCHEMA_DIR / "beispiel-registry.json").read_text(encoding="utf-8"))
    frisch = executor.baue_report(
        text, registry, SCHEMA_DIR,
        quelle_datei="plugins/legal-ops/skills/zitat-verifier-de/schema/beispiel-eingabe.md",
        registry_datei="plugins/legal-ops/skills/zitat-verifier-de/schema/beispiel-registry.json")
    erwartet = json.loads((SCHEMA_DIR / "beispiel-report.json").read_text(encoding="utf-8"))
    assert frisch == erwartet


def test_skill_md_warnt_prominent_vor_unvollstaendiger_registry():
    """Usability-Warnung aus dem Review: eine unvollständige Normen-Registry
    erzeugt systematisch falsche ❌ auf gültige Normen. Muss in SKILL.md
    prominent stehen (vor dem Ablauf-Abschnitt), nicht nur im Kleingedruckten
    von schema/README.md."""
    inhalt = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    ablauf_pos = inhalt.index("## Ablauf")
    warn_pos = inhalt.find("unvollständige")
    assert warn_pos != -1, "SKILL.md muss vor einer unvollständigen Normen-Registry warnen"
    assert warn_pos < ablauf_pos, "Warnung muss vor dem Ablauf-Abschnitt stehen (prominent)"
    assert "❌" in inhalt[warn_pos:ablauf_pos]
