#!/usr/bin/env python3
"""gkg.rechner — GKG-Gerichtskostenberechnung (Wertgebühren), P3.

Baut aus Streitwert, Stichtag (§ 71 Abs. 1 GKG) und einer Liste von
KV-GKG-Positionen eine vollständige, nachvollziehbare Rechenkette:
Tabellenstand-Auswahl, 1,0-Gebühr, je Position Satz × 1,0-Gebühr (mit
Mindestbetrags-Floor, § 34 Abs. 2 GKG bzw. positionsspezifischem
Mindestbetrag wie bei KV 1100), optional die Anrechnung der
Mahnverfahrensgebühr KV 1100 auf KV 1210 beim Übergang in das streitige
Verfahren (Anmerkung Abs. 1 zu KV 1210 GKG).

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
from wertgebuehr_formel import (  # noqa: E402
    D,
    Position,
    WertgebuehrFehler,
    rundung_cent,
)
from rechenschritt import RechenSchritt  # noqa: E402
from gkg.tabelle import (  # noqa: E402
    einfachgebuehr as _einfachgebuehr_stichtag,
    streitwert_hoechstgrenze,
)

KATALOG_PFAD = _GKG_DIR / "kv-katalog.json"

# Positionspaare, die sich gegenseitig ausschließen (Regelfall vs. Ermäßigung
# für dieselbe Instanz).
_AUSSCHLUSSPAARE = [("1210", "1211"), ("1220", "1222"), ("1230", "1232")]


class GKGEingabeFehler(WertgebuehrFehler):
    """Ungültige GKG-Anfrage (Scope, unbekannte Nr., Typfehler, ...)."""


def _pruefe_bool(wert: Any, feld: str) -> bool:
    if not isinstance(wert, bool):
        raise GKGEingabeFehler(
            f"'{feld}' muss ein JSON-Boolean (true/false) sein, nicht {wert!r}")
    return wert


def lade_katalog(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or KATALOG_PFAD).read_text(encoding="utf-8"))


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
    anrechnung: dict[str, Any] | None = None
    rechenkette: list[RechenSchritt] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


def berechne(streitwert: Any, stichtag: _dt.date, positionen: list[dict[str, Any]], *,
            anrechnung_1100_auf_1210: bool = False,
            katalog: dict[str, Any] | None = None) -> GKGErgebnis:
    """Berechnet die GKG-Gerichtskosten für `streitwert`/`stichtag` aus den
    angeforderten `positionen` (Liste von {"nr": "1210"}).

    anrechnung_1100_auf_1210 verlangt KV 1100 und KV 1210 in derselben
    Anfrage (Anmerkung Abs. 1 zu KV 1210 GKG): die Mahnverfahrensgebühr wird
    auf die Gebühr für das Verfahren im Allgemeinen angerechnet — der
    identische Wert (vollständiger Übergang des Streitgegenstands) ist
    konstruktiv sichergestellt, weil eine Anfrage nur einen Streitwert kennt.
    """
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
    nach_nr: dict[str, Position] = {}

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
        nach_nr[nr] = pos
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

    # --- Anrechnung der Mahnverfahrensgebühr auf die Gebühr für das
    #     Verfahren im Allgemeinen (Anmerkung Abs. 1 zu KV 1210 GKG:
    #     "… in diesem Fall wird eine Gebühr 1100 nach dem Wert des
    #     Streitgegenstands angerechnet, der in das Prozessverfahren
    #     übergegangen ist."). Die Norm formuliert eine ANRECHNUNG, keine
    #     Ermäßigung des Gebührensatzes — der Satz 3,0 von KV 1210 bleibt
    #     unverändert, abgezogen wird der Betrag der Gebühr KV 1100
    #     (deshalb kein eigener Rechenweg: der Betrag steht als Position
    #     bereits fest, inkl. des versionierten Mindestbetrags-Floors).
    anrechnung_result: dict[str, Any] | None = None
    if _pruefe_bool(anrechnung_1100_auf_1210, "anrechnung_1100_auf_1210"):
        anr_regel = kat["anrechnung_mahnverfahren_auf_verfahrensgebuehr"]
        fehlend = [nr for nr in ("1100", "1210") if nr not in nach_nr]
        if fehlend:
            zusatz = ""
            if "1211" in nach_nr:
                zusatz = (" Die Anmerkung knüpft an die Gebühr 1210 an; die "
                          "Ermäßigung KV 1211 ist von dieser Mechanik nicht "
                          "erfasst — anwaltlich prüfen.")
            raise GKGEingabeFehler(
                f"'anrechnung_1100_auf_1210' verlangt KV 1100 (Mahnverfahren) "
                f"und KV 1210 (Verfahren im Allgemeinen, erster Rechtszug) "
                f"zusammen in 'positionen' (fehlt: "
                f"{', '.join('KV ' + nr for nr in fehlend)}).{zusatz}")
        mahn = nach_nr["1100"]
        verfahren = nach_nr["1210"]
        anr_betrag = mahn.betrag
        vor_anrechnung = verfahren.betrag
        # Kein Negativ-Fall: beide Positionen laufen über dieselbe
        # Einfachgebühr, KV 1210 (3,0) ist damit immer >= KV 1100
        # (0,5, inkl. Floor) — die kleinste Einfachgebühr beider Stände
        # (38,00/40,00 €) liegt weit über einem Drittel des jeweiligen
        # KV-1100-Mindestbetrags (36,00/38,00 €). Grenzfall-Test:
        # skills/rvg-gkg-rechner/tests/test_gkg_anrechnung_mahnverfahren.py
        neuer_betrag = vor_anrechnung - anr_betrag
        verfahren.betrag = neuer_betrag
        verfahren.hinweise.append(
            f"Um {anr_betrag} € gemindert durch Anrechnung der "
            f"Mahnverfahrensgebühr KV 1100 GKG ({anr_regel['norm']}).")
        anrechnung_result = {
            "norm": anr_regel["norm"],
            "fundstelle": anr_regel["fundstelle"],
            "angerechnete_position": "1100",
            "empfangende_position": "1210",
            "anrechnungsbetrag": str(anr_betrag),
            "gebuehr_1210_vor_anrechnung": str(vor_anrechnung),
            "gebuehr_1210_nach_anrechnung": str(neuer_betrag),
            "quelle": "executor",
        }
        schritt(anr_regel["norm"],
                f"Übergang Mahnverfahren -> streitiges Verfahren: die Gebühr "
                f"KV 1100 GKG ({anr_betrag} €) wird nach dem übergegangenen "
                f"Wert ({wert} €) auf die Gebühr KV 1210 GKG angerechnet — "
                f"{vor_anrechnung} € - {anr_betrag} € = {neuer_betrag} € "
                f"(Gebührensatz 3,0 unverändert, Anrechnung statt Ermäßigung).",
                str(neuer_betrag))

    gesamt = rundung_cent(sum((p.betrag for p in ergebnis_positionen), Decimal("0.00")))
    schritt("Gesamt", "Summe aller Gerichtskosten-Positionen (nicht "
            "umsatzsteuerpflichtig).", str(gesamt))

    return GKGErgebnis(
        streitwert=wert, streitwert_eingabe=wert_eingabe,
        wert_gekappt=wert != wert_eingabe, stichtag=stichtag,
        tabellenstand=stand, einfachgebuehr=einfachgebuehr,
        positionen=ergebnis_positionen, gesamt=gesamt,
        anrechnung=anrechnung_result, rechenkette=kette,
        warnungen=warnungen)
