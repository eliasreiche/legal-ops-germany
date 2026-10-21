#!/usr/bin/env python3
"""famgkg.rechner — FamGKG-Gerichtskostenberechnung (Wertgebühren), P3.

Spiegel von gkg.rechner: aus Verfahrenswert, Stichtag (§ 63 Abs. 1 FamGKG)
und einer Liste von KV-FamGKG-Positionen eine vollständige, nachvollziehbare
Rechenkette — Tabellenstand-Auswahl, 1,0-Gebühr (§ 28 Abs. 1 FamGKG), je
Position Satz × 1,0-Gebühr mit Mindestbetrags-Floor (§ 28 Abs. 2 Satz 1
FamGKG, 15 €), Ausschluss von Regelfall und Ermäßigung derselben Instanz.
Optional je Position ein eigener `gegenstandswert` (Pflicht bei KV 1500,
Vergleich über nicht anhängige Gegenstände); KV 1500 und die Gebühr für das
Verfahren im Allgemeinen werden nach § 30 Abs. 3 FamGKG (Anm. zu KV 1500)
gekappt. Verfahrenswerte über 30 Mio. € werden nach § 33 Abs. 2 FamGKG
sichtbar gekappt.

Anders als beim GKG keine Mahnverfahrens-Anrechnung (die Anmerkung zu
KV 1220 FamGKG verweist auf KV 1100 GKG — nicht modelliert). Gerichts-
gebühren sind nicht umsatzsteuerpflichtig.

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

_FAMGKG_DIR = Path(__file__).resolve().parent
_CALC_DIR = _FAMGKG_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

# Vollqualifizierte Paketimporte (famgkg.tabelle, nicht bloß "tabelle") —
# siehe Kommentar in rvg/rechner.py: ein bloßer Modulname würde im
# sys.modules-Cache mit rvg.tabelle/gkg.tabelle kollidieren.
from wertgebuehr_formel import (  # noqa: E402
    D,
    Position,
    WertgebuehrFehler,
    kappung_beschreibung,
    rundung_cent,
    teilwert_kappung,
)
from rechenschritt import RechenSchritt  # noqa: E402
from famgkg.tabelle import (  # noqa: E402
    einfachgebuehr as _einfachgebuehr_stichtag,
    verfahrenswert_hoechstgrenze,
)

KATALOG_PFAD = _FAMGKG_DIR / "kv-katalog.json"

# Positionsgruppen, deren Mitglieder sich gegenseitig ausschließen (Regelfall
# vs. Ermäßigung(en) für dieselbe Instanz).
_AUSSCHLUSSGRUPPEN = [("1110", "1111"), ("1120", "1121", "1122"),
                      ("1220", "1221"), ("1222", "1223", "1224"),
                      ("1314", "1315"), ("1320", "1321"),
                      ("1322", "1323", "1324"), ("1420", "1421")]


class FamGKGEingabeFehler(WertgebuehrFehler):
    """Ungültige FamGKG-Anfrage (Scope, unbekannte Nr., Typfehler, ...)."""


def lade_katalog(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or KATALOG_PFAD).read_text(encoding="utf-8"))


@dataclass
class FamGKGErgebnis:
    verfahrenswert: Decimal             # ggf. gekappt (§ 33 Abs. 2 FamGKG)
    verfahrenswert_eingabe: Decimal     # wie übergeben
    wert_gekappt: bool
    stichtag: _dt.date
    tabellenstand: dict[str, Any]
    einfachgebuehr: Decimal
    positionen: list[Position]
    gesamt: Decimal
    kappung: dict[str, Any] | None = None     # § 30 Abs. 3 FamGKG (KV 1500)
    rechenkette: list[RechenSchritt] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


def berechne(verfahrenswert: Any, stichtag: _dt.date,
             positionen: list[dict[str, Any]], *,
             katalog: dict[str, Any] | None = None) -> FamGKGErgebnis:
    """Berechnet die FamGKG-Gerichtskosten für `verfahrenswert`/`stichtag`
    aus den angeforderten `positionen` (Liste von {"nr": "1110"})."""
    kat = katalog or lade_katalog()
    positionen_katalog = kat["positionen"]
    allg_mindest = D(kat["hinweis_allgemeine_mindestgebuehr"]["betrag"])

    if not isinstance(positionen, list) or not positionen:
        raise FamGKGEingabeFehler("'positionen' muss eine nichtleere Liste sein")

    wert_eingabe = D(verfahrenswert)
    if wert_eingabe <= 0:
        raise FamGKGEingabeFehler(
            f"Verfahrenswert muss > 0 sein, ist {wert_eingabe}")

    # Teilwerte: wie beim GKG wird mit Teilwerten jeder Wert über der
    # Höchstgrenze abgelehnt statt womöglich falsch je Position gekappt.
    teilwerte = any(isinstance(e, dict) and "gegenstandswert" in e
                    for e in positionen)

    kette: list[RechenSchritt] = []
    warnungen: list[str] = []

    def schritt(norm: str, beschreibung: str, ergebnis: str | None) -> None:
        kette.append(RechenSchritt(schritt=len(kette) + 1, norm=norm,
                                   beschreibung=beschreibung, ergebnis=ergebnis))

    hoechstgrenze = verfahrenswert_hoechstgrenze()

    def _grenze_teilwerte(w: Decimal) -> None:
        if teilwerte and w > hoechstgrenze:
            raise FamGKGEingabeFehler(
                f"Wert {w} € über {hoechstgrenze} € in einer Anfrage mit "
                f"Teilwerten ('gegenstandswert' je Position): die Höchstgrenze "
                f"des § 33 Abs. 2 FamGKG ist für diese Konstellation nicht "
                f"modelliert und wird nicht stillschweigend je Position "
                f"gekappt. Anwaltlich prüfen.")

    _grenze_teilwerte(wert_eingabe)
    wert = wert_eingabe
    if wert_eingabe > hoechstgrenze:
        wert = hoechstgrenze
        schritt("§ 33 Abs. 2 FamGKG",
                f"Verfahrenswert {wert_eingabe} € übersteigt die Höchstgrenze — "
                f"für die Gebührenberechnung auf {hoechstgrenze} € gekappt.",
                str(wert))
        warnungen.append(
            f"Verfahrenswert nach § 33 Abs. 2 FamGKG auf 30 Mio. € gekappt "
            f"(ermittelt/eingegeben: {wert_eingabe} €).")

    eg_ergebnis, stand = _einfachgebuehr_stichtag(wert, stichtag)
    einfachgebuehr = eg_ergebnis.einfachgebuehr

    schritt("§ 63 Abs. 1 FamGKG",
            f"Stichtag (Anhängigkeit/Einleitung des Verfahrens, beim "
            f"Rechtsmittel dessen Einlegung) {stichtag.isoformat()} -> "
            f"Tabellenstand '{stand['bezeichnung']}' (gültig {stand['gueltig_ab']}"
            f"{' bis ' + stand['gueltig_bis'] if stand.get('gueltig_bis') else ' bis heute'}).",
            stand["id"])
    schritt("§ 28 Abs. 1 FamGKG",
            f"1,0-Gebühr (Einfachgebühr) für Verfahrenswert {wert} €.",
            str(einfachgebuehr))

    eg_je_wert: dict[Decimal, Decimal] = {wert: einfachgebuehr}

    def eg(w: Decimal) -> Decimal:
        if w not in eg_je_wert:
            _grenze_teilwerte(w)
            eg_je_wert[w] = _einfachgebuehr_stichtag(w, stichtag)[0].einfachgebuehr
            schritt("§ 28 Abs. 1 FamGKG",
                    f"1,0-Gebühr (Einfachgebühr) für Wert {w} €.",
                    str(eg_je_wert[w]))
        return eg_je_wert[w]

    gesehene_nrn: set[str] = set()
    ergebnis_positionen: list[Position] = []
    nach_nr: dict[str, Position] = {}

    for eintrag in positionen:
        if not isinstance(eintrag, dict) or "nr" not in eintrag:
            raise FamGKGEingabeFehler(
                f"jeder Eintrag in 'positionen' muss ein Objekt mit 'nr' sein, "
                f"nicht {eintrag!r}")
        nr = str(eintrag["nr"])
        unbekannt = sorted(set(eintrag) - {"nr", "gegenstandswert"})
        if unbekannt:
            raise FamGKGEingabeFehler(
                f"unbekanntes Feld in KV {nr} FamGKG: "
                f"{', '.join(repr(f) for f in unbekannt)} (erlaubt: 'nr', "
                f"'gegenstandswert')")
        if nr not in positionen_katalog:
            bekannt = ", ".join(sorted(positionen_katalog))
            raise FamGKGEingabeFehler(
                f"KV {nr} FamGKG ist nicht unterstützt (bekannt: {bekannt}) — "
                f"nicht im Katalog sind u. a. Rechtsbeschwerde, vereinfachtes "
                f"Unterhaltsverfahren, Vormundschaft/Pflegschaft, Beschwerden "
                f"im einstweiligen Rechtsschutz, Festgebühren, Verfahrens"
                f"kostenhilfe und Auslagen — keine automatische Berechnung "
                f"möglich.")
        if nr in gesehene_nrn:
            raise FamGKGEingabeFehler(
                f"KV {nr} FamGKG ist mehrfach in 'positionen' angegeben")
        gesehene_nrn.add(nr)

        katalog_eintrag = positionen_katalog[nr]
        pos_wert = wert
        if "gegenstandswert" in eintrag:
            pos_wert = D(eintrag["gegenstandswert"])
            if pos_wert <= 0:
                raise FamGKGEingabeFehler(
                    f"'gegenstandswert' von KV {nr} muss > 0 sein, ist {pos_wert}")
        elif katalog_eintrag.get("wert_pflicht"):
            raise FamGKGEingabeFehler(
                f"KV {nr} FamGKG verlangt 'gegenstandswert' — den Wert der "
                f"nicht gerichtlich anhängigen Gegenstände, nicht den "
                f"Verfahrenswert des Verfahrens")
        satz = D(katalog_eintrag["satz"])
        betrag = rundung_cent(satz * eg(pos_wert))

        hinweise: list[str] = []
        mindest_gegriffen = False
        if betrag < allg_mindest:
            betrag = allg_mindest
            mindest_gegriffen = True
            hinweise.append(
                f"Mindestbetrag ({allg_mindest} €, § 28 Abs. 2 Satz 1 FamGKG) "
                f"greift — berechneter Betrag lag darunter.")
        if "hinweis" in katalog_eintrag:
            hinweise.append(katalog_eintrag["hinweis"])

        pos = Position(nr=nr, bezeichnung=katalog_eintrag["bezeichnung"],
                       norm=katalog_eintrag["norm"], satz=satz, betrag=betrag,
                       mindestbetrag_gegriffen=mindest_gegriffen, hinweise=hinweise,
                       gegenstandswert=pos_wert if teilwerte else None)
        ergebnis_positionen.append(pos)
        nach_nr[nr] = pos
        schritt(katalog_eintrag["norm"],
                f"{katalog_eintrag['bezeichnung']} (KV {nr} FamGKG)"
                + (f" aus Wert {pos_wert} €" if teilwerte else "")
                + f": Satz {satz} x {eg(pos_wert)} € = {betrag} €"
                + (" (Mindestbetrag angewendet)" if mindest_gegriffen else ""),
                str(betrag))

    for gruppe in _AUSSCHLUSSGRUPPEN:
        treffer = [nr for nr in gruppe if nr in gesehene_nrn]
        if len(treffer) > 1:
            raise FamGKGEingabeFehler(
                f"{' und '.join('KV ' + nr + ' FamGKG' for nr in treffer)} "
                f"schließen sich gegenseitig aus (Regelfall vs. Ermäßigung "
                f"für dieselbe Instanz) — nur eine der Positionen angeben")

    # --- § 30 Abs. 3 FamGKG entsprechend (Anmerkung zu KV 1500). ---
    kappung: dict[str, Any] | None = None
    for nr, pos in nach_nr.items():
        partner_nrn = positionen_katalog[nr].get("kappung_30_abs_3_mit")
        if not partner_nrn:
            continue
        partner = [nach_nr[p] for p in partner_nrn if p in nach_nr]
        if len(partner) > 1:
            raise FamGKGEingabeFehler(
                f"KV {nr} FamGKG zusammen mit mehreren Gebühren für das "
                f"Verfahren im Allgemeinen ({', '.join('KV ' + p.nr for p in partner)}) "
                f"— nicht eindeutig, auf welches Verfahren sich § 30 Abs. 3 "
                f"FamGKG bezieht; je Verfahren/Rechtszug eine eigene Anfrage "
                f"stellen.")
        if partner:
            kappung = teilwert_kappung("§ 30 Abs. 3 FamGKG i. V. m. Anm. zu KV 1500",
                                       [partner[0], pos], eg, allg_mindest)
            schritt(kappung["norm"], kappung_beschreibung(kappung, "KV "),
                    kappung["betrag_nach_kappung"])

    gesamt = rundung_cent(
        sum((p.betrag for p in ergebnis_positionen), Decimal("0.00"))
        - (D(kappung["kuerzung"]) if kappung else Decimal("0.00")))
    schritt("Gesamt", "Summe aller Gerichtskosten-Positionen (FamGKG)"
            + (" abzüglich Kürzung nach § 30 Abs. 3 FamGKG"
               if kappung and kappung["gekappt"] else "")
            + " (nicht umsatzsteuerpflichtig).", str(gesamt))

    return FamGKGErgebnis(
        verfahrenswert=wert, verfahrenswert_eingabe=wert_eingabe,
        wert_gekappt=wert != wert_eingabe, stichtag=stichtag,
        tabellenstand=stand, einfachgebuehr=einfachgebuehr,
        positionen=ergebnis_positionen, gesamt=gesamt, kappung=kappung,
        rechenkette=kette, warnungen=warnungen)
