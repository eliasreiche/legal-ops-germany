"""Tests für core/calc/opos/rechner.py (Auswertungskern) und den Skill-
Executor (CLI: OPOS-CSV / EXTF rein, Report raus).

Deckt ab: offener Restbetrag, Tage seit Fälligkeit, Mahnstufen-Zuordnung
(Default + Override), Priorisierung, Decimal-Genauigkeit (nie float),
EXTF-Belegfeld-1-Aggregation, Zahlungsziel-Annahme, nicht-zuordenbare
Buchungen, Verzugszins-Lücke — plus CLI-Reject-Matrix (Exit 2, keine Datei).
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
CALC = REPO / "plugins" / "legal-ops" / "core" / "calc"
for p in (str(CALC),):
    if p not in sys.path:
        sys.path.insert(0, p)

from opos.rechner import (MAHNSTUFEN_DEFAULT, OposEingabeFehler, Posten,
                          bewerte, lade_mahnstufen_config, lade_opos_csv,
                          stapel_zu_posten)
from extf.parser import parse_extf_datei

EXECUTOR = REPO / "plugins" / "legal-ops" / "skills" / "honorar-mahnwesen" / "executor.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPOS_CSV = FIXTURES / "beispiel-opos.csv"
EXTF_FIXTURE = FIXTURES / "beispiel-buchungsstapel.csv"
STICHTAG = dt.date(2026, 7, 16)


# --------------------------------------------------------------------------
# Auswertungskern: bewerte()
# --------------------------------------------------------------------------

def _posten(**kw):
    basis = dict(rechnungsnummer="R1", betrag=Decimal("100.00"),
                 bereits_gezahlt=Decimal("0"), rechnungsdatum=dt.date(2026, 6, 1),
                 faelligkeitsdatum=dt.date(2026, 6, 15))
    basis.update(kw)
    return Posten(**basis)


def test_offener_rest_und_tage():
    r = bewerte([_posten(betrag=Decimal("1190.00"), bereits_gezahlt=Decimal("190.00"))], STICHTAG)
    p = r["offene_posten"][0]
    assert p["offener_rest"] == "1000.00"
    assert p["tage_seit_faelligkeit"] == (STICHTAG - dt.date(2026, 6, 15)).days == 31


def test_prioritaet_betrag_mal_alter():
    r = bewerte([_posten(betrag=Decimal("1000.00"), bereits_gezahlt=Decimal("0"),
                         faelligkeitsdatum=dt.date(2026, 6, 15))], STICHTAG)
    # 1000 * 31 Tage
    assert r["offene_posten"][0]["prioritaet"] == "31000.00"


def test_mahnstufen_default_schwellen():
    faelle = {
        dt.date(2026, 7, 20): "offen_nicht_faellig",   # in der Zukunft
        dt.date(2026, 7, 16): "zahlungserinnerung",    # heute fällig -> 0 Tage
        dt.date(2026, 7, 2): "1_mahnung",              # 14 Tage
        dt.date(2026, 6, 16): "2_mahnung",             # 30 Tage
    }
    for faellig, erwartet in faelle.items():
        r = bewerte([_posten(faelligkeitsdatum=faellig)], STICHTAG)
        posten = (r["offene_posten"] + r["ausgeglichene_posten"])[0]
        assert posten["mahnstufe"] == erwartet, (faellig, posten["mahnstufe"])


def test_mahnstufe_override_config():
    cfg = lade_mahnstufen_config({"stufen": [
        {"ab_tage": 7, "stufe": "sofort", "bezeichnung": "Sofort mahnen"},
        {"ab_tage": 0, "stufe": "erinnerung", "bezeichnung": "Erinnerung"},
    ]})
    r = bewerte([_posten(faelligkeitsdatum=dt.date(2026, 7, 2))], STICHTAG, cfg)  # 14 Tage
    assert r["offene_posten"][0]["mahnstufe"] == "sofort"


def test_ausgeglichener_posten_nicht_in_offen():
    r = bewerte([_posten(betrag=Decimal("100.00"), bereits_gezahlt=Decimal("100.00"))], STICHTAG)
    assert r["zusammenfassung"]["anzahl_offen"] == 0
    assert r["zusammenfassung"]["anzahl_ausgeglichen"] == 1


def test_sortierung_nach_prioritaet_absteigend():
    posten = [
        _posten(rechnungsnummer="klein", betrag=Decimal("100.00"), faelligkeitsdatum=dt.date(2026, 7, 1)),
        _posten(rechnungsnummer="gross", betrag=Decimal("5000.00"), faelligkeitsdatum=dt.date(2026, 6, 1)),
    ]
    r = bewerte(posten, STICHTAG)
    assert [p["rechnungsnummer"] for p in r["offene_posten"]] == ["gross", "klein"]


def test_ohne_faelligkeit_am_ende_und_unbestimmt():
    posten = [
        _posten(rechnungsnummer="mit", faelligkeitsdatum=dt.date(2026, 6, 1)),
        _posten(rechnungsnummer="ohne", faelligkeitsdatum=None),
    ]
    r = bewerte(posten, STICHTAG)
    assert r["offene_posten"][-1]["rechnungsnummer"] == "ohne"
    assert r["offene_posten"][-1]["tage_seit_faelligkeit"] is None
    assert r["offene_posten"][-1]["mahnstufe"] == "faelligkeit_unbekannt"
    assert r["offene_posten"][-1]["prioritaet"] is None


def test_verzugszins_immer_luecke_nie_zahl():
    r = bewerte([_posten()], STICHTAG)
    hinweis = r["offene_posten"][0]["verzugszins_hinweis"]
    assert "§ 288 BGB" in hinweis
    assert not any(c.isdigit() for c in hinweis.replace("288", "").replace("286", ""))


def test_keine_float_im_report():
    r = bewerte([_posten(betrag=Decimal("0.10"), bereits_gezahlt=Decimal("0"))], STICHTAG)
    text = json.dumps(r)
    # Alle Geldwerte sind Strings; kein float-Artefakt wie 0.30000000000000004.
    assert '"offener_rest": "0.10"' in text


# --------------------------------------------------------------------------
# OPOS-CSV laden
# --------------------------------------------------------------------------

def test_lade_opos_csv_fixture():
    posten = lade_opos_csv(OPOS_CSV)
    assert len(posten) == 4
    assert posten[0].rechnungsnummer == "RE-2026-001"
    assert posten[0].betrag == Decimal("1190.00")
    assert posten[1].bereits_gezahlt == Decimal("1000.00")
    assert posten[3].bereits_gezahlt == Decimal("0")  # leer -> 0


def test_csv_komma_dezimal():
    csv = ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\n"
           "R1;2026-01-01;2026-01-15;1234,56\n")
    assert lade_opos_csv(csv)[0].betrag == Decimal("1234.56")


@pytest.mark.parametrize("csv,enthaelt", [
    ("rechnungsnummer;rechnungsdatum;betrag\nR1;2026-01-01;10,00\n", "faelligkeitsdatum"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag;xtra\nR1;2026-01-01;2026-01-15;10,00;y\n", "unbekannte"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\nR1;2026-01-01;2026-01-15;1.234,56\n", "mehrdeutig"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\nR1;2026-01-01;2026-01-15;-5,00\n", "> 0"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\nR1;2026-01-15;2026-01-01;10,00\n", "liegt vor"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\n;2026-01-01;2026-01-15;10,00\n", "rechnungsnummer"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\nR1;2026-01-01;2026-01-15;10,00\nR1;2026-02-01;2026-02-15;5,00\n", "doppelt"),
    ("rechnungsnummer;rechnungsdatum;faelligkeitsdatum;betrag\nR1;2026-13-01;2026-01-15;10,00\n", "ISO-Datum"),
])
def test_csv_reject(csv, enthaelt):
    with pytest.raises(OposEingabeFehler) as exc:
        lade_opos_csv(csv)
    assert enthaelt in str(exc.value)


# --------------------------------------------------------------------------
# EXTF -> Posten (Belegfeld-1-Aggregation)
# --------------------------------------------------------------------------

def test_extf_aggregation_belegfeld1():
    stapel = parse_extf_datei(EXTF_FIXTURE)
    posten, nicht_zuordenbar = stapel_zu_posten(stapel, zahlungsziel_tage=14)
    nach_nr = {p.rechnungsnummer: p for p in posten}
    # RE-2026-500: Soll 1190 - Haben 400 = 790 offen
    assert (nach_nr["RE-2026-500"].betrag - nach_nr["RE-2026-500"].bereits_gezahlt) == Decimal("790.00")
    # Fälligkeit = frühestes Soll-Belegdatum (2026-04-01) + 14 Tage
    assert nach_nr["RE-2026-500"].faelligkeitsdatum == dt.date(2026, 4, 15)
    # RE-2026-501: nur Soll 595
    assert nach_nr["RE-2026-501"].betrag == Decimal("595.00")
    # Mandant nicht im EXTF -> Lücke
    assert nach_nr["RE-2026-500"].mandant is None
    # Buchung ohne Belegfeld1 -> nicht zuordenbar
    assert len(nicht_zuordenbar) == 1
    assert "nicht zuordenbar" in nicht_zuordenbar[0]["grund"]


def test_extf_skonto_auf_haben_verrechnet():
    # golden erwartet_2: RE-2026-101 nur Haben 238,95 + Skonto 5,00 -> -243,95
    stapel = parse_extf_datei(REPO / "plugins" / "legal-ops" / "skills" /
                              "datev-export" / "tests" / "golden" / "erwartet_2.csv")
    posten, _ = stapel_zu_posten(stapel, zahlungsziel_tage=14)
    nach_nr = {p.rechnungsnummer: p for p in posten}
    rest = nach_nr["RE-2026-101"].betrag - nach_nr["RE-2026-101"].bereits_gezahlt
    assert rest == Decimal("-243.95")


def test_extf_zahlungsziel_negativ_reject():
    stapel = parse_extf_datei(EXTF_FIXTURE)
    with pytest.raises(OposEingabeFehler):
        stapel_zu_posten(stapel, zahlungsziel_tage=-1)


# --------------------------------------------------------------------------
# Mahnstufen-Config-Validierung
# --------------------------------------------------------------------------

def test_mahnstufen_default_wenn_none():
    assert lade_mahnstufen_config(None) == MAHNSTUFEN_DEFAULT


@pytest.mark.parametrize("cfg", [
    [], {"stufen": []},
    [{"ab_tage": -1, "stufe": "x", "bezeichnung": "y"}],
    [{"ab_tage": 5, "stufe": "", "bezeichnung": "y"}],
    [{"ab_tage": "viel", "stufe": "x", "bezeichnung": "y"}],
    "kein objekt",
])
def test_mahnstufen_config_reject(cfg):
    with pytest.raises(OposEingabeFehler):
        lade_mahnstufen_config(cfg)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cli(args, tmp_path, *, mit_output=True):
    output = tmp_path / "report.json"
    cmd = [sys.executable, str(EXECUTOR)] + args
    if mit_output:
        cmd += ["--output", str(output)]
    erg = subprocess.run(cmd, capture_output=True, text=True)
    return erg, output


def test_cli_opos_csv_erfolg(tmp_path):
    erg, output = _cli(["--opos-csv", str(OPOS_CSV), "--stichtag", "2026-07-16"], tmp_path)
    assert erg.returncode == 0, erg.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["zusammenfassung"]["anzahl_offen"] == 3
    assert report["zusammenfassung"]["summe_offen"] == "3020.00"
    assert report["meta"]["quelle_format"] == "opos-csv"
    # höchste Priorität zuerst
    assert report["offene_posten"][0]["rechnungsnummer"] == "RE-2026-001"


def test_cli_extf_erfolg(tmp_path):
    erg, output = _cli(["--extf", str(EXTF_FIXTURE), "--stichtag", "2026-07-16",
                        "--zahlungsziel-tage", "14"], tmp_path)
    assert erg.returncode == 0, erg.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["meta"]["quelle_format"] == "extf"
    assert report["meta"]["zahlungsziel_tage"] == 14
    assert report["zusammenfassung"]["anzahl_nicht_zuordenbar"] == 1


def test_cli_idempotenz_gleiche_eingabe_gleicher_report(tmp_path):
    erg1, out1 = _cli(["--opos-csv", str(OPOS_CSV), "--stichtag", "2026-07-16"], tmp_path)
    out2 = tmp_path / "report2.json"
    subprocess.run([sys.executable, str(EXECUTOR), "--opos-csv", str(OPOS_CSV),
                    "--stichtag", "2026-07-16", "--output", str(out2)], check=True)
    assert out1.read_text() == out2.read_text()


def test_cli_stichtag_pflicht(tmp_path):
    erg, _ = _cli(["--opos-csv", str(OPOS_CSV)], tmp_path, mit_output=False)
    assert erg.returncode == 2
    assert "stichtag" in erg.stderr.lower()


def test_cli_genau_eine_quelle(tmp_path):
    erg, _ = _cli(["--opos-csv", str(OPOS_CSV), "--extf", str(EXTF_FIXTURE),
                   "--stichtag", "2026-07-16"], tmp_path, mit_output=False)
    assert erg.returncode == 2  # mutually exclusive


def test_cli_reject_csv_keine_datei(tmp_path):
    erg, output = _cli(["--opos-csv", str(tmp_path / "gibtsnicht.csv"),
                        "--stichtag", "2026-07-16"], tmp_path)
    assert erg.returncode == 2
    assert "nicht gefunden" in erg.stderr
    assert "Traceback" not in erg.stderr
    assert not output.exists()


def test_cli_reject_ungueltiger_stichtag(tmp_path):
    erg, output = _cli(["--opos-csv", str(OPOS_CSV), "--stichtag", "16.07.2026"], tmp_path)
    assert erg.returncode == 2
    assert "Traceback" not in erg.stderr
    assert not output.exists()


def test_cli_reject_kaputte_extf_mit_zeilenangabe(tmp_path):
    kaputt = tmp_path / "kaputt.csv"
    kaputt.write_bytes(b'"CSV";1;1;"X"\r\n')
    erg, output = _cli(["--extf", str(kaputt), "--stichtag", "2026-07-16"], tmp_path)
    assert erg.returncode == 2
    assert "Traceback" not in erg.stderr
    assert not output.exists()


def test_cli_mahnstufen_config(tmp_path):
    cfg = tmp_path / "stufen.json"
    cfg.write_text(json.dumps({"stufen": [
        {"ab_tage": 7, "stufe": "sofort", "bezeichnung": "Sofort"},
        {"ab_tage": 0, "stufe": "erinnerung", "bezeichnung": "Erinnerung"},
    ]}), encoding="utf-8")
    erg, output = _cli(["--opos-csv", str(OPOS_CSV), "--stichtag", "2026-07-16",
                        "--mahnstufen-config", str(cfg)], tmp_path)
    assert erg.returncode == 0, erg.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["offene_posten"][0]["mahnstufe"] == "sofort"
