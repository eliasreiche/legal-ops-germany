#!/usr/bin/env python3
"""passive-zeiterfassung — deterministischer Zeiterfassungs-Executor (P2/P3).

Rekonstruiert aus Kalender- und Mail-**Metadaten** (M365 via `kontext-sync`
oder manueller Export) Zeiterfassungs-Vorschläge je Akte. Jeder eindeutig
zugeordnete Vorschlag ist bereits ein fertiger `taetigkeitstext-rvg`-
Leistungseintrag (`leistungen.json`-Format) — die Kanzlei bestätigt oder
verwirft ihn, Claude schreibt die bestätigten Einträge und übergibt an
`taetigkeitstext-rvg`.

## Deterministik-Grenze (P3)

- **Termin-Dauer** kommt aus `start`/`ende` (Bibliothek `core/calc/zeit`) —
  nie vom Modell.
- **Mail-Zeitwert** ist ausschließlich die Kanzlei-Konvention
  `config.mail_pauschale_minuten`. Ohne Config/`null` bekommt eine Mail
  **keinen** Zeitwert (landet in `ohne_zeitwert[]`, Lücke) — es wird nie eine
  Minutenzahl erfunden.
- **Akten-Zuordnung** je Termin/Mail über `core/calc/zuordnung` (Stufen
  Z0–Z4) gegen `kontext/mandate/*.md`. Genau ein `treffer` → Vorschlag mit
  diesem `az`; mehrere/nur mögliche → `mehrdeutig[]`; keiner →
  `nicht_zuordenbar[]` (Lücke, nie geraten).

Kein Aktenzeichen, kein Datum, keine Minute wird geraten. Fehlendes wird als
Lücke ausgewiesen. Die abrechnungsrelevante Entscheidung (welcher Vorschlag
stimmt) bleibt immer bei der Kanzlei.

## CLI

    python3 executor.py --termine termine.json --kontext <kontext-dir>
                        [--mails mails.json] [--config config.json]
                        [--output report.json]
    python3 executor.py --mails mails.json --kontext <kontext-dir> ...

Mindestens eines von `--termine`/`--mails` ist Pflicht, `--kontext` ist
Pflicht. Feldkontrakt: [`schema/README.md`](schema/README.md).

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler (kein Traceback).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

# Self-relativ innerhalb des Plugins: skill -> skills -> <plugin-root>/core.
_SKILL_DIR = Path(__file__).resolve().parent
_CORE_DIR = _SKILL_DIR.parents[1] / "core"
_CALC_DIR = _CORE_DIR / "calc"
for _pfad in (_CORE_DIR, _CALC_DIR):
    if str(_pfad) not in sys.path:
        sys.path.insert(0, str(_pfad))

from context.schema import lese_mandate  # noqa: E402
from zeit.rechner import (  # noqa: E402
    ZeitEingabeFehler,
    ZeitEintrag,
    dauer_minuten,
    summe_je_az,
)
from zuordnung import (  # noqa: E402
    STUFE_TREFFER,
    Dokument,
    Kandidat,
    Mandat,
    finde_kandidaten,
)

ERZEUGT_VON = "passive-zeiterfassung/executor.py"

TERMIN_FELDER = {"betreff", "start", "ende", "teilnehmer", "ort"}
TERMIN_PFLICHTFELDER = {"betreff", "start", "ende"}
MAIL_FELDER = {"zeitstempel", "betreff", "absender", "empfaenger", "richtung"}
MAIL_PFLICHTFELDER = {"zeitstempel", "betreff", "richtung"}
RICHTUNG_WERTE = {"eingehend", "ausgehend"}

DETERMINISTIK = ("Alle Minuten-, Datums- und Zuordnungswerte in diesem Report "
                 "sind Executor-Ergebnisse (P3), nicht modellgeneriert.")

OHNE_ZEITWERT_HINWEIS = (
    "Kein Zeitwert konfiguriert (config.mail_pauschale_minuten fehlt oder ist "
    "null) — Minuten manuell nachtragen; es wird kein Wert erfunden.")
NICHT_ZUORDENBAR_HINWEIS = (
    "Kein Mandat zugeordnet — Akte manuell wählen; es wird kein Aktenzeichen "
    "erfunden.")
MEHRDEUTIG_HINWEIS = (
    "Mehr als eine Akte kommt in Frage — die Kanzlei entscheidet, keine "
    "automatische Zuordnung.")


class EingabeFehler(Exception):
    """Strukturell ungültige Eingabe — CLI fängt sie sauber ab (Exit 2)."""


# --------------------------------------------------------------------------
# Kleine Validierungs-Bausteine
# --------------------------------------------------------------------------

def _pruefe_str(wert: Any, feld: str, pfad: str, *, pflicht: bool) -> str:
    if wert is None or wert == "":
        if pflicht:
            raise EingabeFehler(f"{pfad}.{feld}: Pflichtfeld fehlt oder ist leer")
        return ""
    if not isinstance(wert, str):
        raise EingabeFehler(f"{pfad}.{feld}: muss Text sein, ist: {wert!r}")
    return wert


def _pruefe_str_liste(wert: Any, feld: str, pfad: str) -> list[str]:
    if wert is None:
        return []
    if not isinstance(wert, list) or not all(isinstance(s, str) for s in wert):
        raise EingabeFehler(f"{pfad}.{feld}: muss eine Liste von Texten sein, ist: {wert!r}")
    return [s for s in wert if s.strip()]


def _iso_datum(zeitstempel: str, feld: str, pfad: str) -> str:
    """Reduziert einen ISO-8601-Zeitstempel auf sein Datum (JJJJ-MM-TT)."""
    try:
        return _dt.datetime.fromisoformat(zeitstempel).date().isoformat()
    except ValueError as exc:
        raise EingabeFehler(
            f"{pfad}.{feld}: kein gültiger ISO-8601-Zeitstempel: {zeitstempel!r}") from exc


def _lade_liste(daten: Any, wurzel_feld: str, quelle: str) -> list[Any]:
    if not isinstance(daten, dict):
        raise EingabeFehler(f"{quelle}: Wurzel muss ein JSON-Objekt sein")
    unbekannt = set(daten) - {wurzel_feld}
    if unbekannt:
        raise EingabeFehler(f"{quelle}: unbekanntes Feld {sorted(unbekannt)!r}")
    if wurzel_feld not in daten:
        raise EingabeFehler(f"{quelle}: Pflichtfeld `{wurzel_feld}` fehlt")
    liste = daten[wurzel_feld]
    if not isinstance(liste, list):
        raise EingabeFehler(f"{quelle}: `{wurzel_feld}` muss eine Liste sein")
    return liste


# --------------------------------------------------------------------------
# Termine / Mails einlesen (strikt, Tippfehler-Diagnose)
# --------------------------------------------------------------------------

def _pruefe_termin(roh: Any, index: int) -> dict[str, Any]:
    pfad = f"termine[{index}]"
    if not isinstance(roh, dict):
        raise EingabeFehler(f"{pfad}: muss ein JSON-Objekt sein")
    unbekannt = set(roh) - TERMIN_FELDER
    if unbekannt:
        raise EingabeFehler(f"{pfad}: unbekanntes Feld {sorted(unbekannt)!r}")
    fehlend = TERMIN_PFLICHTFELDER - set(roh)
    if fehlend:
        raise EingabeFehler(f"{pfad}: Pflichtfeld(er) fehlen: {sorted(fehlend)!r}")

    betreff = _pruefe_str(roh.get("betreff"), "betreff", pfad, pflicht=True)
    start = _pruefe_str(roh.get("start"), "start", pfad, pflicht=True)
    ende = _pruefe_str(roh.get("ende"), "ende", pfad, pflicht=True)
    teilnehmer = _pruefe_str_liste(roh.get("teilnehmer"), "teilnehmer", pfad)
    ort = _pruefe_str(roh.get("ort"), "ort", pfad, pflicht=False)

    # Dauer + Zeitvalidierung (ende <= start ist ein Eingabefehler, P3).
    try:
        minuten = dauer_minuten(start=start, ende=ende, minuten=None)
    except ZeitEingabeFehler as exc:
        raise EingabeFehler(f"{pfad}: {exc}") from exc

    return {
        "betreff": betreff, "start": start, "ende": ende, "teilnehmer": teilnehmer,
        "ort": ort, "minuten": minuten, "datum": _iso_datum(start, "start", pfad),
    }


def _pruefe_mail(roh: Any, index: int) -> dict[str, Any]:
    pfad = f"mails[{index}]"
    if not isinstance(roh, dict):
        raise EingabeFehler(f"{pfad}: muss ein JSON-Objekt sein")
    unbekannt = set(roh) - MAIL_FELDER
    if unbekannt:
        raise EingabeFehler(f"{pfad}: unbekanntes Feld {sorted(unbekannt)!r}")
    fehlend = MAIL_PFLICHTFELDER - set(roh)
    if fehlend:
        raise EingabeFehler(f"{pfad}: Pflichtfeld(er) fehlen: {sorted(fehlend)!r}")

    zeitstempel = _pruefe_str(roh.get("zeitstempel"), "zeitstempel", pfad, pflicht=True)
    betreff = _pruefe_str(roh.get("betreff"), "betreff", pfad, pflicht=True)
    absender = _pruefe_str(roh.get("absender"), "absender", pfad, pflicht=False)
    empfaenger = _pruefe_str_liste(roh.get("empfaenger"), "empfaenger", pfad)
    richtung = roh.get("richtung")
    if richtung not in RICHTUNG_WERTE:
        raise EingabeFehler(f"{pfad}.richtung: muss eine von {sorted(RICHTUNG_WERTE)} sein, "
                            f"ist: {richtung!r}")

    return {
        "zeitstempel": zeitstempel, "betreff": betreff, "absender": absender,
        "empfaenger": empfaenger, "richtung": richtung,
        "datum": _iso_datum(zeitstempel, "zeitstempel", pfad),
    }


def lese_termine(pfad: Path) -> list[dict[str, Any]]:
    daten = _lade_json(pfad)
    return [_pruefe_termin(t, i) for i, t in enumerate(_lade_liste(daten, "termine", str(pfad)))]


def lese_mails(pfad: Path) -> list[dict[str, Any]]:
    daten = _lade_json(pfad)
    return [_pruefe_mail(m, i) for i, m in enumerate(_lade_liste(daten, "mails", str(pfad)))]


def lese_config(pfad: Path | None) -> int | None:
    """Liest `config.mail_pauschale_minuten` (int > 0 oder null). Fehlt die
    Config, gilt `None` (Mails ohne Zeitwert → `ohne_zeitwert[]`)."""
    if pfad is None:
        return None
    daten = _lade_json(pfad)
    if not isinstance(daten, dict):
        raise EingabeFehler(f"{pfad}: Wurzel muss ein JSON-Objekt sein")
    unbekannt = set(daten) - {"mail_pauschale_minuten"}
    if unbekannt:
        raise EingabeFehler(f"{pfad}: unbekanntes Feld {sorted(unbekannt)!r}")
    wert = daten.get("mail_pauschale_minuten")
    if wert is None:
        return None
    if isinstance(wert, bool) or not isinstance(wert, int) or wert <= 0:
        raise EingabeFehler(f"{pfad}.mail_pauschale_minuten: muss eine ganze Zahl > 0 oder "
                            f"null sein, ist: {wert!r}")
    return wert


def _lade_json(pfad: Path) -> Any:
    if not pfad.is_file():
        raise EingabeFehler(f"{pfad}: Datei nicht gefunden")
    try:
        text = pfad.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise EingabeFehler(f"{pfad}: Datei nicht lesbar ({exc})") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EingabeFehler(f"{pfad}: kein gültiges JSON: {exc}") from exc


# --------------------------------------------------------------------------
# Mandatsliste (kontext/mandate/*.md über core/context/schema.py)
# --------------------------------------------------------------------------

def lese_kontext_mandate(kontext_dir: Path) -> tuple[list[Mandat], list[str]]:
    """Liest `kontext/mandate/*.md` über `lese_mandate()`. Mandate ohne
    Aktenzeichen können nicht zugeordnet werden — sie werden übersprungen und
    als Warnung ausgewiesen, statt geraten zu werden (wie in
    email-akten-zuordnung)."""
    warnungen: list[str] = []
    mandate: list[Mandat] = []
    for pfad, fm in lese_mandate(kontext_dir):
        az = (fm.get("az") or (None, None))[0]
        if not az:
            warnungen.append(f"{pfad.name}: kein Aktenzeichen im Frontmatter — Mandat wird "
                             f"übersprungen (nicht zuordenbar)")
            continue
        mandant = (fm.get("mandant") or (None, None))[0] or ""
        gegenseite = (fm.get("gegenseite") or (None, None))[0]
        try:
            datei_rel = str(pfad.relative_to(kontext_dir))
        except ValueError:
            datei_rel = pfad.name
        mandate.append(Mandat(az=az, mandant=mandant, gegenseite=gegenseite, datei=datei_rel))
    return mandate, warnungen


# --------------------------------------------------------------------------
# Zuordnung + Stichworte
# --------------------------------------------------------------------------

def _beleg(k: Kandidat) -> dict[str, Any]:
    return {"az": k.az, "datei": k.datei, "stufe": k.stufe, "kategorie": k.kategorie,
            "score": k.score, "begruendung": k.begruendung}


def klassifiziere(dokument: Dokument, mandate: list[Mandat]
                  ) -> tuple[str, list[Kandidat], list[Kandidat]]:
    """(status, alle_kandidaten, treffer_kandidaten).

    status = 'eindeutig' (genau ein `treffer`), 'mehrdeutig' (mehrere
    `treffer` **oder** nur `moeglicher_treffer`), 'nicht_zuordenbar' (keiner)."""
    kandidaten = finde_kandidaten(dokument, mandate)
    treffer = [k for k in kandidaten if k.kategorie == STUFE_TREFFER]
    if len(treffer) == 1:
        status = "eindeutig"
    elif kandidaten:
        status = "mehrdeutig"
    else:
        status = "nicht_zuordenbar"
    return status, kandidaten, treffer


def _termin_stichworte(termin: dict[str, Any]) -> list[str]:
    """Stichworte = Fakten aus den Metadaten (Betreff, Ort, Teilnehmerzahl) —
    nichts Erfundenes. Garantiert nicht-leer für den Abnehmer."""
    stichworte: list[str] = []
    if termin["betreff"].strip():
        stichworte.append(termin["betreff"].strip())
    if termin["ort"].strip():
        stichworte.append(f"Ort: {termin['ort'].strip()}")
    if termin["teilnehmer"]:
        stichworte.append(f"Teilnehmerzahl: {len(termin['teilnehmer'])}")
    return stichworte or ["Kalendertermin"]


def _mail_stichworte(mail: dict[str, Any]) -> list[str]:
    stichworte: list[str] = []
    if mail["betreff"].strip():
        stichworte.append(mail["betreff"].strip())
    stichworte.append(f"E-Mail {mail['richtung']}")
    return stichworte


# --------------------------------------------------------------------------
# Report bauen
# --------------------------------------------------------------------------

def _ueberlappungen(termine: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Warnungen für zeitlich überlappende Termine (Intervall-Schnitt). Zwei
    Termine [start, ende) überlappen, wenn start_a < ende_b UND start_b <
    ende_a. Die Zeitstempel sind bereits als gültig validiert (dauer_minuten)."""
    intervalle = [(_dt.datetime.fromisoformat(t["start"]),
                   _dt.datetime.fromisoformat(t["ende"]), t) for t in termine]
    warnungen: list[dict[str, Any]] = []
    for i in range(len(intervalle)):
        for j in range(i + 1, len(intervalle)):
            start_a, ende_a, a = intervalle[i]
            start_b, ende_b, b = intervalle[j]
            if start_a < ende_b and start_b < ende_a:
                warnungen.append({
                    "typ": "termin_ueberlappung",
                    "termin_a": {"betreff": a["betreff"], "start": a["start"], "ende": a["ende"]},
                    "termin_b": {"betreff": b["betreff"], "start": b["start"], "ende": b["ende"]},
                    "hinweis": ("Zeitliche Überlappung — nicht beide Zeiträume in voller "
                                "Länge abrechnen; die Kanzlei löst die Doppelerfassung auf."),
                })
    return warnungen


def baue_report(termine: list[dict[str, Any]], mails: list[dict[str, Any]],
                mandate: list[Mandat], mandat_warnungen: list[str],
                pauschale: int | None, quelle_termine: str | None,
                quelle_mails: str | None, kontext_dir: str) -> dict[str, Any]:
    vorschlaege: list[dict[str, Any]] = []
    mehrdeutig: list[dict[str, Any]] = []
    nicht_zuordenbar: list[dict[str, Any]] = []
    ohne_zeitwert: list[dict[str, Any]] = []

    # --- Termine (haben immer einen Zeitwert aus start/ende) ---
    for termin in termine:
        dokument = Dokument(betreff=termin["betreff"],
                            textauszug=" ".join(termin["teilnehmer"]))
        status, kandidaten, treffer = klassifiziere(dokument, mandate)
        basis = {"quelle_typ": "kalender", "betreff": termin["betreff"],
                 "datum": termin["datum"]}
        if status == "eindeutig":
            leistung = {
                "datum": termin["datum"], "az": treffer[0].az, "minuten": None,
                "start": termin["start"], "ende": termin["ende"],
                "stichworte": _termin_stichworte(termin), "quelle": "kalender",
            }
            vorschlaege.append({**basis, "leistung": leistung,
                                "zuordnung": _beleg(treffer[0]), "status": "zu_bestaetigen"})
        elif status == "mehrdeutig":
            mehrdeutig.append({**basis, "kandidaten": [_beleg(k) for k in kandidaten],
                               "hinweis": MEHRDEUTIG_HINWEIS})
        else:
            nicht_zuordenbar.append({**basis, "hinweis": NICHT_ZUORDENBAR_HINWEIS})

    # --- Mails (Zeitwert nur aus der Kanzlei-Pauschale, sonst Lücke) ---
    for mail in mails:
        dokument = Dokument(betreff=mail["betreff"], absender_name=mail["absender"],
                            textauszug=" ".join(mail["empfaenger"]))
        status, kandidaten, treffer = klassifiziere(dokument, mandate)
        basis = {"quelle_typ": "mail", "betreff": mail["betreff"], "datum": mail["datum"]}
        if pauschale is None:
            ohne_zeitwert.append({
                **basis, "richtung": mail["richtung"],
                "zuordnung_status": status,
                "az": treffer[0].az if status == "eindeutig" else None,
                "kandidaten": [_beleg(k) for k in kandidaten],
                "hinweis": OHNE_ZEITWERT_HINWEIS,
            })
            continue
        if status == "eindeutig":
            leistung = {
                "datum": mail["datum"], "az": treffer[0].az, "minuten": pauschale,
                "start": None, "ende": None,
                "stichworte": _mail_stichworte(mail), "quelle": "mail",
            }
            vorschlaege.append({**basis, "leistung": leistung,
                                "zuordnung": _beleg(treffer[0]), "status": "zu_bestaetigen"})
        elif status == "mehrdeutig":
            mehrdeutig.append({**basis, "kandidaten": [_beleg(k) for k in kandidaten],
                               "hinweis": MEHRDEUTIG_HINWEIS})
        else:
            nicht_zuordenbar.append({**basis, "hinweis": NICHT_ZUORDENBAR_HINWEIS})

    warnungen = _ueberlappungen(termine)

    # --- Summen je Aktenzeichen, nur über eindeutige Vorschläge (P3) ---
    zeit_eintraege = [
        ZeitEintrag(az=v["leistung"]["az"], datum=v["leistung"]["datum"],
                    minuten=_vorschlag_minuten(v))
        for v in vorschlaege
    ]
    je_az = summe_je_az(zeit_eintraege)

    return {
        "meta": {
            "erzeugt_von": ERZEUGT_VON,
            "quelle_termine": quelle_termine,
            "quelle_mails": quelle_mails,
            "kontext_verzeichnis": kontext_dir,
            "mail_pauschale_minuten": pauschale,
            "anzahl_termine": len(termine),
            "anzahl_mails": len(mails),
            "mandat_warnungen": mandat_warnungen,
            "deterministik": DETERMINISTIK,
        },
        "vorschlaege": vorschlaege,
        "mehrdeutig": mehrdeutig,
        "nicht_zuordenbar": nicht_zuordenbar,
        "ohne_zeitwert": ohne_zeitwert,
        "warnungen": warnungen,
        "summen": {
            "je_az": dict(sorted(je_az.items())),
            "minuten_gesamt": sum(e.minuten for e in zeit_eintraege),
        },
    }


def _vorschlag_minuten(vorschlag: dict[str, Any]) -> int:
    """Effektive Minuten eines Vorschlags — einzige Quelle ist die `leistung`
    (Mail-Pauschale ODER Termin-Dauer aus start/ende), nie das Modell."""
    leistung = vorschlag["leistung"]
    if leistung["minuten"] is not None:
        return leistung["minuten"]
    return dauer_minuten(start=leistung["start"], ende=leistung["ende"], minuten=None)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--termine", help="Kalender-Metadaten (JSON, {\"termine\": [...]})")
    parser.add_argument("--mails", help="Mail-Metadaten (JSON, {\"mails\": [...]})")
    parser.add_argument("--kontext", required=True, help="kontext/-Verzeichnis (Mandate)")
    parser.add_argument("--config", help="Config (JSON, {\"mail_pauschale_minuten\": int|null})")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    if not args.termine and not args.mails:
        print("Fehler: mindestens eines von --termine/--mails ist erforderlich",
              file=sys.stderr)
        return 2
    kontext_dir = Path(args.kontext)
    if not kontext_dir.is_dir():
        print(f"Fehler: kontext-Verzeichnis nicht gefunden: {kontext_dir}", file=sys.stderr)
        return 2

    try:
        termine = lese_termine(Path(args.termine)) if args.termine else []
        mails = lese_mails(Path(args.mails)) if args.mails else []
        pauschale = lese_config(Path(args.config) if args.config else None)
        mandate, mandat_warnungen = lese_kontext_mandate(kontext_dir)
    except EingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    report = baue_report(
        termine, mails, mandate, mandat_warnungen, pauschale,
        str(args.termine) if args.termine else None,
        str(args.mails) if args.mails else None, str(kontext_dir))

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Fehler: Datei konnte nicht geschrieben werden: {exc}", file=sys.stderr)
            return 2
    else:
        print(ausgabe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
