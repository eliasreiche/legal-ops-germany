"""Tests für plugins/legal-ops/skills/posteingang-ocr-verteilung/executor.py —
Schema-Prüfung, Provenienz-Normalisierung und die deterministische Ableitung
von `fristrelevant`.

Deckt ab: Pflichtschlüssel, Lücken-Disziplin (eingang.*), ISO-Datumsprüfung,
`aktenzeichen_fremd`/`aktenzeichen_eigen` (null statt leerer String),
Konsistenz von `fristindikatoren[].schluesselwort` zu `quelle_zitat`,
Datums-/Aktenzeichen-/Zitat-Normalisierung und Provenienz (belegt/
nicht_belegt), sowie `bestimme_fristrelevant()` (zählt nur belegte
Indikatoren).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"

# Eindeutiger Modulname, damit sich der Modulname nicht mit gleichnamigen
# Executors anderer Skills im selben pytest-Prozess überschreibt.
_spec = importlib.util.spec_from_file_location("posteingang_ocr_verteilung_executor", EXECUTOR)
executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(executor)


def _basis_eingang() -> dict:
    """Minimal gültiger Eingang, in den Tests gezielt mutiert."""
    return {
        "eingang": {
            "absender": "Muster AG",
            "datum_schreiben": "2026-07-01",
            "aktenzeichen_fremd": None,
            "aktenzeichen_eigen": None,
            "betreff": "Testbetreff",
        },
        "fristindikatoren": [],
        "luecken": [],
    }


# --------------------------------------------------------------------------
# Schema — Pflichtschlüssel / Lücken-Disziplin
# --------------------------------------------------------------------------

def test_schema_ok_fuer_minimalen_eingang():
    assert executor.pruefe_schema(_basis_eingang()) == []


def test_schema_wurzel_muss_dict_sein():
    fehler = executor.pruefe_schema([])
    assert fehler == ["Wurzel: eingang.json muss ein JSON-Objekt sein"]


def test_schema_pflichtschluessel_fehlt():
    eingang = _basis_eingang()
    del eingang["luecken"]
    fehler = executor.pruefe_schema(eingang)
    assert any("luecken" in f and "fehlt" in f for f in fehler)


def test_schema_leeres_pflichtfeld_ohne_luecke_ist_fehler():
    eingang = _basis_eingang()
    eingang["eingang"]["absender"] = ""
    fehler = executor.pruefe_schema(eingang)
    assert any("eingang.absender" in f and "Lücken-Disziplin" in f for f in fehler)


def test_schema_leeres_pflichtfeld_mit_luecke_ist_ok():
    eingang = _basis_eingang()
    eingang["eingang"]["absender"] = ""
    eingang["luecken"] = [{"feld": "eingang.absender", "grund": "unleserlich"}]
    assert executor.pruefe_schema(eingang) == []


def test_schema_ungueltiges_iso_datum():
    eingang = _basis_eingang()
    eingang["eingang"]["datum_schreiben"] = "01.07.2026"
    fehler = executor.pruefe_schema(eingang)
    assert any("kein gültiges ISO-Datum" in f for f in fehler)


def test_schema_datum_null_mit_luecke_ist_ok():
    eingang = _basis_eingang()
    eingang["eingang"]["datum_schreiben"] = None
    eingang["luecken"] = [{"feld": "eingang.datum_schreiben", "grund": "nicht lesbar"}]
    assert executor.pruefe_schema(eingang) == []


def test_schema_aktenzeichen_leerer_string_ist_fehler():
    eingang = _basis_eingang()
    eingang["eingang"]["aktenzeichen_fremd"] = "   "
    fehler = executor.pruefe_schema(eingang)
    assert any("muss `null` sein" in f for f in fehler)


def test_schema_aktenzeichen_null_ist_kein_fehler():
    eingang = _basis_eingang()
    eingang["eingang"]["aktenzeichen_fremd"] = None
    assert executor.pruefe_schema(eingang) == []


# --------------------------------------------------------------------------
# Schema — Frist-Indikatoren
# --------------------------------------------------------------------------

def test_fristindikator_ohne_zitat_ist_fehler():
    eingang = _basis_eingang()
    eingang["fristindikatoren"] = [{"schluesselwort": "Frist", "quelle_zitat": ""}]
    fehler = executor.pruefe_schema(eingang)
    assert any("quelle_zitat" in f for f in fehler)


def test_fristindikator_schluesselwort_nicht_im_zitat_ist_fehler():
    eingang = _basis_eingang()
    eingang["fristindikatoren"] = [
        {"schluesselwort": "Frist", "quelle_zitat": "bitte um Zahlung binnen 14 Tagen"}]
    fehler = executor.pruefe_schema(eingang)
    assert any("kommt nicht in" in f for f in fehler)


def test_fristindikator_konsistent_ist_ok():
    eingang = _basis_eingang()
    eingang["fristindikatoren"] = [
        {"schluesselwort": "Frist", "quelle_zitat": "innerhalb einer Frist von 14 Tagen"}]
    assert executor.pruefe_schema(eingang) == []


# --------------------------------------------------------------------------
# Normalisierung / Provenienz
# --------------------------------------------------------------------------

def _quelle(text: str) -> list[tuple[str, list[str]]]:
    return [("scan.txt", text.splitlines())]


def test_datum_kanon_iso_und_deutsch_sind_gleich():
    assert executor._datum_kanon_wert("2026-07-01") == "2026-07-01"
    assert executor._datum_kanon_wert("01.07.2026") == "2026-07-01"
    assert executor._datum_kanon_wert("1.7.2026") == "2026-07-01"


def test_aktenzeichen_whitespace_wird_kollabiert():
    assert executor._ws_collapse("VB-2026  \t 77") == "VB-2026 77"


def test_beleg_datum_andere_schreibweise_wird_gefunden():
    quellen = _quelle("Hamburg, 01.07.2026")
    beleg = executor.finde_beleg("2026-07-01", "datum", quellen)
    assert beleg is not None
    assert beleg["zeile"] == 1


def test_beleg_aktenzeichen_nicht_gefunden():
    quellen = _quelle("Ohne jeden Bezug.")
    assert executor.finde_beleg("2026-001", "aktenzeichen", quellen) is None


def test_beleg_zitat_wird_als_teilstring_gefunden():
    quellen = _quelle("Wir fordern Sie binnen 14 Tagen zur Zahlung auf.")
    beleg = executor.finde_beleg("binnen 14 Tagen zur Zahlung", "zitat", quellen)
    assert beleg is not None


def test_provenienz_meldet_nicht_belegten_wert():
    eingang = _basis_eingang()
    eingang["eingang"]["aktenzeichen_fremd"] = "ERFUNDEN-123"
    provenienz = executor.pruefe_provenienz(eingang, _quelle("Kein Aktenzeichen hier."))
    treffer = [p for p in provenienz if p["pfad"] == "eingang.aktenzeichen_fremd"]
    assert treffer[0]["status"] == executor.STATUS_NICHT_BELEGT


# --------------------------------------------------------------------------
# fristrelevant — deterministisch, zählt nur belegte Indikatoren
# --------------------------------------------------------------------------

def test_fristrelevant_true_wenn_indikator_belegt():
    eingang = _basis_eingang()
    eingang["fristindikatoren"] = [
        {"schluesselwort": "Mahnung", "quelle_zitat": "Mahnung wegen ausstehender Zahlung"}]
    quellen = _quelle("Mahnung wegen ausstehender Zahlung")
    provenienz = executor.pruefe_provenienz(eingang, quellen)
    assert executor.bestimme_fristrelevant(provenienz) is True


def test_fristrelevant_false_wenn_indikator_nicht_belegt():
    """Ein vom Modell behaupteter, aber im Text nicht auffindbarer Indikator
    darf das Flag NICHT setzen (P3 — verhindert erfundene Fristnennungen)."""
    eingang = _basis_eingang()
    eingang["fristindikatoren"] = [
        {"schluesselwort": "Mahnung", "quelle_zitat": "Mahnung wegen ausstehender Zahlung"}]
    quellen = _quelle("Ein völlig anderer Text ohne jeden Bezug.")
    provenienz = executor.pruefe_provenienz(eingang, quellen)
    assert executor.bestimme_fristrelevant(provenienz) is False


def test_fristrelevant_false_wenn_keine_indikatoren():
    eingang = _basis_eingang()
    provenienz = executor.pruefe_provenienz(eingang, _quelle("Neutraler Text."))
    assert executor.bestimme_fristrelevant(provenienz) is False
