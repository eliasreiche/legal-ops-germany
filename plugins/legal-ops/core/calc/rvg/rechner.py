#!/usr/bin/env python3
"""rvg.rechner — RVG-Gebührenberechnung (Wertgebühren, Zivilsachen), P3.

Baut aus Streitwert, Stichtag (§ 60 Abs. 1 RVG) und einer oder mehreren
**Angelegenheiten** (je eine Liste von Gebührentatbeständen, VV-RVG-Nummern)
eine vollständige, nachvollziehbare Rechenkette:

* Wert-Kappung nach § 22 Abs. 2 Satz 1 RVG (höchstens 30 Mio. € je
  Angelegenheit) — als eigene Rechenketten-Zeile mit Warnung, nie still,
* Tabellenstand-Auswahl, 1,0-Gebühr nach der Stufenformel des § 13 RVG,
* je Angelegenheit: Positionen (Satz × 1,0-Gebühr, Mindestbetrags-Floor
  § 13 Abs. 3 RVG), **eigene** Auslagenpauschale Nr. 7002 (20 %, max. 20 €
  je Angelegenheit) und **eigene** Umsatzsteuer Nr. 7008,
* optionale Anrechnung der Geschäftsgebühr auf die Verfahrensgebühr
  (Vorbem. 3 Abs. 4 VV RVG) — verbindet zwei Angelegenheiten,
* Gesamtvergütung als Summe über die Angelegenheiten (gleicher Gläubiger,
  als solche beschriftet).

**Angelegenheits-Grenze:** Außergerichtliche Vertretung (Teil 2 VV RVG,
Nr. 2300) und gerichtliches Verfahren (Teil 3 VV RVG, Nr. 3100/3104) sind
verschiedene Angelegenheiten (§§ 16 ff. RVG; die Anrechnung nach Vorbem. 3
Abs. 4 VV RVG setzt zwei Angelegenheiten gerade voraus). Teil-2- und
Teil-3-Tatbestände in derselben Angelegenheit sind deshalb ein
Eingabefehler — kein stilles Zusammenrechnen von 7002/USt über die
Angelegenheits-Grenze hinweg. Teil-1-Gebühren (1000/1003/1008) entstehen
neben den Gebühren der anderen Teile (Vorbem. 1 VV RVG) und dürfen in jeder
Angelegenheit stehen.

**Instanzen-Grenze:** Der Katalog deckt den Zivilprozess-Instanzenzug ab —
erste Instanz (Nr. 3100/3104), Berufung (Nr. 3200/3201/3202) und Revision
(Nr. 3206–3210). Jeder Rechtszug ist eine eigene Angelegenheit (§ 17 Nr. 1
RVG); Teil-3-Tatbestände verschiedener Instanzen in derselben Angelegenheit
sind ein Eingabefehler (je Instanz eigene 7002/USt), analog zur Teil-2/Teil-3-
Grenze. Die Einigungsgebühr Nr. 1004 (erhöhter Satz im Berufungs-/Revisions-
verfahren) ist nur in einer Angelegenheit mit einem Berufungs-/Revisions-
Tatbestand zulässig (sonst Nr. 1000/1003). Die Anrechnung nach Vorbem. 3
Abs. 4 VV RVG erfolgt nur auf die Verfahrensgebühr des ersten Rechtszugs
(Nr. 3100), nicht auf Nr. 3200/3206/3208.

**Scope-Grenze (bewusst, siehe SKILL.md):** Nur Wertgebühren in Zivilsachen.
Betragsrahmengebühren (Straf-/Sozialrecht), PKH-Vergütung (§ 49 RVG) und
Beratungshilfe sind nicht im Katalog (`vv-katalog.json`) und werden als
Eingabefehler abgelehnt — nie ein geratener Betrag. § 22 Abs. 2 Satz 2 RVG
(mehrere Auftraggeber wegen verschiedener Gegenstände: je Person 30 Mio. €,
insgesamt 100 Mio. €) ist nicht modelliert — Erhöhungsgebühr Nr. 1008 in
Kombination mit einem Wert über 30 Mio. € wird abgelehnt statt womöglich
falsch gekappt.

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

_RVG_DIR = Path(__file__).resolve().parent
_CALC_DIR = _RVG_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

# Vollqualifizierte Paketimporte (rvg.tabelle, nicht bloß "tabelle") — ein
# bloßer Modulname würde im sys.modules-Cache mit gkg.tabelle kollidieren
# (beide Pakete haben eine gleichnamige tabelle.py), und je nach Importreihen-
# folge stillschweigend die falsche Gebührentabelle liefern.
from wertgebuehr_formel import D, WertgebuehrFehler, rundung_cent  # noqa: E402
from rvg.tabelle import einfachgebuehr as _einfachgebuehr_stichtag  # noqa: E402

KATALOG_PFAD = _RVG_DIR / "vv-katalog.json"

AUSLAGENPAUSCHALE_SATZ = Decimal("0.20")
AUSLAGENPAUSCHALE_MAX = Decimal("20.00")
UST_SATZ = Decimal("0.19")
ERHOEHUNG_JE_AUFTRAGGEBER = Decimal("0.3")
ERHOEHUNG_MAX_SATZ = Decimal("2.0")
ANRECHNUNG_MAX_SATZ = Decimal("0.75")
ANRECHNUNG_FAKTOR = Decimal("0.5")
WERT_HOECHSTGRENZE = Decimal("30000000.00")   # § 22 Abs. 2 Satz 1 RVG

# Positionen, die NICHT als "tatbestaende"-Eintrag angegeben werden — sie
# werden über eigene Anfrage-Flags gesteuert (auslagenpauschale, umsatzsteuer).
_UEBER_FLAG_GESTEUERT = {"7002", "7008"}


class RVGEingabeFehler(WertgebuehrFehler):
    """Ungültige RVG-Anfrage (Scope, unbekannte Nr., Typfehler, ...)."""


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
class AngelegenheitErgebnis:
    """Ergebnis einer einzelnen Angelegenheit — eigene Gebühren, eigene
    Auslagenpauschale (Nr. 7002), eigene USt (Nr. 7008)."""
    bezeichnung: str
    positionen: list[Position]
    zwischensumme_gebuehren: Decimal
    auslagenpauschale: Decimal
    netto: Decimal
    ust_satz: Decimal
    ust: Decimal
    gesamt: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "bezeichnung": self.bezeichnung,
            "positionen": [p.as_dict() for p in self.positionen],
            "ergebnis": {
                "zwischensumme_gebuehren": str(self.zwischensumme_gebuehren),
                "auslagenpauschale": str(self.auslagenpauschale),
                "netto": str(self.netto),
                "ust_satz": str(self.ust_satz),
                "ust": str(self.ust),
                "gesamt": str(self.gesamt),
                "quelle": "executor",
            },
        }


@dataclass
class RVGErgebnis:
    streitwert: Decimal                 # ggf. gekappt (§ 22 Abs. 2 S. 1 RVG)
    streitwert_eingabe: Decimal         # wie eingegeben
    wert_gekappt: bool
    stichtag: _dt.date
    tabellenstand: dict[str, Any]
    einfachgebuehr: Decimal
    angelegenheiten: list[AngelegenheitErgebnis]
    anrechnung: dict[str, Any] | None
    gesamt_verguetung: Decimal          # Summe über alle Angelegenheiten
    rechenkette: list[RechenSchritt] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


def _pruefe_bool(wert: Any, feld: str) -> bool:
    if not isinstance(wert, bool):
        raise RVGEingabeFehler(
            f"'{feld}' muss ein JSON-Boolean (true/false) sein, nicht {wert!r}")
    return wert


def _pruefe_ganzzahl_ab1(wert: Any, feld: str) -> int:
    if not isinstance(wert, int) or isinstance(wert, bool) or wert < 1:
        raise RVGEingabeFehler(f"'{feld}' muss eine ganze Zahl >= 1 sein, nicht {wert!r}")
    return wert


def _bekannte_tatbestaende(positionen_katalog: dict[str, Any]) -> str:
    """Nur die Nummern, die tatsächlich als 'tatbestaende'-Eintrag zulässig
    sind — 7002/7008 laufen über Flags und gehören nicht in diese Liste."""
    return ", ".join(sorted(
        nr for nr in positionen_katalog if nr not in _UEBER_FLAG_GESTEUERT))


def _berechne_positionen(tatbestaende: list[dict[str, Any]],
                         einfachgebuehr: Decimal, mindestbetrag: Decimal,
                         positionen_katalog: dict[str, Any],
                         angelegenheit_label: str,
                         schritt, warnungen: list[str]
                         ) -> dict[str, Position]:
    """Berechnet die Gebührenpositionen EINER Angelegenheit (inkl. Nr. 1008),
    prüft die Teil-2/Teil-3-Kollision und liefert {nr: Position}
    (Nr.-1008-Einträge unter Schlüssel "1008:<basis_nr>")."""
    if not isinstance(tatbestaende, list) or not tatbestaende:
        raise RVGEingabeFehler(
            f"{angelegenheit_label}: 'tatbestaende' muss eine nichtleere "
            f"Liste sein")

    gesehene_nrn: set[str] = set()
    basis_positionen: dict[str, Position] = {}
    erhoehungs_eintraege: list[dict[str, Any]] = []
    teile_vertreten: dict[int, str] = {}   # vv_teil -> erste Nr. dieses Teils
    instanz_vertreten: dict[str, str] = {}  # instanz -> erste Teil-3-Nr. dieser Instanz

    for eintrag in tatbestaende:
        if not isinstance(eintrag, dict) or "nr" not in eintrag:
            raise RVGEingabeFehler(
                f"{angelegenheit_label}: jeder Eintrag in 'tatbestaende' muss "
                f"ein Objekt mit 'nr' sein, nicht {eintrag!r}")
        nr = str(eintrag["nr"])
        if nr in _UEBER_FLAG_GESTEUERT:
            raise RVGEingabeFehler(
                f"Nr. {nr} VV RVG wird nicht als Tatbestand angegeben, sondern "
                f"über die Anfrage-Flags 'auslagenpauschale'/'umsatzsteuer' "
                f"gesteuert")
        if nr == "1008":
            erhoehungs_eintraege.append(eintrag)
            continue
        if nr not in positionen_katalog:
            raise RVGEingabeFehler(
                f"Nr. {nr} VV RVG ist nicht unterstützt — dieser Rechner deckt "
                f"nur Wertgebühren in Zivilsachen ab (bekannte Tatbestände: "
                f"{_bekannte_tatbestaende(positionen_katalog)}; Auslagen-"
                f"pauschale und Umsatzsteuer laufen über die Flags "
                f"'auslagenpauschale'/'umsatzsteuer'). Betragsrahmengebühren "
                f"(Straf-/Sozialrecht), PKH-Vergütung (§ 49 RVG) und "
                f"Beratungshilfe sind außerhalb des Scopes — keine "
                f"automatische Berechnung möglich.")
        if nr in gesehene_nrn:
            raise RVGEingabeFehler(
                f"{angelegenheit_label}: Nr. {nr} VV RVG ist mehrfach in "
                f"'tatbestaende' angegeben — nicht eindeutig, welche Angabe "
                f"gelten soll")
        gesehene_nrn.add(nr)

        katalog_eintrag = positionen_katalog[nr]

        # Teil-2/Teil-3-Kollision: außergerichtliche Vertretung (Teil 2 VV)
        # und gerichtliches Verfahren (Teil 3 VV) sind verschiedene
        # Angelegenheiten — Teil-1-Gebühren entstehen daneben (Vorbem. 1 VV)
        # und lösen keine Prüfung aus.
        teil = int(katalog_eintrag["vv_teil"])
        if teil in (2, 3):
            anderer = 5 - teil   # 2 <-> 3
            if anderer in teile_vertreten:
                raise RVGEingabeFehler(
                    f"{angelegenheit_label}: Nr. {teile_vertreten[anderer]} "
                    f"(Teil {anderer} VV RVG) und Nr. {nr} (Teil {teil} VV "
                    f"RVG) in derselben Angelegenheit — außergerichtliche "
                    f"Vertretung und gerichtliches Verfahren sind verschiedene "
                    f"Angelegenheiten (§§ 16 ff. RVG; die Anrechnung nach "
                    f"Vorbem. 3 Abs. 4 VV RVG setzt zwei Angelegenheiten "
                    f"voraus) mit je eigener Auslagenpauschale Nr. 7002 und "
                    f"eigener USt-Basis. Die Anfrage über "
                    f"'rvg.angelegenheiten' in getrennte Angelegenheiten "
                    f"aufteilen (siehe schema/README.md).")
            teile_vertreten.setdefault(teil, nr)

        # Instanz-Kollision innerhalb Teil 3: jeder Rechtszug ist eine eigene
        # Angelegenheit (§ 17 Nr. 1 RVG) — Berufungs-/Revisions- und
        # erstinstanzliche Tatbestände dürfen nicht in derselben Angelegenheit
        # stehen (sonst würden 7002/USt über die Instanz-Grenze hinweg still
        # zusammengerechnet). Positionen derselben Instanz (z. B.
        # Verfahrens- und Terminsgebühr) sind zulässig.
        if teil == 3:
            instanz = str(katalog_eintrag["instanz"])
            for vorhandene_instanz, vorhandene_nr in instanz_vertreten.items():
                if vorhandene_instanz != instanz:
                    raise RVGEingabeFehler(
                        f"{angelegenheit_label}: Nr. {vorhandene_nr} "
                        f"(Instanz '{vorhandene_instanz}') und Nr. {nr} "
                        f"(Instanz '{instanz}') in derselben Angelegenheit — "
                        f"jeder Rechtszug ist eine eigene Angelegenheit "
                        f"(§ 17 Nr. 1 RVG) mit je eigener Auslagenpauschale "
                        f"Nr. 7002 und eigener USt-Basis. Die Anfrage über "
                        f"'rvg.angelegenheiten' in getrennte Angelegenheiten "
                        f"je Instanz aufteilen (siehe schema/README.md).")
            instanz_vertreten.setdefault(instanz, nr)

        art = katalog_eintrag["art"]
        if art == "festsatz":
            katalog_satz = D(katalog_eintrag["satz"])
            if "satz" in eintrag and D(eintrag["satz"]) != katalog_satz:
                raise RVGEingabeFehler(
                    f"Satz von Nr. {nr} VV RVG ist gesetzlich festgelegt "
                    f"({katalog_satz}, {katalog_eintrag['norm']}) und kann "
                    f"nicht auf {eintrag['satz']!r} überschrieben werden")
            satz = katalog_satz
        elif art == "satzrahmen":
            if "satz" not in eintrag:
                raise RVGEingabeFehler(
                    f"Nr. {nr} VV RVG hat einen Satzrahmen "
                    f"({katalog_eintrag['satzrahmen_min']}-"
                    f"{katalog_eintrag['satzrahmen_max']}) — 'satz' ist "
                    f"Pflichtangabe, keine automatische Annahme des "
                    f"Regelsatzes")
            satz = D(eintrag["satz"])
            smin = D(katalog_eintrag["satzrahmen_min"])
            smax = D(katalog_eintrag["satzrahmen_max"])
            if not (smin <= satz <= smax):
                raise RVGEingabeFehler(
                    f"Satz {satz} für Nr. {nr} VV RVG liegt außerhalb des "
                    f"Satzrahmens {smin}-{smax}")
        else:
            raise RVGEingabeFehler(f"unbekannte Positionsart im Katalog: {art!r}")

        betrag = rundung_cent(satz * einfachgebuehr)
        hinweise: list[str] = []
        mindest_gegriffen = False
        if betrag < mindestbetrag:
            betrag = mindestbetrag
            mindest_gegriffen = True
            hinweise.append(
                f"Mindestbetrag (§ 13 Abs. 3 RVG, {mindestbetrag} €) greift — "
                f"berechneter Betrag lag darunter.")
        if art == "satzrahmen" and satz > D(katalog_eintrag["regelsatz"]):
            hinweise.append(katalog_eintrag["regelsatz_hinweis"])

        pos = Position(nr=nr, bezeichnung=katalog_eintrag["bezeichnung"],
                       norm=katalog_eintrag["norm"], satz=satz, betrag=betrag,
                       mindestbetrag_gegriffen=mindest_gegriffen, hinweise=hinweise)
        basis_positionen[nr] = pos
        schritt(katalog_eintrag["norm"],
                f"{angelegenheit_label}: {katalog_eintrag['bezeichnung']} "
                f"(Nr. {nr} VV RVG): Satz {satz} x {einfachgebuehr} € = {betrag} €"
                + (" (Mindestbetrag angewendet)" if mindest_gegriffen else ""),
                str(betrag))

    # --- Nr. 1004 (Einigungsgebühr im Berufungs-/Revisionsverfahren) nur in
    #     einer Angelegenheit mit einem Berufungs-/Revisions-Tatbestand ---
    if "1004" in basis_positionen:
        erlaubte = positionen_katalog["1004"].get(
            "nur_bei_instanz", ["berufung", "revision"])
        if not any(i in erlaubte for i in instanz_vertreten):
            raise RVGEingabeFehler(
                f"{angelegenheit_label}: Nr. 1004 VV RVG (Einigungsgebühr im "
                f"Berufungs-/Revisionsverfahren) ist nur in einer "
                f"Angelegenheit mit einem Berufungs- oder Revisions-Tatbestand "
                f"(Nr. 3200 ff. / 3206 ff.) zulässig. Für die Einigung in "
                f"erster Instanz oder außergerichtlich gilt Nr. 1000 (1,5) "
                f"bzw. Nr. 1003 (1,0).")

    # --- Erhöhungsgebühr Nr. 1008 ---
    erhoehungs_katalog = positionen_katalog["1008"]
    for eintrag in erhoehungs_eintraege:
        basis_nr = eintrag.get("erhoeht_position")
        if not basis_nr or str(basis_nr) not in basis_positionen:
            raise RVGEingabeFehler(
                f"{angelegenheit_label}: Nr. 1008 VV RVG (Erhöhungsgebühr) "
                f"verlangt 'erhoeht_position' mit der Nr. einer in derselben "
                f"Angelegenheit angeforderten Basis-Position (3100 oder 2300)")
        basis_nr = str(basis_nr)
        schluessel = f"1008:{basis_nr}"
        if schluessel in basis_positionen:
            raise RVGEingabeFehler(
                f"{angelegenheit_label}: mehrere Nr.-1008-Einträge für "
                f"dieselbe Basis-Position {basis_nr} — nicht eindeutig, "
                f"addiere 'weitere_auftraggeber' in einem Eintrag")
        if basis_nr not in erhoehungs_katalog["anwendbar_auf"]:
            raise RVGEingabeFehler(
                f"Nr. 1008 VV RVG ist auf Nr. {basis_nr} nicht anwendbar "
                f"(anwendbar auf: {', '.join(erhoehungs_katalog['anwendbar_auf'])})")
        weitere = _pruefe_ganzzahl_ab1(eintrag.get("weitere_auftraggeber"),
                                       "weitere_auftraggeber")
        roh_satz = D(weitere) * ERHOEHUNG_JE_AUFTRAGGEBER
        gekappt = roh_satz > ERHOEHUNG_MAX_SATZ
        satz = min(roh_satz, ERHOEHUNG_MAX_SATZ)
        betrag = rundung_cent(satz * einfachgebuehr)
        hinweise = []
        if gekappt:
            hinweise.append(
                f"Erhöhung nach Nr. 1008 VV RVG auf Gebührensatz "
                f"{ERHOEHUNG_MAX_SATZ} gekappt (Anm. Abs. 3 zu Nr. 1008 VV RVG) "
                f"— roh berechnet wären {roh_satz} gewesen.")
        pos = Position(nr="1008",
                       bezeichnung=f"Erhöhung für weitere Auftraggeber "
                                   f"({weitere} weitere, bezogen auf Nr. {basis_nr})",
                       norm=erhoehungs_katalog["norm"], satz=satz, betrag=betrag,
                       hinweise=hinweise)
        basis_positionen[schluessel] = pos
        schritt(erhoehungs_katalog["norm"],
                f"{angelegenheit_label}: Erhöhung für {weitere} weitere "
                f"Auftraggeber auf Nr. {basis_nr}: Satz {satz} x "
                f"{einfachgebuehr} € = {betrag} €"
                + (" (gekappt)" if gekappt else ""),
                str(betrag))
        if gekappt:
            warnungen.append(hinweise[0])

    return basis_positionen


def berechne(streitwert: Any, stichtag: _dt.date,
             angelegenheiten: list[dict[str, Any]], *,
             anrechnung_2300_auf_3100: bool = False,
             auslagenpauschale: bool = True,
             umsatzsteuer: bool = True,
             katalog: dict[str, Any] | None = None) -> RVGErgebnis:
    """Berechnet die RVG-Wertgebühren für `streitwert`/`stichtag` über eine
    oder mehrere Angelegenheiten.

    angelegenheiten: Liste von {"bezeichnung": str, "tatbestaende": [...],
    optional "auslagenpauschale"/"umsatzsteuer" (Override der Top-Level-
    Flags)}. Jede Angelegenheit wird separat gerechnet: eigene Gebühren,
    eigene 7002-Pauschale (20 %, max. 20 €), eigene USt.

    tatbestaende je Angelegenheit: Liste von {"nr": "3100", ...}:
      - Festsatz (3100, 3104, 1000, 1003): kein 'satz' — gesetzlich fix.
      - Satzrahmen (2300): 'satz' (Pflicht, im Rahmen 0,5-2,5).
      - Erhöhung (1008): 'erhoeht_position' + 'weitere_auftraggeber'.

    anrechnung_2300_auf_3100 verbindet zwei Angelegenheiten (Vorbem. 3
    Abs. 4 VV RVG): verlangt genau eine Nr. 2300 und genau eine Nr. 3100
    über alle Angelegenheiten hinweg; der identische Gegenstandswert ist
    konstruktiv sichergestellt (ein Streitwert für die gesamte Anfrage).
    """
    kat = katalog or lade_katalog()
    positionen_katalog = kat["positionen"]

    wert_eingabe = D(streitwert)
    if wert_eingabe <= 0:
        raise RVGEingabeFehler(
            f"Streitwert/Gegenstandswert muss > 0 sein, ist {wert_eingabe}")

    if not isinstance(angelegenheiten, list) or not angelegenheiten:
        raise RVGEingabeFehler("'angelegenheiten' muss eine nichtleere Liste sein")

    kette: list[RechenSchritt] = []
    warnungen: list[str] = []

    def schritt(norm: str, beschreibung: str, ergebnis: str | None) -> None:
        kette.append(RechenSchritt(schritt=len(kette) + 1, norm=norm,
                                   beschreibung=beschreibung, ergebnis=ergebnis))

    # --- § 22 Abs. 2 RVG: Wert-Höchstgrenze (Kappung, keine Ablehnung) ---
    wert = wert_eingabe
    wert_gekappt = False
    if wert_eingabe > WERT_HOECHSTGRENZE:
        # § 22 Abs. 2 Satz 2 RVG (mehrere Auftraggeber wegen verschiedener
        # Gegenstände: je Person 30 Mio. €, insgesamt 100 Mio. €) ist nicht
        # modelliert — bei Erhöhungsgebühr Nr. 1008 wäre die einfache
        # 30-Mio-Kappung möglicherweise falsch: ablehnen statt raten.
        hat_1008 = any(
            isinstance(e, dict) and str(e.get("nr")) == "1008"
            for a in angelegenheiten if isinstance(a, dict)
            for e in (a.get("tatbestaende") or [])
            if isinstance(a.get("tatbestaende"), list))
        if hat_1008:
            raise RVGEingabeFehler(
                f"Gegenstandswert {wert_eingabe} € über 30 Mio. € in "
                f"Kombination mit der Erhöhungsgebühr Nr. 1008 VV RVG: bei "
                f"mehreren Auftraggebern wegen verschiedener Gegenstände gilt "
                f"die Höchstgrenze je Person (30 Mio. €, insgesamt höchstens "
                f"100 Mio. €, § 22 Abs. 2 Satz 2 RVG) — diese Konstellation "
                f"ist nicht modelliert und wird nicht stillschweigend auf "
                f"30 Mio. € gekappt. Anwaltlich prüfen und die Werte je "
                f"Auftraggeber getrennt ansetzen.")
        wert = WERT_HOECHSTGRENZE
        wert_gekappt = True
        schritt("§ 22 Abs. 2 Satz 1 RVG",
                f"Gegenstandswert {wert_eingabe} € übersteigt die Höchstgrenze "
                f"— für die Gebührenberechnung auf {WERT_HOECHSTGRENZE} € "
                f"gekappt.", str(wert))
        warnungen.append(
            f"Gegenstandswert nach § 22 Abs. 2 Satz 1 RVG auf 30 Mio. € "
            f"gekappt (eingegeben: {wert_eingabe} €). Sind mehrere Personen "
            f"wegen verschiedener Gegenstände Auftraggeber, gilt die Grenze "
            f"je Person, insgesamt höchstens 100 Mio. € (§ 22 Abs. 2 Satz 2 "
            f"RVG) — das modelliert dieser Rechner nicht; anwaltlich prüfen.")

    eg_ergebnis, stand = _einfachgebuehr_stichtag(wert, stichtag)
    einfachgebuehr = eg_ergebnis.einfachgebuehr
    mindestbetrag = D(stand["mindestbetrag"])

    schritt("§ 60 Abs. 1 RVG",
            f"Stichtag (Auftragserteilung) {stichtag.isoformat()} -> "
            f"Tabellenstand '{stand['bezeichnung']}' (gültig {stand['gueltig_ab']}"
            f"{' bis ' + stand['gueltig_bis'] if stand.get('gueltig_bis') else ' bis heute'}).",
            stand["id"])
    schritt("§ 13 Abs. 1 RVG",
            f"1,0-Gebühr (Einfachgebühr) für Gegenstandswert {wert} €.",
            str(einfachgebuehr))

    auslagen_default = _pruefe_bool(auslagenpauschale, "auslagenpauschale")
    ust_default = _pruefe_bool(umsatzsteuer, "umsatzsteuer")

    # --- je Angelegenheit: Positionen berechnen ---
    angelegenheit_daten: list[dict[str, Any]] = []
    for i, a in enumerate(angelegenheiten):
        if not isinstance(a, dict) or not isinstance(a.get("tatbestaende"), list):
            raise RVGEingabeFehler(
                f"jede Angelegenheit muss ein Objekt mit 'tatbestaende'-Liste "
                f"sein, nicht {a!r}")
        bezeichnung = str(a.get("bezeichnung") or f"Angelegenheit {i + 1}")
        label = f"Angelegenheit '{bezeichnung}'"
        positionen = _berechne_positionen(
            a["tatbestaende"], einfachgebuehr, mindestbetrag,
            positionen_katalog, label, schritt, warnungen)
        a_auslagen = a.get("auslagenpauschale", auslagen_default)
        a_ust = a.get("umsatzsteuer", ust_default)
        angelegenheit_daten.append({
            "bezeichnung": bezeichnung, "label": label,
            "positionen": positionen,
            "auslagenpauschale": _pruefe_bool(a_auslagen, "auslagenpauschale"),
            "umsatzsteuer": _pruefe_bool(a_ust, "umsatzsteuer"),
        })

    # --- Anrechnung Geschäftsgebühr auf Verfahrensgebühr (verbindet zwei
    #     Angelegenheiten, Vorbem. 3 Abs. 4 VV RVG) ---
    anrechnung_result: dict[str, Any] | None = None
    if _pruefe_bool(anrechnung_2300_auf_3100, "anrechnung_2300_auf_3100"):
        fund_2300 = [(d, d["positionen"]["2300"]) for d in angelegenheit_daten
                     if "2300" in d["positionen"]]
        fund_3100 = [(d, d["positionen"]["3100"]) for d in angelegenheit_daten
                     if "3100" in d["positionen"]]
        # Anrechnung ausschließlich auf die Verfahrensgebühr des ERSTEN
        # Rechtszugs (Nr. 3100) — nicht auf eine Berufungs-/Revisions-
        # Verfahrensgebühr (Vorbem. 3 Abs. 4 VV RVG; nach BGH die des ersten
        # Rechtszugs). Gezielte Fehlermeldung, wenn nur eine höherinstanzliche
        # Verfahrensgebühr vorliegt.
        if not fund_3100:
            hoehere_vg = sorted({
                nr for d in angelegenheit_daten
                for nr in ("3200", "3206", "3208") if nr in d["positionen"]})
            if hoehere_vg:
                raise RVGEingabeFehler(
                    f"'anrechnung_2300_auf_3100' verlangt die "
                    f"Verfahrensgebühr des ersten Rechtszugs (Nr. 3100). Die "
                    f"Geschäftsgebühr wird nach Vorbem. 3 Abs. 4 VV RVG nur "
                    f"auf die Verfahrensgebühr des ersten Rechtszugs "
                    f"angerechnet, nicht auf eine Berufungs-/Revisions-"
                    f"Verfahrensgebühr (hier vorhanden: Nr. "
                    f"{', '.join(hoehere_vg)}). In der Berufungs-/Revisions-"
                    f"instanz findet keine Anrechnung der erstinstanzlichen "
                    f"Geschäftsgebühr statt.")
        if len(fund_2300) != 1 or len(fund_3100) != 1:
            raise RVGEingabeFehler(
                "'anrechnung_2300_auf_3100' verlangt genau eine Nr. 2300 und "
                "genau eine Nr. 3100 über alle Angelegenheiten hinweg "
                f"(gefunden: {len(fund_2300)} x 2300, {len(fund_3100)} x 3100)")
        geschaeft_daten, geschaeft = fund_2300[0]
        verfahren_daten, verfahren = fund_3100[0]
        anr_regel = kat["anrechnung_geschaeftsgebuehr_auf_verfahrensgebuehr"]
        halbe_satz = geschaeft.satz * ANRECHNUNG_FAKTOR
        anr_satz = min(halbe_satz, ANRECHNUNG_MAX_SATZ)
        anr_betrag = rundung_cent(anr_satz * einfachgebuehr)
        vor_anrechnung = verfahren.betrag
        neuer_verfahren_betrag = vor_anrechnung - anr_betrag
        if neuer_verfahren_betrag < 0:
            warnungen.append(
                "Anrechnungsbetrag übersteigt die Verfahrensgebühr — auf 0 € "
                "begrenzt; bitte Konstellation anwaltlich prüfen.")
            neuer_verfahren_betrag = Decimal("0.00")
        verfahren.betrag = neuer_verfahren_betrag
        verfahren.hinweise.append(
            f"Um {anr_betrag} € gemindert durch Anrechnung der Geschäftsgebühr "
            f"aus {geschaeft_daten['label']} ({anr_regel['norm']}).")
        anrechnung_result = {
            "norm": anr_regel["norm"],
            "geschaeftsgebuehr_angelegenheit": geschaeft_daten["bezeichnung"],
            "verfahrensgebuehr_angelegenheit": verfahren_daten["bezeichnung"],
            "geschaeftsgebuehr_satz": str(geschaeft.satz),
            "anrechnungssatz": str(anr_satz),
            "anrechnungsbetrag": str(anr_betrag),
            "verfahrensgebuehr_vor_anrechnung": str(vor_anrechnung),
            "verfahrensgebuehr_nach_anrechnung": str(neuer_verfahren_betrag),
            "quelle": "executor",
        }
        schritt(anr_regel["norm"],
                f"Anrechnung Geschäftsgebühr (Satz {geschaeft.satz}, "
                f"{geschaeft_daten['label']}) auf Verfahrensgebühr "
                f"({verfahren_daten['label']}): min({geschaeft.satz} x 0,5; "
                f"0,75) = {anr_satz} x {einfachgebuehr} € = {anr_betrag} € — "
                f"Verfahrensgebühr danach {neuer_verfahren_betrag} €.",
                str(neuer_verfahren_betrag))

    # --- je Angelegenheit: Zwischensumme, 7002, USt, Gesamt ---
    ergebnisse: list[AngelegenheitErgebnis] = []
    for d in angelegenheit_daten:
        positionen = list(d["positionen"].values())
        zwischensumme = rundung_cent(
            sum((p.betrag for p in positionen), Decimal("0.00")))
        schritt("Zwischensumme",
                f"{d['label']}: Summe der Gebührenpositionen (nach Anrechnung, "
                f"sofern angefordert).", str(zwischensumme))

        pauschale = Decimal("0.00")
        if d["auslagenpauschale"]:
            roh = rundung_cent(zwischensumme * AUSLAGENPAUSCHALE_SATZ)
            pauschale = min(roh, AUSLAGENPAUSCHALE_MAX)
            schritt("Nr. 7002 VV RVG",
                    f"{d['label']}: Auslagenpauschale — 20 % von "
                    f"{zwischensumme} € = {roh} €, gedeckelt auf höchstens "
                    f"{AUSLAGENPAUSCHALE_MAX} € (je Angelegenheit).",
                    str(pauschale))

        netto = rundung_cent(zwischensumme + pauschale)
        schritt("Netto", f"{d['label']}: Zwischensumme zzgl. Auslagenpauschale.",
                str(netto))

        ust = Decimal("0.00")
        if d["umsatzsteuer"]:
            ust = rundung_cent(netto * UST_SATZ)
            schritt("Nr. 7008 VV RVG",
                    f"{d['label']}: Umsatzsteuer — 19 % von {netto} € = {ust} €.",
                    str(ust))

        gesamt = rundung_cent(netto + ust)
        schritt("Gesamt (Angelegenheit)",
                f"{d['label']}: Netto zzgl. Umsatzsteuer.", str(gesamt))

        ergebnisse.append(AngelegenheitErgebnis(
            bezeichnung=d["bezeichnung"], positionen=positionen,
            zwischensumme_gebuehren=zwischensumme, auslagenpauschale=pauschale,
            netto=netto, ust_satz=UST_SATZ if d["umsatzsteuer"] else Decimal("0"),
            ust=ust, gesamt=gesamt))

    gesamt_verguetung = rundung_cent(
        sum((e.gesamt for e in ergebnisse), Decimal("0.00")))
    if len(ergebnisse) > 1:
        schritt("Gesamtvergütung",
                "Summe über alle Angelegenheiten (gleicher Gläubiger — die "
                "Angelegenheiten bleiben gebührenrechtlich getrennt, nur die "
                "Vergütungsforderung wird addiert).", str(gesamt_verguetung))

    return RVGErgebnis(
        streitwert=wert, streitwert_eingabe=wert_eingabe,
        wert_gekappt=wert_gekappt, stichtag=stichtag, tabellenstand=stand,
        einfachgebuehr=einfachgebuehr, angelegenheiten=ergebnisse,
        anrechnung=anrechnung_result, gesamt_verguetung=gesamt_verguetung,
        rechenkette=kette, warnungen=warnungen)
