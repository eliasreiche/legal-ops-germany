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

     Das Länder-Gate (Anlage 1 Nr. 3 / Anlage 2 Nr. 3 GwG) prüft NICHT nur den
     Mandantensitz, sondern auch jedes angegebene Sitz-/Staatsangehörigkeits-
     land der wirtschaftlich Berechtigten (`wirtschaftlich_berechtigte_laender`;
     § 10 Abs. 1 Nr. 2 GwG verlangt deren Identifizierung, die geografischen
     Risikofaktoren der Anlagen 1/2 erfassen sie mit). Es entscheidet das
     RISIKOREICHSTE Land: ein Listen-Treffer bei einem wirtschaftlich
     Berechtigten löst `hoch` aus, auch wenn der Mandantensitz in der EU liegt;
     die Anlage-1-Vergünstigung „EU-Sitz" greift nur, wenn Mandantensitz UND
     alle angegebenen Länder der wirtschaftlich Berechtigten in der EU liegen.
     Fehlt die Angabe bei juristischen Personen / trust-ähnlichen Strukturen,
     wird sie als (nicht-kritische) Lücke ausgewiesen — nie geraten.
  3. Ausschließlich Anlage-1-Faktoren, kein Anlage-2-Faktor -> `niedrig`
     (vereinfachte Sorgfaltspflichten nach § 14 GwG *möglich* — Entscheidung
     beim Verpflichteten).
  4. Sonst -> `mittel` (allgemeine Sorgfaltspflichten, § 10 GwG).

Anti-Halluzination: Die Faktoren der Anlagen 1/2 GwG sind als PARAPHRASE mit
exakter Fundstelle in anlage1.json / anlage2.json hinterlegt (kein erfundener
Wortlaut). Jede Fundstelle im erzeugten Report trägt einen 3-Zustands-Marker
(hier stets ⚠️ „nicht prüfbar" — der Executor prüft nicht gegen den
Gesetzestext; die Prüfung ist die händische Abnahme gegen die Quellen-
Registry des Skills und gesetze-im-internet.de).

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

# Frische-Warnung: FATF tagt ca. Februar/Juni/Oktober (drei
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
    kein Netzwerk auf; reiner Datumsvergleich. Der Aufrufer entscheidet:
    der CI-Test lässt `fehler` scheitern, `klassifiziere()` schreibt beide
    Stufen als Warnung in den Report (`warnungen`)."""
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
    "den Gesetzestext geprüft — händisch gegen die Quellen-Registry des Skills "
    "(schema/quellen-registry.json) und gesetze-im-internet.de zu "
    "verifizieren.")

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
    ("kataloggeschaeft", "mandant_typ", "sitz_land",
     "wirtschaftlich_berechtigte_laender") + _JNU_FELDER)

# Mandantentypen, bei denen eine fehlende Länderangabe zum wirtschaftlich
# Berechtigten als Lücke ausgewiesen wird (bei natürlichen Personen ist der
# Mandant regelmäßig selbst der wirtschaftlich Berechtigte).
_WB_LAENDER_PFLICHT_TYPEN = ("juristische_person", "trust_aehnlich")

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
    "wirtschaftlich_berechtigte_laender":
        "In welchen Staaten haben die wirtschaftlich Berechtigten ihren "
        "Sitz/Wohnsitz bzw. welche Staatsangehörigkeit(en) besitzen sie "
        "(ISO-3166-alpha-2)? Ohne diese Angabe prüft das Länder-Gate nur den "
        "Mandantensitz — ein Hochrisiko-Bezug über den wirtschaftlich "
        "Berechtigten bliebe unerkannt.",
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


def _iso2(wert: Any, feld: str, *, oder_unklar: bool = False) -> str:
    """Prüft einen ISO-3166-alpha-2-Code und liefert ihn in Großschreibung."""
    if not isinstance(wert, str):
        raise GwGEingabeFehler(f"'{feld}' muss ein String sein")
    code = wert.strip().upper()
    if len(code) != 2 or not code.isalpha():
        zusatz = " oder 'unklar'" if oder_unklar else ""
        raise GwGEingabeFehler(
            f"'{feld}' muss ein ISO-3166-alpha-2-Code (zwei Buchstaben)"
            f"{zusatz} sein, nicht {wert!r}")
    return code


def _normalisiere(mandat: dict[str, Any]) -> dict[str, Any]:
    """Prüft die Eingabe strikt und füllt fehlende Felder mit 'unklar' (nie
    raten). Unbekannte Felder sind ein Eingabefehler (Tippfehler-Diagnose)."""
    if not isinstance(mandat, dict):
        raise GwGEingabeFehler("Mandat muss ein JSON-Objekt sein")

    for feld in mandat:
        if feld not in FRAGEBOGEN_FELDER:
            raise GwGEingabeFehler(
                f"unbekanntes Feld: '{feld}' (zulässig: "
                f"{', '.join(sorted(FRAGEBOGEN_FELDER))})")

    norm: dict[str, Any] = {}

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
        land = _iso2(land, "sitz_land", oder_unklar=True)
    norm["sitz_land"] = land

    # Optional (rückwärtskompatibel): Sitz-/Staatsangehörigkeitsländer der
    # wirtschaftlich Berechtigten. Fehlt das Feld, bleibt die Liste leer und
    # das Länder-Gate prüft wie bisher nur den Mandantensitz — die Lücke wird
    # im Report ausgewiesen (nie geraten).
    wb_roh = mandat.get("wirtschaftlich_berechtigte_laender") or []
    if not isinstance(wb_roh, list):
        raise GwGEingabeFehler(
            "'wirtschaftlich_berechtigte_laender' muss eine Liste von "
            "ISO-3166-alpha-2-Codes sein (z. B. [\"CY\", \"RU\"]), nicht "
            f"{mandat.get('wirtschaftlich_berechtigte_laender')!r}")
    wb_laender: list[str] = []
    for eintrag in wb_roh:
        code = _iso2(eintrag, "wirtschaftlich_berechtigte_laender")
        if code not in wb_laender:
            wb_laender.append(code)
    norm["wirtschaftlich_berechtigte_laender"] = wb_laender

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


def _stand_block(a1: dict, a2: dict, hr: dict,
                 frische: dict[str, Any]) -> dict[str, Any]:
    return {
        "anlage1": a1.get("stand"),
        "anlage2": a2.get("stand"),
        "hochrisiko_drittstaaten": hr.get("stand"),
        "hochrisiko_abgerufen_am": hr.get("abgerufen_am"),
        "hochrisiko_alter_tage": frische["alter_tage"],
        "hochrisiko_warnung_veraltet": frische["warnung"],
        "hochrisiko_ueberfaellig": frische["fehler"],
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
                  hochrisiko: dict | None = None,
                  heute: date | None = None) -> dict[str, Any]:
    """Bewertet ein Mandat regelbasiert und liefert den Report-Rumpf (ohne
    `meta`). Alle Werte sind Executor-Ergebnisse (P3).

    `heute` ist das Bezugsdatum des Frische-Gates (Default: Systemdatum über
    `_heute()`); der Executor reicht dafür `--heute` durch."""
    if anlage1 is None or anlage2 is None or hochrisiko is None:
        _a1, _a2, _hr = lade_kataloge()
        anlage1 = anlage1 or _a1
        anlage2 = anlage2 or _a2
        hochrisiko = hochrisiko or _hr

    norm = _normalisiere(mandat)
    frische = frische_status(hochrisiko, heute=heute)
    stand = _stand_block(anlage1, anlage2, hochrisiko, frische)

    # --- Frische-Gate der Hochrisiko-Länderliste sichtbar machen ---
    warnungen: list[str] = []
    if frische["fehler"]:
        warnungen.append(
            f"Hochrisiko-Länderliste überfällig (Pflicht-Refresh ab "
            f"{FRISCHE_FEHLER_MONATE} Monaten): {frische['hinweis']} Der "
            "geografische Teil dieses Klassifikationsvorschlags ist ohne "
            "aktuellen Listenstand nicht belastbar — Liste neu abrufen und "
            "Prüfung wiederholen.")
    elif frische["warnung"]:
        warnungen.append(
            f"Hochrisiko-Länderliste älter als {FRISCHE_WARN_MONATE} Monate: "
            f"{frische['hinweis']}")

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
    if (not norm["wirtschaftlich_berechtigte_laender"]
            and norm["mandant_typ"] in _WB_LAENDER_PFLICHT_TYPEN):
        # Nicht kritisch: bestehende Fragebögen ohne das Feld laufen unverändert
        # durch — die Lücke sagt nur, dass der Länderbezug des wirtschaftlich
        # Berechtigten ungeprüft blieb.
        luecken.append(_luecke("wirtschaftlich_berechtigte_laender",
                               kritisch=False))
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
            "warnungen": warnungen,
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

    # Länder-Gate: Mandantensitz UND jedes angegebene Land der wirtschaftlich
    # Berechtigten; das risikoreichste Ergebnis entscheidet (siehe Docstring).
    _WB_HERKUNFT = "Sitz/Staatsangehörigkeit des wirtschaftlich Berechtigten"
    pruef_laender: list[str] = []
    herkunft: dict[str, str] = {}
    for land, quelle in ([(norm["sitz_land"], "Sitzland")]
                         + [(l, _WB_HERKUNFT)
                            for l in norm["wirtschaftlich_berechtigte_laender"]]):
        if land != "unklar" and land not in herkunft:
            pruef_laender.append(land)
            herkunft[land] = quelle

    # Anlage 1 (risikoärmer)
    anlage1_treffer = 0
    for fk in anlage1["faktoren"]:
        if fk["bewertung"] == "ja_nein":
            if norm.get(fk["fragebogen_feld"]) == "ja":
                faktoren.append(_faktor_eintrag(fk, anlage=1))
                anlage1_treffer += 1
        elif fk["bewertung"] == "land_eu":
            land_konsultiert = True
            # Nur wenn ALLE geprüften Länder EU sind — ein Nicht-EU-Land beim
            # wirtschaftlich Berechtigten nimmt die Vergünstigung weg.
            if pruef_laender and all(l in EU_MITGLIEDSTAATEN
                                     for l in pruef_laender):
                detail = f"Sitzland {norm['sitz_land']} ist EU-Mitgliedstaat."
                weitere = [l for l in pruef_laender if l != norm["sitz_land"]]
                if weitere:
                    detail += (" Auch alle angegebenen Länder des wirtschaftlich "
                               f"Berechtigten ({', '.join(weitere)}) sind "
                               "EU-Mitgliedstaaten.")
                faktoren.append(_faktor_eintrag(fk, anlage=1, detail=detail))
                anlage1_treffer += 1

    # Anlage 2 (risikoerhöhend)
    anlage2_treffer = 0
    hochrisiko_land_hit = False
    eu_hochrisiko_hit = False
    hausrichtlinie_hit = False
    laender_listen_treffer: dict[str, Any] | None = None
    alle_laender_treffer: list[dict[str, Any]] = []
    hochrisiko_laender = {e["iso2"]: e for e in hochrisiko["laender"]}
    hochrisiko_quellen = hochrisiko.get("quellen", {})
    for fk in anlage2["faktoren"]:
        if fk["bewertung"] == "ja_nein":
            if norm.get(fk["fragebogen_feld"]) == "ja":
                faktoren.append(_faktor_eintrag(fk, anlage=2))
                anlage2_treffer += 1
        elif fk["bewertung"] == "land_hochrisiko":
            land_konsultiert = True
            for land in pruef_laender:
                eintrag = hochrisiko_laender.get(land)
                if eintrag is None:
                    continue
                hochrisiko_land_hit = True
                listen = eintrag["listen"]
                ist_eu_liste = "eu-hochrisiko" in listen
                eu_hochrisiko_hit = eu_hochrisiko_hit or ist_eu_liste
                hausrichtlinie_hit = hausrichtlinie_hit or not ist_eu_liste
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
                treffer = {
                    "iso2": land,
                    "land": eintrag["land"],
                    "herkunft": herkunft[land],
                    "listen": listen,
                    "je_liste": je_liste,
                }
                alle_laender_treffer.append(treffer)
                # Risikoreichster Treffer führt den Report: eine EU-Listung
                # (Gesetzespflicht) schlägt einen reinen FATF-Treffer.
                if laender_listen_treffer is None or (
                        ist_eu_liste
                        and "eu-hochrisiko" not in laender_listen_treffer["listen"]):
                    laender_listen_treffer = treffer
                detail = (f"{herkunft[land]} {land} ({eintrag['land']}) ist "
                          f"gelistet auf: {listen_text}. "
                          f"{hochrisiko['vorbehalt']}")
                if ist_eu_liste:
                    # Statutorischer Faktor — Anlage 2 Nr. 3 Buchst. a GwG
                    # gilt nur für den EU-Listen-Treffer.
                    faktoren.append(_faktor_eintrag(fk, anlage=2, detail=detail))
                else:
                    # Kein EU-Listen-Treffer — § 15 Abs. 3 Nr. 2 GwG verweist
                    # nur auf die EU-Liste, daher KEIN Zitat der Anlage-2-Norm
                    # (Anti-Halluzination). Konservative Haus-Einstufung.
                    faktoren.append({
                        "id": "haus_fatf_listen_treffer",
                        "anlage": None,
                        "fundstelle": "Hausrichtlinie (keine GwG-Norm)",
                        "paraphrase": (
                            "Land ist nicht auf der EU-Hochrisiko-Liste "
                            "gelistet, aber auf mindestens einer FATF-Liste "
                            "(Schwarz- und/oder Grauliste) — konservative "
                            "Haus-Einstufung dieses Skills als 'hoch', keine "
                            "unmittelbare Gesetzespflicht aus § 15 Abs. 3 "
                            "Nr. 2 GwG (BaFin-Rundschreiben 07/2026)."),
                        "kategorie": "geografisch",
                        "quelle": "executor",
                        **_marker_felder(),
                        "detail": detail,
                    })
                anlage2_treffer += 1

    if land_konsultiert:
        stand_texte = ", ".join(
            f"{k}: {v}" for k, v in hochrisiko.get("stand", {}).items())
        vorbehalte.append(
            "Länder-Einordnung: " + hochrisiko["vorbehalt"] +
            " (Stand der hinterlegten Listen — " + stand_texte +
            "; abgerufen am " + str(hochrisiko.get("abgerufen_am")) + ")")
        for t in alle_laender_treffer:
            if "eu-hochrisiko" in t["listen"]:
                continue
            if t["iso2"] in EU_MITGLIEDSTAATEN:
                vorbehalte.append(
                    f"{t['herkunft']} {t['iso2']} ist EU-Mitgliedstaat und kann "
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
        if any(l in _BAFIN_ALLGEMEINVERFUEGUNG_LAENDER for l in pruef_laender):
            pflichten.append(_pflicht(
                "BaFin-Allgemeinverfügung vom 13.05.2020",
                "Zusätzliche Anzeigepflicht für Geschäftsbeziehungen und "
                "Transaktionen mit Bezug zu Nordkorea/Iran gegenüber der "
                "BaFin — unabhängig von § 15 GwG."))
        pflichten.append(_verdachtsmeldungs_hinweis())

        begr_teile = []
        if pep_hit:
            begr_teile.append("PEP-Status (§ 15 Abs. 3 Nr. 1 GwG)")
        eu_treffer = [t for t in alle_laender_treffer
                      if "eu-hochrisiko" in t["listen"]]
        haus_treffer = [t for t in alle_laender_treffer
                        if "eu-hochrisiko" not in t["listen"]]
        if eu_treffer:
            begr_teile.append(
                "Länderbezug zu EU-Hochrisiko-Drittstaat ("
                + "; ".join(f"{t['iso2']} — {t['herkunft']}" for t in eu_treffer)
                + "; Anlage 2 Nr. 3 Buchst. a GwG, § 15 Abs. 3 Nr. 2 GwG)")
        if haus_treffer:
            begr_teile.append(
                "Länderbezug zu einem nur auf FATF-Listen (schwarz/grau) "
                "geführten Land ohne EU-Listung ("
                + "; ".join(f"{t['iso2']} — {t['herkunft']}"
                            for t in haus_treffer)
                + ") — konservative Haus-Einstufung, keine Gesetzespflicht")
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
