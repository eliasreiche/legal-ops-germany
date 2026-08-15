#!/usr/bin/env python3
"""rvg.tabelle — Tabellenstand-Auswahl und Wertgebühr nach § 13 RVG (P3).

Lädt `gebuehrentabelle.json` (Grundbetrag + Stufenformel je Gültigkeitszeit-
raum) und wählt anhand des Stichtags (§ 60 Abs. 1 RVG: Zeitpunkt der
Erteilung des unbedingten Auftrags) den anzuwendenden Tabellenstand.

Unterstützte Stände: KostRÄG 2021 (01.01.2021–31.05.2025), KostBRÄG 2025
(ab 01.06.2025). Für einen Stichtag außerhalb dieses Fensters gibt es keinen
Tabellenstand — der Executor lehnt die Anfrage als Lücke ab, statt zu raten
(Anti-Halluzination, CONVENTIONS.md).

Nur Standardbibliothek. Kein Netzwerkzugriff.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_CALC_DIR = Path(__file__).resolve().parents[1]
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from wertgebuehr_formel import (  # noqa: E402
    D,
    EinfachgebuehrErgebnis,
    WertgebuehrFehler,
    einfachgebuehr as _einfachgebuehr_formel,
    stand_fuer_stichtag as _stand_fuer_stichtag,
)

TABELLE_PFAD = Path(__file__).resolve().parent / "gebuehrentabelle.json"

_KEIN_STAND = (
    "kein RVG-Tabellenstand für Stichtag {stichtag} "
    "hinterlegt — dieser Rechner unterstützt Aufträge ab {aelteste_ab} "
    "(KostRÄG 2021). Für ältere Stichtage: keine Berechnung möglich, "
    "anwaltlich/manuell nach der damals geltenden Fassung prüfen "
    "(§ 60 Abs. 1 RVG).")


class RVGTabellenFehler(WertgebuehrFehler):
    """Kein Tabellenstand für den angegebenen Stichtag, oder defekte Daten."""


def lade_tabelle(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or TABELLE_PFAD).read_text(encoding="utf-8"))


def stand_fuer_stichtag(stichtag: _dt.date, tabelle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wählt den Tabellenstand, der am `stichtag` gilt (§ 60 Abs. 1 RVG:
    Zeitpunkt der Erteilung des unbedingten Auftrags).

    Wirft RVGTabellenFehler, wenn der Stichtag vor dem ältesten oder nach
    einer Lücke zwischen den unterstützten Ständen liegt (kein Rechnen mit
    unbekannten Fassungen).
    """
    return _stand_fuer_stichtag(stichtag, tabelle or lade_tabelle(),
                                fehler=RVGTabellenFehler, fehlertext=_KEIN_STAND)


def einfachgebuehr(gegenstandswert: Any, stichtag: _dt.date,
                   tabelle: dict[str, Any] | None = None
                   ) -> tuple[EinfachgebuehrErgebnis, dict[str, Any]]:
    """1,0-Gebühr für `gegenstandswert` nach dem für `stichtag` geltenden
    Tabellenstand. Gibt (Ergebnis, verwendeter Stand) zurück."""
    tab = tabelle or lade_tabelle()
    stand = stand_fuer_stichtag(stichtag, tab)
    ergebnis = _einfachgebuehr_formel(D(gegenstandswert), stand)
    return ergebnis, stand
