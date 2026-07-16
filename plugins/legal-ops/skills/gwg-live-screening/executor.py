#!/usr/bin/env python3
"""gwg-live-screening — deterministischer Screening-Executor (P2/P3).

Screent Parteinamen gegen lokale EU-/UN-Sanktionslisten und schreibt einen
Dokumentations-Report (Treffer, mögliche Treffer UND Nicht-Treffer — die
negative clearance ist der Hauptzweck der GwG-Dokumentation). Kein Live-HTTP
(P3-Deterministik): der Abruf ist getrennt in
`core/adapters/sanktionslisten/abruf.py`.

## Datei-Kontrakt (P2), vollständig in schema/README.md

    --parteien           Zu prüfende Parteien. CSV (Pflichtspalte `name`,
                         optional `typ`) oder JSON (Liste von Objekten mit
                         mindestens `name`, oder Liste von Namens-Strings).
    --listen-verzeichnis Verzeichnis mit den lokalen Listen-Dateien (*.xml)
                         UND einer `abruf-meta.json` (Dateiname → {url,
                         abgerufen_am}), wie sie abruf.py schreibt.
    --output             Zieldatei für den JSON-Report (Default: stdout).
    --schwelle-moeglich  Fuzzy-Schwelle Stufe S4 (Default 0.80, siehe unten).
    --heute              Bezugsdatum JJJJ-MM-TT für das Frische-Gate
                         (Default: heute; nur für deterministische Tests).

## Frische-Gate (D19-Muster, verbindlich)

Je Liste MUSS ausgewiesen sein: das XML-Generierungsdatum (aus der Liste) UND
`abgerufen_am` (aus abruf-meta.json). Fehlt eines → harter Fehler (Exit 3),
KEIN Report — ein Screening gegen eine undatierte Liste ist wertlos. Ist eine
Liste älter als WARN_ALTER_TAGE (7) Tage, trägt der Report eine Warnung
(Sanktionslisten ändern sich kurzfristig).

## Schwelle --schwelle-moeglich (Default 0.80)

Bewusst NIEDRIGER als die 0.85 des interessenkollision-check: beim
Sanktions-Screening ist ein übersehener echter Treffer (falsch-negativ)
teurer als eine zusätzliche händisch zu prüfende Meldung (falsch-positiv).
Die Schwelle ist deshalb konservativ (rückruf-orientiert) gewählt und per CLI
überschreibbar statt fest verdrahtet.

## Deterministik-Grenze (P3)

Stufe und Score jedes Paars entscheidet dieser Executor über die
wiederverwendbare Bibliothek core/calc/matching — nie das Modell. Claude
liest nur den Report und übernimmt Werte unverändert; Maßnahmen bei Treffern
(z. B. Verdachtsmeldung § 43 GwG, Bereitstellungsverbot) entscheidet der
Verpflichtete.

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler, 3 = Frische-Gate verletzt.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# core/calc auf den Importpfad legen (matching-Bibliothek) und core/adapters
# für den Sanktionslisten-Parser. Self-relativ: skill -> skills -> plugin-root.
_SKILL_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SKILL_DIR.parents[1]
for _p in (_PLUGIN_ROOT / "core" / "calc", _PLUGIN_ROOT / "core" / "adapters"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from matching import (  # noqa: E402
    koelner_code,
    normalisiere,
    sequenz_ratio,
    token_alignment_ratio,
    tokenisiere,
)
from sanktionslisten import (  # noqa: E402
    ParserFehler,
    Sanktionsliste,
    SanktionsEintrag,
    parse_datei,
)

SCHWELLE_MOEGLICH_DEFAULT = 0.80
WARN_ALTER_TAGE = 7

STUFE_TREFFER = "treffer"
STUFE_MOEGLICH = "moeglicher_treffer"
STUFE_KEIN = "kein_treffer"


class EingabeFehler(Exception):
    """Strukturell ungültige Eingabe — CLI fängt sie sauber ab (Exit 2)."""


class FrischeFehler(Exception):
    """Frische-Gate verletzt (fehlendes Datum) — Exit 3, kein Report."""


@dataclass
class Partei:
    name: str
    typ: str | None = None


@dataclass
class Kandidat:
    regel: str      # "S1" | "S2" | "S3" | "S4"
    stufe: str      # treffer | moeglicher_treffer
    score: float
    begruendung: str


# --------------------------------------------------------------------------
# Parteien einlesen (CSV oder JSON)
# --------------------------------------------------------------------------

def _lese_parteien_csv(pfad: Path) -> list[Partei]:
    try:
        text = pfad.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EingabeFehler(f"{pfad}: keine gültige UTF-8-Datei ({exc})") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    if "name" not in fieldnames:
        raise EingabeFehler(
            f"{pfad}: Pflichtspalte 'name' fehlt (vorhanden: {', '.join(fieldnames)})")
    parteien: list[Partei] = []
    for i, zeile in enumerate(reader, start=2):
        werte = {(h or "").strip(): (v or "").strip() if v is not None else ""
                 for h, v in zeile.items()}
        name = werte.get("name", "")
        if not name:
            raise EingabeFehler(f"{pfad}, Zeile {i}: Pflichtfeld 'name' fehlt oder ist leer")
        parteien.append(Partei(name=name, typ=werte.get("typ") or None))
    if not parteien:
        raise EingabeFehler(f"{pfad}: keine Einträge (nur Kopfzeile)")
    return parteien


def _lese_parteien_json(pfad: Path) -> list[Partei]:
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EingabeFehler(f"{pfad}: kein gültiges JSON/UTF-8: {exc}") from exc
    if not isinstance(daten, list):
        raise EingabeFehler(f"{pfad}: JSON muss eine Liste sein")
    parteien: list[Partei] = []
    for i, eintrag in enumerate(daten, start=1):
        if isinstance(eintrag, str):
            name, typ = eintrag.strip(), None
        elif isinstance(eintrag, dict):
            name = str(eintrag.get("name") or "").strip()
            roh_typ = eintrag.get("typ")
            typ = str(roh_typ).strip() or None if roh_typ else None
        else:
            raise EingabeFehler(f"{pfad}, Eintrag {i}: weder String noch Objekt")
        if not name:
            raise EingabeFehler(f"{pfad}, Eintrag {i}: Pflichtfeld 'name' fehlt oder ist leer")
        parteien.append(Partei(name=name, typ=typ))
    if not parteien:
        raise EingabeFehler(f"{pfad}: leere Liste — keine Parteien zu prüfen")
    return parteien


def lese_parteien(pfad: Path) -> list[Partei]:
    suffix = pfad.suffix.lower()
    if suffix == ".csv":
        return _lese_parteien_csv(pfad)
    if suffix == ".json":
        return _lese_parteien_json(pfad)
    raise EingabeFehler(
        f"{pfad}: nicht unterstützte Dateiendung '{suffix}' — nur .csv oder .json")


# --------------------------------------------------------------------------
# Listen-Verzeichnis laden + Frische-Gate
# --------------------------------------------------------------------------

@dataclass
class GeladeneListe:
    datei: str
    liste: Sanktionsliste
    generierungsdatum: str
    abgerufen_am: str
    alter_tage: int
    warnung: bool


def _parse_iso(datum: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(datum[:10])
    except (ValueError, TypeError):
        return None


def lade_listen_verzeichnis(pfad: Path, heute: _dt.date) -> list[GeladeneListe]:
    if not pfad.is_dir():
        raise EingabeFehler(f"--listen-verzeichnis ist kein Verzeichnis: {pfad}")
    meta_pfad = pfad / "abruf-meta.json"
    if not meta_pfad.is_file():
        raise FrischeFehler(
            f"{pfad}: abruf-meta.json fehlt — ohne Abrufdatum kein Screening "
            f"(Frische-Gate). Erst core/adapters/sanktionslisten/abruf.py laufen lassen.")
    try:
        meta = json.loads(meta_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EingabeFehler(f"{meta_pfad}: kein gültiges JSON: {exc}") from exc
    if not isinstance(meta, dict):
        raise EingabeFehler(f"{meta_pfad}: muss ein JSON-Objekt sein")

    xml_dateien = sorted(p for p in pfad.glob("*.xml") if p.is_file())
    if not xml_dateien:
        raise EingabeFehler(f"{pfad}: keine *.xml-Listen-Datei gefunden")

    geladen: list[GeladeneListe] = []
    for datei in xml_dateien:
        try:
            liste = parse_datei(datei)
        except ParserFehler as exc:
            raise EingabeFehler(f"{datei.name}: {exc}") from exc

        eintrag_meta = meta.get(datei.name)
        abgerufen_am = (eintrag_meta.get("abgerufen_am")
                        if isinstance(eintrag_meta, dict) else None)

        # Frische-Gate: beide Daten Pflicht, sonst harter Fehler (kein Report).
        if not liste.generierungsdatum:
            raise FrischeFehler(
                f"{datei.name}: XML-Generierungsdatum fehlt/unlesbar — "
                f"Frische-Gate: kein Report.")
        if not abgerufen_am:
            raise FrischeFehler(
                f"{datei.name}: `abgerufen_am` fehlt in abruf-meta.json — "
                f"Frische-Gate: kein Report.")

        ref = _parse_iso(abgerufen_am)
        if ref is None:
            raise FrischeFehler(
                f"{datei.name}: `abgerufen_am` ('{abgerufen_am}') ist kein "
                f"JJJJ-MM-TT-Datum — Frische-Gate: kein Report.")
        alter_tage = (heute - ref).days
        geladen.append(GeladeneListe(
            datei=datei.name,
            liste=liste,
            generierungsdatum=liste.generierungsdatum,
            abgerufen_am=abgerufen_am,
            alter_tage=alter_tage,
            warnung=alter_tage > WARN_ALTER_TAGE,
        ))
    return geladen


# --------------------------------------------------------------------------
# Match-Stufen S1-S4 (analog interessenkollision-check, über core/calc/matching)
# --------------------------------------------------------------------------

def _vergleiche(name_a: str, name_b: str, schwelle: float) -> Kandidat | None:
    """Erste greifende Stufe S1->S2->S3->S4 gewinnt (sonst None = kein_treffer)."""
    norm_a, norm_b = normalisiere(name_a), normalisiere(name_b)
    tokens_a, tokens_b = tokenisiere(name_a), tokenisiere(name_b)

    # S1 exakt nach Normalisierung
    if norm_a and norm_b and norm_a == norm_b:
        return Kandidat("S1", STUFE_TREFFER, 1.0,
                        f"exakter Treffer nach Normalisierung: '{norm_a}' = '{norm_b}'")
    # S2 Token-Mengen-Gleichheit / -Teilmenge
    menge_a, menge_b = set(tokens_a), set(tokens_b)
    if menge_a and menge_b:
        if menge_a == menge_b:
            return Kandidat("S2", STUFE_TREFFER, 1.0,
                            "Token-Mengen-Gleichheit nach Normalisierung "
                            f"(Wortreihenfolge unerheblich): {{{', '.join(sorted(menge_a))}}}")
        if menge_a <= menge_b or menge_b <= menge_a:
            kleiner, groesser = ((menge_a, menge_b) if len(menge_a) <= len(menge_b)
                                 else (menge_b, menge_a))
            score = round(len(kleiner) / len(groesser), 4)
            return Kandidat("S2", STUFE_TREFFER, score,
                            f"Token-Teilmenge: {{{', '.join(sorted(kleiner))}}} "
                            f"⊆ {{{', '.join(sorted(groesser))}}}")
    # S3 Kölner Phonetik je Token identisch
    if tokens_a and len(tokens_a) == len(tokens_b):
        codes_a = sorted(koelner_code(t) for t in tokens_a)
        codes_b = sorted(koelner_code(t) for t in tokens_b)
        if all(codes_a) and all(codes_b) and codes_a == codes_b:
            if len(codes_a) == 1:
                begr = f"phonetisch identisch nach Kölner Phonetik: {codes_a[0]} = {codes_b[0]}"
            else:
                begr = ("phonetisch identisch nach Kölner Phonetik je Token: "
                        f"[{', '.join(codes_a)}] = [{', '.join(codes_b)}]")
            return Kandidat("S3", STUFE_MOEGLICH, 1.0, begr)
    # S4 Fuzzy-Ratio >= Schwelle
    score = max(sequenz_ratio(norm_a, norm_b), token_alignment_ratio(tokens_a, tokens_b))
    if score >= schwelle:
        return Kandidat("S4", STUFE_MOEGLICH, round(score, 4),
                        f"Ähnlichkeit {score:.2f} ≥ Schwelle {schwelle:.2f}")
    return None


def _bester_kandidat_gegen_eintrag(
        partei: Partei, eintrag: SanktionsEintrag, schwelle: float
) -> dict[str, Any] | None:
    """Prüft die Partei gegen Primärname UND alle Aliase; stärkste Stufe gewinnt."""
    rang = {"S1": 4, "S2": 3, "S3": 2, "S4": 1}
    bestes: tuple[int, dict[str, Any]] | None = None
    for feld, gelisteter_name in [("primaername", eintrag.primaername),
                                  *[("alias", a) for a in eintrag.aliase]]:
        kandidat = _vergleiche(partei.name, gelisteter_name, schwelle)
        if kandidat is None:
            continue
        gewicht = rang[kandidat.regel]
        if bestes is None or gewicht > bestes[0]:
            bestes = (gewicht, {
                "gelisteter_name": gelisteter_name,
                "namensfeld": feld,
                "regel": kandidat.regel,
                "stufe": kandidat.stufe,
                "score": kandidat.score,
                "begruendung": kandidat.begruendung,
            })
    return bestes[1] if bestes else None


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def baue_report(parteien: list[Partei], listen: list[GeladeneListe],
                schwelle: float, heute: _dt.date, parteien_datei: str,
                listen_verzeichnis: str) -> dict[str, Any]:
    parteien_ergebnisse: list[dict[str, Any]] = []
    gesamt_treffer = 0
    gesamt_moeglich = 0

    for partei in parteien:
        treffer: list[dict[str, Any]] = []
        for gl in listen:
            for eintrag in gl.liste.eintraege:
                match = _bester_kandidat_gegen_eintrag(partei, eintrag, schwelle)
                if match is None:
                    continue
                treffer.append({
                    "liste": gl.datei,
                    "quelle": eintrag.quelle,
                    "listen_referenz": eintrag.referenz,
                    "programm": eintrag.programm,
                    "eintrag_typ": eintrag.typ,
                    "geburtsdatum": eintrag.geburtsdatum,
                    **match,
                })
        treffer.sort(key=lambda t: (
            0 if t["stufe"] == STUFE_TREFFER else 1, -t["score"],
            t["quelle"], t["gelisteter_name"]))
        anz_t = sum(1 for t in treffer if t["stufe"] == STUFE_TREFFER)
        anz_m = len(treffer) - anz_t
        gesamt_treffer += anz_t
        gesamt_moeglich += anz_m
        parteien_ergebnisse.append({
            "partei": {"name": partei.name, "typ": partei.typ},
            "ergebnis": (STUFE_TREFFER if anz_t else
                         STUFE_MOEGLICH if anz_m else STUFE_KEIN),
            "anzahl_treffer": anz_t,
            "anzahl_moegliche_treffer": anz_m,
            "treffer": treffer,
        })

    return {
        "meta": {
            "erzeugt_von": "plugins/legal-ops/skills/gwg-live-screening/executor.py",
            "parteien_datei": parteien_datei,
            "listen_verzeichnis": listen_verzeichnis,
            "schwelle_moeglich": schwelle,
            "bezugsdatum": heute.isoformat(),
            "deterministik": ("Stufe/Score jedes Paars stammen aus dem Executor "
                              "(core/calc/matching), nicht vom Modell (P3)."),
            "hinweis_massnahmen": ("Treffer/mögliche Treffer sind Recherche-"
                                   "Kandidaten. Maßnahmen (z. B. Verdachtsmeldung "
                                   "§ 43 GwG, Bereitstellungsverbot) entscheidet "
                                   "der Verpflichtete."),
        },
        "listen_frische": [{
            "liste": gl.datei,
            "quelle": gl.liste.quelle,
            "generierungsdatum": gl.generierungsdatum,
            "abgerufen_am": gl.abgerufen_am,
            "alter_tage": gl.alter_tage,
            "warnung_veraltet": gl.warnung,
            "anzahl_eintraege": len(gl.liste.eintraege),
        } for gl in listen],
        "warnungen": [
            f"Liste {gl.datei} ist {gl.alter_tage} Tage alt (abgerufen_am "
            f"{gl.abgerufen_am}) — älter als {WARN_ALTER_TAGE} Tage; "
            f"Sanktionslisten ändern sich kurzfristig, bitte neu abrufen."
            for gl in listen if gl.warnung
        ],
        "parteien": parteien_ergebnisse,
        "zusammenfassung": {
            "anzahl_parteien": len(parteien),
            "anzahl_listen": len(listen),
            "anzahl_listeneintraege": sum(len(gl.liste.eintraege) for gl in listen),
            "parteien_mit_treffer": sum(1 for p in parteien_ergebnisse
                                        if p["ergebnis"] == STUFE_TREFFER),
            "parteien_mit_moeglichem_treffer": sum(1 for p in parteien_ergebnisse
                                                   if p["ergebnis"] == STUFE_MOEGLICH),
            "parteien_ohne_treffer": sum(1 for p in parteien_ergebnisse
                                         if p["ergebnis"] == STUFE_KEIN),
            "gesamt_treffer": gesamt_treffer,
            "gesamt_moegliche_treffer": gesamt_moeglich,
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parteien", required=True, help="Parteien (CSV oder JSON)")
    parser.add_argument("--listen-verzeichnis", required=True, dest="listen_verzeichnis",
                        help="Verzeichnis mit *.xml-Listen + abruf-meta.json")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    parser.add_argument("--schwelle-moeglich", type=float, default=SCHWELLE_MOEGLICH_DEFAULT,
                        help=f"Fuzzy-Schwelle Stufe S4 (Default {SCHWELLE_MOEGLICH_DEFAULT})")
    parser.add_argument("--heute", help="Bezugsdatum JJJJ-MM-TT fürs Frische-Gate "
                                        "(Default: heute; nur für Tests)")
    args = parser.parse_args(argv)

    parteien_pfad = Path(args.parteien)
    listen_pfad = Path(args.listen_verzeichnis)

    if not parteien_pfad.is_file():
        print(f"Fehler: Parteien-Datei nicht gefunden: {parteien_pfad}", file=sys.stderr)
        return 2
    if not (0.0 <= args.schwelle_moeglich <= 1.0):
        print(f"Fehler: --schwelle-moeglich muss zwischen 0.0 und 1.0 liegen, "
              f"ist: {args.schwelle_moeglich}", file=sys.stderr)
        return 2
    if args.heute:
        heute = _parse_iso(args.heute)
        if heute is None:
            print(f"Fehler: --heute ('{args.heute}') ist kein JJJJ-MM-TT-Datum",
                  file=sys.stderr)
            return 2
    else:
        heute = _dt.date.today()

    try:
        parteien = lese_parteien(parteien_pfad)
        listen = lade_listen_verzeichnis(listen_pfad, heute)
    except FrischeFehler as exc:
        print(f"Frische-Gate: {exc}", file=sys.stderr)
        return 3
    except EingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    report = baue_report(parteien, listen, args.schwelle_moeglich, heute,
                         parteien_datei=str(parteien_pfad),
                         listen_verzeichnis=str(listen_pfad))

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
    else:
        print(ausgabe)
    if report["warnungen"]:
        for w in report["warnungen"]:
            print(f"Warnung: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
