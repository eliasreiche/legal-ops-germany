"""Tests für die Zuordnungs-Stufe Z2N (Nachname + Korroboration), P3/P4.

Hintergrund ist ein reproduzierter Pilot-Befund (Abnahme 2026-08): eigene
Kanzleikorrespondenz redet mit "Sehr geehrte Frau Dr. Merkel" — der Vorname
fehlt, Z1/Z2 verlangen aber den vollständigen `mandant`/`gegenseite`-String,
und sachlich eindeutige Post landete als `kein_treffer`.

Deckt ab: (a) Pilot-Repro -> Z2N mit Kategorie `moeglicher_treffer`,
(b) Nachname allein (kein zweites Signal / keine Gegenseite) -> weiterhin
`kein_treffer`, (c) zwei Mandate mit demselben Nachname-Signal -> Enthaltung
mit Hinweis, (d) Vollname/Az behalten Vorrang vor Z2N.
"""
from __future__ import annotations

import importlib.util
import sys

from conftest import SKILLS  # noqa: E402
from zuordnung import (  # noqa: E402
    Dokument,
    Mandat,
    finde_kandidaten,
    finde_kandidaten_mit_hinweisen,
    nachname,
)

SKILL_DIR = SKILLS / "email-akten-zuordnung"

_SPEC = importlib.util.spec_from_file_location(
    "email_akten_zuordnung_executor_z2n", SKILL_DIR / "executor.py")
executor = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = executor
_SPEC.loader.exec_module(executor)


# --------------------------------------------------------------------------
# Fixture: Pilotfall (Testakte Roosendaal, erfundene Daten) nachgebaut
# --------------------------------------------------------------------------

# Mandat mit Gegenseite -> Z2N erreichbar; Mandat ohne Gegenseite -> nie.
MANDAT_MIT_GEGENSEITE = Mandat(az="RT-2026-Q2-0318", mandant="Dr. Petra Merkel",
                                gegenseite="Robert Köhn",
                                datei="mandate/RT-2026-Q2-0318.md")
MANDAT_OHNE_GEGENSEITE = Mandat(az="RT-2026-Q2-0315", mandant="Günter Hagenbroich",
                                 gegenseite=None,
                                 datei="mandate/RT-2026-Q2-0315.md")


def _pilot_mail_merkel() -> Dokument:
    """Ausgehende Mandatsbestätigung: nur Anrede-Nachnamen, kein Vorname,
    kein Aktenzeichen — exakt die Konstellation aus der Pilot-Abnahme."""
    return Dokument(
        absender_name="",
        absender_adresse="kanzlei@roosendaal-tannenfels.example",
        betreff="Mandatsbestaetigung - Ihre Anfrage Gesellschafterstreit",
        textauszug=("Sehr geehrte Frau Dr. Merkel,\n\nwir freuen uns, Ihnen "
                    "mitteilen zu können, dass wir Ihr Mandat aufgenommen haben. "
                    "Bitte bringen Sie zum Termin die Korrespondenz mit Herrn "
                    "Köhn oder dessen Vertretern mit."))


def _pilot_mail_hagenbroich() -> Dokument:
    """Ausgehendes Ablehnungsschreiben: nur ein Nachname, Mandat hat keine
    Gegenseite — muss `kein_treffer` bleiben (kein Raten)."""
    return Dokument(
        absender_name="",
        absender_adresse="kanzlei@roosendaal-tannenfels.example",
        betreff="Ihre Anfrage vom 22.04.2026 - Fahrradschaden",
        textauszug=("Sehr geehrter Herr Hagenbroich,\n\nnach eingehender Prüfung "
                    "müssen wir Ihnen mitteilen, dass wir eine Mandatierung nicht "
                    "vornehmen können."))


# --------------------------------------------------------------------------
# nachname() — Nachname-Signal aus dem Mandatsfeld
# --------------------------------------------------------------------------

def test_nachname_strippt_titel_und_vorname():
    assert nachname("Dr. Petra Merkel") == "merkel"


def test_nachname_bei_einteiligem_namen_ist_der_name_selbst():
    assert nachname("Tannenmoor GmbH") == "tannenmoor"


def test_nachname_leer():
    assert nachname("") == ""
    assert nachname("Dr.") == ""


# --------------------------------------------------------------------------
# (a) Pilot-Repro — Nachname + Korroboration trifft als Z2N
# --------------------------------------------------------------------------

def test_z2n_pilotfall_anrede_nur_nachname_plus_gegenseite():
    kandidaten, hinweise = finde_kandidaten_mit_hinweisen(
        _pilot_mail_merkel(), [MANDAT_MIT_GEGENSEITE, MANDAT_OHNE_GEGENSEITE])

    assert [k.az for k in kandidaten] == ["RT-2026-Q2-0318"]
    assert kandidaten[0].stufe == "Z2N"
    assert kandidaten[0].kategorie == "moeglicher_treffer"
    assert kandidaten[0].datei == "mandate/RT-2026-Q2-0318.md"
    assert "merkel" in kandidaten[0].begruendung
    assert "koehn" in kandidaten[0].begruendung
    assert hinweise == []


def test_z2n_greift_auch_wenn_das_zweite_signal_im_betreff_steht():
    dokument = Dokument(betreff="Gesellschafterstreit Merkel ./. Köhn",
                        textauszug="Sehr geehrte Frau Dr. Merkel, anbei ...")
    kandidaten = finde_kandidaten(dokument, [MANDAT_MIT_GEGENSEITE])
    assert len(kandidaten) == 1
    assert kandidaten[0].stufe == "Z2N"


# --------------------------------------------------------------------------
# (b) Ein Nachname allein reicht nie
# --------------------------------------------------------------------------

def test_nachname_allein_ohne_gegenseite_bleibt_kein_treffer():
    kandidaten, hinweise = finde_kandidaten_mit_hinweisen(
        _pilot_mail_hagenbroich(), [MANDAT_OHNE_GEGENSEITE, MANDAT_MIT_GEGENSEITE])
    assert kandidaten == []
    assert hinweise == []


def test_nachname_allein_bei_vorhandener_gegenseite_bleibt_kein_treffer():
    # Nur "Merkel" im Text, "Köhn" fehlt -> keine Korroboration -> kein Kandidat.
    dokument = Dokument(betreff="Rueckfrage",
                        textauszug="Sehr geehrte Frau Dr. Merkel, kurze Rückfrage.")
    assert finde_kandidaten(dokument, [MANDAT_MIT_GEGENSEITE]) == []


def test_z2n_setzt_woertliche_signale_voraus_keine_phonetik():
    # "Merkl"/"Köhne" sind phonetisch/fuzzy nah, aber nicht wörtlich —
    # Z2N darf darauf nicht aufsetzen (Anti-Halluzination).
    dokument = Dokument(betreff="",
                        textauszug="Sehr geehrte Frau Merkl, Korrespondenz mit Herrn Köhne")
    kandidaten = finde_kandidaten(dokument, [MANDAT_MIT_GEGENSEITE])
    assert all(k.stufe != "Z2N" for k in kandidaten)


def test_z2n_matcht_nicht_auf_namensteil_innerhalb_eines_wortes():
    # Wortgrenzen-Disziplin von Z1: "Merkelbach"/"Köhnemann" sind andere Wörter.
    dokument = Dokument(betreff="",
                        textauszug="Frau Merkelbach und Herr Köhnemann melden sich")
    assert finde_kandidaten(dokument, [MANDAT_MIT_GEGENSEITE]) == []


# --------------------------------------------------------------------------
# (b2) Organisations-Gegenseite: ein Orts-/Gattungstoken korroboriert nicht
# --------------------------------------------------------------------------

MANDAT_ORGANISATION = Mandat(az="RT-2026-Q3-0501", mandant="Lena Vogt",
                              gegenseite="Stadtwerke Berlin",
                              datei="mandate/RT-2026-Q3-0501.md")


def test_z2n_ortstoken_einer_organisation_korroboriert_nicht():
    # Regression (D12-Review 2026-08): "berlin" ist das letzte Token der
    # Gegenseite, steht im Text aber als Teil eines Gerichtsnamens — kein
    # Nachname-Signal, also kein Z2N-Kandidat (Enthaltung).
    dokument = Dokument(
        betreff="Kuendigungsschutzklage",
        textauszug=("Sehr geehrte Frau Vogt,\n\nwir haben die Klage heute vor "
                    "dem Arbeitsgericht Berlin eingereicht."))
    kandidaten, hinweise = finde_kandidaten_mit_hinweisen(dokument, [MANDAT_ORGANISATION])
    assert kandidaten == []
    assert hinweise == []


def test_vollname_der_organisation_bleibt_ein_regulaerer_treffer():
    # Gegenprobe: nennt der Text die Organisation vollständig, greift Z1/Z2
    # wie bisher — die neue Regel verengt nur Z2N, nicht den Vollnamen-Weg.
    dokument = Dokument(betreff="Klage gegen die Stadtwerke Berlin",
                        textauszug="Sehr geehrte Frau Vogt, ...")
    kandidaten = finde_kandidaten(dokument, [MANDAT_ORGANISATION])
    assert [k.kategorie for k in kandidaten] == ["treffer"]
    assert kandidaten[0].stufe in ("Z1", "Z2")


# --------------------------------------------------------------------------
# (b3) Bloße Wort-Nachbarschaft ohne Anrede/Rubrum-Trenner korroboriert nicht
# --------------------------------------------------------------------------

MANDAT_FRANK_KOELN = Mandat(az="RT-2026-Q3-0602", mandant="Peter Frank",
                             gegenseite="Sparkasse Köln",
                             datei="mandate/RT-2026-Q3-0602.md")


def test_z2n_blosse_nachbarschaft_ohne_trenner_korroboriert_nicht():
    # Repro (D12-Nachreview): "Frank" und "Köln" stehen im Text nur durch ein
    # Komma getrennt nebeneinander (Signaturzeile), kein Anrede-Bezug, kein
    # Rubrum-Trenner ("./.", " gegen ") — darf kein Z2N-Signal für BEIDE
    # Nachnamen aus derselben Nachbarschaft ableiten.
    dokument = Dokument(
        betreff="Rueckfrage zum Termin",
        textauszug="Mit freundlichen Grüßen\nRechtsanwalt Frank, Köln")
    kandidaten, hinweise = finde_kandidaten_mit_hinweisen(dokument, [MANDAT_FRANK_KOELN])
    assert kandidaten == []
    assert hinweise == []


def test_z2n_rubrum_trenner_gegen_korroboriert():
    # Positivprobe zum selben Fix: ein expliziter Rubrum-Trenner aus der
    # geschlossenen Menge ("gegen") unmittelbar zwischen den beiden
    # Nachname-Tokens verbindet weiterhin (Rubrum-Kurzform, ohne Rechtsform).
    dokument = Dokument(betreff="Rechtsstreit Frank gegen Köln", textauszug="")
    kandidaten = finde_kandidaten(dokument, [MANDAT_FRANK_KOELN])
    assert len(kandidaten) == 1
    assert kandidaten[0].stufe == "Z2N"


# --------------------------------------------------------------------------
# (c) Mehrdeutigkeit -> Enthaltung mit Hinweis
# --------------------------------------------------------------------------

def _zwei_mandate_gleicher_nachname() -> list[Mandat]:
    return [
        Mandat(az="RT-2026-Q2-0318", mandant="Dr. Petra Merkel",
               gegenseite="Robert Köhn", datei="mandate/RT-2026-Q2-0318.md"),
        Mandat(az="RT-2026-Q2-0401", mandant="Klaus Merkel",
               gegenseite="Robert Köhn", datei="mandate/RT-2026-Q2-0401.md"),
    ]


def test_z2n_mehrdeutiges_nachname_signal_erzeugt_keinen_kandidaten():
    kandidaten, hinweise = finde_kandidaten_mit_hinweisen(
        _pilot_mail_merkel(), _zwei_mandate_gleicher_nachname())

    assert kandidaten == []          # Enthaltung, kein Raten
    assert len(hinweise) == 2        # je Mandat ein nachvollziehbarer Grund
    assert all("merkel" in h for h in hinweise)
    assert all("Enthaltung" in h for h in hinweise)


def test_z2n_eindeutig_trotz_gleichem_einzel_signal_im_anderen_mandat():
    # Zweites Mandat teilt nur den Mandanten-Nachnamen, seine Gegenseite kommt
    # im Text nicht vor -> es ist gar nicht Z2N-fähig, das erste Mandat bleibt
    # über die KOMBINATION beider Nachnamen eindeutig.
    mandate = [
        MANDAT_MIT_GEGENSEITE,
        Mandat(az="RT-2026-Q2-0402", mandant="Klaus Merkel",
               gegenseite="Sabine Windhorst", datei="mandate/RT-2026-Q2-0402.md"),
    ]
    kandidaten, hinweise = finde_kandidaten_mit_hinweisen(_pilot_mail_merkel(), mandate)
    assert [k.az for k in kandidaten] == ["RT-2026-Q2-0318"]
    assert hinweise == []


# --------------------------------------------------------------------------
# (d) Rangfolge — Z2N ist nie so stark wie Z0/Z1/Z2
# --------------------------------------------------------------------------

def test_az_treffer_hat_vorrang_vor_z2n():
    dokument = Dokument(betreff="Az. RT-2026-Q2-0318 - Gesellschafterstreit",
                        textauszug="Sehr geehrte Frau Dr. Merkel, ... Herrn Köhn ...")
    kandidaten = finde_kandidaten(dokument, [MANDAT_MIT_GEGENSEITE])
    assert kandidaten[0].stufe == "Z0"
    assert kandidaten[0].kategorie == "treffer"


def test_vollname_treffer_hat_vorrang_vor_z2n():
    dokument = Dokument(betreff="",
                        textauszug="Frau Dr. Petra Merkel und Herr Köhn haben ...")
    kandidaten = finde_kandidaten(dokument, [MANDAT_MIT_GEGENSEITE])
    assert kandidaten[0].stufe == "Z1"
    assert kandidaten[0].kategorie == "treffer"


# --------------------------------------------------------------------------
# Executor-Anbindung: Report führt Stufe und Enthaltungs-Hinweise
# --------------------------------------------------------------------------

def _eintrag(dokument: Dokument, mandate: list[Mandat]) -> dict:
    return executor.baue_dokument_eintrag(
        {"quelle": "test.eml", "absender_name": dokument.absender_name,
         "absender_adresse": dokument.absender_adresse, "empfaenger": [], "cc": [],
         "betreff": dokument.betreff, "textauszug": dokument.textauszug,
         "textauszug_gekuerzt": False, "datum": "2026-06-02"},
        mandate, 0.85)


def test_report_weist_z2n_kandidat_und_prioritaet_normal_aus():
    eintrag = _eintrag(_pilot_mail_merkel(), [MANDAT_MIT_GEGENSEITE])
    assert eintrag["kein_treffer"] is False
    assert eintrag["kandidaten"][0]["stufe"] == "Z2N"
    assert eintrag["kandidaten"][0]["kategorie"] == "moeglicher_treffer"
    assert eintrag["zuordnung_hinweise"] == []
    # `moeglicher_treffer` allein hebt die Priorität nicht — hier trägt sie
    # der Fristverdacht ("Mandat" ist kein Signalwort, "Anfrage" auch nicht).
    assert eintrag["prioritaet"] == "normal"


def test_report_weist_enthaltungs_hinweis_aus():
    eintrag = _eintrag(_pilot_mail_merkel(), _zwei_mandate_gleicher_nachname())
    assert eintrag["kein_treffer"] is True
    assert len(eintrag["zuordnung_hinweise"]) == 2
