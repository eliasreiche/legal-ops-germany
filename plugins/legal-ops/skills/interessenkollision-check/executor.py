#!/usr/bin/env python3
"""interessenkollision-check — deterministischer Matching-Executor (P2/P3).

Vergleicht neue Mandats-Parteien gegen die Mandanten-/Gegnerliste der Kanzlei
und ordnet jedes geprüfte Paar (neue Partei × Listeneintrag) einer von vier
deterministischen Match-Stufen zu:

    S1  exakter Treffer nach Normalisierung             -> stufe "treffer"
    S2  Token-Mengen-Gleichheit bzw. -Teilmenge          -> stufe "treffer"
        nach Normalisierung (Wortreihenfolge unerheblich)
    S3  Kölner Phonetik je Token identisch               -> stufe "moeglicher_treffer"
        (primär Personennamen: Meyer/Maier/Mayr, Schmidt/Schmitt)
    S4  Fuzzy-Ratio >= --schwelle-moeglich                -> stufe "moeglicher_treffer"

Alles darunter ist `kein_treffer` — erscheint NICHT als Kandidat im Report,
nur als Anzahl in der Zusammenfassung. Die Stufen werden in der Reihenfolge
S1 -> S2 -> S3 -> S4 geprüft; die erste zutreffende Stufe gewinnt (kein
Paar wird doppelt gezählt).

WICHTIG (Deterministik-Grenze, P3): Dieses Modul entscheidet Stufe und
Score. Ein Modell (Claude) präsentiert den Report als Markdown-Tabelle und
weist bei `moeglicher_treffer` sowie bei Treffern mit Gegner-Rolle auf die
anwaltliche Kollisionsentscheidung hin (§ 43a Abs. 4 BRAO, § 3 BORA) — es
vergibt selbst nie eine Stufe oder einen Score.

## Schwellenwert --schwelle-moeglich (Default 0.85)

0.85 ist ein bewusst hoch angesetzter Kompromiss zwischen Rückruf (Tipp-
fehler/OCR-Varianten wie "Mustermann" vs. "Mustremann" noch erkennen) und
Präzision (kurze oder häufige Namensbestandteile nicht reihenweise als
möglicher Treffer melden, siehe False-Positive-Tests in tests/). Ein
niedrigerer Wert erhöht den Rückruf, aber auch die Zahl der von Hand zu
prüfenden möglichen Treffer — die Schwelle ist deshalb per CLI überschreibbar
statt fest verdrahtet.

## Datei-Kontrakt (P2)

Vollständig dokumentiert in schema/README.md. Kurzfassung:

    --liste       Mandanten-/Gegnerliste, CSV (`;`-getrennt, UTF-8, BOM
                  toleriert), Pflichtspalten name;rolle;typ, optional az;notiz.
    --parteien    Neue Parteien, CSV (gleicher Kontrakt, nur `name` Pflicht)
                  oder JSON (Liste von Objekten mit mindestens `name`).
    --output      Zieldatei für den JSON-Report (Default: stdout).

Keine Persistierung durch den Executor: Beide Eingabedateien werden nur
gelesen, nie kopiert oder verändert; es findet kein Netzwerkzugriff statt.

CLI:
    python3 executor.py --liste LISTE.csv --parteien PARTEIEN.csv|.json
                        [--output REPORT.json] [--schwelle-moeglich 0.85]

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler (kein Traceback).
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path
from typing import Any

# Plugin-Wurzel: skills/<skill>/executor.py -> <plugin>/core.
_CORE = Path(__file__).resolve().parents[2] / "core"
sys.path[:0] = [str(p) for p in (_CORE, _CORE / "calc", _CORE / "adapters")
                if str(p) not in sys.path]

from cli import CliFehler, schreibe_report  # noqa: E402
from matching import (  # noqa: E402
    STUFE_MOEGLICH,
    STUFE_TREFFER,
    NamensTreffer,
    vergleiche_namen,
)
from parteien import Partei  # noqa: E402
from parteien import lese_parteien_csv as _lese_parteien_csv  # noqa: E402

SCHWELLE_MOEGLICH_DEFAULT = 0.85

ROLLEN = {"mandant", "gegner", "sonstige"}
TYPEN = {"natuerlich", "juristisch"}

LISTE_PFLICHTSPALTEN = ("name", "rolle", "typ")


class EingabeFehler(Exception):
    """Strukturell ungültige Eingabedatei — CLI fängt sie sauber ab (Exit 2)."""


# Der Kandidat dieses Reports ist genau das Ergebnis des Namensvergleichs
# (regel/stufe/score/begruendung) — kein eigener Typ nötig.
Kandidat = NamensTreffer

lese_parteien_csv = functools.partial(_lese_parteien_csv, fehler=EingabeFehler)


# --------------------------------------------------------------------------
# CSV/JSON-Einlesen
# --------------------------------------------------------------------------

def _pruefe_rolle(rolle: str, pfad: Path, ort: str, pflicht: bool) -> str | None:
    if not rolle:
        if pflicht:
            raise EingabeFehler(f"{pfad}, {ort}: Pflichtfeld 'rolle' fehlt oder ist leer")
        return None
    if rolle not in ROLLEN:
        raise EingabeFehler(
            f"{pfad}, {ort}: 'rolle' muss einer von {sorted(ROLLEN)} sein, ist: '{rolle}'")
    return rolle


def _pruefe_typ(typ: str, pfad: Path, ort: str, pflicht: bool) -> str | None:
    if not typ:
        if pflicht:
            raise EingabeFehler(f"{pfad}, {ort}: Pflichtfeld 'typ' fehlt oder ist leer")
        return None
    if typ not in TYPEN:
        raise EingabeFehler(
            f"{pfad}, {ort}: 'typ' muss einer von {sorted(TYPEN)} sein, ist: '{typ}'")
    return typ


def _zusatzfelder(pfad: Path, pflicht: bool):
    """Callback für `core/calc/parteien`: rolle/typ validieren, az/notiz roh."""
    def felder(zeile: dict[str, str], ort: str) -> dict[str, Any]:
        return {
            "rolle": _pruefe_rolle(zeile.get("rolle", ""), pfad, ort, pflicht),
            "typ": _pruefe_typ(zeile.get("typ", ""), pfad, ort, pflicht),
            "az": zeile.get("az") or None,
            "notiz": zeile.get("notiz") or None,
        }
    return felder


def lese_mandantenliste(pfad: Path) -> list[Partei]:
    """Mandanten-/Gegnerliste: name;rolle;typ Pflicht, az;notiz optional."""
    return lese_parteien_csv(pfad, zusatz=_zusatzfelder(pfad, pflicht=True),
                             pflichtspalten=LISTE_PFLICHTSPALTEN)


def lese_neue_parteien_csv(pfad: Path) -> list[Partei]:
    """Neue Parteien als CSV: nur 'name' Pflicht, rolle/typ/az/notiz optional."""
    return lese_parteien_csv(pfad, zusatz=_zusatzfelder(pfad, pflicht=False))


def lese_neue_parteien_json(pfad: Path) -> list[Partei]:
    """Neue Parteien als JSON: Liste von Objekten mit mindestens 'name'."""
    try:
        text = pfad.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EingabeFehler(f"{pfad}: keine gültige UTF-8-Datei ({exc})") from exc
    try:
        daten = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EingabeFehler(f"{pfad}: kein gültiges JSON: {exc}") from exc
    if not isinstance(daten, list):
        raise EingabeFehler(f"{pfad}: JSON muss eine Liste von Partei-Objekten sein")
    parteien: list[Partei] = []
    for i, eintrag in enumerate(daten, start=1):
        ort = f"Eintrag {i}"
        if not isinstance(eintrag, dict):
            raise EingabeFehler(f"{pfad}, {ort}: kein JSON-Objekt")
        name = str(eintrag.get("name") or "").strip()
        if not name:
            raise EingabeFehler(f"{pfad}, {ort}: Pflichtfeld 'name' fehlt oder ist leer")
        roh_rolle = eintrag.get("rolle")
        rolle = _pruefe_rolle(str(roh_rolle).strip() if roh_rolle else "", pfad, ort, pflicht=False)
        roh_typ = eintrag.get("typ")
        typ = _pruefe_typ(str(roh_typ).strip() if roh_typ else "", pfad, ort, pflicht=False)
        roh_az = eintrag.get("az")
        az = str(roh_az).strip() or None if roh_az else None
        roh_notiz = eintrag.get("notiz")
        notiz = str(roh_notiz).strip() or None if roh_notiz else None
        parteien.append(Partei(name=name, rolle=rolle, typ=typ, az=az, notiz=notiz))
    if not parteien:
        raise EingabeFehler(f"{pfad}: leere Liste — keine Parteien zu prüfen")
    return parteien


def lese_neue_parteien(pfad: Path) -> list[Partei]:
    suffix = pfad.suffix.lower()
    if suffix == ".csv":
        return lese_neue_parteien_csv(pfad)
    if suffix == ".json":
        return lese_neue_parteien_json(pfad)
    raise EingabeFehler(
        f"{pfad}: nicht unterstützte Dateiendung '{suffix}' — nur .csv oder .json")


# --------------------------------------------------------------------------
# Match-Stufen S1-S4 (Kaskade in core/calc/matching, geteilt mit gwg-live-screening)
# --------------------------------------------------------------------------

def vergleiche(neue_partei: Partei, listeneintrag: Partei, schwelle: float) -> Kandidat | None:
    """Prüft ein Paar gegen S1->S2->S3->S4; die erste zutreffende Stufe gewinnt."""
    return vergleiche_namen(neue_partei.name, listeneintrag.name, schwelle)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def _partei_dict(p: Partei) -> dict[str, Any]:
    return {"name": p.name, "rolle": p.rolle, "typ": p.typ}


def baue_report(neue_parteien: list[Partei], liste: list[Partei], schwelle: float,
                 liste_datei: str, parteien_datei: str) -> dict[str, Any]:
    kandidaten: list[dict[str, Any]] = []
    anzahl_treffer = 0
    anzahl_moeglich = 0
    geprueft = 0

    for neue in neue_parteien:
        for eintrag in liste:
            geprueft += 1
            kandidat = vergleiche(neue, eintrag, schwelle)
            if kandidat is None:
                continue
            if kandidat.stufe == STUFE_TREFFER:
                anzahl_treffer += 1
            else:
                anzahl_moeglich += 1
            eintrag_dict = _partei_dict(eintrag)
            eintrag_dict["az"] = eintrag.az
            kandidaten.append({
                "neue_partei": _partei_dict(neue),
                "listeneintrag": eintrag_dict,
                "regel": kandidat.regel,
                "stufe": kandidat.stufe,
                "score": kandidat.score,
                "begruendung": kandidat.begruendung,
            })

    kandidaten.sort(key=lambda k: (
        0 if k["stufe"] == STUFE_TREFFER else 1,
        -k["score"],
        k["neue_partei"]["name"],
        k["listeneintrag"]["name"],
    ))

    return {
        "meta": {
            "liste_datei": liste_datei,
            "parteien_datei": parteien_datei,
            "erzeugt_von": "interessenkollision-check/executor.py",
            "schwelle_moeglich": schwelle,
        },
        "kandidaten": kandidaten,
        "zusammenfassung": {
            "anzahl_neue_parteien": len(neue_parteien),
            "anzahl_listeneintraege": len(liste),
            "anzahl_geprueft_paare": geprueft,
            "anzahl_treffer": anzahl_treffer,
            "anzahl_moegliche_treffer": anzahl_moeglich,
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--liste", required=True,
                        help="Mandanten-/Gegnerliste (CSV, ';'-getrennt)")
    parser.add_argument("--parteien", required=True,
                        help="Neue Parteien (CSV oder JSON)")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    parser.add_argument("--schwelle-moeglich", type=float, default=SCHWELLE_MOEGLICH_DEFAULT,
                        help=f"Fuzzy-Schwelle für Stufe S4 (Default {SCHWELLE_MOEGLICH_DEFAULT})")
    args = parser.parse_args(argv)

    liste_pfad = Path(args.liste)
    parteien_pfad = Path(args.parteien)

    if not liste_pfad.is_file():
        print(f"Fehler: Mandanten-/Gegnerliste nicht gefunden: {liste_pfad}", file=sys.stderr)
        return 2
    if not parteien_pfad.is_file():
        print(f"Fehler: Parteien-Datei nicht gefunden: {parteien_pfad}", file=sys.stderr)
        return 2
    if not (0.0 <= args.schwelle_moeglich <= 1.0):
        print(f"Fehler: --schwelle-moeglich muss zwischen 0.0 und 1.0 liegen, "
              f"ist: {args.schwelle_moeglich}", file=sys.stderr)
        return 2

    try:
        liste = lese_mandantenliste(liste_pfad)
        neue_parteien = lese_neue_parteien(parteien_pfad)
    except EingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    report = baue_report(neue_parteien, liste, args.schwelle_moeglich,
                          liste_datei=str(liste_pfad), parteien_datei=str(parteien_pfad))

    try:
        schreibe_report(report, args.output)
    except CliFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
