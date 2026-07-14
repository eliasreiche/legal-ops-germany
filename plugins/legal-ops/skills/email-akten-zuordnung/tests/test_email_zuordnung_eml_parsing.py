"""Tests für executor.py — EML-Parsing (P4).

Deckt ab: RFC-2047-kodierte Umlaut-Header (Subject/From), fehlende Header
(From/Subject/Date), Absender ohne Anzeigename, Datum-Extraktion sowie die
PII-Grenze (Textauszug-Truncation auf TEXTAUSZUG_MAX_LEN). CLI-Verhalten
(subprocess) steht in test_email_zuordnung_executor_cli.py.
"""
from __future__ import annotations

import importlib.util
import sys
from email.message import EmailMessage
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = REPO / "plugins" / "legal-ops" / "skills" / "email-akten-zuordnung"

# Eindeutiger Modul-Name (nicht "executor") - siehe Begründung in
# interessenkollision-check/tests/test_konflikt_executor.py: mehrere Skills
# haben je ein eigenes executor.py, ein generischer Name würde im
# sys.modules-Cache kollidieren.
_SPEC = importlib.util.spec_from_file_location(
    "email_akten_zuordnung_executor", SKILL_DIR / "executor.py")
executor = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = executor
_SPEC.loader.exec_module(executor)


def _eml_bytes(msg: EmailMessage) -> bytes:
    return bytes(msg)


def _schreibe_eml(tmp_path: Path, name: str, msg: EmailMessage) -> Path:
    pfad = tmp_path / name
    pfad.write_bytes(_eml_bytes(msg))
    return pfad


# --------------------------------------------------------------------------
# RFC-2047-Umlaut-Header
# --------------------------------------------------------------------------

def test_rfc2047_umlaut_header_werden_dekodiert(tmp_path):
    msg = EmailMessage()
    msg["From"] = "Müller Rechtsanwälte <mueller@beispiel.example>"
    msg["To"] = "kanzlei@beispiel.example"
    msg["Subject"] = "Kündigung des Vertrags über Bürobedarf"
    msg["Date"] = "Wed, 24 Jun 2026 11:45:00 +0200"
    msg.set_content("Sehr geehrte Damen und Herren, mit freundlichen Grüßen")

    pfad = _schreibe_eml(tmp_path, "umlaut.eml", msg)
    # Sicherstellen, dass die Header tatsächlich RFC-2047-kodiert auf der
    # Platte liegen (kein Verstecken des Encodings durch set_content-Defaults).
    roh = pfad.read_bytes()
    assert b"=?utf-8?q?" in roh.lower() or b"=?utf-8?b?" in roh.lower()

    eintrag = executor.parse_eml_datei(pfad)
    assert eintrag["absender_name"] == "Müller Rechtsanwälte"
    assert eintrag["absender_adresse"] == "mueller@beispiel.example"
    assert eintrag["betreff"] == "Kündigung des Vertrags über Bürobedarf"
    assert eintrag["datum"] == "2026-06-24"
    assert "Grüßen" in eintrag["textauszug"]


# --------------------------------------------------------------------------
# Fehlende Felder
# --------------------------------------------------------------------------

def test_fehlender_from_header(tmp_path):
    msg = EmailMessage()
    msg["Subject"] = "Ohne Absender"
    msg["Date"] = "Mon, 01 Jun 2026 08:00:00 +0200"
    msg.set_content("Text ohne From-Header.")
    pfad = _schreibe_eml(tmp_path, "kein_from.eml", msg)

    eintrag = executor.parse_eml_datei(pfad)
    assert eintrag["absender_name"] == ""
    assert eintrag["absender_adresse"] == ""
    assert eintrag["betreff"] == "Ohne Absender"


def test_fehlender_subject_und_date_header(tmp_path):
    msg = EmailMessage()
    msg["From"] = "Erika Mustermann <erika@beispiel.example>"
    msg.set_content("Text ohne Subject/Date.")
    pfad = _schreibe_eml(tmp_path, "kein_subject.eml", msg)

    eintrag = executor.parse_eml_datei(pfad)
    assert eintrag["betreff"] == ""
    assert eintrag["datum"] is None


def test_absender_ohne_anzeigename_faellt_auf_adresse_zurueck(tmp_path):
    msg = EmailMessage()
    msg["From"] = "nur-adresse@beispiel.example"
    msg["Subject"] = "Test"
    msg.set_content("Text.")
    pfad = _schreibe_eml(tmp_path, "nur_adresse.eml", msg)

    eintrag = executor.parse_eml_datei(pfad)
    assert eintrag["absender_adresse"] == "nur-adresse@beispiel.example"
    assert eintrag["absender_name"] in ("nur-adresse@beispiel.example", "")


# --------------------------------------------------------------------------
# PII-Grenze: Textauszug-Truncation
# --------------------------------------------------------------------------

def test_textauszug_wird_auf_max_laenge_gekuerzt(tmp_path):
    langer_text = "A" * (executor.TEXTAUSZUG_MAX_LEN + 250)
    msg = EmailMessage()
    msg["From"] = "Absender <a@beispiel.example>"
    msg["Subject"] = "Langer Text"
    msg.set_content(langer_text)
    pfad = _schreibe_eml(tmp_path, "lang.eml", msg)

    eintrag = executor.parse_eml_datei(pfad)
    assert len(eintrag["textauszug"]) == executor.TEXTAUSZUG_MAX_LEN
    assert eintrag["textauszug_gekuerzt"] is True


def test_textauszug_kurzer_text_nicht_gekuerzt(tmp_path):
    msg = EmailMessage()
    msg["From"] = "Absender <a@beispiel.example>"
    msg["Subject"] = "Kurzer Text"
    msg.set_content("Kurzer Inhalt.")
    pfad = _schreibe_eml(tmp_path, "kurz.eml", msg)

    eintrag = executor.parse_eml_datei(pfad)
    assert eintrag["textauszug_gekuerzt"] is False
    assert "Kurzer Inhalt." in eintrag["textauszug"]


def test_voller_body_erscheint_nie_im_report_ueber_textauszug_hinaus(tmp_path):
    """PII-Minimierung: der zurückgegebene Metadaten-Eintrag hat kein
    Volltext-Feld, nur den (ggf. gekürzten) `textauszug`."""
    msg = EmailMessage()
    msg["From"] = "Absender <a@beispiel.example>"
    msg["Subject"] = "Geheimnisträchtiger Betreff"
    msg.set_content("VERTRAULICH " * 100)
    pfad = _schreibe_eml(tmp_path, "vertraulich.eml", msg)

    eintrag = executor.parse_eml_datei(pfad)
    assert set(eintrag.keys()) == {
        "quelle", "absender_name", "absender_adresse", "empfaenger", "cc",
        "betreff", "textauszug", "textauszug_gekuerzt", "datum",
    }
    assert len(eintrag["textauszug"]) <= executor.TEXTAUSZUG_MAX_LEN


# --------------------------------------------------------------------------
# --eml auf Verzeichnis (sortiert)
# --------------------------------------------------------------------------

def test_lese_eml_quelle_verzeichnis_sortiert(tmp_path):
    for name, betreff in (("b.eml", "B-Mail"), ("a.eml", "A-Mail")):
        msg = EmailMessage()
        msg["From"] = "Absender <a@beispiel.example>"
        msg["Subject"] = betreff
        msg.set_content("Text.")
        _schreibe_eml(tmp_path, name, msg)

    eintraege = executor.lese_eml_quelle(tmp_path)
    assert [e["betreff"] for e in eintraege] == ["A-Mail", "B-Mail"]


def test_lese_eml_quelle_leeres_verzeichnis_ist_eingabefehler(tmp_path):
    import pytest
    with pytest.raises(executor.EingabeFehler):
        executor.lese_eml_quelle(tmp_path)


def test_lese_eml_quelle_pfad_existiert_nicht(tmp_path):
    import pytest
    with pytest.raises(executor.EingabeFehler):
        executor.lese_eml_quelle(tmp_path / "nicht-vorhanden.eml")
