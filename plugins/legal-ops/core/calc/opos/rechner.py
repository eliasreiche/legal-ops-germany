#!/usr/bin/env python3
"""opos.rechner — deterministische Auswertung offener Posten (P3).

Zwei Datei-Quellen, ein Auswertungskern:

  * **OPOS-CSV** (`lade_opos_csv`) — die präzise Primärquelle: je Zeile ein
    offener Posten mit Rechnungs-/Fälligkeitsdatum, Betrag und bereits
    gezahltem Anteil. Format-Kontrakt siehe
    skills/honorar-mahnwesen/schema/README.md.
  * **EXTF-Buchungsstapel** (`stapel_zu_posten`, über core/calc/extf/parser.py)
    — eine *vereinfachte* Aggregation: Buchungen werden über das Belegfeld 1
    (OPOS-Schlüssel) gruppiert, offener Rest = Σ Soll − Σ Haben − Σ Skonto
    (auf Haben-Buchungen). Ein Buchungsstapel enthält selten Rechnung UND
    Zahlung zugleich, daher ist diese Quelle ergänzend; Lücken (fehlender
    Mandant, fehlende Fälligkeit) werden ausgewiesen, nie erfunden.

Der Kern (`bewerte`) rechnet ausschließlich:
  * offener Restbetrag  = betrag − bereits_gezahlt         (Decimal, nie float)
  * tage_seit_faelligkeit = stichtag − faelligkeitsdatum   (Kalendertage)
  * Mahnstufe            = konfigurierbare Tagesschwellen (Default unten)
  * prioritaet           = offener Rest × max(tage_seit_faelligkeit, 0)

**Bewusst NICHT berechnet (v1, siehe SKILL.md):**
  * Verzugszinsen (§ 288 BGB) — bräuchte gepflegte Basiszinssatz-Stammdaten;
    erscheinen im Report nur als Hinweis-Lücke, nie als Zahl.
  * die rechtliche Verzugsfeststellung (§ 286 BGB) — verbraucherabhängig,
    bleibt ausdrücklich Kanzleisache. „Tage seit Fälligkeit" ist eine reine
    Kalenderdifferenz, keine Verzugseinordnung.

Der Stichtag kommt immer aus der Eingabe, nie aus der Wall-Clock (Idempotenz,
wie erzeugt_am im EXTF-Writer). Nur Standardbibliothek, `Decimal` für Geld.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

_OPOS_DIR = Path(__file__).resolve().parent
_CALC_DIR = _OPOS_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from wertgebuehr_formel import D, WertgebuehrFehler, parse_datum_strikt  # noqa: E402

VERZUGSZINS_HINWEIS = (
    "Verzugszinsen (§ 288 BGB) werden nicht berechnet — dafür sind gepflegte "
    "Basiszinssatz-Stammdaten nötig; auch die rechtliche Verzugsfeststellung "
    "(§ 286 BGB) bleibt Kanzleisache. 'Tage seit Fälligkeit' ist eine reine "
    "Kalenderdifferenz."
)

# Default-Mahnstufen (konfigurierbar, siehe lade_mahnstufen_config). Absteigend
# nach ab_tage geordnet — die erste Schwelle, die tage_seit_faelligkeit
# erreicht, greift. Rechtlich unverbindlich: die Kanzlei entscheidet, ob und
# wann eine Mahnung ergeht (§ 286 BGB bleibt Kanzleisache).
MAHNSTUFEN_DEFAULT: list[dict[str, Any]] = [
    {"ab_tage": 30, "stufe": "2_mahnung", "bezeichnung": "2. Mahnung"},
    {"ab_tage": 14, "stufe": "1_mahnung", "bezeichnung": "1. Mahnung"},
    {"ab_tage": 0, "stufe": "zahlungserinnerung", "bezeichnung": "Zahlungserinnerung"},
]
_STUFE_NICHT_FAELLIG = {"stufe": "offen_nicht_faellig", "bezeichnung": "offen, noch nicht fällig"}
_STUFE_UNBESTIMMT = {"stufe": "faelligkeit_unbekannt", "bezeichnung": "Fälligkeit unbekannt"}

_CSV_PFLICHTSPALTEN = ["rechnungsnummer", "rechnungsdatum", "faelligkeitsdatum", "betrag"]
_CSV_ALLE_SPALTEN = _CSV_PFLICHTSPALTEN + ["mandant", "aktenzeichen", "bereits_gezahlt"]


class OposEingabeFehler(ValueError):
    """Format-/Eingabefehler beim Laden oder Auswerten offener Posten."""


@dataclass
class Posten:
    """Ein offener Posten (normalisiert, quellenunabhängig)."""
    rechnungsnummer: str
    betrag: Decimal
    bereits_gezahlt: Decimal
    rechnungsdatum: _dt.date | None = None
    faelligkeitsdatum: _dt.date | None = None
    mandant: str | None = None
    aktenzeichen: str | None = None
    quelle: str = "opos-csv"
    hinweise: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Geld-Helfer (deutsche Komma-Dezimalzahl aus CSV)
# --------------------------------------------------------------------------

def _geld_csv(wert: str, feld: str, zeile: int) -> Decimal:
    """CSV-Betrag (deutsche Konvention: Dezimalkomma, kein Tausenderpunkt) →
    Decimal. '952,50' und '952.50' sind zulässig, '1.234,56' (Tausenderpunkt)
    wird als mehrdeutig abgelehnt — keine stille Reparatur."""
    roh = wert.strip()
    if not roh:
        raise OposEingabeFehler(f"Zeile {zeile}: '{feld}' ist leer")
    if "." in roh and "," in roh:
        raise OposEingabeFehler(
            f"Zeile {zeile}: '{feld}' ({roh!r}) ist mehrdeutig — Betrag ohne "
            f"Tausendertrennzeichen angeben (z. B. 1234,56)")
    try:
        return D(roh.replace(",", "."))
    except WertgebuehrFehler as exc:
        raise OposEingabeFehler(f"Zeile {zeile}: '{feld}' ist kein gültiger Betrag: {wert!r} ({exc})")


def _datum_csv(wert: str, feld: str, zeile: int, *, pflicht: bool) -> _dt.date | None:
    roh = wert.strip()
    if not roh:
        if pflicht:
            raise OposEingabeFehler(f"Zeile {zeile}: Pflichtfeld '{feld}' ist leer")
        return None
    try:
        return parse_datum_strikt(roh, feld)
    except WertgebuehrFehler as exc:
        raise OposEingabeFehler(f"Zeile {zeile}: {exc}")


# --------------------------------------------------------------------------
# Quelle 1: OPOS-CSV
# --------------------------------------------------------------------------

def lade_opos_csv(quelle: str | Path | bytes) -> list[Posten]:
    """Liest eine OPOS-CSV (Semikolon-getrennt, Kopfzeile mit Spaltennamen)
    in eine Postenliste. Strenge Validierung mit Zeilenangabe — fehlende
    Pflichtspalten, ungültige Beträge/Daten oder eine doppelte
    Rechnungsnummer sind ein Fehler, keine stille Reparatur."""
    if isinstance(quelle, (str, Path)) and Path(str(quelle)).is_file() and not isinstance(quelle, bytes):
        text = Path(quelle).read_text(encoding="utf-8")
    elif isinstance(quelle, bytes):
        text = quelle.decode("utf-8")
    else:
        text = str(quelle)

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if reader.fieldnames is None:
        raise OposEingabeFehler("OPOS-CSV ist leer (keine Kopfzeile)")
    spalten = [f.strip() for f in reader.fieldnames]
    fehlend = [s for s in _CSV_PFLICHTSPALTEN if s not in spalten]
    if fehlend:
        raise OposEingabeFehler(
            f"OPOS-CSV: Pflichtspalten fehlen in der Kopfzeile: {', '.join(fehlend)} "
            f"(erwartet mindestens {', '.join(_CSV_PFLICHTSPALTEN)})")
    unbekannt = [s for s in spalten if s not in _CSV_ALLE_SPALTEN]
    if unbekannt:
        raise OposEingabeFehler(
            f"OPOS-CSV: unbekannte Spalte(n): {', '.join(unbekannt)} "
            f"(erlaubt: {', '.join(_CSV_ALLE_SPALTEN)})")

    posten: list[Posten] = []
    gesehen: dict[str, int] = {}
    for i, roh in enumerate(reader, start=2):  # Zeile 1 = Kopf
        werte = {k.strip(): (v.strip() if isinstance(v, str) else "") for k, v in roh.items() if k}
        rnr = werte.get("rechnungsnummer", "")
        if not rnr:
            raise OposEingabeFehler(f"Zeile {i}: Pflichtfeld 'rechnungsnummer' ist leer")
        if rnr in gesehen:
            raise OposEingabeFehler(
                f"Zeile {i}: Rechnungsnummer {rnr!r} kommt doppelt vor "
                f"(bereits in Zeile {gesehen[rnr]}) — offene Posten müssen eindeutig sein")
        gesehen[rnr] = i

        betrag = _geld_csv(werte["betrag"], "betrag", i)
        gezahlt_roh = werte.get("bereits_gezahlt", "")
        bereits_gezahlt = _geld_csv(gezahlt_roh, "bereits_gezahlt", i) if gezahlt_roh else Decimal("0")
        if betrag <= 0:
            raise OposEingabeFehler(f"Zeile {i}: 'betrag' muss > 0 sein, ist {betrag}")
        if bereits_gezahlt < 0:
            raise OposEingabeFehler(f"Zeile {i}: 'bereits_gezahlt' darf nicht negativ sein, ist {bereits_gezahlt}")

        rdatum = _datum_csv(werte["rechnungsdatum"], "rechnungsdatum", i, pflicht=True)
        fdatum = _datum_csv(werte["faelligkeitsdatum"], "faelligkeitsdatum", i, pflicht=True)
        if rdatum and fdatum and fdatum < rdatum:
            raise OposEingabeFehler(
                f"Zeile {i}: 'faelligkeitsdatum' ({fdatum.isoformat()}) liegt vor "
                f"'rechnungsdatum' ({rdatum.isoformat()})")

        posten.append(Posten(
            rechnungsnummer=rnr,
            betrag=betrag,
            bereits_gezahlt=bereits_gezahlt,
            rechnungsdatum=rdatum,
            faelligkeitsdatum=fdatum,
            mandant=werte.get("mandant") or None,
            aktenzeichen=werte.get("aktenzeichen") or None,
            quelle="opos-csv",
        ))
    if not posten:
        raise OposEingabeFehler("OPOS-CSV enthält keine Datenzeile")
    return posten


# --------------------------------------------------------------------------
# Quelle 2: EXTF-Buchungsstapel (vereinfachte Aggregation)
# --------------------------------------------------------------------------

def stapel_zu_posten(stapel: Any, zahlungsziel_tage: int) -> tuple[list[Posten], list[dict[str, Any]]]:
    """Aggregiert einen geparsten EXTF-Stapel (core/calc/extf/parser.ExtfStapel)
    über das Belegfeld 1 (OPOS-Schlüssel) zu offenen Posten.

    Vereinfachung (v1, dokumentiert): offener Rest je Belegfeld 1 =
    Σ Umsatz(Soll) − Σ Umsatz(Haben) − Σ Skonto(Haben). Rechnungsdatum ist das
    früheste Soll-Belegdatum der Gruppe; Fälligkeit = Rechnungsdatum +
    `zahlungsziel_tage` (EXTF trägt kein Fälligkeitsdatum — die Annahme wird je
    Posten als Hinweis ausgewiesen). Mandant/Aktenzeichen stehen nicht im EXTF
    und bleiben Lücke. Buchungen ohne Belegfeld 1 sind nicht zuordenbar und
    werden separat gemeldet, nie geraten.

    Gibt (posten, nicht_zuordenbar) zurück; Anomalien (z. B. Zahlung ohne
    zugehörige Rechnung → negativer Rest) tragen einen Hinweis am Posten."""
    if zahlungsziel_tage < 0:
        raise OposEingabeFehler(f"zahlungsziel_tage darf nicht negativ sein, ist {zahlungsziel_tage}")

    gruppen: dict[str, list[Any]] = {}
    nicht_zuordenbar: list[dict[str, Any]] = []
    for b in stapel.buchungen:
        if b.belegfeld1:
            gruppen.setdefault(b.belegfeld1, []).append(b)
        else:
            nicht_zuordenbar.append({
                "zeile": b.zeile,
                "umsatz": str(b.umsatz),
                "soll_haben": b.soll_haben,
                "konto": b.konto,
                "grund": "keine Belegfeld-1-Angabe (OPOS-Schlüssel) — nicht zuordenbar",
            })

    posten: list[Posten] = []
    for rnr, buchungen in gruppen.items():
        soll = sum((b.umsatz for b in buchungen if b.soll_haben == "S"), Decimal("0"))
        haben = sum((b.umsatz for b in buchungen if b.soll_haben == "H"), Decimal("0"))
        skonto_haben = sum((b.skonto for b in buchungen
                            if b.soll_haben == "H" and b.skonto is not None), Decimal("0"))
        offener_rest = soll - haben - skonto_haben

        hinweise = [
            "EXTF-Quelle: offener Rest aus Belegfeld-1-Aggregation "
            "(Σ Soll − Σ Haben − Σ Skonto), Mandant/Aktenzeichen nicht im EXTF enthalten.",
            f"Fälligkeit angenommen als Rechnungsdatum + {zahlungsziel_tage} Tage "
            f"(Zahlungsziel-Annahme; EXTF trägt kein Fälligkeitsdatum).",
        ]
        if any(b.soll_haben == "S" and b.skonto is not None for b in buchungen):
            hinweise.append("Skonto auf einer Soll-Buchung wurde NICHT verrechnet — bitte prüfen.")
        if offener_rest < 0:
            hinweise.append("Negativer offener Rest (Haben > Soll) — vermutlich Zahlung ohne "
                            "zugehörige Rechnung im Stapel oder Guthaben; bitte prüfen.")

        soll_daten = [b.belegdatum for b in buchungen if b.soll_haben == "S" and b.belegdatum]
        rdatum = min(soll_daten) if soll_daten else None
        fdatum = rdatum + _dt.timedelta(days=zahlungsziel_tage) if rdatum else None
        if rdatum is None:
            hinweise.append("Kein Soll-Belegdatum in der Gruppe — Rechnungs-/Fälligkeitsdatum unbekannt.")

        # betrag/bereits_gezahlt so füllen, dass betrag − bereits_gezahlt == offener_rest.
        posten.append(Posten(
            rechnungsnummer=rnr,
            betrag=soll,
            bereits_gezahlt=haben + skonto_haben,
            rechnungsdatum=rdatum,
            faelligkeitsdatum=fdatum,
            mandant=None,
            aktenzeichen=None,
            quelle="extf",
            hinweise=hinweise,
        ))
    return posten, nicht_zuordenbar


# --------------------------------------------------------------------------
# Mahnstufen-Konfiguration
# --------------------------------------------------------------------------

def lade_mahnstufen_config(config: Any) -> list[dict[str, Any]]:
    """Validiert eine Mahnstufen-Konfiguration (Liste von {ab_tage, stufe,
    bezeichnung}) und gibt sie absteigend nach ab_tage sortiert zurück. Bei
    None → MAHNSTUFEN_DEFAULT."""
    if config is None:
        return list(MAHNSTUFEN_DEFAULT)
    if isinstance(config, dict) and "stufen" in config:
        config = config["stufen"]
    if not isinstance(config, list) or not config:
        raise OposEingabeFehler("Mahnstufen-Konfiguration muss eine nicht-leere Liste sein")
    stufen: list[dict[str, Any]] = []
    for i, s in enumerate(config):
        if not isinstance(s, dict):
            raise OposEingabeFehler(f"Mahnstufe {i}: muss ein Objekt sein, nicht {s!r}")
        ab = s.get("ab_tage")
        if isinstance(ab, bool) or not isinstance(ab, int) or ab < 0:
            raise OposEingabeFehler(f"Mahnstufe {i}: 'ab_tage' muss eine ganze Zahl >= 0 sein, ist {ab!r}")
        stufe = s.get("stufe")
        bez = s.get("bezeichnung")
        if not isinstance(stufe, str) or not stufe.strip():
            raise OposEingabeFehler(f"Mahnstufe {i}: 'stufe' muss ein nicht-leerer Text sein")
        if not isinstance(bez, str) or not bez.strip():
            raise OposEingabeFehler(f"Mahnstufe {i}: 'bezeichnung' muss ein nicht-leerer Text sein")
        stufen.append({"ab_tage": ab, "stufe": stufe, "bezeichnung": bez})
    return sorted(stufen, key=lambda s: s["ab_tage"], reverse=True)


def _mahnstufe(tage: int | None, stufen: list[dict[str, Any]]) -> dict[str, str]:
    if tage is None:
        return dict(_STUFE_UNBESTIMMT)
    if tage < 0:
        return dict(_STUFE_NICHT_FAELLIG)
    for s in stufen:  # absteigend nach ab_tage
        if tage >= s["ab_tage"]:
            return {"stufe": s["stufe"], "bezeichnung": s["bezeichnung"]}
    return dict(_STUFE_NICHT_FAELLIG)


# --------------------------------------------------------------------------
# Auswertungskern
# --------------------------------------------------------------------------

def _bewerte_posten(p: Posten, stichtag: _dt.date, stufen: list[dict[str, Any]]) -> dict[str, Any]:
    offener_rest = p.betrag - p.bereits_gezahlt
    if p.faelligkeitsdatum is not None:
        tage = (stichtag - p.faelligkeitsdatum).days
        prioritaet = offener_rest * Decimal(max(tage, 0))
    else:
        tage = None
        prioritaet = None
    stufe = _mahnstufe(tage, stufen)
    return {
        "rechnungsnummer": p.rechnungsnummer,
        "mandant": p.mandant,
        "aktenzeichen": p.aktenzeichen,
        "rechnungsdatum": p.rechnungsdatum.isoformat() if p.rechnungsdatum else None,
        "faelligkeitsdatum": p.faelligkeitsdatum.isoformat() if p.faelligkeitsdatum else None,
        "betrag": str(p.betrag),
        "bereits_gezahlt": str(p.bereits_gezahlt),
        "offener_rest": str(offener_rest),
        "tage_seit_faelligkeit": tage,
        "mahnstufe": stufe["stufe"],
        "mahnstufe_bezeichnung": stufe["bezeichnung"],
        "prioritaet": str(prioritaet) if prioritaet is not None else None,
        "verzugszins_hinweis": VERZUGSZINS_HINWEIS,
        "quelle": p.quelle,
        "hinweise": list(p.hinweise),
    }


def _sortkey(eintrag: dict[str, Any]) -> tuple:
    # Höchste Priorität zuerst; Posten ohne Fälligkeit (prioritaet None) ganz
    # ans Ende. Sekundär nach offenem Rest, dann Rechnungsnummer (stabil).
    prio = eintrag["prioritaet"]
    hat_prio = prio is not None
    return (
        0 if hat_prio else 1,
        -Decimal(prio) if hat_prio else Decimal("0"),
        -Decimal(eintrag["offener_rest"]),
        eintrag["rechnungsnummer"],
    )


def bewerte(posten: list[Posten], stichtag: _dt.date,
            mahnstufen: list[dict[str, Any]] | None = None,
            *, nicht_zuordenbar: list[dict[str, Any]] | None = None,
            quelle_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wertet eine Postenliste zum Stichtag aus. Liefert ein Report-Dict mit
    offenen Posten (nach Priorität sortiert), ausgeglichenen Posten und einer
    Zusammenfassung. Rechnet nur Restbetrag/Tage/Priorität — nie Zinsen oder
    eine Verzugseinordnung (P3)."""
    if not isinstance(stichtag, _dt.date):
        raise OposEingabeFehler("stichtag muss ein datetime.date sein")
    stufen = mahnstufen if mahnstufen is not None else list(MAHNSTUFEN_DEFAULT)

    offene: list[dict[str, Any]] = []
    ausgeglichen: list[dict[str, Any]] = []
    summe_offen = Decimal("0")
    for p in posten:
        bewertung = _bewerte_posten(p, stichtag, stufen)
        rest = Decimal(bewertung["offener_rest"])
        if rest > 0:
            offene.append(bewertung)
            summe_offen += rest
        else:
            ausgeglichen.append(bewertung)
    offene.sort(key=_sortkey)

    return {
        "meta": {
            "erzeugt_von": "plugins/legal-ops/core/calc/opos/rechner.py",
            "deterministik": ("Alle Beträge, Tage und Prioritäten in diesem Report "
                              "sind Executor-Ergebnisse (P3), nicht modellgeneriert."),
            "verzugszins_hinweis": VERZUGSZINS_HINWEIS,
            "mahn_hinweis": ("Mahnstufen sind eine kalendarische Einordnung nach "
                             "Tagesschwellen — ob und wann gemahnt wird, entscheidet "
                             "die Kanzlei (§ 286 BGB bleibt Kanzleisache)."),
            **(quelle_meta or {}),
        },
        "stichtag": stichtag.isoformat(),
        "mahnstufen_konfiguration": stufen,
        "zusammenfassung": {
            "anzahl_offen": len(offene),
            "summe_offen": str(summe_offen),
            "anzahl_ausgeglichen": len(ausgeglichen),
            "anzahl_nicht_zuordenbar": len(nicht_zuordenbar or []),
        },
        "offene_posten": offene,
        "ausgeglichene_posten": ausgeglichen,
        "nicht_zuordenbar": list(nicht_zuordenbar or []),
    }
