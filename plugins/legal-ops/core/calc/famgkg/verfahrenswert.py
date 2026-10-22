#!/usr/bin/env python3
"""famgkg.verfahrenswert — Verfahrenswert-Ermittlung nach §§ 33 ff. FamGKG (P3).

Rechnet ausschließlich die **gesetzlich festen** Wertregeln — keine
Billigkeits- oder Ermessensentscheidung des Gerichts:

  * Ehesache (§ 43 FamGKG): Einkommenskomponente nach Abs. 2 (in drei
    Monaten erzieltes Nettoeinkommen beider Ehegatten) und die Grenzen nach
    Abs. 1 Satz 2 (mindestens 3.000 €, höchstens 1 Mio. €). Alles weitere
    (Umfang, Bedeutung, Vermögen) ist Ermessen nach Abs. 1 Satz 1 und kommt
    nur als ausdrücklicher Nutzer-`zuschlag` mit Pflicht-`begruendung`
    hinein — im Report als `quelle: "eingabe"` markiert, nie berechnet.
  * Versorgungsausgleich (§ 50 Abs. 1 FamGKG): je Anrecht 10 % (bei
    Ausgleichsansprüchen nach der Scheidung 20 %) des Drei-Monats-Netto
    beider Ehegatten, insgesamt mindestens 1.000 €.
  * Unterhalt (§ 51 Abs. 1 Satz 1, Abs. 2 Satz 1 FamGKG): für die ersten
    zwölf Monate nach Einreichung geforderter Betrag (höchstens der
    Gesamtbetrag der geforderten Leistung) plus bei Einreichung fällige
    Beträge.
  * Kindschaftssache (§ 45 Abs. 1, 2 FamGKG): gesetzlicher Festwert je
    Kindschaftssache (versioniert: 4.000 € / 5.000 €).
  * Abstammung, Ehewohnung, Haushalt, Gewaltschutz (§§ 47–49 FamGKG):
    gesetzlicher Festwert je Fallgruppe (versioniert). Die Fallgruppe ist
    Pflichteingabe — der Executor nimmt sie nie an. Ehewohnungs- und
    Haushaltssachen können Folgesachen sein (§ 137 Abs. 2 Satz 1 Nr. 3
    FamFG, nur wenn eine Entscheidung für den Fall der Scheidung zu treffen
    ist: § 200 Abs. 1 Nr. 2 / Abs. 2 Nr. 2 FamFG), Abstammungs- und
    Gewaltschutzsachen nie.
  * Bezifferte Geldforderung (§ 35 FamGKG): deren Höhe.
  * Auffangwert (§ 42 Abs. 3 FamGKG): 5.000 €.
  * Verbund (§ 44 FamGKG): Ehesache + Folgesachen; je Kindschaftsfolgesache
    Erhöhung des Ehesachenwerts um 20 %, höchstens um 4.000 € / 5.000 €
    (versioniert); übrige Folgesachen werden hinzugerechnet.
  * `verfahrenswert_festgesetzt` (je Gegenstand oder für das Ganze): der vom
    Gericht festgesetzte Wert schlägt die Berechnung — `quelle: "eingabe"`.
  * Einstweilige Anordnung (§ 41 Satz 2 FamGKG), nur auf ausdrückliche
    Angabe `einstweilige_anordnung: true` an einem Gegenstand einer
    selbständigen Familiensache: Ausgangswert = Hälfte des für die
    Hauptsache bestimmten Werts (inklusive gesetzlicher Mindestwerte), auf
    volle Cent gerundet. Die weitere Ermäßigung nach § 41 Satz 1 ist
    Ermessen des Gerichts und wird nie gerechnet.

Zahlen und Fundstellen stehen in `wertvorschriften.json` (versioniert nach
den Ständen der gebuehrentabelle.json, Auswahl nach § 63 Abs. 1 FamGKG).

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

from wertgebuehr_formel import D, WertgebuehrFehler, rundung_cent  # noqa: E402
from rechenschritt import RechenSchritt  # noqa: E402
from famgkg.tabelle import stand_fuer_stichtag  # noqa: E402

WERTVORSCHRIFTEN_PFAD = _FAMGKG_DIR / "wertvorschriften.json"

_ARTEN = ("versorgungsausgleich", "kindesunterhalt", "ehegattenunterhalt",
          "kindschaftssache", "abstammungssache", "ehewohnungssache",
          "haushaltssache", "gewaltschutzsache", "geldforderung", "auffangwert")

# §§ 47–49 FamGKG: Festwert je gesetzlicher Fallgruppe (Werte in
# wertvorschriften.json, `festwerte_47_49`). `folgesache` = die einzige
# Fallgruppe, die nach § 137 Abs. 2 Satz 1 Nr. 3 FamFG Folgesache sein kann
# ("wenn eine Entscheidung für den Fall der Scheidung zu treffen ist" —
# §§ 1568a, 1568b BGB), None = nie Folgesache (§ 137 Abs. 2, 3 FamFG nennen
# Abstammungs- und Gewaltschutzsachen nicht).
_FESTWERT_ARTEN: dict[str, dict[str, Any]] = {
    "abstammungssache": {
        "bezeichnung": "Abstammungssache", "norm": "§ 47 Abs. 1 FamGKG",
        "billigkeit": "§ 47 Abs. 2 FamGKG", "folgesache": None,
        "fallgruppen": {
            "169_nr_1_4": "§ 169 Nr. 1 und 4 FamFG — Feststellung des Bestehens "
                          "oder Nichtbestehens eines Eltern-Kind-Verhältnisses, "
                          "Anfechtung der Vaterschaft",
            "169_nr_2_3": "übrige Abstammungssachen, § 169 Nr. 2 und 3 FamFG — "
                          "Ersetzung der Einwilligung in eine genetische "
                          "Abstammungsuntersuchung, Einsicht in ein "
                          "Abstammungsgutachten"}},
    "ehewohnungssache": {
        "bezeichnung": "Ehewohnungssache", "norm": "§ 48 Abs. 1 FamGKG",
        "billigkeit": "§ 48 Abs. 3 FamGKG", "folgesache": "200_abs_1_nr_2",
        "fallgruppen": {
            "200_abs_1_nr_1": "§ 200 Abs. 1 Nr. 1 FamFG — § 1361b BGB (Ehewohnung "
                              "bei Getrenntleben)",
            "200_abs_1_nr_2": "§ 200 Abs. 1 Nr. 2 FamFG — § 1568a BGB (Ehewohnung "
                              "anlässlich der Scheidung)"}},
    "haushaltssache": {
        "bezeichnung": "Haushaltssache", "norm": "§ 48 Abs. 2 FamGKG",
        "billigkeit": "§ 48 Abs. 3 FamGKG", "folgesache": "200_abs_2_nr_2",
        "fallgruppen": {
            "200_abs_2_nr_1": "§ 200 Abs. 2 Nr. 1 FamFG — § 1361a BGB "
                              "(Haushaltsgegenstände bei Getrenntleben)",
            "200_abs_2_nr_2": "§ 200 Abs. 2 Nr. 2 FamFG — § 1568b BGB "
                              "(Haushaltsgegenstände anlässlich der Scheidung)"}},
    "gewaltschutzsache": {
        "bezeichnung": "Gewaltschutzsache", "norm": "§ 49 Abs. 1 FamGKG",
        "billigkeit": "§ 49 Abs. 2 FamGKG", "folgesache": None,
        "fallgruppen": {
            "1_gewschg": "§ 1 GewSchG — gerichtliche Schutzmaßnahmen",
            "eu_gewschvg": "Verfahren nach dem EU-Gewaltschutzverfahrensgesetz — "
                           "keine Gewaltschutzsache i. S. d. § 210 FamFG, von § 49 "
                           "Abs. 1 FamGKG gesondert erfasst; Bescheinigungsverfahren "
                           "laufen nach Vorbem. 1.3.2 Abs. 3 KV FamGKG über "
                           "Hauptabschnitt 7 (Positionen prüfen)",
            "2_gewschg": "§ 2 GewSchG — Überlassung einer gemeinsam genutzten "
                         "Wohnung"}},
}

# Gebühren für das Verfahren der einstweiligen Anordnung im KV-Katalog
# (KV 1410 Kindschaftssachen, KV 1420/1421 übrige Familiensachen).
_EA_POSITIONEN = ("1410", "1420", "1421")

# § 45 Abs. 1 Nr. 1–4 FamGKG (Nr. 5, § 1631e Abs. 3 BGB, nicht modelliert).
_KINDSCHAFT_45 = {"sorge": "Nr. 1", "umgang": "Nr. 2", "auskunft": "Nr. 3",
                  "herausgabe": "Nr. 4"}
# § 137 Abs. 3 FamFG: Kindschaftssachen, die Folgesachen sein können.
_KINDSCHAFT_137 = ("sorge", "umgang", "herausgabe")

_FELDER = {
    "ehesache": ("nettoeinkommen_monatlich", "zuschlag", "begruendung",
                 "verfahrenswert_festgesetzt"),
    "versorgungsausgleich": ("art", "anzahl_anrechte", "ausgleich_nach_scheidung",
                             "nettoeinkommen_monatlich", "verfahrenswert_festgesetzt"),
    "kindesunterhalt": ("art", "monatsbetrag", "anzahl_monate", "rueckstaende",
                        "verfahrenswert_festgesetzt"),
    "ehegattenunterhalt": ("art", "monatsbetrag", "anzahl_monate", "rueckstaende",
                           "verfahrenswert_festgesetzt"),
    "kindschaftssache": ("art", "gegenstand", "verfahrenswert_festgesetzt"),
    "geldforderung": ("art", "betrag", "verfahrenswert_festgesetzt"),
    "auffangwert": ("art", "verfahrenswert_festgesetzt"),
    **{a: ("art", "fallgruppe", "verfahrenswert_festgesetzt") for a in _FESTWERT_ARTEN},
}
# § 41 FamGKG: an jedem Gegenstand einer selbständigen Familiensache zulässig
# (im Verbund und an der Ehesache abgelehnt, siehe _gegenstand/_ehesache).
_FELDER = {a: f + ("einstweilige_anordnung",) if a != "ehesache" else f
           for a, f in _FELDER.items()}

_EA_HINWEIS = ("Einstweilige Anordnung: Der Wert ist der gesetzliche Ausgangswert "
               "nach § 41 Satz 2 FamGKG (Hälfte des für die Hauptsache "
               "bestimmten Werts), keine Festsetzung. Das Gericht kann ihn nach "
               "§ 41 Satz 1 FamGKG weiter ermäßigen ('in der Regel ... zu "
               "ermäßigen') — maßgeblich ist dann der festgesetzte Wert "
               "('verfahrenswert_festgesetzt').")


class VerfahrenswertFehler(WertgebuehrFehler):
    """Ungültige Angaben zur Verfahrenswert-Ermittlung."""


def lade_wertvorschriften(pfad: Path | None = None) -> dict[str, Any]:
    return json.loads((pfad or WERTVORSCHRIFTEN_PFAD).read_text(encoding="utf-8"))


def _s(d: Decimal) -> str:
    """Dezimalstring mit mindestens zwei Nachkommastellen — exakt, ohne
    Rundung (ein Verfahrenswert ist keine Gebühr; das Gesetz kennt für ihn
    keine Rundungsregel)."""
    return str(d.quantize(Decimal("0.01"))) if d == d.quantize(Decimal("0.01")) else str(d)


def _nur(eintrag: dict[str, Any], erlaubt: tuple[str, ...], kontext: str) -> None:
    for feld in eintrag:
        if feld not in erlaubt:
            raise VerfahrenswertFehler(
                f"unbekanntes Feld {kontext}: '{feld}' (erlaubt: "
                f"{', '.join(repr(f) for f in erlaubt)})")


def _betrag(wert: Any, feld: str, *, null_erlaubt: bool = False) -> Decimal:
    if wert is None or wert == "":
        raise VerfahrenswertFehler(f"Pflichtfeld '{feld}' fehlt oder ist leer")
    d = D(wert)
    if d < 0 or (d == 0 and not null_erlaubt):
        raise VerfahrenswertFehler(
            f"'{feld}' muss {'>= 0' if null_erlaubt else '> 0'} sein, ist {d}")
    return d


def _ganzzahl(wert: Any, feld: str, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(wert, bool) or not isinstance(wert, int):
        raise VerfahrenswertFehler(
            f"'{feld}' muss eine ganze JSON-Zahl sein, nicht {wert!r}")
    if wert < minimum or (maximum is not None and wert > maximum):
        grenze = f"{minimum}–{maximum}" if maximum is not None else f">= {minimum}"
        raise VerfahrenswertFehler(f"'{feld}' muss {grenze} sein, ist {wert}")
    return wert


def _netto_drei_monate(liste: Any, kontext: str, monate: int
                       ) -> tuple[Decimal, list[RechenSchritt]]:
    if not isinstance(liste, list) or len(liste) != 2:
        raise VerfahrenswertFehler(
            f"'{kontext}.nettoeinkommen_monatlich' muss eine Liste mit genau "
            f"zwei Dezimalstrings sein (je Ehegatte ein bereinigtes monatliches "
            f"Nettoeinkommen), nicht {liste!r}")
    a = _betrag(liste[0], f"{kontext}.nettoeinkommen_monatlich[0]", null_erlaubt=True)
    b = _betrag(liste[1], f"{kontext}.nettoeinkommen_monatlich[1]", null_erlaubt=True)
    summe = monate * (a + b)
    return summe, [RechenSchritt(
        schritt=0, norm="§ 43 Abs. 2 FamGKG" if kontext == "ehesache" else "§ 50 Abs. 1 Satz 1 FamGKG",
        beschreibung=(f"In {monate} Monaten erzieltes Nettoeinkommen der "
                      f"Ehegatten (Eingabe, bereinigt): {monate} x ({_s(a)} € + "
                      f"{_s(b)} €) = {_s(summe)} €."),
        ergebnis=_s(summe))]


@dataclass
class Gegenstand:
    art: str
    bezeichnung: str
    norm: str
    wert: Decimal
    quelle: str                                  # "executor" | "eingabe"
    rechenschritte: list[RechenSchritt] = field(default_factory=list)
    nutzereingaben: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    # § 41 FamGKG — nur im Report, wenn gesetzt (Schema der übrigen
    # Gegenstände bleibt unverändert).
    einstweilige_anordnung: bool = False
    hauptsachewert: Decimal | None = None        # vor Halbierung (§ 41 Satz 2)

    def as_dict(self) -> dict[str, Any]:
        for i, s in enumerate(self.rechenschritte, start=1):
            s.schritt = i
        d = {"art": self.art, "bezeichnung": self.bezeichnung,
             "norm": self.norm, "wert": _s(self.wert), "quelle": self.quelle,
             "rechenschritte": [s.as_dict() for s in self.rechenschritte],
             "nutzereingaben": list(self.nutzereingaben),
             "hinweise": list(self.hinweise)}
        if self.einstweilige_anordnung:
            d["einstweilige_anordnung"] = True
            if self.hauptsachewert is not None:
                d["hauptsachewert"] = _s(self.hauptsachewert)
        return d


@dataclass
class VerfahrenswertErgebnis:
    gesamt: Decimal
    # "eingabe", sobald der Gesamtwert eine Nutzereingabe enthält
    # (festgesetzter Wert, Ermessens-Zuschlag) — sonst "executor".
    quelle: str
    form: str                                    # "verbund" | "selbstaendig" | "festgesetzt"
    stand: dict[str, Any]
    gegenstaende: list[Gegenstand]
    rechenkette: list[RechenSchritt] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    # Für den `warnungen`-Block des Reports (nicht Teil von as_dict) — siehe
    # report_warnungen().
    warnungen: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"gesamt": _s(self.gesamt), "quelle": self.quelle,
                "form": self.form,
                "wertvorschriften_stand": self.stand["id"],
                "gegenstaende": [g.as_dict() for g in self.gegenstaende],
                "rechenkette": [s.as_dict() for s in self.rechenkette],
                "hinweise": list(self.hinweise)}


def _festgesetzt(eintrag: dict[str, Any], kontext: str, art: str, bezeichnung: str,
                 norm_hinweis: str) -> Gegenstand:
    wert = _betrag(eintrag["verfahrenswert_festgesetzt"],
                   f"{kontext}.verfahrenswert_festgesetzt")
    return Gegenstand(
        art=art, bezeichnung=bezeichnung, norm=norm_hinweis, wert=wert,
        quelle="eingabe",
        rechenschritte=[RechenSchritt(
            schritt=0, norm=norm_hinweis,
            beschreibung=(f"Vom Gericht festgesetzter Wert (Nutzereingabe "
                          f"'verfahrenswert_festgesetzt'): {_s(wert)} € — ersetzt "
                          f"die gesetzliche Berechnung."),
            ergebnis=_s(wert), quelle="eingabe")],
        nutzereingaben=[f"verfahrenswert_festgesetzt = {_s(wert)} €"])


def _ehesache(e: Any, w: dict[str, Any]) -> tuple[Gegenstand, Decimal | None]:
    """Gibt (Gegenstand, Drei-Monats-Netto oder None) zurück."""
    if not isinstance(e, dict):
        raise VerfahrenswertFehler("'ehesache' muss ein JSON-Objekt sein")
    if "einstweilige_anordnung" in e:
        raise VerfahrenswertFehler(
            "'ehesache.einstweilige_anordnung' ist nicht zulässig — die "
            "einstweilige Anordnung ist ein selbständiges Verfahren (§ 51 "
            "Abs. 3 Satz 1 FamFG), nicht Teil des Verbunds; für sie eine "
            "eigene Anfrage mit 'gegenstaende' stellen und das Flag am "
            "Gegenstand setzen (§ 41 FamGKG)")
    _nur(e, _FELDER["ehesache"], "in 'ehesache'")
    monate = int(w["ehesache_einkommensmonate"])
    netto3 = None
    netto_schritte: list[RechenSchritt] = []
    if "nettoeinkommen_monatlich" in e:
        netto3, netto_schritte = _netto_drei_monate(
            e["nettoeinkommen_monatlich"], "ehesache", monate)

    if "verfahrenswert_festgesetzt" in e:
        for f in ("zuschlag", "begruendung"):
            if f in e:
                raise VerfahrenswertFehler(
                    f"'ehesache.{f}' und 'ehesache.verfahrenswert_festgesetzt' "
                    f"schließen sich aus — der festgesetzte Wert ersetzt die "
                    f"Berechnung vollständig")
        g = _festgesetzt(e, "ehesache", "ehesache", "Ehesache (Scheidungssache)",
                         "§ 43 Abs. 1 FamGKG (gerichtliche Festsetzung)")
        if netto3 is not None:
            g.hinweise.append(
                "Die eingegebenen Nettoeinkommen dienen nur als Basis für "
                "Versorgungsausgleichs-Folgesachen (§ 50 Abs. 1 FamGKG).")
        return g, netto3

    if netto3 is None:
        raise VerfahrenswertFehler(
            "Pflichtfeld 'ehesache.nettoeinkommen_monatlich' fehlt (oder "
            "'ehesache.verfahrenswert_festgesetzt' angeben)")

    schritte = list(netto_schritte)
    nutzereingaben: list[str] = []
    quelle = "executor"
    wert = netto3
    hat_zuschlag = "zuschlag" in e
    hat_begruendung = "begruendung" in e
    if hat_zuschlag != hat_begruendung:
        raise VerfahrenswertFehler(
            "'ehesache.zuschlag' und 'ehesache.begruendung' nur zusammen "
            "angeben — ein Ermessens-Zuschlag (§ 43 Abs. 1 Satz 1 FamGKG) "
            "braucht eine Begründung, eine Begründung ohne Zuschlag ist sinnlos")
    if hat_zuschlag:
        zuschlag = _betrag(e["zuschlag"], "ehesache.zuschlag")
        begruendung = e["begruendung"]
        if not isinstance(begruendung, str) or not begruendung.strip():
            raise VerfahrenswertFehler(
                "'ehesache.begruendung' muss ein nichtleerer String sein")
        wert = netto3 + zuschlag
        quelle = "eingabe"
        nutzereingaben.append(
            f"zuschlag = {_s(zuschlag)} € (Ermessen nach § 43 Abs. 1 Satz 1 "
            f"FamGKG, Begründung: {begruendung.strip()})")
        schritte.append(RechenSchritt(
            schritt=0, norm="§ 43 Abs. 1 Satz 1 FamGKG (Ermessen — Nutzereingabe)",
            beschreibung=(f"Zuschlag laut Nutzereingabe, nicht berechnet "
                          f"(Begründung: {begruendung.strip()}): {_s(netto3)} € + "
                          f"{_s(zuschlag)} € = {_s(wert)} €."),
            ergebnis=_s(wert), quelle="eingabe"))

    mindest = D(w["ehesache_mindestwert"])
    hoechst = D(w["ehesache_hoechstwert"])
    if wert < mindest:
        text = f"{_s(wert)} € liegt unter dem Mindestwert — angesetzt: {_s(mindest)} €."
        wert = mindest
    elif wert > hoechst:
        text = f"{_s(wert)} € liegt über dem Höchstwert — angesetzt: {_s(hoechst)} €."
        wert = hoechst
    else:
        text = (f"{_s(wert)} € liegt zwischen Mindestwert {_s(mindest)} € und "
                f"Höchstwert {_s(hoechst)} € — keine Anpassung.")
    schritte.append(RechenSchritt(
        schritt=0, norm="§ 43 Abs. 1 Satz 2 FamGKG", beschreibung=text,
        ergebnis=_s(wert)))
    g = Gegenstand(
        art="ehesache", bezeichnung="Ehesache (Scheidungssache)",
        norm="§ 43 FamGKG", wert=wert, quelle=quelle, rechenschritte=schritte,
        nutzereingaben=nutzereingaben,
        hinweise=["§ 43 Abs. 1 Satz 1 FamGKG ist eine Ermessensnorm: der "
                  "Executor rechnet nur die Einkommenskomponente (Abs. 2) und "
                  "die Grenzen (Abs. 1 Satz 2). Abzüge vom Nettoeinkommen "
                  "(z. B. für Kinder) sind Gerichtspraxis, kein Gesetz — "
                  "einzugeben ist das bereinigte Netto. Das Gericht kann "
                  "anders festsetzen."])
    return g, netto3


def _versorgungsausgleich(f: dict[str, Any], kontext: str, w: dict[str, Any],
                          netto3_verbund: Decimal | None, verbund: bool) -> Gegenstand:
    if verbund and "nettoeinkommen_monatlich" in f:
        raise VerfahrenswertFehler(
            f"'{kontext}.nettoeinkommen_monatlich' ist im Verbund nicht "
            f"zulässig — Basis ist das Nettoeinkommen aus 'ehesache' "
            f"(dieselben Ehegatten)")
    if "anzahl_anrechte" not in f:
        raise VerfahrenswertFehler(f"Pflichtfeld '{kontext}.anzahl_anrechte' fehlt")
    anzahl = _ganzzahl(f["anzahl_anrechte"], f"{kontext}.anzahl_anrechte", minimum=1)
    nach_scheidung = f.get("ausgleich_nach_scheidung", False)
    if not isinstance(nach_scheidung, bool):
        raise VerfahrenswertFehler(
            f"'{kontext}.ausgleich_nach_scheidung' muss ein JSON-Boolean sein, "
            f"nicht {nach_scheidung!r}")
    schritte: list[RechenSchritt] = []
    if verbund:
        if netto3_verbund is None:
            raise VerfahrenswertFehler(
                f"'{kontext}': Versorgungsausgleich im Verbund braucht "
                f"'ehesache.nettoeinkommen_monatlich' als Basis (§ 50 Abs. 1 "
                f"FamGKG) — oder für diese Folgesache "
                f"'verfahrenswert_festgesetzt' angeben")
        netto3 = netto3_verbund
        schritte.append(RechenSchritt(
            schritt=0, norm="§ 50 Abs. 1 Satz 1 FamGKG",
            beschreibung=(f"Basis: in drei Monaten erzieltes Nettoeinkommen der "
                          f"Ehegatten aus der Ehesache = {_s(netto3)} €."),
            ergebnis=_s(netto3)))
    else:
        if "nettoeinkommen_monatlich" not in f:
            raise VerfahrenswertFehler(
                f"Pflichtfeld '{kontext}.nettoeinkommen_monatlich' fehlt")
        netto3, schritte = _netto_drei_monate(
            f["nettoeinkommen_monatlich"], kontext, int(w["ehesache_einkommensmonate"]))
    satz = D(w["versorgungsausgleich_satz_je_anrecht_nach_scheidung"
               if nach_scheidung else "versorgungsausgleich_satz_je_anrecht"])
    roh = anzahl * satz * netto3
    schritte.append(RechenSchritt(
        schritt=0, norm="§ 50 Abs. 1 Satz 1 FamGKG",
        beschreibung=(f"{anzahl} Anrecht(e) x {satz * 100:.0f} % "
                      f"({'Ausgleichsansprüche nach der Scheidung' if nach_scheidung else 'je Anrecht'}) "
                      f"x {_s(netto3)} € = {_s(roh)} €."),
        ergebnis=_s(roh)))
    mindest = D(w["versorgungsausgleich_mindestwert"])
    wert = max(roh, mindest)
    schritte.append(RechenSchritt(
        schritt=0, norm="§ 50 Abs. 1 Satz 2 FamGKG",
        beschreibung=(f"Mindestwert {_s(mindest)} € "
                      + ("greift." if roh < mindest else "überschritten — keine Anpassung.")),
        ergebnis=_s(wert)))
    return Gegenstand(
        art="versorgungsausgleich", bezeichnung="Versorgungsausgleichssache",
        norm="§ 50 Abs. 1 FamGKG", wert=wert, quelle="executor",
        rechenschritte=schritte,
        hinweise=["Auskunfts-/Abtretungsverfahren (§ 50 Abs. 2 FamGKG) und "
                  "Billigkeitskorrektur (§ 50 Abs. 3 FamGKG) sind nicht "
                  "modelliert."])


def _unterhalt(f: dict[str, Any], kontext: str, w: dict[str, Any], art: str) -> Gegenstand:
    monatsbetrag = _betrag(f.get("monatsbetrag"), f"{kontext}.monatsbetrag")
    monate_max = int(w["unterhalt_monate"])
    monate = monate_max
    schritte: list[RechenSchritt] = []
    if "anzahl_monate" in f:
        monate = _ganzzahl(f["anzahl_monate"], f"{kontext}.anzahl_monate",
                           minimum=1, maximum=monate_max)
    laufend = monate * monatsbetrag
    schritte.append(RechenSchritt(
        schritt=0, norm="§ 51 Abs. 1 Satz 1 FamGKG",
        beschreibung=(f"Für die ersten {monate_max} Monate nach Einreichung "
                      f"geforderter Betrag"
                      + (f" (höchstens Gesamtbetrag der geforderten Leistung: "
                         f"nur {monate} Monatsbeträge gefordert)" if monate < monate_max else "")
                      + f": {monate} x {_s(monatsbetrag)} € = {_s(laufend)} €."),
        ergebnis=_s(laufend)))
    wert = laufend
    if "rueckstaende" in f:
        rueck = _betrag(f["rueckstaende"], f"{kontext}.rueckstaende", null_erlaubt=True)
        wert = laufend + rueck
        schritte.append(RechenSchritt(
            schritt=0, norm="§ 51 Abs. 2 Satz 1 FamGKG",
            beschreibung=(f"Bei Einreichung fällige Beträge hinzugerechnet: "
                          f"{_s(laufend)} € + {_s(rueck)} € = {_s(wert)} €."),
            ergebnis=_s(wert)))
    return Gegenstand(
        art=art, bezeichnung=("Unterhaltssache (Kindesunterhalt)" if art == "kindesunterhalt"
                              else "Unterhaltssache (Ehegattenunterhalt)"),
        norm="§ 51 FamGKG", wert=wert, quelle="executor", rechenschritte=schritte,
        hinweise=["Nur Unterhaltssachen, die Familienstreitsachen sind und "
                  "wiederkehrende Leistungen betreffen (§ 51 Abs. 1 FamGKG); "
                  "§ 51 Abs. 3 FamGKG ist nicht modelliert. Bei dynamisiertem "
                  "Unterhalt (§§ 1612a–1612c BGB) ist als 'monatsbetrag' der "
                  "Monatsbetrag nach dem bei Einreichung geltenden "
                  "Mindestunterhalt der maßgebenden Altersstufe einzugeben "
                  "(§ 51 Abs. 1 Satz 2 FamGKG) — der Executor kennt die "
                  "Mindestunterhaltstabelle nicht. Innerhalb der zwölf Monate "
                  "wechselnde Monatsbeträge sind nicht modelliert."])


def _kindschaft(f: dict[str, Any], kontext: str, w: dict[str, Any],
                wert_43: Decimal | None) -> Gegenstand:
    gegenstand = f.get("gegenstand")
    erlaubt = _KINDSCHAFT_137 if wert_43 is not None else tuple(_KINDSCHAFT_45)
    if gegenstand not in erlaubt:
        raise VerfahrenswertFehler(
            f"'{kontext}.gegenstand' muss einer von "
            f"{', '.join(repr(x) for x in erlaubt)} sein, ist {gegenstand!r}"
            + (" (Kindschafts-Folgesachen nach § 137 Abs. 3 FamFG)" if wert_43 is not None
               else " (§ 45 Abs. 1 Nr. 1–4 FamGKG; andere Kindschaftssachen "
                    "sind nicht modelliert)"))
    if wert_43 is None:
        wert = D(w["kindschaftssache_festwert"])
        return Gegenstand(
            art="kindschaftssache",
            bezeichnung=f"Kindschaftssache ({gegenstand})",
            norm=f"§ 45 Abs. 1 {_KINDSCHAFT_45[gegenstand]} FamGKG", wert=wert,
            quelle="executor",
            rechenschritte=[RechenSchritt(
                schritt=0, norm=f"§ 45 Abs. 1 {_KINDSCHAFT_45[gegenstand]} FamGKG",
                beschreibung=f"Gesetzlicher Festwert der Kindschaftssache: {_s(wert)} €.",
                ergebnis=_s(wert))],
            hinweise=["Eine Kindschaftssache ist auch dann ein Gegenstand, wenn "
                      "sie mehrere Kinder betrifft (§ 45 Abs. 2 FamGKG). Ob "
                      "mehrere Kindschaftssachen (z. B. Sorge und Umgang) in "
                      "einem Verfahren getrennt zu bewerten sind, entscheidet "
                      "die Kanzlei über die Zahl der Einträge — der Executor "
                      "rechnet je Eintrag einen Festwert. Billigkeitsabweichung "
                      "(§ 45 Abs. 3 FamGKG) nur über 'verfahrenswert_festgesetzt'."])
    prozent = D(w["verbund_kindschaft_prozentsatz"])
    hoechst = D(w["verbund_kindschaft_hoechstbetrag"])
    roh = prozent * wert_43
    wert = min(roh, hoechst)
    return Gegenstand(
        art="kindschaftssache",
        bezeichnung=f"Kindschafts-Folgesache ({gegenstand}) — Erhöhung des Ehesachenwerts",
        norm="§ 44 Abs. 2 Satz 1 FamGKG", wert=wert, quelle="executor",
        rechenschritte=[RechenSchritt(
            schritt=0, norm="§ 44 Abs. 2 Satz 1 FamGKG",
            beschreibung=(f"Erhöhung um {prozent * 100:.0f} % des Werts der "
                          f"Ehesache ({_s(wert_43)} €) = {_s(roh)} €, höchstens "
                          f"{_s(hoechst)} € — "
                          + ("Höchstbetrag greift." if roh > hoechst else "Höchstbetrag greift nicht.")),
            ergebnis=_s(wert))],
        hinweise=["Eine Kindschaftssache ist auch dann ein Gegenstand, wenn sie "
                  "mehrere Kinder betrifft (§ 44 Abs. 2 Satz 1 Hs. 2 FamGKG); "
                  "die Erhöhung fällt 'für jede Kindschaftssache' an — ob z. B. "
                  "Sorge und Umgang getrennte Kindschaftssachen sind, "
                  "entscheidet die Kanzlei über die Zahl der Einträge. "
                  "Billigkeitsabweichung (§ 44 Abs. 3 FamGKG) nur über "
                  "'verfahrenswert_festgesetzt' (dann = Erhöhungsbetrag)."])


def _fallgruppe(f: dict[str, Any], kontext: str, art: str, verbund: bool) -> str:
    """Pflichtfeld `fallgruppe` der Festwert-Arten (§§ 47–49 FamGKG) — nie
    angenommen; im Verbund nur die Fallgruppe, die Folgesache sein kann."""
    spec = _FESTWERT_ARTEN[art]
    if verbund and spec["folgesache"] is None:
        raise VerfahrenswertFehler(
            f"'{kontext}': {spec['bezeichnung']}n sind keine Folgesachen "
            f"(§ 137 Abs. 2, 3 FamFG) — als selbständige Familiensache in einer "
            f"eigenen Anfrage mit 'gegenstaende' angeben")
    fg = f.get("fallgruppe")
    if fg not in spec["fallgruppen"]:
        raise VerfahrenswertFehler(
            f"Pflichtfeld '{kontext}.fallgruppe' fehlt oder ist unbekannt "
            f"({fg!r}) — für art '{art}' ({spec['norm']}) einer von: "
            + "; ".join(f"'{k}' = {v}" for k, v in spec["fallgruppen"].items())
            + ". Die Fallgruppe wird nie angenommen.")
    if verbund and fg != spec["folgesache"]:
        raise VerfahrenswertFehler(
            f"'{kontext}': {spec['bezeichnung']} mit Fallgruppe '{fg}' kann keine "
            f"Folgesache sein — § 137 Abs. 2 Satz 1 Nr. 3 FamFG verlangt, dass "
            f"eine Entscheidung für den Fall der Scheidung zu treffen ist; das "
            f"ist nur Fallgruppe '{spec['folgesache']}' "
            f"({spec['fallgruppen'][spec['folgesache']]}). Ein Verfahren für die "
            f"Zeit des Getrenntlebens ist eine selbständige Familiensache "
            f"(eigene Anfrage mit 'gegenstaende').")
    return fg


def _festwert(art: str, fg: str, w: dict[str, Any], verbund: bool) -> Gegenstand:
    spec = _FESTWERT_ARTEN[art]
    wert = D(w["festwerte_47_49"][art][fg])
    hinweise = [f"Die Fallgruppe '{fg}' ist eine Angabe der Kanzlei — der Executor "
                f"nimmt sie nie an. Billigkeitsabweichung ({spec['billigkeit']}) "
                f"nur über 'verfahrenswert_festgesetzt'."]
    if verbund:
        hinweise.append("Folgesache nach § 137 Abs. 2 Satz 1 Nr. 3 FamFG — ihr Wert "
                        "wird dem Wert der Ehesache hinzugerechnet (§ 44 Abs. 2 "
                        "Satz 2 FamGKG).")
    return Gegenstand(
        art=art,
        bezeichnung=(f"{spec['bezeichnung']} ({spec['fallgruppen'][fg]})"
                     + (" — Folgesache" if verbund else "")),
        norm=spec["norm"], wert=wert, quelle="executor",
        rechenschritte=[RechenSchritt(
            schritt=0, norm=spec["norm"],
            beschreibung=(f"Gesetzlicher Festwert, Fallgruppe '{fg}' "
                          f"({spec['fallgruppen'][fg]}): {_s(wert)} €."),
            ergebnis=_s(wert))],
        hinweise=hinweise)


def _einstweilige_anordnung(g: Gegenstand, w: dict[str, Any], festgesetzt: bool) -> None:
    """§ 41 FamGKG am fertig bewerteten Gegenstand (nur auf ausdrückliche
    Angabe `einstweilige_anordnung: true`)."""
    g.einstweilige_anordnung = True
    g.bezeichnung += " — einstweilige Anordnung"
    if festgesetzt:
        g.rechenschritte.append(RechenSchritt(
            schritt=0, norm="§ 41 FamGKG",
            beschreibung=(f"Einstweilige Anordnung (Angabe der Kanzlei): der vom "
                          f"Gericht festgesetzte Wert {_s(g.wert)} € gilt — keine "
                          f"Halbierung nach § 41 Satz 2 FamGKG."),
            ergebnis=_s(g.wert), quelle="eingabe"))
        g.hinweise.append("Einstweilige Anordnung mit gerichtlich festgesetztem "
                          "Wert: § 41 FamGKG wird nicht mehr angewendet.")
        return
    anteil = D(w["einstweilige_anordnung_ausgangsanteil"])
    haupt = g.wert
    exakt = haupt * anteil
    wert = rundung_cent(exakt)
    g.rechenschritte.append(RechenSchritt(
        schritt=0, norm="§ 41 Satz 2 FamGKG",
        beschreibung=(f"Einstweilige Anordnung (Angabe der Kanzlei): Ausgangswert "
                      f"= Hälfte des für die Hauptsache bestimmten Werts: "
                      f"{_s(haupt)} € x {anteil} = {_s(wert)} €"
                      + (f" (rechnerisch {exakt}, auf volle Cent gerundet)"
                         if wert != exakt else "") + "."),
        ergebnis=_s(wert)))
    g.hauptsachewert = haupt
    g.wert = wert
    g.norm += " i. V. m. § 41 Satz 2 FamGKG"
    g.hinweise.append(_EA_HINWEIS)


def _gegenstand(f: Any, kontext: str, w: dict[str, Any], *,
                wert_43: Decimal | None, netto3: Decimal | None) -> Gegenstand:
    verbund = wert_43 is not None
    if not isinstance(f, dict):
        raise VerfahrenswertFehler(f"'{kontext}' muss ein JSON-Objekt sein")
    art = f.get("art")
    if art == "ehesache":
        raise VerfahrenswertFehler(
            f"'{kontext}': die Ehesache gehört in 'verfahrenswert_ermittlung."
            f"ehesache' (Verbund-Form), nicht in die Liste")
    if art not in _ARTEN:
        raise VerfahrenswertFehler(
            f"'{kontext}.art' ist unbekannt: {art!r} (unterstützt: "
            f"{', '.join(_ARTEN)}). Andere Familiensachen (z. B. "
            f"vermögensrechtliche Kindschaftssachen § 46 FamGKG) sind nicht "
            f"modelliert — dann den Verfahrenswert direkt als "
            f"'famgkg.verfahrenswert' eingeben.")
    ea = f.get("einstweilige_anordnung", False)
    if "einstweilige_anordnung" in f:
        if verbund:
            raise VerfahrenswertFehler(
                f"'{kontext}.einstweilige_anordnung' ist im Verbund nicht "
                f"zulässig — die einstweilige Anordnung ist ein selbständiges "
                f"Verfahren (§ 51 Abs. 3 Satz 1 FamFG); dafür eine eigene "
                f"Anfrage mit 'gegenstaende' stellen (§ 41 FamGKG)")
        if not isinstance(ea, bool):
            raise VerfahrenswertFehler(
                f"'{kontext}.einstweilige_anordnung' muss ein JSON-Boolean "
                f"(true/false) sein, nicht {ea!r}")
    g = _hauptsache(f, kontext, w, art, verbund, wert_43, netto3)
    if ea:
        _einstweilige_anordnung(g, w, "verfahrenswert_festgesetzt" in f)
    return g


def _hauptsache(f: dict[str, Any], kontext: str, w: dict[str, Any], art: str,
                verbund: bool, wert_43: Decimal | None,
                netto3: Decimal | None) -> Gegenstand:
    """Wert des Gegenstands, wie er für die Hauptsache bestimmt ist."""
    fg = _fallgruppe(f, kontext, art, verbund) if art in _FESTWERT_ARTEN else None
    if "verfahrenswert_festgesetzt" in f:
        erlaubt = ("art", "verfahrenswert_festgesetzt", "einstweilige_anordnung") + (
            ("gegenstand",) if art == "kindschaftssache" else ()) + (
            ("fallgruppe",) if fg is not None else ())
        _nur(f, erlaubt, f"in '{kontext}' neben 'verfahrenswert_festgesetzt'")
        if art == "kindschaftssache" and verbund:
            norm = "§ 44 Abs. 3 FamGKG (gerichtliche Festsetzung des Erhöhungsbetrags)"
        elif fg is not None:
            norm = f"{_FESTWERT_ARTEN[art]['billigkeit']} (gerichtliche Festsetzung)"
        else:
            norm = "gerichtliche Festsetzung"
        return _festgesetzt(f, kontext, art, f"{art} (festgesetzter Wert)", norm)
    _nur(f, _FELDER[art], f"in '{kontext}' (art '{art}')")
    if fg is not None:
        return _festwert(art, fg, w, verbund)
    if art == "versorgungsausgleich":
        return _versorgungsausgleich(f, kontext, w, netto3, verbund)
    if art in ("kindesunterhalt", "ehegattenunterhalt"):
        return _unterhalt(f, kontext, w, art)
    if art == "kindschaftssache":
        return _kindschaft(f, kontext, w, wert_43)
    if art == "geldforderung":
        betrag = _betrag(f.get("betrag"), f"{kontext}.betrag")
        return Gegenstand(
            art=art, bezeichnung="Bezifferte Geldforderung (z. B. Zugewinnausgleich)",
            norm="§ 35 FamGKG", wert=betrag, quelle="executor",
            rechenschritte=[RechenSchritt(
                schritt=0, norm="§ 35 FamGKG",
                beschreibung=f"Höhe der bezifferten Geldforderung: {_s(betrag)} €.",
                ergebnis=_s(betrag))])
    # auffangwert
    wert = D(w["auffangwert"])
    return Gegenstand(
        art=art, bezeichnung="Auffangwert (keine genügenden Anhaltspunkte)",
        norm="§ 42 Abs. 3 FamGKG", wert=wert, quelle="executor",
        rechenschritte=[RechenSchritt(
            schritt=0, norm="§ 42 Abs. 3 FamGKG",
            beschreibung=f"Gesetzlicher Auffangwert: {_s(wert)} €.",
            ergebnis=_s(wert))],
        hinweise=["Nur wenn keine besondere Wertvorschrift greift und keine "
                  "genügenden Anhaltspunkte für eine Bestimmung nach billigem "
                  "Ermessen (§ 42 Abs. 1, 2 FamGKG) bestehen — diese Einordnung "
                  "trifft die Kanzlei; eine Billigkeitsabweichung rechnet der "
                  "Executor nicht."])


def ermittle(angaben: Any, stichtag: _dt.date, *,
             wertvorschriften: dict[str, Any] | None = None) -> VerfahrenswertErgebnis:
    """Ermittelt den Verfahrenswert aus `angaben` (Block
    `famgkg.verfahrenswert_ermittlung`) für den `stichtag` (§ 63 Abs. 1
    FamGKG — bestimmt den Stand der versionierten Werte)."""
    if not isinstance(angaben, dict):
        raise VerfahrenswertFehler("'verfahrenswert_ermittlung' muss ein JSON-Objekt sein")
    _nur(angaben, ("ehesache", "folgesachen", "gegenstaende", "verfahrenswert_festgesetzt"),
         "in 'verfahrenswert_ermittlung'")
    hat_ehe = "ehesache" in angaben
    hat_geg = "gegenstaende" in angaben
    hat_fest = "verfahrenswert_festgesetzt" in angaben
    if hat_ehe and hat_geg:
        raise VerfahrenswertFehler(
            "entweder 'ehesache' (+ 'folgesachen', Verbund § 44 FamGKG) ODER "
            "'gegenstaende' (selbständige Familiensache) angeben — nicht beides")
    if "folgesachen" in angaben and not hat_ehe:
        raise VerfahrenswertFehler(
            "'folgesachen' gibt es nur im Verbund mit einer 'ehesache' "
            "(§ 44 FamGKG) — für selbständige Familiensachen 'gegenstaende'")
    if not (hat_ehe or hat_geg or hat_fest):
        raise VerfahrenswertFehler(
            "'verfahrenswert_ermittlung' braucht 'ehesache' (Verbund), "
            "'gegenstaende' (selbständig) oder 'verfahrenswert_festgesetzt'")

    stand = stand_fuer_stichtag(stichtag)
    wv = wertvorschriften or lade_wertvorschriften()
    w = wv["staende"][stand["id"]]

    kette: list[RechenSchritt] = []
    hinweise: list[str] = []

    def schritt(norm: str, beschreibung: str, ergebnis: str | None,
                quelle: str = "executor") -> None:
        kette.append(RechenSchritt(schritt=len(kette) + 1, norm=norm,
                                   beschreibung=beschreibung, ergebnis=ergebnis,
                                   quelle=quelle))

    schritt("§ 63 Abs. 1 FamGKG",
            f"Stichtag {stichtag.isoformat()} -> Wertvorschriften im Stand "
            f"'{stand['bezeichnung']}'.", stand["id"])

    gegenstaende: list[Gegenstand] = []
    gesamt: Decimal | None = None
    form = "festgesetzt"

    if hat_ehe:
        form = "verbund"
        ehe, netto3 = _ehesache(angaben["ehesache"], w)
        gegenstaende.append(ehe)
        folgesachen = angaben.get("folgesachen", [])
        if not isinstance(folgesachen, list):
            raise VerfahrenswertFehler("'folgesachen' muss eine Liste sein")
        _pruefe_kindschaft_doppelt(folgesachen, "folgesachen")
        erhoehungen: list[Gegenstand] = []
        uebrige: list[Gegenstand] = []
        for i, f in enumerate(folgesachen):
            g = _gegenstand(f, f"folgesachen[{i}]", w, wert_43=ehe.wert, netto3=netto3)
            (erhoehungen if g.art == "kindschaftssache" else uebrige).append(g)
            gegenstaende.append(g)
        gesamt = ehe.wert + sum((g.wert for g in gegenstaende[1:]), Decimal("0"))
        teile = [f"Ehesache {_s(ehe.wert)} €"]
        teile += [f"Erhöhung Kindschafts-Folgesache {_s(g.wert)} €" for g in erhoehungen]
        teile += [f"{g.bezeichnung} {_s(g.wert)} €" for g in uebrige]
        schritt("§ 44 Abs. 1, 2 FamGKG",
                "Verbund — Scheidungssache und Folgesachen gelten als ein "
                "Verfahren; Werte der Folgesachen hinzugerechnet (§ 33 Abs. 1 "
                "Satz 2 FamGKG nicht anzuwenden): " + " + ".join(teile)
                + f" = {_s(gesamt)} €.", _s(gesamt))
    elif hat_geg:
        form = "selbstaendig"
        liste = angaben["gegenstaende"]
        if not isinstance(liste, list) or not liste:
            raise VerfahrenswertFehler("'gegenstaende' muss eine nichtleere Liste sein")
        _pruefe_kindschaft_doppelt(liste, "gegenstaende")
        for i, f in enumerate(liste):
            gegenstaende.append(_gegenstand(f, f"gegenstaende[{i}]", w,
                                            wert_43=None, netto3=None))
        ea = [g.einstweilige_anordnung for g in gegenstaende]
        if any(ea) and not all(ea):
            raise VerfahrenswertFehler(
                "'gegenstaende' mischt Gegenstände mit und ohne "
                "'einstweilige_anordnung: true' — das Verfahren der "
                "einstweiligen Anordnung ist ein selbständiges Verfahren, auch "
                "wenn eine Hauptsache anhängig ist (§ 51 Abs. 3 Satz 1 FamFG); "
                "Hauptsache und einstweilige Anordnung in getrennten Anfragen "
                "rechnen")
        gesamt = sum((g.wert for g in gegenstaende), Decimal("0"))
        if len(gegenstaende) > 1:
            schritt("§ 33 Abs. 1 Satz 1 FamGKG",
                    "Werte mehrerer Verfahrensgegenstände zusammengerechnet: "
                    + " + ".join(f"{g.bezeichnung} {_s(g.wert)} €" for g in gegenstaende)
                    + f" = {_s(gesamt)} €.", _s(gesamt))
            hinweise.append(
                "§ 33 Abs. 1 Satz 2 FamGKG (nichtvermögensrechtlicher Anspruch "
                "mit daraus hergeleitetem vermögensrechtlichem Anspruch: nur "
                "der höhere) ist nicht modelliert — anwaltlich prüfen.")
        else:
            schritt(gegenstaende[0].norm,
                    f"Ein Verfahrensgegenstand: {gegenstaende[0].bezeichnung} = "
                    f"{_s(gesamt)} €.", _s(gesamt), gegenstaende[0].quelle)

    quelle = "executor"
    if hat_fest:
        fest = _betrag(angaben["verfahrenswert_festgesetzt"],
                       "verfahrenswert_ermittlung.verfahrenswert_festgesetzt")
        schritt("gerichtliche Festsetzung",
                f"Vom Gericht festgesetzter Verfahrenswert (Nutzereingabe "
                f"'verfahrenswert_festgesetzt'): {_s(fest)} €"
                + (f" — ersetzt den berechneten Gesamtwert {_s(gesamt)} €."
                   if gesamt is not None else "."),
                _s(fest), "eingabe")
        gesamt = fest
        quelle = "eingabe"
    elif any(g.quelle == "eingabe" for g in gegenstaende):
        quelle = "eingabe"
        hinweise.append(
            "Der Gesamtwert enthält Nutzereingaben (Ermessens-Zuschlag bzw. "
            "festgesetzte Werte) — siehe 'nutzereingaben' je Gegenstand.")

    if gesamt is None:  # nicht erreichbar: oben ist mindestens ein Zweig Pflicht
        raise VerfahrenswertFehler("kein Verfahrenswert ermittelbar")
    warnungen: list[str] = []
    if not hat_fest and any(g.hauptsachewert is not None for g in gegenstaende):
        warnungen.append(
            f"Einstweilige Anordnung (§ 41 FamGKG): Der ermittelte "
            f"Verfahrenswert {_s(gesamt)} € ist der gesetzliche Ausgangswert "
            f"nach § 41 Satz 2 FamGKG (Hälfte des Hauptsachewerts), keine "
            f"Festsetzung — das Gericht kann ihn nach § 41 Satz 1 FamGKG "
            f"weiter ermäßigen.")
    return VerfahrenswertErgebnis(gesamt=gesamt, quelle=quelle, form=form,
                                  stand=stand, gegenstaende=gegenstaende,
                                  rechenkette=kette, hinweise=hinweise,
                                  warnungen=warnungen)


def report_warnungen(vw: VerfahrenswertErgebnis, positionen: Any) -> list[str]:
    """Warnungen der Verfahrenswert-Ermittlung für den `warnungen`-Block des
    famgkg-Reports — plus Positions-Plausibilität bei einstweiliger
    Anordnung: die KV-Positionen bleiben Nutzereingabe, der Executor wählt
    sie nie; fehlt bei `einstweilige_anordnung: true` jede EA-Gebühr
    (KV 1410/1420/1421), obwohl Hauptsache-Positionen angegeben sind, gibt es
    nur eine Warnung, keinen Fehler."""
    warnungen = list(vw.warnungen)
    if not any(g.einstweilige_anordnung for g in vw.gegenstaende):
        return warnungen
    nrn = {str(p["nr"]) for p in positionen if isinstance(p, dict) and "nr" in p} \
        if isinstance(positionen, list) else set()
    hauptsache = sorted(n for n in nrn if n not in _EA_POSITIONEN and n != "1500")
    if hauptsache and not nrn & set(_EA_POSITIONEN):
        warnungen.append(
            f"'einstweilige_anordnung: true' ist gesetzt, die Positionen enthalten "
            f"aber nur Hauptsache-Gebühren ({', '.join('KV ' + n for n in hauptsache)} "
            f"FamGKG) und keine Gebühr für das Verfahren der einstweiligen "
            f"Anordnung (KV 1410 in Kindschaftssachen, KV 1420/1421 in den "
            f"übrigen Familiensachen) — Positionen prüfen; der Executor wählt "
            f"sie nicht selbst.")
    return warnungen


def _pruefe_kindschaft_doppelt(liste: list[Any], kontext: str) -> None:
    """§ 44 Abs. 2 Satz 1 Hs. 2 / § 45 Abs. 2 FamGKG: eine Kindschaftssache
    ist auch dann EIN Gegenstand, wenn sie mehrere Kinder betrifft — derselbe
    `gegenstand` zweimal (z. B. Sorge je Kind) wäre eine doppelte Bewertung."""
    gesehen: set[str] = set()
    for f in liste:
        if isinstance(f, dict) and f.get("art") == "kindschaftssache":
            g = f.get("gegenstand")
            if isinstance(g, str) and g in gesehen:
                raise VerfahrenswertFehler(
                    f"Kindschaftssache '{g}' mehrfach in '{kontext}' — eine "
                    f"Kindschaftssache ist auch dann ein Gegenstand, wenn sie "
                    f"mehrere Kinder betrifft (§ 44 Abs. 2 Satz 1, § 45 Abs. 2 "
                    f"FamGKG); nur einmal angeben")
            if isinstance(g, str):
                gesehen.add(g)
