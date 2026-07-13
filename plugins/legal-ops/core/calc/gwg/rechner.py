#!/usr/bin/env python3
"""gwg.rechner — regelbasiertes GwG-Risikoscoring (P3, deterministisch, offline).

Klassifiziert ein Mandat anhand der Katalogfaktoren der Anlagen 1 und 2 GwG in
einen Klassifikationsvorschlag. **Kein** numerisches Gewichts-Scoring, sondern
transparente Wenn-dann-Regeln — das Ergebnis ist ein nachvollziehbarer
Vorschlag, kein Verwaltungsakt. Die eigentliche Risikobewertung und die
Maßnahmenentscheidung trifft der Verpflichtete (risikobasierter Ansatz,
§ 10 Abs. 2 GwG).

Regelwerk (Reihenfolge ist bindend, erste greifende Regel entscheidet):

  0. Anwendbarkeits-Gate (§ 2 Abs. 1 Nr. 10 GwG): Rechtsanwälte sind nur bei
     bestimmten Kataloggeschäften Verpflichtete. Kein Kataloggeschäft
     -> `nicht_verpflichtet` (keine Risikoklasse). Unklar, ob ein
     Kataloggeschäft vorliegt -> `unvollstaendig`.
  1. Kritische Lücken (PEP-Status, Sitzland, wirtschaftlich Berechtigter):
     sind diese nicht belastbar beantwortet, wird NICHT klassifiziert
     -> `unvollstaendig`.
  2. PEP (§ 15 Abs. 3 Nr. 1 GwG) oder Hochrisiko-Drittstaat
     (§ 15 Abs. 3 Nr. 2 GwG, Anlage 2 Nr. 3 GwG) -> `hoch` (verstärkte
     Sorgfaltspflichten, § 15 GwG).
  3. Ausschließlich Anlage-1-Faktoren, kein Anlage-2-Faktor -> `niedrig`
     (vereinfachte Sorgfaltspflichten nach § 14 GwG *möglich* — Entscheidung
     beim Verpflichteten).
  4. Sonst -> `mittel` (allgemeine Sorgfaltspflichten, § 10 GwG).

Anti-Halluzination: Die Faktoren der Anlagen 1/2 GwG sind als PARAPHRASE mit
exakter Fundstelle in anlage1.json / anlage2.json hinterlegt (kein erfundener
Wortlaut). Jede Fundstelle im erzeugten Report trägt einen 3-Zustands-Marker
(hier stets ⚠️ „nicht prüfbar" — der Executor prüft nicht gegen den
Gesetzestext; die Prüfung übernimmt der abschließende zitat-pruefer-Lauf
bzw. die händische Abnahme gegen gesetze-im-internet.de).

Nur Standardbibliothek. Kein Netzwerkzugriff. JSON rein -> Report-Dict raus.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

_GWG_DIR = Path(__file__).resolve().parent

ANLAGE1_PFAD = _GWG_DIR / "anlage1.json"
ANLAGE2_PFAD = _GWG_DIR / "anlage2.json"
HOCHRISIKO_PFAD = _GWG_DIR / "hochrisiko_drittstaaten.json"

# Deutsche Kurzbezeichnungen der drei Länderlisten (für Report-Fließtext).
LISTEN_LABELS: dict[str, str] = {
    "eu-hochrisiko": "EU-Hochrisiko-Drittstaaten (Delegierte VO (EU) 2016/1675)",
    "fatf-blacklist": "FATF-Schwarzliste (High-Risk Jurisdictions subject to a "
                      "Call for Action)",
    "fatf-greylist": "FATF-Grauliste (Jurisdictions under Increased "
                     "Monitoring)",
}

# Länder mit zusätzlicher BaFin-Anzeigepflicht (Allgemeinverfügung vom
# 13.05.2020) — nur Nordkorea und Iran, nicht jeder Blacklist-Treffer.
_BAFIN_ALLGEMEINVERFUEGUNG_LAENDER = frozenset({"KP", "IR"})

# CI-Frische-Warnung (Aufgabe 3): FATF tagt ca. Februar/Juni/Oktober (drei
# Plena/Jahr) — eine Warnung ab 4 Monaten deckt ein verpasstes Plenum ab, ohne
# dass CI bei jedem Zwischenstand rot wird. Der harte Fehler erst ab 12
# Monaten erzwingt spätestens einen Jahres-Refresh, ohne bei planmäßiger
# Kadenz spontan zu failen.
FRISCHE_WARN_MONATE = 4
FRISCHE_FEHLER_MONATE = 12
_TAGE_PRO_MONAT = 30.44  # Durchschnitt (365.25 / 12), für grobe Monatsschätzung


def _heute() -> date:
    """Eigene Funktion (statt date.today() inline), damit Tests sie per
    monkeypatch überschreiben können, ohne die echte Systemzeit zu berühren."""
    return date.today()


def frische_status(hochrisiko: dict[str, Any], *,
                    heute: date | None = None) -> dict[str, Any]:
    """Bewertet das Alter von `abgerufen_am` der Hochrisiko-Länderliste.

    Liefert nur Fakten (warnung/fehler-Flags) zurück — kein Assert. Ruft
    kein Netzwerk auf; reiner Datumsvergleich. Der Aufrufer (CI-Test)
    entscheidet, ob `fehler` einen Test scheitern lässt."""
    heute = heute if heute is not None else _heute()
    roh = hochrisiko.get("abgerufen_am")
    try:
        abgerufen = datetime.strptime(str(roh), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"ok": False, "warnung": True, "fehler": True,
                "alter_tage": None,
                "hinweis": f"'abgerufen_am' fehlt oder ist ungültig: {roh!r}"}
    alter_tage = (heute - abgerufen).days
    alter_monate = alter_tage / _TAGE_PRO_MONAT
    warnung = alter_monate >= FRISCHE_WARN_MONATE
    fehler = alter_monate >= FRISCHE_FEHLER_MONATE
    return {
        "ok": not warnung,
        "warnung": warnung,
        "fehler": fehler,
        "alter_tage": alter_tage,
        "hinweis": (f"Hochrisiko-Länderliste zuletzt am {roh} abgerufen "
                    f"({alter_tage} Tage / ~{alter_monate:.1f} Monate) — "
                    f"Quartals-Review nach FATF-Plenum (Feb/Jun/Okt) "
                    f"empfohlen; Pflicht-Refresh ab 12 Monaten."),
    }

# 3-Zustands-Marker (CONVENTIONS.md): der Executor kann eine Fundstelle nicht
# gegen den Gesetzestext prüfen -> immer ⚠️ „nicht prüfbar".
MARKER_NICHT_PRUEFBAR = "⚠️"
MARKER_BEGRUENDUNG = (
    "Fundstelle stammt aus den Katalog-Daten dieses Skills und ist nicht gegen "
    "den Gesetzestext geprüft — im Skill-Ablauf durch zitat-pruefer gegen "
    "die Quellen-Registry und bei der händischen Abnahme gegen "
    "gesetze-im-internet.de zu verifizieren.")

# Klassifikationsvorschläge (abschließende Aufzählung).
KLASSIFIKATIONEN = (
    "nicht_verpflichtet", "unvollstaendig", "niedrig", "mittel", "hoch")

# § 2 Abs. 1 Nr. 10 GwG — Kataloggeschäfte, bei denen Rechtsanwälte
# Verpflichtete sind. Paraphrasen, keine Wortlaut-Zitate.
KATALOGGESCHAEFTE: dict[str, dict[str, str]] = {
    "immobilien_gewerbe_kauf": {
        "fundstelle": "§ 2 Abs. 1 Nr. 10 Buchst. a GwG",
        "paraphrase": "Mitwirkung an Kauf oder Verkauf von Immobilien oder "
                      "Gewerbebetrieben."},
    "vermoegensverwaltung": {
        "fundstelle": "§ 2 Abs. 1 Nr. 10 Buchst. b GwG",
        "paraphrase": "Verwaltung von Geld, Wertpapieren oder sonstigen "
                      "Vermögenswerten des Mandanten."},
    "konten_depot": {
        "fundstelle": "§ 2 Abs. 1 Nr. 10 Buchst. c GwG",
        "paraphrase": "Eröffnung oder Verwaltung von Bank-, Spar- oder "
                      "Wertpapierkonten bzw. Depots."},
    "gesellschaft_mittelbeschaffung": {
        "fundstelle": "§ 2 Abs. 1 Nr. 10 Buchst. d GwG",
        "paraphrase": "Beschaffung der zur Gründung, zum Betrieb oder zur "
                      "Verwaltung von Gesellschaften erforderlichen Mittel."},
    "treuhand_gesellschaft": {
        "fundstelle": "§ 2 Abs. 1 Nr. 10 Buchst. e GwG",
        "paraphrase": "Gründung, Betrieb oder Verwaltung von "
                      "Treuhandgesellschaften, Gesellschaften oder ähnlichen "
                      "Strukturen."},
    "finanz_immobilien_transaktion": {
        "fundstelle": "§ 2 Abs. 1 Nr. 10 GwG",
        "paraphrase": "Durchführung von Finanz- oder Immobilientransaktionen "
                      "im Namen und auf Rechnung des Mandanten."},
}

# EU-Mitgliedstaaten (ISO-3166-1 alpha-2), Stand der 27er-Union. Stabil, daher
# als Konstante; Anlage 1 Nr. 3 Buchst. a GwG (geringeres geografisches Risiko).
EU_MITGLIEDSTAATEN = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE"})

# Ja/Nein/Unklar-Felder des Fragebogens.
_JNU_FELDER = (
    "pep", "wirtschaftlich_berechtigter_geklaert", "bargeldintensiv",
    "komplexe_eigentumsstruktur", "distanzgeschaeft", "herkunft_der_mittel_klar",
    "boersennotiert_reguliert", "oeffentliche_stelle", "nominee_inhaberaktien",
    "private_vermoegensstruktur", "anonymitaets_produkt",
    "zahlung_unbekannte_dritte")
_JNU_WERTE = ("ja", "nein", "unklar")

# Alle zulässigen Fragebogen-Felder (Kontrakt). Jedes `fragebogen_feld` im
# Katalog muss hier enthalten sein (durch Test abgesichert).
FRAGEBOGEN_FELDER: frozenset[str] = frozenset(
    ("kataloggeschaeft", "mandant_typ", "sitz_land") + _JNU_FELDER)

# Kritische Felder — ohne belastbare Antwort keine Klassifikation.
KRITISCHE_FELDER = ("pep", "sitz_land", "wirtschaftlich_berechtigter_geklaert")

_MANDANT_TYPEN = ("natuerliche_person", "juristische_person", "trust_aehnlich",
                  "unklar")

# Klartext-Fragen je Feld für die Lücken-Ausweisung im Report.
_FRAGEN = {
    "kataloggeschaeft": "Liegt ein Kataloggeschäft nach § 2 Abs. 1 Nr. 10 GwG "
                        "vor und welches?",
    "mandant_typ": "Um welchen Mandantentyp handelt es sich (natürliche "
                   "Person / juristische Person / trust-ähnliche Struktur)?",
    "sitz_land": "In welchem Staat hat der Mandant seinen Sitz bzw. Wohnsitz "
                 "(ISO-3166-alpha-2)?",
    "pep": "Ist der Mandant oder wirtschaftlich Berechtigte eine politisch "
           "exponierte Person (PEP)?",
    "wirtschaftlich_berechtigter_geklaert":
        "Ist der wirtschaftlich Berechtigte abschließend geklärt "
        "(§ 10 Abs. 1 Nr. 2 GwG)?",
    "bargeldintensiv": "Handelt es sich um ein bargeldintensives Geschäft?",
    "komplexe_eigentumsstruktur": "Ist die Eigentums-/Beteiligungsstruktur "
                                  "ungewöhnlich oder übermäßig komplex?",
    "distanzgeschaeft": "Wurde die Geschäftsbeziehung ohne persönlichen "
                        "Kontakt begründet (Distanzgeschäft)?",
    "herkunft_der_mittel_klar": "Ist die Herkunft der eingesetzten Mittel "
                                "klar?",
    "boersennotiert_reguliert": "Ist der Mandant eine börsennotierte, "
                                "transparenzpflichtige Gesellschaft?",
    "oeffentliche_stelle": "Ist der Mandant eine öffentliche Verwaltung oder "
                           "ein öffentliches Unternehmen?",
    "nominee_inhaberaktien": "Bestehen nominelle Anteilseigner oder "
                             "Inhaberaktien?",
    "private_vermoegensstruktur": "Dient die Struktur der privaten "
                                  "Vermögensverwaltung?",
    "anonymitaets_produkt": "Sind anonymitätsbegünstigende Produkte/"
                            "Transaktionen betroffen?",
    "zahlung_unbekannte_dritte": "Gibt es Zahlungen von unbekannten oder nicht "
                                 "verbundenen Dritten?",
}


class GwGEingabeFehler(Exception):
    """Ungültige Mandats-Eingabe (unbekanntes Feld, unzulässiger Wert)."""


def lade_json(pfad: Path) -> dict[str, Any]:
    return json.loads(pfad.read_text(encoding="utf-8"))


def lade_kataloge() -> tuple[dict, dict, dict]:
    return (lade_json(ANLAGE1_PFAD), lade_json(ANLAGE2_PFAD),
            lade_json(HOCHRISIKO_PFAD))


def _marker_felder() -> dict[str, str]:
    return {"marker": MARKER_NICHT_PRUEFBAR,
            "marker_begruendung": MARKER_BEGRUENDUNG}


def _normalisiere(mandat: dict[str, Any]) -> dict[str, str]:
    """Prüft die Eingabe strikt und füllt fehlende Felder mit 'unklar' (nie
    raten). Unbekannte Felder sind ein Eingabefehler (Tippfehler-Diagnose)."""
    if not isinstance(mandat, dict):
        raise GwGEingabeFehler("Mandat muss ein JSON-Objekt sein")

    for feld in mandat:
        if feld not in FRAGEBOGEN_FELDER:
            raise GwGEingabeFehler(
                f"unbekanntes Feld: '{feld}' (zulässig: "
                f"{', '.join(sorted(FRAGEBOGEN_FELDER))})")

    norm: dict[str, str] = {}

    kg = mandat.get("kataloggeschaeft", "unklar")
    if kg is None or kg == "":
        kg = "unklar"
    zulaessig_kg = set(KATALOGGESCHAEFTE) | {"keins", "unklar"}
    if kg not in zulaessig_kg:
        raise GwGEingabeFehler(
            f"'kataloggeschaeft' hat unzulässigen Wert {kg!r} (zulässig: "
            f"{', '.join(sorted(zulaessig_kg))})")
    norm["kataloggeschaeft"] = kg

    mt = mandat.get("mandant_typ", "unklar")
    if mt is None or mt == "":
        mt = "unklar"
    if mt not in _MANDANT_TYPEN:
        raise GwGEingabeFehler(
            f"'mandant_typ' hat unzulässigen Wert {mt!r} (zulässig: "
            f"{', '.join(_MANDANT_TYPEN)})")
    norm["mandant_typ"] = mt

    land = mandat.get("sitz_land", "unklar")
    if land is None or land == "":
        land = "unklar"
    if not isinstance(land, str):
        raise GwGEingabeFehler("'sitz_land' muss ein String sein")
    if land != "unklar":
        land = land.strip().upper()
        if len(land) != 2 or not land.isalpha():
            raise GwGEingabeFehler(
                f"'sitz_land' muss ein ISO-3166-alpha-2-Code (zwei Buchstaben) "
                f"oder 'unklar' sein, nicht {mandat.get('sitz_land')!r}")
    norm["sitz_land"] = land

    for feld in _JNU_FELDER:
        wert = mandat.get(feld, "unklar")
        if wert is None or wert == "":
            wert = "unklar"
        if wert not in _JNU_WERTE:
            raise GwGEingabeFehler(
                f"'{feld}' muss 'ja', 'nein' oder 'unklar' sein, nicht "
                f"{wert!r}")
        norm[feld] = wert

    return norm


def _luecke(feld: str, kritisch: bool) -> dict[str, Any]:
    return {"feld": feld, "frage": _FRAGEN.get(feld, feld), "kritisch": kritisch}


def _faktor_eintrag(fk: dict[str, Any], anlage: int,
                    detail: str | None = None) -> dict[str, Any]:
    eintrag = {
        "id": fk["id"],
        "anlage": anlage,
        "fundstelle": fk["fundstelle"],
        "paraphrase": fk["paraphrase"],
        "kategorie": fk["kategorie"],
        "quelle": "executor",
        **_marker_felder(),
    }
    if detail:
        eintrag["detail"] = detail
    return eintrag


def _pflicht(norm: str, hinweis: str) -> dict[str, Any]:
    return {"norm": norm, "hinweis": hinweis, "quelle": "executor",
            **_marker_felder()}


def _stand_block(a1: dict, a2: dict, hr: dict) -> dict[str, Any]:
    return {
        "anlage1": a1.get("stand"),
        "anlage2": a2.get("stand"),
        "hochrisiko_drittstaaten": hr.get("stand"),
        "hochrisiko_abgerufen_am": hr.get("abgerufen_am"),
        "hinweis": ("Anlagen-Inhalte, Fundstellen und die drei Länderlisten "
                    "(EU-Hochrisiko, FATF-Schwarzliste, FATF-Grauliste) sind "
                    "vor produktiver Nutzung gegen gesetze-im-internet.de bzw. "
                    "die in `quellen` je Liste genannten aktuellen Quellen zu "
                    "prüfen (händische Abnahme, Reifegrad 'getestet')."),
    }


# Grund-Vorbehalt, der jeden Report begleitet.
_VORBEHALT_SCORING = (
    "Der Klassifikationsvorschlag ist ein regelbasierter Vorschlag, kein "
    "Verwaltungsakt-sicherer Nachweis. Die Risikobewertung und die "
    "Maßnahmenentscheidung trifft der Verpflichtete (risikobasierter Ansatz, "
    "§ 10 Abs. 2 GwG).")
_VORBEHALT_FUNDSTELLEN = (
    "Alle Norm-Fundstellen sind mit ⚠️ als nicht gegen den Gesetzestext "
    "geprüft gekennzeichnet; sie sind gegen die aktuelle Gesetzesfassung zu "
    "verifizieren.")


def _verdachtsmeldungs_hinweis() -> dict[str, Any]:
    return _pflicht(
        "§ 43 GwG",
        "Bei Tatsachen, die auf Geldwäsche/Terrorismusfinanzierung hindeuten, "
        "besteht grundsätzlich eine Verdachtsmeldepflicht an die FIU. Für "
        "Rechtsanwälte gilt die Ausnahme des § 43 Abs. 2 GwG (Erkenntnisse aus "
        "der Rechtsberatung/Prozessvertretung), soweit deren Voraussetzungen "
        "vorliegen — im Einzelfall anwaltlich zu prüfen.")


def klassifiziere(mandat: dict[str, Any], *,
                  anlage1: dict | None = None,
                  anlage2: dict | None = None,
                  hochrisiko: dict | None = None) -> dict[str, Any]:
    """Bewertet ein Mandat regelbasiert und liefert den Report-Rumpf (ohne
    `meta`). Alle Werte sind Executor-Ergebnisse (P3)."""
    if anlage1 is None or anlage2 is None or hochrisiko is None:
        _a1, _a2, _hr = lade_kataloge()
        anlage1 = anlage1 or _a1
        anlage2 = anlage2 or _a2
        hochrisiko = hochrisiko or _hr

    norm = _normalisiere(mandat)
    stand = _stand_block(anlage1, anlage2, hochrisiko)

    # --- Lücken erfassen (jede unbeantwortete Pflichtfrage) ---
    luecken: list[dict[str, Any]] = []
    kritische_luecke = False

    if norm["kataloggeschaeft"] == "unklar":
        luecken.append(_luecke("kataloggeschaeft", kritisch=True))
        kritische_luecke = True
    if norm["pep"] == "unklar":
        luecken.append(_luecke("pep", kritisch=True))
        kritische_luecke = True
    if norm["sitz_land"] == "unklar":
        luecken.append(_luecke("sitz_land", kritisch=True))
        kritische_luecke = True
    if norm["wirtschaftlich_berechtigter_geklaert"] != "ja":
        luecken.append(_luecke("wirtschaftlich_berechtigter_geklaert",
                               kritisch=True))
        kritische_luecke = True

    # nicht-kritische Lücken (unbeantwortete Ja/Nein-Fragen, Mandantentyp)
    if norm["mandant_typ"] == "unklar":
        luecken.append(_luecke("mandant_typ", kritisch=False))
    for feld in _JNU_FELDER:
        if feld in ("pep", "wirtschaftlich_berechtigter_geklaert"):
            continue  # oben bereits als kritisch behandelt
        if norm[feld] == "unklar":
            luecken.append(_luecke(feld, kritisch=False))

    def report(status_anwendbarkeit: str, klass: str, klass_begr: str,
               regel: str, *, kg_meta: dict[str, str] | None,
               faktoren: list[dict[str, Any]],
               pflichten: list[dict[str, Any]],
               vorbehalte: list[str],
               anwend_begr: str, anwend_vorbehalt: str | None,
               laender_listen_treffer: dict[str, Any] | None = None
               ) -> dict[str, Any]:
        anwendbarkeit = {
            "status": status_anwendbarkeit,
            "kataloggeschaeft": norm["kataloggeschaeft"],
            "begruendung": anwend_begr,
            "quelle": "executor",
        }
        if kg_meta is not None:
            anwendbarkeit["fundstelle"] = kg_meta["fundstelle"]
            anwendbarkeit["paraphrase"] = kg_meta["paraphrase"]
            anwendbarkeit.update(_marker_felder())
        else:
            anwendbarkeit["fundstelle"] = "§ 2 Abs. 1 Nr. 10 GwG"
            anwendbarkeit.update(_marker_felder())
        if anwend_vorbehalt:
            anwendbarkeit["vorbehalt"] = anwend_vorbehalt
        return {
            "eingabe_normalisiert": norm,
            "anwendbarkeit": anwendbarkeit,
            "klassifikationsvorschlag": klass,
            "klassifikation_begruendung": klass_begr,
            "regel_angewendet": regel,
            "angewandte_faktoren": faktoren,
            "pflichten_hinweise": pflichten,
            "luecken": luecken,
            "vorbehalte": vorbehalte,
            "stand": stand,
            "laender_listen_treffer": laender_listen_treffer,
        }

    # --- Regel 0: Anwendbarkeits-Gate (§ 2 Abs. 1 Nr. 10 GwG) ---
    if norm["kataloggeschaeft"] == "keins":
        return report(
            "nicht_verpflichtet", "nicht_verpflichtet",
            "Kein Kataloggeschäft nach § 2 Abs. 1 Nr. 10 GwG angegeben — der "
            "Rechtsanwalt ist insoweit kein Verpflichteter; keine Risikoklasse.",
            "anwendbarkeits_gate", kg_meta=None, faktoren=[],
            pflichten=[],
            vorbehalte=[_VORBEHALT_SCORING, _VORBEHALT_FUNDSTELLEN],
            anwend_begr="Kein Kataloggeschäft angegeben.",
            anwend_vorbehalt="Einordnung prüfen: ob wirklich kein "
                             "Kataloggeschäft vorliegt, ist anwaltlich zu "
                             "verantworten.")

    if norm["kataloggeschaeft"] == "unklar":
        return report(
            "unklar", "unvollstaendig",
            "Ob ein Kataloggeschäft nach § 2 Abs. 1 Nr. 10 GwG vorliegt, ist "
            "unklar — ohne diese Angabe keine Verpflichteten-Einordnung und "
            "keine Risikoklassifikation.",
            "kritische_luecke", kg_meta=None, faktoren=[],
            pflichten=[],
            vorbehalte=[_VORBEHALT_SCORING, _VORBEHALT_FUNDSTELLEN],
            anwend_begr="Kataloggeschäft unklar.",
            anwend_vorbehalt="Einordnung prüfen.")

    kg_meta = KATALOGGESCHAEFTE[norm["kataloggeschaeft"]]

    # --- Regel 1: kritische Lücken -> keine Klassifikation ---
    if kritische_luecke:
        return report(
            "verpflichtet", "unvollstaendig",
            "Kritische Angaben (PEP-Status, Sitzland oder wirtschaftlich "
            "Berechtigter) sind nicht belastbar beantwortet — es wird bewusst "
            "keine Risikoklasse vergeben.",
            "kritische_luecke", kg_meta=kg_meta, faktoren=[],
            pflichten=[_verdachtsmeldungs_hinweis()],
            vorbehalte=[_VORBEHALT_SCORING, _VORBEHALT_FUNDSTELLEN],
            anwend_begr="Kataloggeschäft nach § 2 Abs. 1 Nr. 10 GwG angegeben "
                        "— Rechtsanwalt ist insoweit Verpflichteter.",
            anwend_vorbehalt=None)

    # --- Faktoren auswerten (Verpflichteter, keine kritische Lücke) ---
    faktoren: list[dict[str, Any]] = []
    vorbehalte = [_VORBEHALT_SCORING, _VORBEHALT_FUNDSTELLEN]
    land_konsultiert = False

    # Anlage 1 (risikoärmer)
    anlage1_treffer = 0
    for fk in anlage1["faktoren"]:
        if fk["bewertung"] == "ja_nein":
            if norm.get(fk["fragebogen_feld"]) == "ja":
                faktoren.append(_faktor_eintrag(fk, anlage=1))
                anlage1_treffer += 1
        elif fk["bewertung"] == "land_eu":
            land_konsultiert = True
            if norm["sitz_land"] in EU_MITGLIEDSTAATEN:
                faktoren.append(_faktor_eintrag(
                    fk, anlage=1,
                    detail=f"Sitzland {norm['sitz_land']} ist EU-Mitgliedstaat."))
                anlage1_treffer += 1

    # Anlage 2 (risikoerhöhend)
    anlage2_treffer = 0
    hochrisiko_land_hit = False
    eu_hochrisiko_hit = False
    hausrichtlinie_hit = False
    laender_listen_treffer: dict[str, Any] | None = None
    hochrisiko_laender = {e["iso2"]: e for e in hochrisiko["laender"]}
    hochrisiko_quellen = hochrisiko.get("quellen", {})
    for fk in anlage2["faktoren"]:
        if fk["bewertung"] == "ja_nein":
            if norm.get(fk["fragebogen_feld"]) == "ja":
                faktoren.append(_faktor_eintrag(fk, anlage=2))
                anlage2_treffer += 1
        elif fk["bewertung"] == "land_hochrisiko":
            land_konsultiert = True
            eintrag = hochrisiko_laender.get(norm["sitz_land"])
            if eintrag is not None:
                hochrisiko_land_hit = True
                listen = eintrag["listen"]
                eu_hochrisiko_hit = "eu-hochrisiko" in listen
                hausrichtlinie_hit = not eu_hochrisiko_hit
                listen_text = ", ".join(
                    LISTEN_LABELS.get(l, l) for l in listen)
                je_liste = [
                    {
                        "liste": l,
                        "bezeichnung": LISTEN_LABELS.get(l, l),
                        "rechtsfolge": hochrisiko_quellen.get(l, {}).get(
                            "rechtsfolge"),
                        "stand_quelle": hochrisiko_quellen.get(l, {}).get(
                            "stand_quelle"),
                        "url": hochrisiko_quellen.get(l, {}).get("url"),
                    }
                    for l in listen
                ]
                laender_listen_treffer = {
                    "iso2": norm["sitz_land"],
                    "land": eintrag["land"],
                    "listen": listen,
                    "je_liste": je_liste,
                }
                if eu_hochrisiko_hit:
                    # Statutorischer Faktor — Anlage 2 Nr. 3 Buchst. a GwG
                    # gilt nur für den EU-Listen-Treffer.
                    faktoren.append(_faktor_eintrag(
                        fk, anlage=2,
                        detail=f"Sitzland {norm['sitz_land']} "
                               f"({eintrag['land']}) ist gelistet auf: "
                               f"{listen_text}. {hochrisiko['vorbehalt']}"))
                else:
                    # Kein EU-Listen-Treffer — § 15 Abs. 3 Nr. 2 GwG verweist
                    # nur auf die EU-Liste, daher KEIN Zitat der Anlage-2-Norm
                    # (Anti-Halluzination). Konservative Haus-Einstufung.
                    faktoren.append({
                        "id": "haus_fatf_listen_treffer",
                        "anlage": None,
                        "fundstelle": "Hausrichtlinie (keine GwG-Norm)",
                        "paraphrase": (
                            "Sitzland ist nicht auf der EU-Hochrisiko-Liste "
                            "gelistet, aber auf mindestens einer FATF-Liste "
                            "(Schwarz- und/oder Grauliste) — konservative "
                            "Haus-Einstufung dieses Skills als 'hoch', keine "
                            "unmittelbare Gesetzespflicht aus § 15 Abs. 3 "
                            "Nr. 2 GwG (BaFin-Rundschreiben 07/2026)."),
                        "kategorie": "geografisch",
                        "quelle": "executor",
                        **_marker_felder(),
                        "detail": f"Sitzland {norm['sitz_land']} "
                                  f"({eintrag['land']}) ist gelistet auf: "
                                  f"{listen_text}. {hochrisiko['vorbehalt']}",
                    })
                anlage2_treffer += 1

    if land_konsultiert:
        stand_texte = ", ".join(
            f"{k}: {v}" for k, v in hochrisiko.get("stand", {}).items())
        vorbehalte.append(
            "Länder-Einordnung: " + hochrisiko["vorbehalt"] +
            " (Stand der hinterlegten Listen — " + stand_texte +
            "; abgerufen am " + str(hochrisiko.get("abgerufen_am")) + ")")
        if hausrichtlinie_hit and norm["sitz_land"] in EU_MITGLIEDSTAATEN:
            vorbehalte.append(
                f"Sitzland {norm['sitz_land']} ist EU-Mitgliedstaat und kann "
                "begrifflich schon kein 'Drittstaat mit hohem Risiko' i. S. d. "
                "§ 15 Abs. 3 Nr. 2 GwG sein — der FATF-Grauliste-Treffer "
                "bleibt eine reine Haus-Einstufung ohne Gesetzesgrundlage.")

    # PEP als eigener § 15-Tatbestand (nicht Teil der Anlage-2-Katalogfaktoren)
    pep_hit = norm["pep"] == "ja"
    if pep_hit:
        faktoren.append({
            "id": "pep_status",
            "anlage": None,
            "fundstelle": "§ 15 Abs. 3 Nr. 1 GwG",
            "paraphrase": "Politisch exponierte Person (PEP), Familienmitglied "
                          "oder bekanntermaßen nahestehende Person — löst "
                          "verstärkte Sorgfaltspflichten aus.",
            "kategorie": "kundenrisiko",
            "quelle": "executor",
            **_marker_felder(),
        })

    anwend_begr = ("Kataloggeschäft nach § 2 Abs. 1 Nr. 10 GwG angegeben — "
                   "Rechtsanwalt ist insoweit Verpflichteter.")

    # --- Regel 2: § 15 GwG (PEP/EU-Hochrisiko) ODER Haus-Einstufung
    # (reiner FATF-Treffer ohne EU-Listung) -> hoch. Maintainer-Entscheidung:
    # JEDER Listen-Treffer (EU, FATF-schwarz, FATF-grau) löst 'hoch' aus
    # (konservative Haus-Praxis); der Report weist aber je Treffer aus, ob es
    # sich um eine Gesetzespflicht (§ 15 GwG) oder eine Haus-Einstufung ohne
    # unmittelbare Rechtsfolge handelt.
    if pep_hit or hochrisiko_land_hit:
        gesetzlicher_trigger = pep_hit or eu_hochrisiko_hit
        pflichten = []
        if gesetzlicher_trigger:
            pflichten.append(_pflicht(
                "§ 15 GwG",
                "Verstärkte Sorgfaltspflichten sind anzuwenden "
                + ("(PEP, § 15 Abs. 3 Nr. 1 GwG). " if pep_hit else "")
                + ("(EU-Hochrisiko-Drittstaat, § 15 Abs. 3 Nr. 2 GwG, "
                   "mindestens § 15 Abs. 5 GwG). " if eu_hochrisiko_hit
                   else "")
                + "Umfang und konkrete Maßnahmen bestimmt der "
                  "Verpflichtete."))
            pflichten.append(_pflicht(
                "§ 10 GwG",
                "Die allgemeinen Sorgfaltspflichten gelten fort und werden "
                "durch die verstärkten Pflichten ergänzt."))
        if hausrichtlinie_hit and not gesetzlicher_trigger:
            pflichten.append({
                "norm": "Hausrichtlinie (keine GwG-Norm)",
                "hinweis": (
                    "Sitzland ist nicht auf der EU-Hochrisiko-Liste gelistet "
                    "(§ 15 Abs. 3 Nr. 2 GwG verweist ausschließlich auf diese "
                    "Liste), aber auf mindestens einer FATF-Liste. Es besteht "
                    "laut BaFin-Rundschreiben 07/2026 KEINE unmittelbare "
                    "Gesetzespflicht aus dieser Listung. Die Klassifikation "
                    "'hoch' ist eine konservative Haus-Einstufung dieses "
                    "Skills; die allgemeinen Sorgfaltspflichten (§ 10 GwG) "
                    "bleiben Ausgangspunkt, ergänzt um verschärfte interne "
                    "Maßnahmen ohne eigene Gesetzesgrundlage."),
                "quelle": "executor", **_marker_felder(),
            })
            pflichten.append(_pflicht(
                "§ 10 GwG",
                "Die allgemeinen Sorgfaltspflichten sind unabhängig von der "
                "Haus-Einstufung anzuwenden."))
        if norm["sitz_land"] in _BAFIN_ALLGEMEINVERFUEGUNG_LAENDER:
            pflichten.append(_pflicht(
                "BaFin-Allgemeinverfügung vom 13.05.2020",
                "Zusätzliche Anzeigepflicht für Geschäftsbeziehungen und "
                "Transaktionen mit Bezug zu Nordkorea/Iran gegenüber der "
                "BaFin — unabhängig von § 15 GwG."))
        pflichten.append(_verdachtsmeldungs_hinweis())

        begr_teile = []
        if pep_hit:
            begr_teile.append("PEP-Status (§ 15 Abs. 3 Nr. 1 GwG)")
        if eu_hochrisiko_hit:
            begr_teile.append(
                "Sitz in EU-Hochrisiko-Drittstaat (Anlage 2 Nr. 3 Buchst. a "
                "GwG, § 15 Abs. 3 Nr. 2 GwG)")
        if hausrichtlinie_hit and not eu_hochrisiko_hit:
            begr_teile.append(
                "Sitz in einem nur auf FATF-Listen (schwarz/grau) geführten "
                "Land ohne EU-Listung — konservative Haus-Einstufung, keine "
                "Gesetzespflicht")
        return report(
            "verpflichtet", "hoch",
            "Mindestens ein Tatbestand für die Klassifikation 'hoch' liegt "
            "vor: " + " und ".join(begr_teile) + ".",
            "paragraph_15", kg_meta=kg_meta, faktoren=faktoren,
            pflichten=pflichten, vorbehalte=vorbehalte,
            anwend_begr=anwend_begr, anwend_vorbehalt=None,
            laender_listen_treffer=laender_listen_treffer)

    # --- Regel 3: nur Anlage-1-Faktoren, kein Anlage-2-Faktor -> niedrig ---
    if anlage1_treffer > 0 and anlage2_treffer == 0:
        pflichten = [
            _pflicht("§ 14 GwG",
                     "Vereinfachte Sorgfaltspflichten sind *möglich*, da nur "
                     "risikoärmere Faktoren (Anlage 1 GwG) vorliegen. Ob "
                     "davon Gebrauch gemacht wird, entscheidet der "
                     "Verpflichtete nach eigener Risikobewertung."),
            _pflicht("§ 10 GwG",
                     "Die allgemeinen Sorgfaltspflichten bleiben Ausgangspunkt; "
                     "Vereinfachungen betreffen nur Umfang/Intensität."),
            _verdachtsmeldungs_hinweis(),
        ]
        return report(
            "verpflichtet", "niedrig",
            "Ausschließlich risikoärmere Faktoren nach Anlage 1 GwG erfüllt, "
            "kein Faktor nach Anlage 2 GwG und kein § 15-Tatbestand.",
            "nur_anlage1", kg_meta=kg_meta, faktoren=faktoren,
            pflichten=pflichten, vorbehalte=vorbehalte,
            anwend_begr=anwend_begr, anwend_vorbehalt=None)

    # --- Regel 4: sonst -> mittel ---
    pflichten = [
        _pflicht("§ 10 GwG",
                 "Allgemeine Sorgfaltspflichten sind anzuwenden (Identifizierung, "
                 "wirtschaftlich Berechtigter, Zweck der Geschäftsbeziehung, "
                 "kontinuierliche Überwachung)."),
        _verdachtsmeldungs_hinweis(),
    ]
    if anlage2_treffer > 0:
        klass_begr = ("Mindestens ein risikoerhöhender Faktor nach Anlage 2 GwG "
                      "liegt vor, ohne dass ein § 15-Tatbestand (PEP/"
                      "Hochrisiko-Drittstaat) erfüllt ist.")
    else:
        klass_begr = ("Weder ausschließlich Anlage-1-Faktoren noch ein "
                      "§ 15-Tatbestand — es bleibt bei den allgemeinen "
                      "Sorgfaltspflichten.")
    return report(
        "verpflichtet", "mittel", klass_begr, "allgemein",
        kg_meta=kg_meta, faktoren=faktoren, pflichten=pflichten,
        vorbehalte=vorbehalte, anwend_begr=anwend_begr, anwend_vorbehalt=None)
