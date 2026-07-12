#!/usr/bin/env python3
"""gkg.tabelle — Tabellenstand-Auswahl und Wertgebühr nach § 34 GKG (P3).

Lädt `gebuehrentabelle.json` (Grundbetrag + Stufenformel je Gültigkeitszeit-
raum) und wählt anhand des Stichtags (§ 71 Abs. 1 GKG: Zeitpunkt, zu dem die
Rechtsstreitigkeit anhängig geworden ist — NICHT der Auftragserteilung wie
bei § 60 RVG) den anzuwendenden Tabellenstand.

Unterstützte Stände: KostRÄG 2021 (01.01.2021–31.05.2025), KostBRÄG 2025
(ab 01.06.2025).

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
)

TABELLE_PFAD = Path(__file__).resolve().parent / "gebuehrentabelle.json"


class GKGTabellenFehler(WertgebuehrFehler):
    """Kein Tabellenstand für den angegebenen Stichtag, oder defekte Daten."""


def lade_tabelle(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or TABELLE_PFAD).read_text(encoding="utf-8"))


def streitwert_hoechstgrenze(tabelle: dict[str, Any] | None = None) -> Any:
    tab = tabelle or lade_tabelle()
    return D(tab["streitwert_hoechstgrenze"])


def stand_fuer_stichtag(stichtag: _dt.date, tabelle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wählt den Tabellenstand, der am `stichtag` gilt (§ 71 Abs. 1 GKG:
    Zeitpunkt, zu dem die Rechtsstreitigkeit anhängig geworden ist)."""
    tab = tabelle or lade_tabelle()
    staende = sorted(tab["staende"], key=lambda s: s["gueltig_ab"])
    for stand in staende:
        ab = _dt.date.fromisoformat(stand["gueltig_ab"])
        bis = (_dt.date.fromisoformat(stand["gueltig_bis"])
               if stand.get("gueltig_bis") else None)
        if stichtag >= ab and (bis is None or stichtag <= bis):
            return stand
    aelteste_ab = staende[0]["gueltig_ab"]
    raise GKGTabellenFehler(
        f"kein GKG-Tabellenstand für Stichtag {stichtag.isoformat()} "
        f"hinterlegt — dieser Rechner unterstützt Verfahren, die ab "
        f"{aelteste_ab} anhängig geworden sind (KostRÄG 2021). Für ältere "
        f"Stichtage: keine Berechnung möglich, anwaltlich/manuell nach der "
        f"damals geltenden Fassung prüfen (§ 71 Abs. 1 GKG).")


def einfachgebuehr(streitwert: Any, stichtag: _dt.date,
                   tabelle: dict[str, Any] | None = None
                   ) -> tuple[EinfachgebuehrErgebnis, dict[str, Any]]:
    """1,0-Gebühr für `streitwert` nach dem für `stichtag` geltenden
    Tabellenstand. Gibt (Ergebnis, verwendeter Stand) zurück.

    § 39 Abs. 2 GKG ist eine **Kappungsgrenze**, keine Zulässigkeitsgrenze:
    Streitwerte über 30 Mio. € werden für die Gebührenberechnung auf
    30 Mio. € gekappt (das `EinfachgebuehrErgebnis.gegenstandswert` trägt
    den gekappten Wert). Die sichtbare Ausweisung der Kappung (Rechenketten-
    Zeile + Warnung) übernimmt gkg.rechner.berechne — direkte Aufrufer
    erkennen die Kappung am Vergleich mit dem Eingabewert.
    """
    tab = tabelle or lade_tabelle()
    hoechstgrenze = streitwert_hoechstgrenze(tab)
    wert = D(streitwert)
    if wert > hoechstgrenze:
        wert = hoechstgrenze
    stand = stand_fuer_stichtag(stichtag, tab)
    ergebnis = _einfachgebuehr_formel(wert, stand)
    return ergebnis, stand
