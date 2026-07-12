#!/usr/bin/env python3
"""konflikt-check-offline — deterministischer Matching-Executor (P2/P3).

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
import csv
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SKILL_DIR = Path(__file__).resolve().parent
_CALC_DIR = _SKILL_DIR.parents[3] / "core" / "calc"
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from matching import (  # noqa: E402
    koelner_code,
    normalisiere,
    sequenz_ratio,
    token_alignment_ratio,
    tokenisiere,
)

SCHWELLE_MOEGLICH_DEFAULT = 0.85

STUFE_TREFFER = "treffer"
STUFE_MOEGLICH = "moeglicher_treffer"

ROLLEN = {"mandant", "gegner", "sonstige"}
TYPEN = {"natuerlich", "juristisch"}

LISTE_PFLICHTSPALTEN = ("name", "rolle", "typ")


class EingabeFehler(Exception):
    """Strukturell ungültige Eingabedatei — CLI fängt sie sauber ab (Exit 2)."""


@dataclass
class Partei:
    name: str
    rolle: str | None = None
    typ: str | None = None
    az: str | None = None
    notiz: str | None = None


@dataclass
class Kandidat:
    regel: str      # "S1" | "S2" | "S3" | "S4"
    stufe: str      # "treffer" | "moeglicher_treffer"
    score: float
    begruendung: str


# --------------------------------------------------------------------------
# CSV/JSON-Einlesen
# --------------------------------------------------------------------------

def _lese_csv_zeilen(pfad: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = pfad.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EingabeFehler(f"{pfad}: keine gültige UTF-8-Datei ({exc})") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    if not fieldnames:
        raise EingabeFehler(f"{pfad}: CSV ist leer oder hat keine Kopfzeile")
    zeilen = [{(h or "").strip(): (v or "").strip() if v is not None else ""
               for h, v in zeile.items()} for zeile in reader]
    return fieldnames, zeilen


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


def lese_mandantenliste(pfad: Path) -> list[Partei]:
    """Mandanten-/Gegnerliste: name;rolle;typ Pflicht, az;notiz optional."""
    fieldnames, zeilen = _lese_csv_zeilen(pfad)
    fehlend = [s for s in LISTE_PFLICHTSPALTEN if s not in fieldnames]
    if fehlend:
        raise EingabeFehler(
            f"{pfad}: Pflichtspalte(n) fehlen: {', '.join(fehlend)} "
            f"(vorhanden: {', '.join(fieldnames)})")
    parteien: list[Partei] = []
    for i, zeile in enumerate(zeilen, start=2):  # Zeile 1 = Kopfzeile
        ort = f"Zeile {i}"
        name = zeile.get("name", "")
        if not name:
            raise EingabeFehler(f"{pfad}, {ort}: Pflichtfeld 'name' fehlt oder ist leer")
        rolle = _pruefe_rolle(zeile.get("rolle", ""), pfad, ort, pflicht=True)
        typ = _pruefe_typ(zeile.get("typ", ""), pfad, ort, pflicht=True)
        az = zeile.get("az") or None
        notiz = zeile.get("notiz") or None
        parteien.append(Partei(name=name, rolle=rolle, typ=typ, az=az, notiz=notiz))
    if not parteien:
        raise EingabeFehler(f"{pfad}: keine Einträge (nur Kopfzeile)")
    return parteien


def lese_neue_parteien_csv(pfad: Path) -> list[Partei]:
    """Neue Parteien als CSV: nur 'name' Pflicht, rolle/typ/az/notiz optional."""
    fieldnames, zeilen = _lese_csv_zeilen(pfad)
    if "name" not in fieldnames:
        raise EingabeFehler(
            f"{pfad}: Pflichtspalte 'name' fehlt (vorhanden: {', '.join(fieldnames)})")
    parteien: list[Partei] = []
    for i, zeile in enumerate(zeilen, start=2):
        ort = f"Zeile {i}"
        name = zeile.get("name", "")
        if not name:
            raise EingabeFehler(f"{pfad}, {ort}: Pflichtfeld 'name' fehlt oder ist leer")
        rolle = _pruefe_rolle(zeile.get("rolle", ""), pfad, ort, pflicht=False)
        typ = _pruefe_typ(zeile.get("typ", ""), pfad, ort, pflicht=False)
        az = zeile.get("az") or None
        notiz = zeile.get("notiz") or None
        parteien.append(Partei(name=name, rolle=rolle, typ=typ, az=az, notiz=notiz))
    if not parteien:
        raise EingabeFehler(f"{pfad}: keine Einträge (nur Kopfzeile)")
    return parteien


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
# Match-Stufen S1-S4
# --------------------------------------------------------------------------

def _s1_exakt(norm_a: str, norm_b: str) -> Kandidat | None:
    if norm_a and norm_b and norm_a == norm_b:
        return Kandidat("S1", STUFE_TREFFER, 1.0,
                         f"exakter Treffer nach Normalisierung: '{norm_a}' = '{norm_b}'")
    return None


def _s2_token_mengen(tokens_a: list[str], tokens_b: list[str]) -> Kandidat | None:
    menge_a, menge_b = set(tokens_a), set(tokens_b)
    if not menge_a or not menge_b:
        return None
    if menge_a == menge_b:
        anzeige = ", ".join(sorted(menge_a))
        return Kandidat("S2", STUFE_TREFFER, 1.0,
                         f"Token-Mengen-Gleichheit nach Normalisierung (Wortreihenfolge "
                         f"unerheblich): {{{anzeige}}}")
    if menge_a <= menge_b or menge_b <= menge_a:
        kleinere, groessere = (menge_a, menge_b) if len(menge_a) <= len(menge_b) else (menge_b, menge_a)
        score = round(len(kleinere) / len(groessere), 4)
        return Kandidat("S2", STUFE_TREFFER, score,
                         f"Token-Teilmenge nach Normalisierung: {{{', '.join(sorted(kleinere))}}} "
                         f"⊆ {{{', '.join(sorted(groessere))}}}")
    return None


def _s3_phonetik(tokens_a: list[str], tokens_b: list[str]) -> Kandidat | None:
    if not tokens_a or len(tokens_a) != len(tokens_b):
        return None
    codes_a = sorted(koelner_code(t) for t in tokens_a)
    codes_b = sorted(koelner_code(t) for t in tokens_b)
    if any(c == "" for c in codes_a) or any(c == "" for c in codes_b):
        return None
    if codes_a != codes_b:
        return None
    if len(codes_a) == 1:
        begruendung = f"phonetisch identisch nach Kölner Phonetik: {codes_a[0]} = {codes_b[0]}"
    else:
        begruendung = ("phonetisch identisch nach Kölner Phonetik je Token: "
                        f"[{', '.join(codes_a)}] = [{', '.join(codes_b)}]")
    return Kandidat("S3", STUFE_MOEGLICH, 1.0, begruendung)


def _s4_fuzzy(norm_a: str, norm_b: str, tokens_a: list[str], tokens_b: list[str],
              schwelle: float) -> Kandidat | None:
    score_zeichen = sequenz_ratio(norm_a, norm_b)
    score_token = token_alignment_ratio(tokens_a, tokens_b)
    score = max(score_zeichen, score_token)
    if score < schwelle:
        return None
    verfahren = "Zeichenketten-Vergleich" if score_zeichen >= score_token else "Token-Alignment"
    return Kandidat("S4", STUFE_MOEGLICH, round(score, 4),
                     f"Ähnlichkeit {score:.2f} ≥ Schwelle {schwelle:.2f} ({verfahren})")


def vergleiche(neue_partei: Partei, listeneintrag: Partei, schwelle: float) -> Kandidat | None:
    """Prüft ein Paar gegen S1->S2->S3->S4; die erste zutreffende Stufe gewinnt."""
    norm_a = normalisiere(neue_partei.name)
    norm_b = normalisiere(listeneintrag.name)
    tokens_a = tokenisiere(neue_partei.name)
    tokens_b = tokenisiere(listeneintrag.name)

    for pruefung in (
        lambda: _s1_exakt(norm_a, norm_b),
        lambda: _s2_token_mengen(tokens_a, tokens_b),
        lambda: _s3_phonetik(tokens_a, tokens_b),
        lambda: _s4_fuzzy(norm_a, norm_b, tokens_a, tokens_b, schwelle),
    ):
        kandidat = pruefung()
        if kandidat is not None:
            return kandidat
    return None


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
            "erzeugt_von": "konflikt-check-offline/executor.py",
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

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
    else:
        print(ausgabe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
