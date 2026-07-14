#!/usr/bin/env python3
"""email-akten-zuordnung — deterministischer Zuordnungs-Executor (P2/P3).

Ordnet eingehende E-Mails (EML-Dateien oder gleichwertige Metadaten aus dem
kontext-sync/M365-Weg) den Mandaten aus `kontext/mandate/*.md` zu und schlägt
je E-Mail eine Priorität und eine Ablage in `posteingang/` vor. Die
inhaltliche Entscheidung (welche Zuordnung stimmt, ob und wohin abgelegt
wird) bleibt immer bei der Kanzlei/Claude — dieser Executor liefert nur
deterministische Kandidaten, nie eine automatische Ablage.

## Zuordnung (Stufen Z0-Z4)

Delegiert vollständig an `core/calc/zuordnung/` (siehe dort für die
Stufen-Definition und Schwellenwert-Begründung):

    Z0  eigenes Aktenzeichen wörtlich in Betreff/Textauszug   -> treffer
    Z1  Parteiname als Phrase im Text                          -> treffer
    Z2  alle Namens-Tokens im Text (Reihenfolge egal)          -> treffer
    Z3  Namens-Tokens phonetisch (Kölner Phonetik) im Text     -> moeglicher_treffer
    Z4  Namens-Tokens fuzzy-ähnlich im Text (Schwelle 0.85)    -> moeglicher_treffer

Kein Kandidat für eine E-Mail -> `kein_treffer` (Lücke, nie geraten).

## Fristverdacht (regelbasiert, dokumentierte Wortliste)

Enthält Betreff **oder** Textauszug eines der Signalwörter in
`FRISTVERDACHT_WOERTER` (Frist, Urteil, Beschluss, Bescheid, Zustellung,
Mahnung, Kündigung, Klage, einstweilige — Substring-Suche, case-insensitiv,
damit auch zusammengesetzte Wörter wie "Kündigungsschreiben" erkannt
werden), wird `fristverdacht: true` gesetzt samt einem statischen
Hinweistext. Der Hinweistext enthält **keine Fristberechnung und kein
Normzitat** — er verweist ausschließlich auf die Zweitkontrolle durch den
Skill `fristenrechner`. `prioritaet` ist `hoch`, wenn `fristverdacht` **oder**
mindestens ein Kandidat der Kategorie `treffer` vorliegt, sonst `normal`.

⚠️ **Begrenzte Genauigkeit der Wortliste**: nur echte Umlaute erkannt (keine
ASCII-Transliteration wie "kuendigung"), Substring-Suche kann in seltenen
Fällen auch inhaltlich unpassende Treffer erzeugen (z. B. "frist" in einem
unrelated zusammengesetzten Wort) — bewusster Kompromiss zugunsten des
Rückrufs, siehe `schema/README.md`.

## PII-Minimierung

Der Report enthält NUR Metadaten (Absender, Betreff, Datum) plus einen
Textauszug von höchstens `TEXTAUSZUG_MAX_LEN` Zeichen — nie den vollen
E-Mail-Text. § 203 StGB / DSGVO: Mail-Volltexte bleiben lokal beim
Ursprungssystem, nur der gekürzte Auszug landet im Report.

## CLI

    python3 executor.py --eml <datei-oder-verzeichnis> --kontext <kontext-dir>
                        [--output report.json] [--schwelle-moeglich 0.85]
    python3 executor.py --input <metadaten.json> --kontext <kontext-dir>
                        [--output report.json] [--schwelle-moeglich 0.85]

`--eml` und `--input` schließen sich gegenseitig aus, genau eines ist
Pflicht. `--eml` akzeptiert eine einzelne `.eml`-Datei oder ein Verzeichnis
(alle `*.eml`-Dateien darin, sortiert). `--input` erwartet ein JSON-**Array**
von Dokument-Objekten (auch bei nur einem Dokument), Feldkontrakt:
[`schema/README.md`](schema/README.md).

Exit-Codes: 0 = Report erzeugt, 2 = Eingabefehler (kein Traceback).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from email import policy
from email.parser import BytesParser
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
from zuordnung import Dokument, Kandidat, Mandat, finde_kandidaten  # noqa: E402
from zuordnung import SCHWELLE_MOEGLICH_DEFAULT, STUFE_TREFFER  # noqa: E402

ERZEUGT_VON = "email-akten-zuordnung/executor.py"

TEXTAUSZUG_MAX_LEN = 500

FRISTVERDACHT_WOERTER: tuple[str, ...] = (
    "frist", "urteil", "beschluss", "bescheid", "zustellung", "mahnung",
    "kündigung", "klage", "einstweilige",
)

FRISTVERDACHT_HINWEIS = (
    "Signalwort für eine mögliche Frist erkannt — diese Post gesondert der "
    "Fristenkontrolle zuführen (Skill 'fristenrechner' als Zweitkontrolle). "
    "Dies ist KEINE Fristberechnung und KEIN Normzitat."
)

SLUG_MAX_LEN = 60
_SLUG_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                              "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_SLUG_NICHT_ERLAUBT_RE = re.compile(r"[^a-z0-9]+")
_ISO_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EingabeFehler(Exception):
    """Strukturell ungültige Eingabe — CLI fängt sie sauber ab (Exit 2)."""


# --------------------------------------------------------------------------
# EML-Parsing (Python-stdlib `email`-Modul, RFC-2047-Header über policy.default)
# --------------------------------------------------------------------------

def _header_text(msg: Any, feld: str) -> str:
    wert = msg.get(feld)
    return str(wert) if wert is not None else ""


def _absender(msg: Any) -> tuple[str, str]:
    """(absender_name, absender_adresse) aus dem `From`-Header.

    Fällt auf die reine Adresse zurück, wenn kein Anzeigename gesetzt ist;
    fällt auf leere Strings zurück, wenn der Header fehlt oder von der
    `email`-Bibliothek nicht als Adress-Header erkannt wird (defensiv, kein
    Traceback bei kaputten/exotischen From-Headern)."""
    header = msg.get("From")
    if header is None:
        return "", ""
    try:
        adressen = header.addresses
    except AttributeError:
        return str(header), ""
    if not adressen:
        return str(header), ""
    erster = adressen[0]
    name = erster.display_name or erster.addr_spec or ""
    adresse = erster.addr_spec or ""
    return name, adresse


def _empfaenger(msg: Any, feld: str) -> list[str]:
    header = msg.get(feld)
    if header is None:
        return []
    try:
        return [a.addr_spec for a in header.addresses if a.addr_spec]
    except AttributeError:
        return [str(header)]


def _textauszug(msg: Any) -> tuple[str, bool]:
    """(Auszug, gekürzt) aus dem ersten `text/plain`-Teil, max.
    `TEXTAUSZUG_MAX_LEN` Zeichen. PII-Minimierung: der volle Body wird nie
    zurückgegeben, nur dieser Auszug."""
    try:
        teil = msg.get_body(preferencelist=("plain",))
    except Exception:
        return "", False
    if teil is None:
        return "", False
    try:
        inhalt = teil.get_content()
    except Exception:
        return "", False
    gekuerzt = len(inhalt) > TEXTAUSZUG_MAX_LEN
    return inhalt[:TEXTAUSZUG_MAX_LEN], gekuerzt


def _mail_datum_iso(msg: Any) -> str | None:
    header = msg.get("Date")
    if header is None:
        return None
    try:
        zeitpunkt = header.datetime
    except (AttributeError, ValueError, TypeError):
        return None
    if zeitpunkt is None:
        return None
    return zeitpunkt.date().isoformat()


def parse_eml_datei(pfad: Path) -> dict[str, Any]:
    try:
        rohbytes = pfad.read_bytes()
    except OSError as exc:
        raise EingabeFehler(f"{pfad}: Datei nicht lesbar ({exc})") from exc
    msg = BytesParser(policy=policy.default).parsebytes(rohbytes)
    absender_name, absender_adresse = _absender(msg)
    textauszug, gekuerzt = _textauszug(msg)
    return {
        "quelle": str(pfad),
        "absender_name": absender_name,
        "absender_adresse": absender_adresse,
        "empfaenger": _empfaenger(msg, "To"),
        "cc": _empfaenger(msg, "Cc"),
        "betreff": _header_text(msg, "Subject"),
        "textauszug": textauszug,
        "textauszug_gekuerzt": gekuerzt,
        "datum": _mail_datum_iso(msg),
    }


def lese_eml_quelle(pfad: Path) -> list[dict[str, Any]]:
    if pfad.is_dir():
        dateien = sorted(pfad.glob("*.eml"))
        if not dateien:
            raise EingabeFehler(f"{pfad}: keine .eml-Dateien im Verzeichnis gefunden")
    elif pfad.is_file():
        dateien = [pfad]
    else:
        raise EingabeFehler(f"{pfad}: Datei oder Verzeichnis nicht gefunden")
    return [parse_eml_datei(d) for d in dateien]


# --------------------------------------------------------------------------
# --input-Metadaten (kontext-sync/M365-Weg): JSON-Array gleicher Feldkontrakt
# --------------------------------------------------------------------------

def lese_metadaten_json(pfad: Path) -> list[dict[str, Any]]:
    if not pfad.is_file():
        raise EingabeFehler(f"{pfad}: Datei nicht gefunden")
    try:
        text = pfad.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise EingabeFehler(f"{pfad}: Datei nicht lesbar ({exc})") from exc
    try:
        daten = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EingabeFehler(f"{pfad}: kein gültiges JSON: {exc}") from exc
    if not isinstance(daten, list):
        raise EingabeFehler(
            f"{pfad}: JSON muss ein Array von Dokument-Objekten sein "
            f"(auch bei nur einem Dokument)")
    if not daten:
        raise EingabeFehler(f"{pfad}: leeres Array — keine Dokumente")

    ergebnis: list[dict[str, Any]] = []
    for i, eintrag in enumerate(daten, start=1):
        ort = f"Eintrag {i}"
        if not isinstance(eintrag, dict):
            raise EingabeFehler(f"{pfad}, {ort}: kein JSON-Objekt")
        roh_datum = eintrag.get("datum")
        datum = str(roh_datum).strip() if roh_datum else None
        if datum and not _ISO_DATUM_RE.match(datum):
            raise EingabeFehler(
                f"{pfad}, {ort}: 'datum' ist kein ISO-Datum (JJJJ-MM-TT): {datum!r}")
        roh_text = str(eintrag.get("textauszug") or "")
        ergebnis.append({
            "quelle": str(eintrag.get("quelle") or f"{pfad}#{i}"),
            "absender_name": str(eintrag.get("absender_name") or ""),
            "absender_adresse": str(eintrag.get("absender_adresse") or ""),
            "empfaenger": [str(e) for e in (eintrag.get("empfaenger") or [])],
            "cc": [str(e) for e in (eintrag.get("cc") or [])],
            "betreff": str(eintrag.get("betreff") or ""),
            "textauszug": roh_text[:TEXTAUSZUG_MAX_LEN],
            "textauszug_gekuerzt": len(roh_text) > TEXTAUSZUG_MAX_LEN,
            "datum": datum,
        })
    return ergebnis


# --------------------------------------------------------------------------
# Fristverdacht / Priorität
# --------------------------------------------------------------------------

def fristverdacht(betreff: str, textauszug: str) -> bool:
    """Regelbasiert, dokumentierte Wortliste (`FRISTVERDACHT_WOERTER`):
    case-insensitive Substring-Suche über Betreff + Textauszug."""
    text = f"{betreff} {textauszug}".lower()
    return any(wort in text for wort in FRISTVERDACHT_WOERTER)


def prioritaet(hat_fristverdacht: bool, kandidaten: list[Kandidat]) -> str:
    """`hoch` = Fristverdacht ODER mindestens ein `treffer`-Kandidat, sonst `normal`."""
    hat_treffer = any(k.kategorie == STUFE_TREFFER for k in kandidaten)
    return "hoch" if (hat_fristverdacht or hat_treffer) else "normal"


# --------------------------------------------------------------------------
# Ablage-Vorschlag (Dateiname + Kommunikations-Zeile)
# --------------------------------------------------------------------------

def betreff_slug(betreff: str) -> str:
    """Slug-Regel: Umlaute transliterieren, kleinschreiben, alles außer
    a-z/0-9 zu '-' kollabieren, Ränder trimmen, auf `SLUG_MAX_LEN` kürzen.
    Leerer/fehlender Betreff ergibt `ohne-betreff` (kein erfundener Titel)."""
    basis = (betreff or "").translate(_SLUG_UMLAUT).lower()
    slug = _SLUG_NICHT_ERLAUBT_RE.sub("-", basis).strip("-")
    slug = slug[:SLUG_MAX_LEN].rstrip("-")
    return slug or "ohne-betreff"


def baue_ablage_vorschlag(datum: str | None, betreff: str) -> dict[str, Any]:
    """Ziel: `posteingang/JJJJ-MM-TT-<betreff-slug>.eml` + die fertige
    Kommunikations-Zeile nach dem Format aus `core/context/README.md`
    (`## Kommunikation`: `Datum — Betreff — [Datei](relativer-Link)`,
    relativ aus Sicht von `mandate/<az>.md`, also `../posteingang/...`).

    Ohne auswertbares ISO-Datum wird NIE ein Datum erfunden — stattdessen
    `moeglich: false` mit Hinweis (Lücke, manuell zu ergänzen)."""
    if not datum or not _ISO_DATUM_RE.match(datum):
        return {
            "moeglich": False,
            "dateiname": None,
            "kommunikations_zeile": None,
            "hinweis": ("Kein auswertbares Datum in Mail-Header/Metadaten gefunden — "
                        "Ablage-Dateiname und Kommunikations-Zeile können nicht "
                        "automatisch gebildet werden. Datum manuell ergänzen, kein "
                        "Datum wird erfunden."),
        }
    slug = betreff_slug(betreff)
    dateiname_basis = f"{datum}-{slug}.eml"
    betreff_anzeige = betreff.strip() if betreff and betreff.strip() else "(ohne Betreff)"
    return {
        "moeglich": True,
        "dateiname": f"posteingang/{dateiname_basis}",
        "kommunikations_zeile": (f"{datum} — {betreff_anzeige} — "
                                  f"[Datei](../posteingang/{dateiname_basis})"),
        "hinweis": None,
    }


# --------------------------------------------------------------------------
# Mandatsliste (kontext/mandate/*.md über core/context/schema.py)
# --------------------------------------------------------------------------

def lese_kontext_mandate(kontext_dir: Path) -> tuple[list[Mandat], list[str]]:
    """Liest `kontext/mandate/*.md` über `lese_mandate()` (keine erneute
    Schema-Prüfung, dafür ist `core/context/validator.py` zuständig). Mandate
    ohne Aktenzeichen können nicht zugeordnet werden — sie werden
    übersprungen und als Warnung ausgewiesen, statt geraten zu werden."""
    warnungen: list[str] = []
    mandate: list[Mandat] = []
    for pfad, fm in lese_mandate(kontext_dir):
        az = (fm.get("az") or (None, None))[0]
        if not az:
            warnungen.append(f"{pfad}: kein Aktenzeichen im Frontmatter — Mandat wird "
                              f"übersprungen (nicht zuordenbar)")
            continue
        mandant = (fm.get("mandant") or (None, None))[0] or ""
        gegenseite = (fm.get("gegenseite") or (None, None))[0]
        try:
            datei_rel = str(pfad.relative_to(kontext_dir))
        except ValueError:
            datei_rel = str(pfad)
        mandate.append(Mandat(az=az, mandant=mandant, gegenseite=gegenseite, datei=datei_rel))
    return mandate, warnungen


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def _kandidat_dict(k: Kandidat) -> dict[str, Any]:
    return {"az": k.az, "datei": k.datei, "stufe": k.stufe, "kategorie": k.kategorie,
            "score": k.score, "begruendung": k.begruendung}


def baue_dokument_eintrag(doc_meta: dict[str, Any], mandate: list[Mandat],
                           schwelle: float) -> dict[str, Any]:
    dokument = Dokument(
        absender_name=doc_meta["absender_name"],
        absender_adresse=doc_meta["absender_adresse"],
        betreff=doc_meta["betreff"],
        textauszug=doc_meta["textauszug"],
    )
    kandidaten = finde_kandidaten(dokument, mandate, schwelle)
    hat_fristverdacht = fristverdacht(dokument.betreff, dokument.textauszug)

    return {
        "quelle": doc_meta["quelle"],
        "absender_name": dokument.absender_name,
        "absender_adresse": dokument.absender_adresse,
        "empfaenger": doc_meta.get("empfaenger", []),
        "cc": doc_meta.get("cc", []),
        "betreff": dokument.betreff,
        "textauszug": dokument.textauszug,
        "textauszug_gekuerzt": doc_meta.get("textauszug_gekuerzt", False),
        "datum": doc_meta.get("datum"),
        "kandidaten": [_kandidat_dict(k) for k in kandidaten],
        "kein_treffer": not kandidaten,
        "fristverdacht": hat_fristverdacht,
        "fristverdacht_hinweis": FRISTVERDACHT_HINWEIS if hat_fristverdacht else None,
        "prioritaet": prioritaet(hat_fristverdacht, kandidaten),
        "ablage_vorschlag": baue_ablage_vorschlag(doc_meta.get("datum"), dokument.betreff),
    }


def baue_report(dokumente_meta: list[dict[str, Any]], mandate: list[Mandat],
                mandat_warnungen: list[str], schwelle: float, quelle_typ: str,
                kontext_dir: str) -> dict[str, Any]:
    eintraege = [baue_dokument_eintrag(m, mandate, schwelle) for m in dokumente_meta]
    return {
        "meta": {
            "erzeugt_von": ERZEUGT_VON,
            "quelle_typ": quelle_typ,
            "kontext_verzeichnis": kontext_dir,
            "schwelle_moeglich": schwelle,
            "textauszug_max_len": TEXTAUSZUG_MAX_LEN,
            "anzahl_dokumente": len(eintraege),
            "anzahl_mandate": len(mandate),
            "mandat_warnungen": mandat_warnungen,
        },
        "dokumente": eintraege,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    quelle = parser.add_mutually_exclusive_group(required=True)
    quelle.add_argument("--eml", help="EML-Datei oder Verzeichnis mit .eml-Dateien")
    quelle.add_argument("--input", help="Metadaten als JSON-Array (kontext-sync/M365-Weg)")
    parser.add_argument("--kontext", required=True, help="kontext/-Verzeichnis (Mandate)")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    parser.add_argument("--schwelle-moeglich", type=float, default=SCHWELLE_MOEGLICH_DEFAULT,
                        help=f"Fuzzy-Schwelle für Stufe Z4 (Default {SCHWELLE_MOEGLICH_DEFAULT})")
    args = parser.parse_args(argv)

    kontext_dir = Path(args.kontext)
    if not kontext_dir.is_dir():
        print(f"Fehler: kontext-Verzeichnis nicht gefunden: {kontext_dir}", file=sys.stderr)
        return 2
    if not (0.0 <= args.schwelle_moeglich <= 1.0):
        print(f"Fehler: --schwelle-moeglich muss zwischen 0.0 und 1.0 liegen, "
              f"ist: {args.schwelle_moeglich}", file=sys.stderr)
        return 2

    try:
        if args.eml:
            dokumente_meta = lese_eml_quelle(Path(args.eml))
            quelle_typ = "eml"
        else:
            dokumente_meta = lese_metadaten_json(Path(args.input))
            quelle_typ = "input"
        mandate, mandat_warnungen = lese_kontext_mandate(kontext_dir)
    except EingabeFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    report = baue_report(dokumente_meta, mandate, mandat_warnungen,
                          args.schwelle_moeglich, quelle_typ, str(kontext_dir))

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
    else:
        print(ausgabe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
