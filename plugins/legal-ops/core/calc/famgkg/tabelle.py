#!/usr/bin/env python3
"""famgkg.tabelle — Tabellenstand-Auswahl und Wertgebühr nach § 28 FamGKG (P3).

Lädt `gebuehrentabelle.json` (Grundbetrag + Stufenformel je Gültigkeitszeit-
raum) und wählt anhand des Stichtags den anzuwendenden Tabellenstand —
Übergangsvorschrift § 63 Abs. 1 FamGKG: in Verfahren, die vor dem
Inkrafttreten einer Gesetzesänderung anhängig geworden oder eingeleitet
worden sind, werden die Kosten nach bisherigem Recht erhoben (Satz 1); das
gilt nicht im Verfahren über ein Rechtsmittel, das nach dem Inkrafttreten
eingelegt worden ist (Satz 2).

Unterstützte Stände: KostRÄG 2021 (01.01.2021–31.05.2025), KostBRÄG 2025
(ab 01.06.2025). Grundbetrag und Stufen sind in beiden Ständen identisch mit
§ 34 GKG — trotzdem eigene Daten, weil eigene Norm (§ 28 FamGKG).

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
    "kein FamGKG-Tabellenstand für Stichtag {stichtag} "
    "hinterlegt — dieser Rechner unterstützt Verfahren, die ab "
    "{aelteste_ab} anhängig geworden oder eingeleitet worden sind "
    "(KostRÄG 2021). Für ältere Stichtage: keine Berechnung möglich, "
    "anwaltlich/manuell nach der damals geltenden Fassung prüfen "
    "(§ 63 Abs. 1 FamGKG).")


class FamGKGTabellenFehler(WertgebuehrFehler):
    """Kein Tabellenstand für den angegebenen Stichtag, oder defekte Daten."""


def lade_tabelle(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or TABELLE_PFAD).read_text(encoding="utf-8"))


def verfahrenswert_hoechstgrenze(tabelle: dict[str, Any] | None = None) -> Any:
    tab = tabelle or lade_tabelle()
    return D(tab["verfahrenswert_hoechstgrenze"])


def stand_fuer_stichtag(stichtag: _dt.date, tabelle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wählt den Tabellenstand, der am `stichtag` gilt (§ 63 Abs. 1 FamGKG:
    Zeitpunkt, zu dem das Verfahren anhängig geworden oder eingeleitet
    worden ist; beim Rechtsmittel: dessen Einlegung)."""
    return _stand_fuer_stichtag(stichtag, tabelle or lade_tabelle(),
                                fehler=FamGKGTabellenFehler, fehlertext=_KEIN_STAND)


def einfachgebuehr(verfahrenswert: Any, stichtag: _dt.date,
                   tabelle: dict[str, Any] | None = None
                   ) -> tuple[EinfachgebuehrErgebnis, dict[str, Any]]:
    """1,0-Gebühr für `verfahrenswert` nach dem für `stichtag` geltenden
    Tabellenstand. Gibt (Ergebnis, verwendeter Stand) zurück.

    § 33 Abs. 2 FamGKG ist eine **Kappungsgrenze**: Werte über 30 Mio. €
    werden auf 30 Mio. € gekappt (`EinfachgebuehrErgebnis.gegenstandswert`
    trägt den gekappten Wert). Die sichtbare Ausweisung (Rechenketten-Zeile
    + Warnung) übernimmt famgkg.rechner.berechne.
    """
    tab = tabelle or lade_tabelle()
    hoechstgrenze = verfahrenswert_hoechstgrenze(tab)
    wert = D(verfahrenswert)
    if wert > hoechstgrenze:
        wert = hoechstgrenze
    stand = stand_fuer_stichtag(stichtag, tab)
    return _einfachgebuehr_formel(wert, stand), stand
