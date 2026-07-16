"""sanktionslisten — Adapter für offizielle EU-/UN-Sanktionslisten (P2).

Datenquellen-Adapter außerhalb des Kontext-Layers (siehe
`core/adapters/README.md`): er füttert die Datei-Schnittstelle des Skills
`gwg-live-screening`, bindet aber keine Kanzleisoftware an (kein D11-Bezug).

  * `parser`  — wandelt EU-FSF- und UN-XML in `Sanktionsliste`/
    `SanktionsEintrag` (reine Stdlib, kein Netzwerk).
  * `abruf`   — kleines, klar getrenntes Abruf-Skript (Stdlib `urllib`), lädt
    die zwei offiziellen URLs lokal und schreibt eine `abgerufen_am`-Metadatei.
    Bewusst getrennt vom Screening (Deterministik-Grenze P3) und in CI nicht
    netzwerk-getestet.
"""
from __future__ import annotations

from .parser import (
    QUELLE_EU,
    QUELLE_UN,
    TYP_ORGANISATION,
    TYP_PERSON,
    TYP_UNBEKANNT,
    ParserFehler,
    Sanktionsliste,
    SanktionsEintrag,
    erkenne_format,
    parse_datei,
    parse_eu_fsf,
    parse_un_consolidated,
)

__all__ = [
    "QUELLE_EU",
    "QUELLE_UN",
    "TYP_PERSON",
    "TYP_ORGANISATION",
    "TYP_UNBEKANNT",
    "ParserFehler",
    "Sanktionsliste",
    "SanktionsEintrag",
    "erkenne_format",
    "parse_datei",
    "parse_eu_fsf",
    "parse_un_consolidated",
]
