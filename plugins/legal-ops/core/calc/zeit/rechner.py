#!/usr/bin/env python3
"""zeit — deterministische Dauer-Berechnung und Aggregation (P3).

Wiederverwendbare Bibliothek für Skills, die aus Zeitangaben abrechnungsfähige
Minutenwerte berechnen. Aktuell genutzt von `taetigkeitstext-rvg`; für
`passive-zeiterfassung` (dieselbe Welle) mit derselben API vorgesehen — die
API bleibt deshalb bewusst klein und generisch (keine skill-spezifischen
Annahmen wie Aktenzeichen-Formate oder Stichworte).

Eine Dauer kommt aus GENAU einer Quelle: entweder `minuten` (int > 0) oder
`start`+`ende` (ISO-8601-Zeitstempel) — nie beides, nie keines. Das Modell
erfindet keine Zeitwerte; dieser Rechner leitet sie ausschließlich aus dem
Input ab (Deterministik-Grenze, CONVENTIONS.md P3).

Taktung (`takt_minuten`): optionales Runden auf einen Abrechnungstakt (z. B.
6 Minuten). Es wird immer AUFgerundet — kaufmännisches Runden ist hier
ausdrücklich nicht gewollt. Das ist eine dokumentierte Kanzlei-Konvention zur
Abrechnungspraxis, keine RVG-Vorgabe, und wird deshalb nie als Norm zitiert.

Nur Standardbibliothek. Kein Netzwerkzugriff, kein Datei-I/O in diesem Modul —
reine Funktionen.
"""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass
from typing import Any


class ZeitEingabeFehler(ValueError):
    """Eingabefehler bei der Zeitberechnung (P3: nie stillschweigend raten)."""


def dauer_minuten(*, start: str | None, ende: str | None,
                   minuten: int | None) -> int:
    """Berechnet die Dauer in Minuten aus genau einer Quelle.

    Entweder `minuten` (ganze Zahl > 0) oder `start`+`ende` (ISO-8601). Beides
    zugleich oder nur eine Seite von `start`/`ende` ist ein Eingabefehler.

    Bei `start`/`ende` wird eine angebrochene Minute konservativ AUFgerundet
    (die tatsächlich erfasste Arbeitszeit wird nie unterschätzt) — das ist
    eine reine Rundungsentscheidung dieser Bibliothek, kein Normzitat.
    """
    hat_minuten = minuten is not None
    hat_zeitraum = start is not None or ende is not None
    if hat_minuten and hat_zeitraum:
        raise ZeitEingabeFehler(
            "entweder `minuten` oder `start`+`ende` angeben, nie beides")
    if hat_minuten:
        if isinstance(minuten, bool) or not isinstance(minuten, int) or minuten <= 0:
            raise ZeitEingabeFehler(
                f"`minuten` muss eine ganze Zahl > 0 sein, ist: {minuten!r}")
        return minuten
    if start is None or ende is None:
        raise ZeitEingabeFehler(
            "`start` und `ende` müssen beide angegeben werden (oder keines "
            "von beiden, dann `minuten`)")
    start_dt = _parse_iso(start, feld="start")
    ende_dt = _parse_iso(ende, feld="ende")
    delta_sekunden = (ende_dt - start_dt).total_seconds()
    if delta_sekunden <= 0:
        raise ZeitEingabeFehler(f"`ende` ({ende}) muss nach `start` ({start}) liegen")
    return math.ceil(delta_sekunden / 60)


def _parse_iso(wert: str, *, feld: str) -> _dt.datetime:
    if not isinstance(wert, str):
        raise ZeitEingabeFehler(f"`{feld}` muss ein ISO-8601-Zeitstempel (Text) sein, "
                                f"ist: {wert!r}")
    try:
        return _dt.datetime.fromisoformat(wert)
    except ValueError as exc:
        raise ZeitEingabeFehler(
            f"`{feld}` ist kein gültiger ISO-8601-Zeitstempel: {wert!r}") from exc


def runde_auf_takt(minuten: int, takt_minuten: int | None) -> int:
    """Rundet `minuten` auf ein Vielfaches von `takt_minuten` — immer AUFrunden.

    `takt_minuten=None` (keine Taktung konfiguriert) gibt `minuten` unverändert
    zurück.
    """
    if takt_minuten is None:
        return minuten
    if isinstance(takt_minuten, bool) or not isinstance(takt_minuten, int) or takt_minuten <= 0:
        raise ZeitEingabeFehler(
            f"`takt_minuten` muss eine ganze Zahl > 0 sein, ist: {takt_minuten!r}")
    return math.ceil(minuten / takt_minuten) * takt_minuten


@dataclass(frozen=True)
class ZeitEintrag:
    """Ein aggregationsfähiger Zeit-Eintrag — Ergebnis der Dauer-Berechnung,
    kein eigenständiges Eingabeformat. `minuten` ist der Wert, über den
    summiert werden soll (roh oder bereits getaktet, je nach Aufrufer)."""
    az: str
    datum: str
    minuten: int

    def as_dict(self) -> dict[str, Any]:
        return {"az": self.az, "datum": self.datum, "minuten": self.minuten}


def summe_je_az(eintraege: list[ZeitEintrag]) -> dict[str, int]:
    """Summiert `minuten` je Aktenzeichen `az`."""
    summen: dict[str, int] = {}
    for e in eintraege:
        summen[e.az] = summen.get(e.az, 0) + e.minuten
    return summen


def summe_je_az_und_datum(eintraege: list[ZeitEintrag]) -> dict[tuple[str, str], int]:
    """Summiert `minuten` je (Aktenzeichen, Datum)."""
    summen: dict[tuple[str, str], int] = {}
    for e in eintraege:
        schluessel = (e.az, e.datum)
        summen[schluessel] = summen.get(schluessel, 0) + e.minuten
    return summen
