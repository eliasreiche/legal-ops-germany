#!/usr/bin/env python3
"""sanktionslisten/parser — Parser für offizielle EU-/UN-Sanktionslisten (P2/P3).

Wandelt die zwei offiziellen, öffentlich abrufbaren XML-Formate in eine
einheitliche, matching-fertige Datenstruktur (`Sanktionsliste` /
`SanktionsEintrag`). Reine Standardbibliothek (`xml.etree.ElementTree`), kein
Netzwerkzugriff, keine Persistierung — der Abruf ist bewusst in `abruf.py`
getrennt (Deterministik-Grenze, CONVENTIONS.md P3: das Screening arbeitet nur
auf lokalen Dateien).

Zwei Formate:

  * **EU-Konsolidierte Finanzsanktionsliste** (FSF „full file", XML-Export von
    webgate.ec.europa.eu). Wurzel `<export …>` in einem Namensraum, darunter
    `<sanctionEntity>` je Eintrag mit `<subjectType code="person|enterprise">`,
    einem oder mehreren `<nameAlias wholeName firstName lastName …>`, optional
    `<birthdate birthdate year month day>` und `<regulation programme
    numberTitle publicationDate>`. Das Listen-Generierungsdatum steht als
    Attribut `generationDate` an der Wurzel.
  * **UN Security Council Consolidated List** (XML von scsanctions.un.org).
    Wurzel `<CONSOLIDATED_LIST dateGenerated="…">` mit `<INDIVIDUALS>` /
    `<ENTITIES>`; je Person `<INDIVIDUAL>` mit `<FIRST_NAME>…<FOURTH_NAME>`,
    `<INDIVIDUAL_ALIAS><ALIAS_NAME>`, `<INDIVIDUAL_DATE_OF_BIRTH>` und
    `<REFERENCE_NUMBER>` / `<UN_LIST_TYPE>`; je Organisation `<ENTITY>`
    analog (Name in `<FIRST_NAME>`, Aliase `<ENTITY_ALIAS>`).

Schema-Herkunft (verifiziert 2026-07-16): Die UN-Struktur ist gegen die
Live-Datei geprüft; die EU-FSF-Struktur (Element-/Attributnamen) gegen den
öffentlichen Referenz-Parser des OpenSanctions-Projekts (`zavod.shed.fsf`),
der dieselben Tags liest. Beide Parser sind bewusst **namensraum-tolerant**
(Vergleich über den lokalen Tag-Namen, siehe `_lokal`), damit ein
Namensraum-Präfix oder eine Schema-Minor-Version die Extraktion nicht bricht.

Grenzen (dokumentiert):
  * Nicht-lateinische Originalschreibweisen (arab./kyrill. Skript) werden
    unverändert übernommen, aber das Downstream-Matching (Kölner Phonetik,
    lateinisches Fuzzy) ist dafür nicht ausgelegt — Transliterations-Grenze,
    siehe SKILL.md `haftung`.
  * Extrahiert werden nur die für ein Namens-Screening nötigen Felder
    (Primärname, Aliase, Typ, Geburtsdatum, Referenz/Programm). Adressen,
    Staatsangehörigkeit, Ausweisnummern usw. werden bewusst nicht gelesen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

QUELLE_EU = "EU-FSF"
QUELLE_UN = "UN"

TYP_PERSON = "person"
TYP_ORGANISATION = "organisation"
TYP_UNBEKANNT = "unbekannt"

_ISO_DATUM_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


class ParserFehler(Exception):
    """Strukturell nicht verwertbare Listen-Datei (unbekannte Wurzel, kaputtes XML)."""


@dataclass
class SanktionsEintrag:
    """Ein Listeneintrag, reduziert auf die Screening-relevanten Felder."""
    quelle: str                 # QUELLE_EU | QUELLE_UN
    referenz: str               # euReferenceNumber / REFERENCE_NUMBER (kann leer sein)
    programm: str | None        # regulation/@programme bzw. UN_LIST_TYPE
    typ: str                    # person | organisation | unbekannt
    primaername: str
    aliase: list[str] = field(default_factory=list)
    geburtsdatum: str | None = None


@dataclass
class Sanktionsliste:
    """Eine geparste Liste inkl. ihres XML-Generierungsdatums (Frische-Gate)."""
    quelle: str
    generierungsdatum: str | None    # aus den XML-Metadaten, None = fehlt
    eintraege: list[SanktionsEintrag]


# --------------------------------------------------------------------------
# Namensraum-Toleranz
# --------------------------------------------------------------------------

def _lokal(tag: str) -> str:
    """Lokaler Tag-Name ohne '{namespace}'-Präfix (etree-Notation)."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _finde_alle(element: ET.Element, name: str) -> list[ET.Element]:
    """Direkte Kinder mit lokalem Tag-Namen `name` (namensraum-tolerant)."""
    return [k for k in element if _lokal(k.tag) == name]


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _erstes_kind_text(element: ET.Element, name: str) -> str:
    for kind in _finde_alle(element, name):
        return _text(kind)
    return ""


def _iso_datum(rohwert: str | None) -> str | None:
    """Extrahiert das erste YYYY-MM-TT aus einem Datums-/Zeitstempel-String."""
    if not rohwert:
        return None
    treffer = _ISO_DATUM_RE.search(rohwert)
    return treffer.group(1) if treffer else None


def _dedupe_erhalte_reihenfolge(werte: list[str]) -> list[str]:
    gesehen: set[str] = set()
    ergebnis: list[str] = []
    for w in werte:
        schluessel = w.casefold()
        if w and schluessel not in gesehen:
            gesehen.add(schluessel)
            ergebnis.append(w)
    return ergebnis


# --------------------------------------------------------------------------
# XML laden / Format erkennen
# --------------------------------------------------------------------------

def _lade_wurzel(quelle: str | Path) -> ET.Element:
    try:
        if isinstance(quelle, Path):
            wurzel = ET.parse(str(quelle)).getroot()
        else:
            wurzel = ET.fromstring(quelle)
    except ET.ParseError as exc:
        raise ParserFehler(f"kein gültiges XML: {exc}") from exc
    return wurzel


def erkenne_format(quelle: str | Path) -> str:
    """Ermittelt anhand der XML-Wurzel das Format (QUELLE_EU | QUELLE_UN)."""
    wurzel = _lade_wurzel(quelle)
    return _format_aus_wurzel(wurzel)


def _format_aus_wurzel(wurzel: ET.Element) -> str:
    tag = _lokal(wurzel.tag)
    if tag == "export":
        return QUELLE_EU
    if tag == "CONSOLIDATED_LIST":
        return QUELLE_UN
    raise ParserFehler(
        f"unbekannte XML-Wurzel '{tag}' — erwartet 'export' (EU-FSF) oder "
        f"'CONSOLIDATED_LIST' (UN)")


# --------------------------------------------------------------------------
# EU-FSF-Parser
# --------------------------------------------------------------------------

def _eu_name(name_el: ET.Element) -> str:
    ganz = (name_el.get("wholeName") or "").strip()
    if ganz:
        return ganz
    teile = [(name_el.get(a) or "").strip()
             for a in ("firstName", "middleName", "lastName")]
    return " ".join(t for t in teile if t).strip()


def _eu_typ(entity: ET.Element) -> str:
    for st in _finde_alle(entity, "subjectType"):
        code = (st.get("code") or "").strip().lower()
        if code == "person":
            return TYP_PERSON
        if code in ("enterprise", "organisation", "entity"):
            return TYP_ORGANISATION
    return TYP_UNBEKANNT


def _eu_eintrag(entity: ET.Element) -> SanktionsEintrag | None:
    namen = [_eu_name(n) for n in _finde_alle(entity, "nameAlias")]
    namen = _dedupe_erhalte_reihenfolge([n for n in namen if n])
    if not namen:
        return None  # ohne Namen für ein Namens-Screening wertlos

    programme = [(r.get("programme") or "").strip()
                 for r in _finde_alle(entity, "regulation")]
    programme = _dedupe_erhalte_reihenfolge([p for p in programme if p])

    geburtsdatum = None
    for bd in _finde_alle(entity, "birthdate"):
        geburtsdatum = _iso_datum(bd.get("birthdate")) or (bd.get("year") or None)
        if geburtsdatum:
            break

    return SanktionsEintrag(
        quelle=QUELLE_EU,
        referenz=(entity.get("euReferenceNumber")
                  or entity.get("logicalId") or "").strip(),
        programm="; ".join(programme) if programme else None,
        typ=_eu_typ(entity),
        primaername=namen[0],
        aliase=namen[1:],
        geburtsdatum=geburtsdatum,
    )


def parse_eu_fsf(quelle: str | Path) -> Sanktionsliste:
    wurzel = _lade_wurzel(quelle)
    if _lokal(wurzel.tag) != "export":
        raise ParserFehler(
            f"EU-FSF-Parser erwartet Wurzel 'export', bekam '{_lokal(wurzel.tag)}'")
    eintraege = [e for entity in _finde_alle(wurzel, "sanctionEntity")
                 if (e := _eu_eintrag(entity)) is not None]
    return Sanktionsliste(
        quelle=QUELLE_EU,
        generierungsdatum=_iso_datum(wurzel.get("generationDate")),
        eintraege=eintraege,
    )


# --------------------------------------------------------------------------
# UN-Parser
# --------------------------------------------------------------------------

def _un_person_name(el: ET.Element) -> str:
    teile = [_erstes_kind_text(el, feld) for feld in
             ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
    return " ".join(t for t in teile if t).strip()


def _un_aliase(el: ET.Element, alias_tag: str) -> list[str]:
    namen = [_erstes_kind_text(a, "ALIAS_NAME") for a in _finde_alle(el, alias_tag)]
    return _dedupe_erhalte_reihenfolge([n for n in namen if n])


def _un_geburtsdatum(el: ET.Element) -> str | None:
    for bd in _finde_alle(el, "INDIVIDUAL_DATE_OF_BIRTH"):
        datum = _iso_datum(_erstes_kind_text(bd, "DATE"))
        if datum:
            return datum
        jahr = _erstes_kind_text(bd, "YEAR")
        if jahr:
            return jahr
    return None


def _un_eintrag(el: ET.Element, typ: str, alias_tag: str) -> SanktionsEintrag | None:
    if typ == TYP_PERSON:
        primaer = _un_person_name(el)
        geburtsdatum = _un_geburtsdatum(el)
    else:
        primaer = _erstes_kind_text(el, "FIRST_NAME")
        geburtsdatum = None
    if not primaer:
        return None
    return SanktionsEintrag(
        quelle=QUELLE_UN,
        referenz=_erstes_kind_text(el, "REFERENCE_NUMBER"),
        programm=_erstes_kind_text(el, "UN_LIST_TYPE") or None,
        typ=typ,
        primaername=primaer,
        aliase=_un_aliase(el, alias_tag),
        geburtsdatum=geburtsdatum,
    )


def parse_un_consolidated(quelle: str | Path) -> Sanktionsliste:
    wurzel = _lade_wurzel(quelle)
    if _lokal(wurzel.tag) != "CONSOLIDATED_LIST":
        raise ParserFehler(
            f"UN-Parser erwartet Wurzel 'CONSOLIDATED_LIST', "
            f"bekam '{_lokal(wurzel.tag)}'")
    eintraege: list[SanktionsEintrag] = []
    for container in _finde_alle(wurzel, "INDIVIDUALS"):
        for ind in _finde_alle(container, "INDIVIDUAL"):
            if (e := _un_eintrag(ind, TYP_PERSON, "INDIVIDUAL_ALIAS")) is not None:
                eintraege.append(e)
    for container in _finde_alle(wurzel, "ENTITIES"):
        for ent in _finde_alle(container, "ENTITY"):
            if (e := _un_eintrag(ent, TYP_ORGANISATION, "ENTITY_ALIAS")) is not None:
                eintraege.append(e)
    return Sanktionsliste(
        quelle=QUELLE_UN,
        generierungsdatum=_iso_datum(wurzel.get("dateGenerated")),
        eintraege=eintraege,
    )


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

def parse_datei(pfad: str | Path) -> Sanktionsliste:
    """Erkennt das Format anhand der XML-Wurzel und parst entsprechend."""
    pfad = Path(pfad)
    if not pfad.is_file():
        raise ParserFehler(f"Listen-Datei nicht gefunden: {pfad}")
    wurzel = _lade_wurzel(pfad)
    fmt = _format_aus_wurzel(wurzel)
    return parse_eu_fsf(pfad) if fmt == QUELLE_EU else parse_un_consolidated(pfad)
