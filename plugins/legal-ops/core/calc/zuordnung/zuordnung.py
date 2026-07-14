"""zuordnung.zuordnung — Dokument-Metadaten -> Mandats-Kandidaten (P2/P3-Bibliothek).

Öffentliche Haupt-API von `core/calc/zuordnung/`, genutzt vom Skill
`email-akten-zuordnung/executor.py` und später (D-Vorgabe) vom Skill #14
`posteingang-ocr-verteilung` — deshalb bewusst klein gehaltene Signatur
(siehe `finde_kandidaten()`).

## Stufen-Übersicht

    Z0  eigenes Aktenzeichen wörtlich (nach Az-Normalisierung, siehe `az.py`)
        in Betreff **oder** Textauszug                          -> treffer
    Z1-Z4  Parteiname (`mandant`/`gegenseite`) gegen Betreff,
        Textauszug oder Absendername (siehe `parteisuche.py`)    -> treffer (Z1/Z2)
                                                                    moeglicher_treffer (Z3/Z4)

Z0 wird IMMER zuerst geprüft (sicherste Stufe) — findet sich das eigene
Az, wird kein Parteiname-Abgleich mehr für dieses Mandat durchgeführt
(Az-Treffer ist eindeutiger als jeder Namens-Treffer). Pro Mandat wird
höchstens EIN Kandidat erzeugt (die beste gefundene Stufe über Az,
`mandant` und `gegenseite`) — kein Mandat erscheint doppelt im Report.

Kein Kandidat für ein Mandat -> das Mandat erscheint nicht in
`kandidaten[]`. Eine leere `kandidaten`-Liste insgesamt bedeutet
`kein_treffer` — eine Lücke, die der Executor/Skill explizit als solche
ausweist (Anti-Halluzination: kein Mandat wird geraten).

Reine Funktionen, keine Persistierung, kein Netzwerkzugriff.
"""
from __future__ import annotations

from dataclasses import dataclass

from .az import az_gefunden_in_text
from .parteisuche import (
    STUFE_MOEGLICH,
    STUFE_TREFFER,
    SCHWELLE_MOEGLICH_DEFAULT,
    suche_name_in_text,
)

# Suchfelder für den Parteiname-Abgleich (Z1-Z4), in dieser Priorität, falls
# derselbe Name in mehreren Feldern zugleich träfe (siehe `_bester_treffer`).
# `absender_adresse` (E-Mail-Adresse) ist bewusst AUSGESCHLOSSEN: eine
# E-Mail-Adresse ist kein Namens-Fließtext, ein Treffer dort wäre Zufall
# (z. B. generische Domain-Bestandteile) statt eines echten Namens-Fundes.
FELD_REIHENFOLGE: tuple[str, ...] = ("betreff", "textauszug", "absender_name")
# Aktenzeichen-Suche (Z0) ist enger gefasst als der Parteiname-Abgleich:
# nur Betreff/Textauszug (Auftragsvorgabe) — ein Aktenzeichen im
# Absendernamen wäre ohnehin untypisch.
AZ_SUCHFELDER: tuple[str, ...] = ("betreff", "textauszug")

_STUFE_ORDNUNG = {"Z0": 0, "Z1": 1, "Z2": 2, "Z3": 3, "Z4": 4}


@dataclass
class Dokument:
    """Eingang für die Zuordnung — eine E-Mail (oder gleichwertige Metadaten)."""
    absender_name: str = ""
    absender_adresse: str = ""
    betreff: str = ""
    textauszug: str = ""


@dataclass
class Mandat:
    """Ein Eintrag der Mandatsliste (aus `core/context/schema.py:lese_mandate()`)."""
    az: str
    mandant: str = ""
    gegenseite: str | None = None
    datei: str | None = None  # Referenz für den Report (z. B. "mandate/2026-001.md")


@dataclass
class Kandidat:
    az: str
    stufe: str        # "Z0".."Z4"
    kategorie: str    # "treffer" | "moeglicher_treffer"
    score: float
    begruendung: str
    datei: str | None = None


def _bester_partei_treffer(name: str, dokument: Dokument,
                            schwelle: float) -> tuple[str, "object"] | None:
    """Sucht `name` über `FELD_REIHENFOLGE`, liefert (feldname, ParteiTreffer)
    der besten (niedrigsten Z-Stufe, bei Gleichstand höchstem Score)
    gefundenen Stelle, oder `None`, wenn keines der Felder trifft."""
    kandidaten: list[tuple[str, object]] = []
    for feldname in FELD_REIHENFOLGE:
        text = getattr(dokument, feldname, "")
        if not text:
            continue
        treffer = suche_name_in_text(name, text, schwelle)
        if treffer is not None:
            kandidaten.append((feldname, treffer))
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda kv: (_STUFE_ORDNUNG[kv[1].stufe], -kv[1].score))


def vergleiche_dokument_mandat(dokument: Dokument, mandat: Mandat,
                                schwelle: float = SCHWELLE_MOEGLICH_DEFAULT) -> Kandidat | None:
    """Prüft ein (Dokument, Mandat)-Paar: erst Z0 (Az), dann Z1-Z4 (mandant,
    dann gegenseite). Gibt höchstens einen `Kandidaten` zurück."""
    # Z0 — Aktenzeichen wörtlich in Betreff/Textauszug.
    for feldname in AZ_SUCHFELDER:
        text = getattr(dokument, feldname, "")
        if text and az_gefunden_in_text(mandat.az, text):
            return Kandidat(
                az=mandat.az, stufe="Z0", kategorie=STUFE_TREFFER, score=1.0,
                begruendung=f"Aktenzeichen '{mandat.az}' wörtlich (nach Whitespace-"
                            f"Normalisierung) im Feld '{feldname}' gefunden",
                datei=mandat.datei)

    # Z1-Z4 — Parteiname (mandant, dann gegenseite).
    ergebnisse: list[tuple[str, str, object]] = []  # (rolle, feldname, ParteiTreffer)
    if mandat.mandant:
        treffer = _bester_partei_treffer(mandat.mandant, dokument, schwelle)
        if treffer is not None:
            ergebnisse.append(("mandant", treffer[0], treffer[1]))
    if mandat.gegenseite:
        treffer = _bester_partei_treffer(mandat.gegenseite, dokument, schwelle)
        if treffer is not None:
            ergebnisse.append(("gegenseite", treffer[0], treffer[1]))

    if not ergebnisse:
        return None

    rolle, feldname, treffer = min(
        ergebnisse, key=lambda e: (_STUFE_ORDNUNG[e[2].stufe], -e[2].score, e[0]))
    name = mandat.mandant if rolle == "mandant" else mandat.gegenseite
    begruendung = (f"Partei '{name}' (Rolle: {rolle}) per Stufe {treffer.stufe} im "
                   f"Feld '{feldname}' gefunden: {treffer.begruendung}")
    return Kandidat(az=mandat.az, stufe=treffer.stufe, kategorie=treffer.kategorie,
                     score=treffer.score, begruendung=begruendung, datei=mandat.datei)


def finde_kandidaten(dokument: Dokument, mandate: list[Mandat],
                      schwelle_moeglich: float = SCHWELLE_MOEGLICH_DEFAULT) -> list[Kandidat]:
    """Vergleicht `dokument` gegen jedes Mandat in `mandate`, liefert die
    sortierte Kandidatenliste (treffer vor moeglicher_treffer, darin nach
    Stufe, dann absteigend nach Score, dann Az als Tie-Breaker).

    Eine leere Rückgabe ist `kein_treffer` — die aufrufende Stelle (Executor)
    weist das explizit als Lücke aus, statt ein Mandat zu raten."""
    kandidaten = [
        k for k in (vergleiche_dokument_mandat(dokument, m, schwelle_moeglich)
                    for m in mandate)
        if k is not None
    ]
    kandidaten.sort(key=lambda k: (
        0 if k.kategorie == STUFE_TREFFER else 1,
        _STUFE_ORDNUNG.get(k.stufe, 9),
        -k.score,
        k.az,
    ))
    return kandidaten
