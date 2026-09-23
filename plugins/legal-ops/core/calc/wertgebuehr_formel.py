#!/usr/bin/env python3
"""wertgebuehr_formel — gemeinsame Stufenformel für § 13 RVG und § 34 GKG (P3).

Beide Normen sind identisch aufgebaut: eine Grundgebühr bis zu einem
Sockelwert, danach je „angefangenem Betrag" einer Stufenbreite ein fester
Zuschlag, gestaffelt über mehrere Wertbereiche, und oberhalb des höchsten
tabellierten Werts ein fester Zuschlag je angefangenem Schritt (§ 13 Abs. 1
Satz 2, 3 RVG bzw. § 34 Abs. 1 Satz 2, 3 GKG). Diese Datei implementiert die
Formel einmal; `core/calc/rvg/tabelle.py` und `core/calc/gkg/tabelle.py`
liefern nur die je Gesetz und Gültigkeitszeitraum unterschiedlichen
Parameter (Daten, nicht Logik — P3).

Die Parameterdaten sind wörtlich aus den Gesetzestexten übernommen
(gesetze-im-internet.de, Wayback-Machine-Schnappschüsse für Vorfassungen,
Fassungsvergleich buzer.de für die Geltungszeiträume) — siehe die
`quelle`-Felder in den jeweiligen `gebuehrentabelle.json`.

Nur Standardbibliothek. Kein Netzwerkzugriff. Ausschließlich `decimal.Decimal`
— niemals `float` (Geldbeträge, CONVENTIONS.md P3).
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any

_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class WertgebuehrFehler(ValueError):
    """Ungültige Eingabe oder Tabellendaten (Formel- oder Stand-Fehler)."""


def parse_datum_strikt(wert: Any, feld: str) -> _dt.date:
    """Strikt JJJJ-MM-TT als String — kein fromisoformat()-Umweg, der auch
    JSON-Zahlen oder die Wochen-Notation schlucken würde (P3-Konvention,
    siehe core/calc/fristen/executor.py)."""
    if isinstance(wert, bool) or not isinstance(wert, str) or not _DATUM_RE.match(wert):
        raise WertgebuehrFehler(
            f"'{feld}' muss ein ISO-Datum als String im Format JJJJ-MM-TT "
            f"sein, nicht {wert!r}")
    try:
        return _dt.date.fromisoformat(wert)
    except ValueError as exc:
        raise WertgebuehrFehler(
            f"'{feld}' ist kein gültiges ISO-Datum (JJJJ-MM-TT): {wert!r} ({exc})")


def D(wert: Any) -> Decimal:
    """Wandelt einen Wert strikt in Decimal um — niemals über float.

    Akzeptiert `Decimal`, `int` und `str` (im Format eines Dezimalbetrags,
    z. B. "1234.56" oder "1234"). `float` wird explizit abgelehnt: ein
    JSON-Betrag wie 0.1 wird beim Parsen als IEEE-754-Näherung gelesen
    (klassische 0.1+0.2-Falle) — bei Geldbeträgen ein Haftungsrisiko, daher
    hartes Fehlschlagen statt stiller Ungenauigkeit.
    """
    if isinstance(wert, bool):
        raise WertgebuehrFehler(f"Zahlenwert erwartet, nicht bool: {wert!r}")
    if isinstance(wert, Decimal):
        return wert
    if isinstance(wert, int):
        return Decimal(wert)
    if isinstance(wert, float):
        raise WertgebuehrFehler(
            f"Geldbeträge/Sätze müssen als JSON-String (z. B. \"1234.56\") "
            f"oder ganze Zahl übergeben werden, nicht als float: {wert!r} "
            f"(float-Rundungsfehler wie 0.1+0.2 sind bei Geldbeträgen ein "
            f"Haftungsrisiko).")
    if isinstance(wert, str):
        s = wert.strip()
        try:
            d = Decimal(s)
        except Exception as exc:
            raise WertgebuehrFehler(f"kein gültiger Dezimalbetrag: {wert!r} ({exc})")
        if not d.is_finite():
            # Decimal("NaN")/Decimal("Infinity") parsen klaglos, sprengen
            # aber jeden späteren Vergleich (<=, <) mit InvalidOperation
            # statt einem sauberen Eingabefehler — hier abfangen, bevor sie
            # in eine Berechnung gelangen.
            raise WertgebuehrFehler(
                f"kein gültiger endlicher Dezimalbetrag: {wert!r}")
        return d
    raise WertgebuehrFehler(f"Zahlenwert erwartet, nicht {type(wert).__name__}: {wert!r}")


def rundung_cent(betrag: Decimal) -> Decimal:
    """Kaufmännische Rundung auf den vollen Cent (ROUND_HALF_UP).

    Entspricht wörtlich § 34 Abs. 2 Satz 2 GKG (seit KostBRÄG 2025: „Gebühren
    werden auf den nächstliegenden Cent auf- oder abgerundet; 0,5 Cent werden
    aufgerundet.") — als Haus-Konvention (CONVENTIONS.md) einheitlich auf
    beide Rechner (RVG und GKG, alle Tabellenstände) angewendet.
    """
    return betrag.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stand_fuer_stichtag(stichtag: _dt.date, tabelle: dict[str, Any], *,
                        fehler: type[Exception], fehlertext: str) -> dict[str, Any]:
    """Wählt aus `tabelle["staende"]` den am `stichtag` geltenden Stand.

    Identisch für § 13 RVG und § 34 GKG — verschieden sind nur der maßgebliche
    Stichtag (§ 60 Abs. 1 RVG: Auftragserteilung; § 71 Abs. 1 GKG:
    Anhängigkeit) und der Wortlaut der Fehlermeldung; beides liefert der
    Aufrufer (`core/calc/{rvg,gkg}/tabelle.py`).

    Liegt der Stichtag vor dem ältesten oder in einer Lücke zwischen den
    hinterlegten Ständen, wird `fehler` mit `fehlertext` geworfen (Platzhalter
    `{stichtag}` und `{aelteste_ab}`) — es wird nie mit einer unbekannten
    Fassung gerechnet.
    """
    staende = sorted(tabelle["staende"], key=lambda s: s["gueltig_ab"])
    for stand in staende:
        ab = _dt.date.fromisoformat(stand["gueltig_ab"])
        bis = (_dt.date.fromisoformat(stand["gueltig_bis"])
               if stand.get("gueltig_bis") else None)
        if stichtag >= ab and (bis is None or stichtag <= bis):
            return stand
    raise fehler(fehlertext.format(stichtag=stichtag.isoformat(),
                                   aelteste_ab=staende[0]["gueltig_ab"]))


@dataclass
class Position:
    """Eine berechnete Gebührenposition (VV RVG bzw. KV GKG)."""
    nr: str
    bezeichnung: str
    norm: str
    satz: Decimal
    betrag: Decimal
    mindestbetrag_gegriffen: bool = False
    hinweise: list[str] = field(default_factory=list)
    # Nur gesetzt, wenn die Anfrage Teilwerte ('gegenstandswert' je
    # Position) nutzt — sonst gilt der Streitwert der Anfrage.
    gegenstandswert: Decimal | None = None

    def as_dict(self) -> dict[str, Any]:
        d = {"nr": self.nr, "bezeichnung": self.bezeichnung, "norm": self.norm,
             "satz": str(self.satz), "betrag": str(self.betrag),
             "mindestbetrag_gegriffen": self.mindestbetrag_gegriffen,
             "hinweise": list(self.hinweise), "quelle": "executor"}
        if self.gegenstandswert is not None:
            d["gegenstandswert"] = str(self.gegenstandswert)
        return d


def teilwert_kappung(norm: str, teile: list[Position], einfachgebuehr_fuer,
                     mindestbetrag: Decimal = Decimal("0")) -> dict[str, Any]:
    """Kappung bei verschiedenen Gebührensätzen für Teile des Gegenstands
    (§ 15 Abs. 3 RVG / § 36 Abs. 3 GKG, gleicher Wortlaut): die Einzel-
    gebühren der Teile, höchstens die aus dem Gesamtbetrag der Wertteile nach
    dem höchsten Satz berechnete Gebühr. `teile` brauchen `gegenstandswert`;
    `einfachgebuehr_fuer(wert)` liefert die 1,0-Gebühr. Report-Dict (Strings),
    `kuerzung` ist 0.00, wenn die Kappung nicht greift."""
    roh = rundung_cent(sum((p.betrag for p in teile), Decimal("0")))
    wertsumme = sum((p.gegenstandswert for p in teile), Decimal("0"))
    hoechster_satz = max(p.satz for p in teile)
    einfach = einfachgebuehr_fuer(wertsumme)
    grenze = max(rundung_cent(hoechster_satz * einfach), mindestbetrag)
    nach = min(roh, grenze)
    return {"norm": norm, "positionen": [p.nr for p in teile],
            "summe_einzelgebuehren": str(roh),
            "gesamtwert_wertteile": str(wertsumme),
            "hoechster_satz": str(hoechster_satz),
            "einfachgebuehr_gesamtwert": str(einfach),
            "hoechstbetrag": str(grenze), "gekappt": roh > grenze,
            "kuerzung": str(roh - nach), "betrag_nach_kappung": str(nach),
            "quelle": "executor"}


def kappung_beschreibung(k: dict[str, Any], nr_praefix: str) -> str:
    """Rechenketten-Text zu `teilwert_kappung` — auch wenn sie nicht greift."""
    return (f"Verschiedene Gebührensätze für Teile des Gegenstands "
            f"({', '.join(nr_praefix + nr for nr in k['positionen'])}): Summe "
            f"der Einzelgebühren {k['summe_einzelgebuehren']} €; Höchstbetrag "
            f"= Satz {k['hoechster_satz']} x 1,0-Gebühr aus dem Gesamtbetrag "
            f"der Wertteile {k['gesamtwert_wertteile']} € "
            f"({k['einfachgebuehr_gesamtwert']} €) = {k['hoechstbetrag']} € — "
            + (f"Kappung greift, Kürzung um {k['kuerzung']} € auf "
               f"{k['betrag_nach_kappung']} €." if k["gekappt"] else
               "Kappung greift nicht, es bleibt bei der Summe der "
               "Einzelgebühren."))


@dataclass
class StufenSchritt:
    """Ein Glied der Herleitung der 1,0-Gebühr (für die Rechenkette)."""
    von_wert: Decimal
    bis_wert: Decimal
    schritt: Decimal
    zuschlag_je_schritt: Decimal
    angefangene_schritte: int
    teilbetrag: Decimal
    bereich: str  # "grundbetrag" | "stufe" | "ueber_hoechstwert"

    def as_dict(self) -> dict[str, Any]:
        return {
            "bereich": self.bereich,
            "von_wert": str(self.von_wert),
            "bis_wert": str(self.bis_wert) if self.bis_wert is not None else None,
            "schritt": str(self.schritt) if self.schritt else None,
            "zuschlag_je_schritt": str(self.zuschlag_je_schritt) if self.zuschlag_je_schritt else None,
            "angefangene_schritte": self.angefangene_schritte,
            "teilbetrag": str(self.teilbetrag),
        }


@dataclass
class EinfachgebuehrErgebnis:
    gegenstandswert: Decimal
    einfachgebuehr: Decimal
    herleitung: list[StufenSchritt] = field(default_factory=list)


def _ceil_schritte(spanne: Decimal, schritt: Decimal) -> int:
    """Anzahl der „angefangenen" Schritte (aufrunden, § 13/§ 34: „für jeden
    angefangenen Betrag von weiteren ... Euro")."""
    quotient = (spanne / schritt).to_integral_value(rounding=ROUND_CEILING)
    return int(quotient)


def einfachgebuehr(gegenstandswert: Decimal, stand: dict[str, Any]) -> EinfachgebuehrErgebnis:
    """Berechnet die 1,0-Gebühr (Wertgebühr) für `gegenstandswert` nach der
    gesetzlichen Stufenformel des übergebenen Tabellenstands.

    `stand` (Daten aus gebuehrentabelle.json, ein Eintrag aus "staende"):
        grundbetrag, grundbetrag_bis_wert, stufen (Liste von
        {bis_wert, schritt, zuschlag}, aufsteigend), ueber_hoechstwert
        ({schritt, zuschlag}).

    Wirft WertgebuehrFehler bei gegenstandswert <= 0 oder kaputten
    Tabellendaten (nicht aufsteigende Stufen) — nie eine stille
    Fehlberechnung.
    """
    wert = D(gegenstandswert)
    if wert <= 0:
        raise WertgebuehrFehler(
            f"Gegenstandswert/Streitwert muss > 0 sein, ist {wert}")

    grundbetrag_bis = D(stand["grundbetrag_bis_wert"])
    gebuehr = D(stand["grundbetrag"])
    herleitung: list[StufenSchritt] = [StufenSchritt(
        von_wert=Decimal("0.01"), bis_wert=grundbetrag_bis,
        schritt=Decimal("0"), zuschlag_je_schritt=Decimal("0"),
        angefangene_schritte=0, teilbetrag=gebuehr, bereich="grundbetrag")]

    if wert <= grundbetrag_bis:
        return EinfachgebuehrErgebnis(wert, rundung_cent(gebuehr), herleitung)

    vorherige_grenze = grundbetrag_bis
    stufen = stand["stufen"]
    letzte_bis = grundbetrag_bis
    for i, stufe in enumerate(stufen):
        bis = D(stufe["bis_wert"])
        schritt = D(stufe["schritt"])
        zuschlag = D(stufe["zuschlag"])
        if bis <= vorherige_grenze:
            raise WertgebuehrFehler(
                f"Tabellendaten defekt: Stufe {i} (bis_wert={bis}) liegt nicht "
                f"aufsteigend hinter der vorherigen Grenze ({vorherige_grenze})")
        if schritt <= 0 or zuschlag <= 0:
            raise WertgebuehrFehler(
                f"Tabellendaten defekt: Stufe {i} hat nicht-positiven "
                f"schritt/zuschlag ({schritt}/{zuschlag})")
        obergrenze = min(wert, bis)
        spanne = obergrenze - vorherige_grenze
        anzahl = _ceil_schritte(spanne, schritt)
        teilbetrag = anzahl * zuschlag
        gebuehr += teilbetrag
        herleitung.append(StufenSchritt(
            von_wert=vorherige_grenze, bis_wert=obergrenze, schritt=schritt,
            zuschlag_je_schritt=zuschlag, angefangene_schritte=anzahl,
            teilbetrag=teilbetrag, bereich="stufe"))
        vorherige_grenze = bis
        letzte_bis = bis
        if wert <= bis:
            return EinfachgebuehrErgebnis(wert, rundung_cent(gebuehr), herleitung)

    # über der höchsten tabellierten Stufe (§ 13 Abs. 1 S. 3 RVG / § 34 Abs. 1
    # S. 3 GKG): fester Zuschlag je angefangenem Schritt.
    ueber = stand["ueber_hoechstwert"]
    schritt = D(ueber["schritt"])
    zuschlag = D(ueber["zuschlag"])
    if schritt <= 0 or zuschlag <= 0:
        raise WertgebuehrFehler(
            "Tabellendaten defekt: ueber_hoechstwert hat nicht-positiven "
            "schritt/zuschlag")
    spanne = wert - letzte_bis
    anzahl = _ceil_schritte(spanne, schritt)
    teilbetrag = anzahl * zuschlag
    gebuehr += teilbetrag
    herleitung.append(StufenSchritt(
        von_wert=letzte_bis, bis_wert=None, schritt=schritt,
        zuschlag_je_schritt=zuschlag, angefangene_schritte=anzahl,
        teilbetrag=teilbetrag, bereich="ueber_hoechstwert"))
    return EinfachgebuehrErgebnis(wert, rundung_cent(gebuehr), herleitung)
