"""Tests für core/adapters/sanktionslisten/parser.py (P4).

Prüft die Extraktion aus fiktiven EU-FSF- und UN-Fixtures: Primärname, Aliase,
Typ, Geburtsdatum, Listen-Referenz/Programm, Generierungsdatum — inkl.
Namensraum-Toleranz (EU-Fixture trägt einen Namensraum) und Format-Erkennung.
Keine echten Personendaten, kein Netzwerkzugriff.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "adapters"))

from sanktionslisten import (  # noqa: E402
    QUELLE_EU,
    QUELLE_UN,
    TYP_ORGANISATION,
    TYP_PERSON,
    ParserFehler,
    erkenne_format,
    parse_datei,
    parse_eu_fsf,
    parse_un_consolidated,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EU = FIXTURES / "eu-fsf-mini.xml"
UN = FIXTURES / "un-consolidated-mini.xml"


# --------------------------------------------------------------------------
# Format-Erkennung
# --------------------------------------------------------------------------

def test_erkenne_format_eu_trotz_namespace():
    assert erkenne_format(EU) == QUELLE_EU


def test_erkenne_format_un():
    assert erkenne_format(UN) == QUELLE_UN


def test_unbekannte_wurzel_fehler():
    with pytest.raises(ParserFehler):
        erkenne_format("<foobar/>")


def test_kaputtes_xml_fehler():
    with pytest.raises(ParserFehler):
        erkenne_format("<nichtgeschlossen>")


# --------------------------------------------------------------------------
# EU-FSF
# --------------------------------------------------------------------------

def test_eu_generierungsdatum_aus_metadaten():
    liste = parse_eu_fsf(EU)
    assert liste.quelle == QUELLE_EU
    assert liste.generierungsdatum == "2026-07-15"


def test_eu_person_primaername_und_aliase():
    liste = parse_eu_fsf(EU)
    person = next(e for e in liste.eintraege if e.referenz == "EU.9001.99")
    assert person.typ == TYP_PERSON
    assert person.primaername == "Max Mustermann"
    assert "Maximilian Mustremann" in person.aliase
    assert person.geburtsdatum == "1970-01-01"
    assert person.programm == "MUSTER-PROG"


def test_eu_organisation_typ_aus_enterprise_code():
    liste = parse_eu_fsf(EU)
    org = next(e for e in liste.eintraege if e.referenz == "EU.9002.99")
    assert org.typ == TYP_ORGANISATION
    assert org.primaername == "Musterhandel GmbH"
    assert "Musterhandel Import Export" in org.aliase


def test_eu_alle_eintraege_haben_namen():
    liste = parse_eu_fsf(EU)
    assert len(liste.eintraege) == 3
    assert all(e.primaername for e in liste.eintraege)


# --------------------------------------------------------------------------
# UN
# --------------------------------------------------------------------------

def test_un_generierungsdatum_aus_dategenerated():
    liste = parse_un_consolidated(UN)
    assert liste.quelle == QUELLE_UN
    assert liste.generierungsdatum == "2026-07-14"


def test_un_individual_name_aus_namensteilen():
    liste = parse_un_consolidated(UN)
    person = next(e for e in liste.eintraege if e.referenz == "MUi.9001")
    assert person.typ == TYP_PERSON
    assert person.primaername == "Hans Beispiel Mustermann"
    assert "Hans Mustermann" in person.aliase
    assert person.geburtsdatum == "1962-03-04"
    assert person.programm == "MUSTER"


def test_un_individual_nur_jahr_als_geburtsdatum():
    liste = parse_un_consolidated(UN)
    person = next(e for e in liste.eintraege if e.referenz == "MUi.9002")
    assert person.geburtsdatum == "1978"


def test_un_entity_name_und_alias():
    liste = parse_un_consolidated(UN)
    org = next(e for e in liste.eintraege if e.referenz == "MUe.9101")
    assert org.typ == TYP_ORGANISATION
    assert org.primaername == "Musterbau Aktiengesellschaft"
    assert "Musterbau AG" in org.aliase


def test_un_zaehlt_individuals_und_entities():
    liste = parse_un_consolidated(UN)
    assert len(liste.eintraege) == 3  # 2 Personen + 1 Organisation


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

def test_parse_datei_dispatch_eu():
    assert parse_datei(EU).quelle == QUELLE_EU


def test_parse_datei_dispatch_un():
    assert parse_datei(UN).quelle == QUELLE_UN


def test_parse_datei_fehlende_datei():
    with pytest.raises(ParserFehler):
        parse_datei(FIXTURES / "gibtsnicht.xml")


def test_falscher_parser_auf_falsche_wurzel():
    with pytest.raises(ParserFehler):
        parse_eu_fsf(UN)
    with pytest.raises(ParserFehler):
        parse_un_consolidated(EU)
