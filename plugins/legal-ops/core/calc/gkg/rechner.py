#!/usr/bin/env python3
"""gkg.rechner — GKG-Gerichtskostenberechnung (Wertgebühren), P3.

Baut aus Streitwert, Stichtag (§ 71 Abs. 1 GKG) und einer Liste von
KV-GKG-Positionen eine vollständige, nachvollziehbare Rechenkette:
Tabellenstand-Auswahl, 1,0-Gebühr, je Position Satz × 1,0-Gebühr (mit
Mindestbetrags-Floor, § 34 Abs. 2 GKG bzw. positionsspezifischem
Mindestbetrag wie bei KV 1100).

Gerichtsgebühren sind nicht umsatzsteuerpflichtig — anders als beim RVG gibt
es hier keine Auslagenpauschale/USt-Position.

Nur Standardbibliothek. Kein Netzwerkzugriff. Ausschließlich Decimal.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

_GKG_DIR = Path(__file__).resolve().parent
_CALC_DIR = _GKG_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

# Vollqualifizierte Paketimporte (gkg.tabelle, nicht bloß "tabelle") — siehe
# Kommentar in rvg/rechner.py: ein bloßer Modulname würde im
# sys.modules-Cache mit rvg.tabelle kollidieren.
from wertgebuehr_formel import D, WertgebuehrFehler, rundung_cent  # noqa: E402
from gkg.tabelle import (  # noqa: E402
    einfachgebuehr as _einfachgebuehr_stichtag,
    streitwert_hoechstgrenze,
)

KATALOG_PFAD = _GKG_DIR / "kv-katalog.json"

# Positionspaare, die sich gegenseitig ausschließen (Regelfall vs. Ermäßigung
# für dieselbe Instanz).
_AUSSCHLUSSPAARE = [("1210", "1211"), ("1220", "1222")]


class GKGEingabeFehler(WertgebuehrFehler):
    """Ungültige GKG-Anfrage (Scope, unbekannte Nr., Typfehler, ...)."""


def lade_katalog(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or KATALOG_PFAD).read_text(encoding="utf-8"))


@dataclass
class RechenSchritt:
    schritt: int
    norm: str
    beschreibung: str
    ergebnis: str | None
    quelle: str = "executor"

    def as_dict(self) -> dict[str, Any]:
        return {"schritt": self.schritt, "norm": self.norm,
                "beschreibung": self.beschreibung, "ergebnis": self.ergebnis,
                "quelle": self.quelle}


@dataclass
class Position:
    nr: str
    bezeichnung: str
    norm: str
    satz: Decimal
    betrag: Decimal
    mindestbetrag_gegriffen: bool = False
    hinweise: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"nr": self.nr, "bezeichnung": self.bezeichnung, "norm": self.norm,
                "satz": str(self.satz), "betrag": str(self.betrag),
                "mindestbetrag_gegriffen": self.mindestbetrag_gegriffen,
                "hinweise": list(self.hinweise), "quelle": "executor"}


@dataclass
class GKGErgebnis:
    streitwert: Decimal                 # ggf. gekappt (§ 39 Abs. 2 GKG)
    streitwert_eingabe: Decimal         # wie eingegeben
    wert_gekappt: bool
    stichtag: _dt.date
    tabellenstand: dict[str, Any]
    einfachgebuehr: Decimal
    positionen: list[Position]
    gesamt: Decimal
    rechenkette: list[RechenSchritt] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


def berechne(streitwert: Any, stichtag: _dt.date, positionen: list[dict[str, Any]], *,
            katalog: dict[str, Any] | None = None) -> GKGErgebnis:
    """Berechnet die GKG-Gerichtskosten für `streitwert`/`stichtag` aus den
    angeforderten `positionen` (Liste von {"nr": "1210"})."""
    kat = katalog or lade_katalog()
    positionen_katalog = kat["positionen"]
    allg_mindest = D(kat["hinweis_allgemeine_mindestgebuehr"]["betrag"])

    if not isinstance(positionen, list) or not positionen:
        raise GKGEingabeFehler("'positionen' muss eine nichtleere Liste sein")

    wert_eingabe = D(streitwert)
    if wert_eingabe <= 0:
        raise GKGEingabeFehler(f"Streitwert muss > 0 sein, ist {wert_eingabe}")

    kette: list[RechenSchritt] = []
    warnungen: list[str] = []

    def schritt(norm: str, beschreibung: str, ergebnis: str | None) -> None:
        kette.append(RechenSchritt(schritt=len(kette) + 1, norm=norm,
                                   beschreibung=beschreibung, ergebnis=ergebnis))

    # --- § 39 Abs. 2 GKG: Höchstgrenze ist eine KAPPUNGS-, keine
    #     Zulässigkeitsgrenze — kappen und sichtbar ausweisen, nie ablehnen.
    hoechstgrenze = streitwert_hoechstgrenze()
    wert = wert_eingabe
    if wert_eingabe > hoechstgrenze:
        wert = hoechstgrenze
        schritt("§ 39 Abs. 2 GKG",
                f"Streitwert {wert_eingabe} € übersteigt die Höchstgrenze — "
                f"für die Gebührenberechnung auf {hoechstgrenze} € gekappt.",
                str(wert))
        warnungen.append(
            f"Streitwert nach § 39 Abs. 2 GKG auf 30 Mio. € gekappt "
            f"(eingegeben: {wert_eingabe} €).")

    eg_ergebnis, stand = _einfachgebuehr_stichtag(wert, stichtag)
    einfachgebuehr = eg_ergebnis.einfachgebuehr

    schritt("§ 71 Abs. 1 GKG",
            f"Stichtag (Anhängigkeit der Rechtsstreitigkeit) "
            f"{stichtag.isoformat()} -> Tabellenstand '{stand['bezeichnung']}' "
            f"(gültig {stand['gueltig_ab']}"
            f"{' bis ' + stand['gueltig_bis'] if stand.get('gueltig_bis') else ' bis heute'}).",
            stand["id"])
    schritt("§ 34 Abs. 1 GKG",
            f"1,0-Gebühr (Einfachgebühr) für Streitwert {wert} €.",
            str(einfachgebuehr))

    gesehene_nrn: set[str] = set()
    ergebnis_positionen: list[Position] = []

    for eintrag in positionen:
        if not isinstance(eintrag, dict) or "nr" not in eintrag:
            raise GKGEingabeFehler(
                f"jeder Eintrag in 'positionen' muss ein Objekt mit 'nr' sein, "
                f"nicht {eintrag!r}")
        nr = str(eintrag["nr"])
        if nr not in positionen_katalog:
            bekannt = ", ".join(sorted(positionen_katalog))
            raise GKGEingabeFehler(
                f"KV {nr} GKG ist nicht unterstützt (bekannt: {bekannt}) — "
                f"keine automatische Berechnung möglich.")
        if nr in gesehene_nrn:
            raise GKGEingabeFehler(
                f"KV {nr} GKG ist mehrfach in 'positionen' angegeben")
        gesehene_nrn.add(nr)

        katalog_eintrag = positionen_katalog[nr]
        satz = D(katalog_eintrag["satz"])
        betrag = rundung_cent(satz * einfachgebuehr)

        mindestbetrag = allg_mindest
        if "mindestbetrag" in katalog_eintrag:
            mindestbetrag = D(katalog_eintrag["mindestbetrag"][stand["id"]])

        hinweise: list[str] = []
        mindest_gegriffen = False
        if betrag < mindestbetrag:
            betrag = mindestbetrag
            mindest_gegriffen = True
            hinweise.append(
                f"Mindestbetrag ({mindestbetrag} €) greift — berechneter "
                f"Betrag lag darunter.")
        if "hinweis" in katalog_eintrag:
            hinweise.append(katalog_eintrag["hinweis"])

        pos = Position(nr=nr, bezeichnung=katalog_eintrag["bezeichnung"],
                       norm=katalog_eintrag["norm"], satz=satz, betrag=betrag,
                       mindestbetrag_gegriffen=mindest_gegriffen, hinweise=hinweise)
        ergebnis_positionen.append(pos)
        schritt(katalog_eintrag["norm"],
                f"{katalog_eintrag['bezeichnung']} (KV {nr} GKG): "
                f"Satz {satz} x {einfachgebuehr} € = {betrag} €"
                + (" (Mindestbetrag angewendet)" if mindest_gegriffen else ""),
                str(betrag))

    for a, b in _AUSSCHLUSSPAARE:
        if a in gesehene_nrn and b in gesehene_nrn:
            raise GKGEingabeFehler(
                f"KV {a} GKG (Regelfall) und KV {b} GKG (Ermäßigung) schließen "
                f"sich gegenseitig aus — nur eine der beiden Positionen für "
                f"dieselbe Instanz angeben")

    gesamt = rundung_cent(sum((p.betrag for p in ergebnis_positionen), Decimal("0.00")))
    schritt("Gesamt", "Summe aller Gerichtskosten-Positionen (nicht "
            "umsatzsteuerpflichtig).", str(gesamt))

    return GKGErgebnis(
        streitwert=wert, streitwert_eingabe=wert_eingabe,
        wert_gekappt=wert != wert_eingabe, stichtag=stichtag,
        tabellenstand=stand, einfachgebuehr=einfachgebuehr,
        positionen=ergebnis_positionen, gesamt=gesamt, rechenkette=kette,
        warnungen=warnungen)
