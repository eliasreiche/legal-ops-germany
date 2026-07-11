#!/usr/bin/env python3
"""fristen — deterministische Fristberechnung nach §§ 186–193 BGB, § 222 ZPO (P3).

Berechnet das Ende einer Frist aus fristauslösendem Ereignis, Dauer und
Fristtyp — mit vollständiger, nachvollziehbarer Rechenkette: jedes
Zwischenergebnis (Fristbeginn, rechnerisches Ende, jede Verschiebung mit
Grund und Norm) wird einzeln ausgewiesen. Jeder Datumswert im Ergebnis stammt
aus diesem Modul, nie vom Modell (Deterministik-Grenze, CONVENTIONS.md P3).

Rechtsgrundlagen:

* **§ 186 BGB**: Die Auslegungsregeln der §§ 187–193 BGB gelten für Fristen in
  Gesetzen, Gerichtsverfügungen und Rechtsgeschäften; § 222 Abs. 1 ZPO
  verweist für prozessuale Fristen auf sie.
* **§ 187 Abs. 1 BGB** (Ereignisfrist): Der Tag des Ereignisses (z. B. der
  Zustellung) wird nicht mitgerechnet.
* **§ 187 Abs. 2 BGB** (Beginnfrist): Der Anfangstag wird mitgerechnet
  (z. B. Lebensalter).
* **§ 188 BGB**: Fristende bei Tages- (Abs. 1), Wochen-, Monats- und
  Jahresfristen (Abs. 2); fehlt der entsprechende Tag im Zielmonat
  (31.01. + 1 Monat), endet die Frist mit dem letzten Tag des Monats (Abs. 3).
* **§ 193 BGB / § 222 Abs. 2 ZPO**: Fällt das Fristende auf einen Sonnabend,
  Sonntag oder einen **am Fristende-Ort** staatlich anerkannten allgemeinen
  Feiertag, endet die Frist mit dem nächsten Werktag. Deshalb ist das
  Bundesland Pflicht-Eingabe — die Feiertage liefert core/calc/feiertage.

Teilgebietliche Feiertage (BY: Mariä Himmelfahrt/Augsburger Friedensfest,
SN/TH: Fronleichnam in einzelnen Gemeinden) werden nie stillschweigend
angenommen oder weggelassen: Ergäbe sich mit ihnen ein anderes Fristende,
weist das Ergebnis beide möglichen Enden mit Warnung aus.

Nur Standardbibliothek. Kein Netzwerkzugriff.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# feiertage liegt als Schwester-Paket in core/calc/ — Pfad robust einhängen,
# egal ob dieses Modul als Paket importiert oder direkt geladen wird.
_CALC_DIR = Path(__file__).resolve().parents[1]
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from feiertage import (  # noqa: E402
    BUNDESLAENDER,
    ist_feiertag,
    jahres_hinweise,
)

EINHEITEN = ("tage", "wochen", "monate", "jahre")
FRISTTYP_EREIGNIS = "ereignis"   # § 187 Abs. 1 BGB
FRISTTYP_BEGINN = "beginn"       # § 187 Abs. 2 BGB

KATALOG_PFAD = Path(__file__).resolve().parent / "fristarten.json"

_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
               "Freitag", "Samstag", "Sonntag"]


def _wochentag(d: _dt.date) -> str:
    return _WOCHENTAGE[d.weekday()]


class FristEingabeFehler(ValueError):
    """Ungültige Eingabe (unbekannte Einheit, Fristart, Bundesland, …)."""


# --------------------------------------------------------------------------
# Ergebnis-Strukturen
# --------------------------------------------------------------------------

@dataclass
class Verschiebung:
    """Eine einzelne Verschiebung im Rahmen von § 193 BGB / § 222 Abs. 2 ZPO."""
    von: _dt.date
    auf: _dt.date
    grund: str
    norm: str = "§ 193 BGB / § 222 Abs. 2 ZPO"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["von"] = self.von.isoformat()
        d["auf"] = self.auf.isoformat()
        return d


@dataclass
class RechenSchritt:
    """Ein Glied der nachvollziehbaren Rechenkette (P3: quelle=executor)."""
    schritt: int
    norm: str
    beschreibung: str
    ergebnis: str | None          # ISO-Datum des Zwischenergebnisses
    quelle: str = "executor"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FristErgebnis:
    ereignis_datum: _dt.date
    dauer: int
    einheit: str
    fristtyp: str
    bundesland: str
    fristbeginn: _dt.date
    fristende_rechnerisch: _dt.date        # § 188, vor § 193-Verschiebung
    fristende: _dt.date                    # nach § 193 (das Ergebnis)
    verschoben: bool
    verschiebungen: list[Verschiebung] = field(default_factory=list)
    # Abweichendes Ende, falls teilgebietliche Feiertage am Fristende-Ort
    # tatsächlich gelten (None = kein Unterschied):
    fristende_bei_teilgebietlichem_feiertag: _dt.date | None = None
    rechenkette: list[RechenSchritt] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ereignis_datum": self.ereignis_datum.isoformat(),
            "dauer": self.dauer,
            "einheit": self.einheit,
            "fristtyp": self.fristtyp,
            "bundesland": self.bundesland,
            "fristbeginn": self.fristbeginn.isoformat(),
            "fristende_rechnerisch": self.fristende_rechnerisch.isoformat(),
            "fristende": self.fristende.isoformat(),
            "verschoben": self.verschoben,
            "verschiebungen": [v.as_dict() for v in self.verschiebungen],
            "fristende_bei_teilgebietlichem_feiertag": (
                self.fristende_bei_teilgebietlichem_feiertag.isoformat()
                if self.fristende_bei_teilgebietlichem_feiertag else None),
            "rechenkette": [s.as_dict() for s in self.rechenkette],
            "warnungen": list(self.warnungen),
            "quelle": "executor",
        }


# --------------------------------------------------------------------------
# Fristarten-Katalog (Daten, nicht Logik)
# --------------------------------------------------------------------------

def lade_katalog(pfad: Path | None = None) -> dict[str, Any]:
    daten = json.loads((pfad or KATALOG_PFAD).read_text(encoding="utf-8"))
    ids = [f["id"] for f in daten["fristarten"]]
    if len(ids) != len(set(ids)):
        raise FristEingabeFehler("Fristarten-Katalog enthält doppelte ids")
    return daten


def fristart_nach_id(fristart_id: str, katalog: dict[str, Any] | None = None) -> dict[str, Any]:
    kat = katalog or lade_katalog()
    for f in kat["fristarten"]:
        if f["id"] == fristart_id:
            return f
    bekannte = ", ".join(f["id"] for f in kat["fristarten"])
    raise FristEingabeFehler(
        f"unbekannte Fristart: {fristart_id!r} (bekannt: {bekannte})")


# --------------------------------------------------------------------------
# Kernberechnung
# --------------------------------------------------------------------------

def _monatsende_addition(ereignis: _dt.date, monate: int,
                         fristtyp: str) -> tuple[_dt.date, bool]:
    """§ 188 Abs. 2 (ggf. i. V. m. Abs. 3) BGB für Monats-/Jahresfristen.

    Liefert (Fristende, monatsueberlauf). monatsueberlauf=True, wenn der dem
    Ereignistag nach seiner Zahl entsprechende Tag im Zielmonat fehlt
    (z. B. 31.01. + 1 Monat) — dann endet die Frist mit dem letzten Tag des
    Zielmonats (§ 188 Abs. 3 BGB), und zwar bei Ereignis- wie Beginnfrist.
    """
    gesamt = ereignis.year * 12 + (ereignis.month - 1) + monate
    ziel_jahr, ziel_monat0 = divmod(gesamt, 12)
    ziel_monat = ziel_monat0 + 1
    letzter = calendar.monthrange(ziel_jahr, ziel_monat)[1]
    ueberlauf = ereignis.day > letzter
    if fristtyp == FRISTTYP_EREIGNIS:
        ende = _dt.date(ziel_jahr, ziel_monat, letzter if ueberlauf else ereignis.day)
    else:
        if ueberlauf:
            # Der dem (fehlenden) entsprechenden Tag vorhergehende Tag ist der
            # letzte existierende Tag des Zielmonats (§ 188 Abs. 2 Alt. 2
            # i. V. m. Abs. 3 BGB) — nicht letzter Tag minus 1.
            ende = _dt.date(ziel_jahr, ziel_monat, letzter)
        else:
            ende = _dt.date(ziel_jahr, ziel_monat, ereignis.day) - _dt.timedelta(days=1)
    return ende, ueberlauf


def _feiertagsgrund(d: _dt.date, bundesland: str,
                    mit_teilgebietlichen: bool) -> str | None:
    """Grund, aus dem `d` kein Werktag i. S. v. § 193 BGB ist — sonst None."""
    gruende: list[str] = []
    if d.weekday() == 5:
        gruende.append("Sonnabend (Samstag)")
    elif d.weekday() == 6:
        gruende.append("Sonntag")
    auskunft = ist_feiertag(d, bundesland)
    if auskunft.gesetzlich:
        gruende.append(f"gesetzlicher Feiertag ({auskunft.name})")
    elif mit_teilgebietlichen and auskunft.teilgebietlich:
        gruende.append(f"teilgebietlicher Feiertag ({auskunft.teilgebiet_name})")
    return "; zugleich ".join(gruende) if gruende else None


def _verschiebe_193(ende: _dt.date, bundesland: str,
                    mit_teilgebietlichen: bool) -> tuple[_dt.date, list[Verschiebung]]:
    """§ 193 BGB / § 222 Abs. 2 ZPO: auf den nächsten Werktag verschieben.

    Jeder übersprungene Tag wird als eigene Verschiebung mit Grund ausgewiesen
    (Kaskade Sa → So → Feiertag → … bleibt nachvollziehbar).
    """
    verschiebungen: list[Verschiebung] = []
    d = ende
    while True:
        grund = _feiertagsgrund(d, bundesland, mit_teilgebietlichen)
        if grund is None:
            return d, verschiebungen
        naechster = d + _dt.timedelta(days=1)
        verschiebungen.append(Verschiebung(von=d, auf=naechster, grund=grund))
        d = naechster


def berechne_frist(ereignis_datum: _dt.date, dauer: int, einheit: str,
                   fristtyp: str = FRISTTYP_EREIGNIS, *,
                   bundesland: str,
                   paragraf_193_anwenden: bool = True) -> FristErgebnis:
    """Berechnet eine Frist nach §§ 187, 188, 193 BGB (§ 222 ZPO).

    Args:
        ereignis_datum: fristauslösendes Ereignis (z. B. Zustellung) bzw.
            Anfangstag bei einer Beginnfrist.
        dauer: Anzahl der Einheiten (>= 1).
        einheit: "tage" | "wochen" | "monate" | "jahre".
        fristtyp: "ereignis" (§ 187 Abs. 1 BGB, Ereignistag zählt nicht) oder
            "beginn" (§ 187 Abs. 2 BGB, Anfangstag zählt mit).
        bundesland: Pflicht — Feiertage am Fristende-Ort (§ 193 BGB), bei
            gerichtlichen Fristen der Sitz des Gerichts.
        paragraf_193_anwenden: Verschiebung nach § 193 BGB / § 222 Abs. 2 ZPO
            anwenden (Default). False z. B. für reine Zeitraumberechnungen,
            auf die § 193 nicht anwendbar ist (etwa Beginn eines Zinslaufs).
    """
    einheit = einheit.lower().strip()
    if einheit not in EINHEITEN:
        raise FristEingabeFehler(
            f"einheit muss eine von {EINHEITEN} sein, nicht {einheit!r}")
    if fristtyp not in (FRISTTYP_EREIGNIS, FRISTTYP_BEGINN):
        raise FristEingabeFehler(
            f"fristtyp muss 'ereignis' oder 'beginn' sein, nicht {fristtyp!r}")
    if not isinstance(dauer, int) or dauer < 1:
        raise FristEingabeFehler("dauer muss eine ganze Zahl >= 1 sein")
    land = bundesland.strip().upper()
    if land not in BUNDESLAENDER:
        raise FristEingabeFehler(
            f"unbekanntes Bundesland-Kürzel: {bundesland!r} "
            f"(erlaubt: {', '.join(sorted(BUNDESLAENDER))})")

    # Bereichsgrenze: Die Feiertagsberechnung (gregorianische Osterformel)
    # trägt nur die Jahre 1583–4099. Ereignisse außerhalb werden als
    # Eingabefehler abgelehnt statt als Traceback durchzuschlagen.
    if not (1583 <= ereignis_datum.year <= 4099):
        raise FristEingabeFehler(
            f"ereignis_datum {ereignis_datum.isoformat()} liegt außerhalb des "
            f"berechenbaren Bereichs (Jahre 1583–4099, gregorianische "
            f"Osterformel)")
    try:
        return _berechne_kern(ereignis_datum, dauer, einheit, fristtyp,
                              land=land,
                              paragraf_193_anwenden=paragraf_193_anwenden)
    except FristEingabeFehler:
        raise
    except (ValueError, OverflowError) as exc:
        # z. B. Fristende jenseits von 4099 (Feiertagsprüfung des Endjahres)
        # oder jenseits des datetime-Wertebereichs bei extremen Dauern.
        raise FristEingabeFehler(
            f"Fristende liegt außerhalb des berechenbaren Bereichs "
            f"(Jahre 1583–4099): {exc}")


def _berechne_kern(ereignis_datum: _dt.date, dauer: int, einheit: str,
                   fristtyp: str, *, land: str,
                   paragraf_193_anwenden: bool) -> FristErgebnis:
    """Kernrechnung nach validierter Eingabe (nur über berechne_frist rufen)."""
    kette: list[RechenSchritt] = []
    warnungen: list[str] = []

    def schritt(norm: str, beschreibung: str, ergebnis: _dt.date | None) -> None:
        kette.append(RechenSchritt(
            schritt=len(kette) + 1, norm=norm, beschreibung=beschreibung,
            ergebnis=ergebnis.isoformat() if ergebnis else None))

    # --- Fristbeginn, § 187 BGB ---
    if fristtyp == FRISTTYP_EREIGNIS:
        fristbeginn = ereignis_datum + _dt.timedelta(days=1)
        schritt("§ 187 Abs. 1 BGB",
                f"Ereignistag {ereignis_datum:%d.%m.%Y} ({_wochentag(ereignis_datum)}) "
                f"wird nicht mitgerechnet; Fristbeginn am Folgetag.",
                fristbeginn)
    else:
        fristbeginn = ereignis_datum
        schritt("§ 187 Abs. 2 BGB",
                f"Anfangstag {ereignis_datum:%d.%m.%Y} ({_wochentag(ereignis_datum)}) "
                f"wird mitgerechnet; Fristbeginn am Anfangstag.",
                fristbeginn)

    # --- rechnerisches Fristende, § 188 BGB ---
    if einheit == "tage":
        if fristtyp == FRISTTYP_EREIGNIS:
            ende = ereignis_datum + _dt.timedelta(days=dauer)
        else:
            ende = ereignis_datum + _dt.timedelta(days=dauer - 1)
        schritt("§ 188 Abs. 1 BGB",
                f"Tagesfrist: {dauer} Tage ab Fristbeginn enden mit Ablauf des "
                f"letzten Tages der Frist.", ende)
    elif einheit == "wochen":
        if fristtyp == FRISTTYP_EREIGNIS:
            ende = ereignis_datum + _dt.timedelta(weeks=dauer)
            schritt("§ 188 Abs. 2 Alt. 1 BGB",
                    f"Wochenfrist ({dauer} Wo.): Ende mit Ablauf des Tages der "
                    f"letzten Woche, der durch seine Benennung dem Ereignistag "
                    f"entspricht ({_wochentag(ende)}).", ende)
        else:
            ende = ereignis_datum + _dt.timedelta(weeks=dauer, days=-1)
            schritt("§ 188 Abs. 2 Alt. 2 BGB",
                    f"Wochenfrist ({dauer} Wo., Beginnfrist): Ende mit Ablauf des "
                    f"Tages, der dem Tag vorhergeht, der dem Anfangstag entspricht.",
                    ende)
    else:  # monate / jahre
        monate = dauer if einheit == "monate" else dauer * 12
        ende, ueberlauf = _monatsende_addition(ereignis_datum, monate, fristtyp)
        einheit_text = f"{dauer} Monat(e)" if einheit == "monate" else f"{dauer} Jahr(e)"
        if fristtyp == FRISTTYP_EREIGNIS:
            schritt("§ 188 Abs. 2 Alt. 1 BGB",
                    f"Monats-/Jahresfrist ({einheit_text}): Ende mit Ablauf des "
                    f"Tages, der durch seine Zahl dem Ereignistag entspricht.",
                    ende)
        else:
            schritt("§ 188 Abs. 2 Alt. 2 BGB",
                    f"Monats-/Jahresfrist ({einheit_text}, Beginnfrist): Ende mit "
                    f"Ablauf des Tages, der dem Tag vorhergeht, der dem Anfangstag "
                    f"entspricht.", ende)
        if ueberlauf:
            schritt("§ 188 Abs. 3 BGB",
                    f"Der dem Ereignistag ({ereignis_datum.day}.) entsprechende Tag "
                    f"fehlt im Zielmonat — die Frist endet mit Ablauf des letzten "
                    f"Tages dieses Monats.", ende)

    fristende_rechnerisch = ende

    # --- § 193 BGB / § 222 Abs. 2 ZPO ---
    verschiebungen: list[Verschiebung] = []
    fristende = fristende_rechnerisch
    ende_teilgebietlich: _dt.date | None = None

    if paragraf_193_anwenden:
        fristende, verschiebungen = _verschiebe_193(
            fristende_rechnerisch, land, mit_teilgebietlichen=False)
        for v in verschiebungen:
            schritt(v.norm,
                    f"Fristende {v.von:%d.%m.%Y} ({_wochentag(v.von)}) ist "
                    f"{v.grund} in {BUNDESLAENDER[land]} — Verschiebung auf den "
                    f"nächsten Tag.", v.auf)
        if fristende != fristende_rechnerisch:
            schritt("§ 193 BGB / § 222 Abs. 2 ZPO",
                    f"Fristende nach Verschiebung: {fristende:%d.%m.%Y} "
                    f"({_wochentag(fristende)}), nächster Werktag.", fristende)

        # Teilgebietliche Feiertage: Alternativ-Rechnung, nie stillschweigend.
        alt_ende, _alt_verschiebungen = _verschiebe_193(
            fristende_rechnerisch, land, mit_teilgebietlichen=True)
        if alt_ende != fristende:
            ende_teilgebietlich = alt_ende
            betroffene = sorted({
                f"{v.grund}" for v in _alt_verschiebungen
                if "teilgebietlicher Feiertag" in v.grund})
            warnungen.append(
                f"Teilgebietlicher Feiertag betroffen ({'; '.join(betroffene)}): "
                f"Gilt der Feiertag am konkreten Fristende-Ort, verschiebt sich "
                f"das Fristende auf {alt_ende:%d.%m.%Y} ({_wochentag(alt_ende)}); "
                f"gilt er dort nicht, bleibt es beim {fristende:%d.%m.%Y} "
                f"({_wochentag(fristende)}). Konkrete Gemeinde prüfen — beide "
                f"Enden sind ausgewiesen.")
            schritt("§ 193 BGB / § 222 Abs. 2 ZPO (teilgebietlich)",
                    "Alternatives Fristende, falls der teilgebietliche Feiertag "
                    "am Fristende-Ort gilt.", alt_ende)
    else:
        schritt("§ 193 BGB / § 222 Abs. 2 ZPO",
                "Verschiebung auf Wunsch nicht angewendet "
                "(paragraf_193_anwenden=false).", fristende)

    # Verlässlichkeits-Hinweise der Feiertagsdaten: nur der Altjahre-Hinweis —
    # der allgemeine Teilgebiets-Hinweis wäre hier Rauschen, denn ob ein
    # teilgebietlicher Feiertag das Fristende tatsächlich berührt, prüft die
    # Alternativ-Rechnung oben bereits datumsgenau.
    for jahr in range(fristbeginn.year, fristende.year + 1):
        for h in jahres_hinweise(jahr, land):
            if "teilgebietliche Feiertage" not in h and h not in warnungen:
                warnungen.append(h)

    return FristErgebnis(
        ereignis_datum=ereignis_datum,
        dauer=dauer,
        einheit=einheit,
        fristtyp=fristtyp,
        bundesland=land,
        fristbeginn=fristbeginn,
        fristende_rechnerisch=fristende_rechnerisch,
        fristende=fristende,
        verschoben=fristende != fristende_rechnerisch,
        verschiebungen=verschiebungen,
        fristende_bei_teilgebietlichem_feiertag=ende_teilgebietlich,
        rechenkette=kette,
        warnungen=warnungen,
    )


def naechster_werktag(datum: _dt.date, bundesland: str) -> _dt.date:
    """Nächster Werktag (Mo–Fr, kein landesweiter gesetzlicher Feiertag) am
    oder nach `datum` — Hilfsfunktion, teilgebietliche Feiertage zählen hier
    bewusst nicht (siehe berechne_frist für die ehrliche Doppel-Ausweisung)."""
    ende, _ = _verschiebe_193(datum, bundesland.strip().upper(),
                              mit_teilgebietlichen=False)
    return ende
