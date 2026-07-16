#!/usr/bin/env python3
"""posteingang-ocr-verteilung — Provenienz-Validator + Routing-Executor (P2/P3).

Kein OCR-Code hier (siehe SKILL.md, Voraussetzung: Text liegt bereits als
`<scan>.txt`/`.md` neben der Scan-Datei vor, erzeugt durch ein externes,
lokales Werkzeug, oder Claude liest den Scan direkt). Die inhaltliche
Extraktion je Eingang (Absender, Datum des Schreibens, fremdes/eigenes
Aktenzeichen, Betreff, Frist-Indikatoren) macht das Modell (Claude) und
schreibt einen `eingang.json`-Entwurf nach dem Schema in schema/README.md.
Dieser Executor erfindet nichts — er ist die maschinelle Absicherung:

  (a) Schema-Konformität  — Pflichtstruktur, ISO-Datumsformat, Lücken-Disziplin,
                            Konsistenz von `fristindikatoren[].schluesselwort`
                            zu `quelle_zitat`.
  (b) Provenienz          — Datum des Schreibens, fremdes/eigenes Aktenzeichen
                            und jedes Frist-Indikator-Zitat müssen — nach
                            definierter Normalisierung — wörtlich in
                            mindestens einer Quelldatei vorkommen.
  (c) Fristrelevanz       — `fristrelevant` ist NIE eine Modell-Behauptung,
                            sondern deterministisch abgeleitet: true nur, wenn
                            mindestens ein Frist-Indikator provenienzgeprüft
                            `belegt` ist. Dies ist KEINE Fristberechnung — nur
                            ein Flag für die Zweitkontrolle (`fristenrechner`).
  (d) Mandats-Zuordnung   — delegiert vollständig an `core/calc/zuordnung/`
                            (dieselbe Bibliothek wie `email-akten-zuordnung`)
                            gegen `kontext/mandate/*.md`; kein Treffer oder
                            Mehrdeutigkeit ⇒ `unzugeordnet`, nie geraten.
  (e) Routing-Plan        — Default ist ein Dry-Run (Datei-Output, kein
                            Dateisystem-Zugriff auf das Ziel); nur mit
                            `--ausfuehren` wird tatsächlich **kopiert**
                            (nie verschoben/gelöscht/überschrieben — eine
                            bestehende Zielstruktur ist ein Fehler, kein
                            stillschweigendes Zusammenführen).

Nur Standardbibliothek. Kein Netzwerkzugriff. Liest nur die übergebenen
Dateien und das `kontext/`-Verzeichnis; schreibt nur bei `--ausfuehren` in
`kontext/posteingang/`.

Exit-Codes:
    0 — Schema in Ordnung, alle kritischen Werte belegt, Routing (falls
        `--ausfuehren`) ohne Kollision durchgeführt
    1 — mindestens ein `nicht_belegt`-Wert, ein Schema-Fehler und/oder ein
        Routing-Fehler (Kollision)
    2 — Eingabefehler (Datei/Verzeichnis fehlt, kaputtes JSON, ungültige
        Schwelle, nicht schreibbares Ziel)

CLI:
    python3 executor.py --eingang eingang.json --quelle scan.txt
                        [--quelle weitere.txt ...] --kontext <kontext-dir>
                        [--scan-datei <datei> ...] [--schwelle-moeglich 0.85]
                        [--ausfuehren] [--output report.json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
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
from zuordnung import Dokument, Kandidat, Mandat, finde_kandidaten  # noqa: E402
from zuordnung import SCHWELLE_MOEGLICH_DEFAULT, STUFE_TREFFER  # noqa: E402

ERZEUGT_VON = "posteingang-ocr-verteilung/executor.py"

STATUS_BELEGT = "belegt"
STATUS_NICHT_BELEGT = "nicht_belegt"

FRISTRELEVANT_HINWEIS = (
    "Mindestens ein Frist-Indikator ist provenienzgeprüft belegt — dieser "
    "Eingang ist gesondert der Fristenkontrolle zuzuführen (Skill "
    "'fristenrechner' als Zweitkontrolle). Dies ist KEINE Fristberechnung "
    "und KEIN Normzitat."
)

_ISO_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EingabeFehler(Exception):
    """Strukturell ungültige Eingabe — CLI fängt sie sauber ab (Exit 2)."""


# --------------------------------------------------------------------------
# Normalisierung — Datum (identisches Muster wie aktenkopf-extraktor/executor.py;
# bewusst NICHT importiert: core/calc darf nicht von plugins/legal-ops/skills/*
# abhängen, und skill-lokale Executor-Module importieren einander nicht — siehe
# core/calc/zuordnung/az.py für dieselbe Wiederverwendungs-Entscheidung. Die
# Normalisierung selbst ist mit wenigen Zeilen trivial und stabil.)
# --------------------------------------------------------------------------

_ISO_RAW = r"(\d{4})-(\d{1,2})-(\d{1,2})"
_DE_RAW = r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})"
_DATUM_ISO = re.compile(r"\b" + _ISO_RAW + r"\b")
_DATUM_DE = re.compile(r"(?<!\d)" + _DE_RAW + r"(?!\d)")


def _norm_jahr(j: str) -> str:
    if len(j) == 2:
        jj = int(j)
        return ("20" if jj <= 69 else "19") + j
    return j.zfill(4)


def _kanon_datum(jahr: str, monat: str, tag: str) -> str | None:
    j = _norm_jahr(jahr)
    try:
        datetime.date(int(j), int(monat), int(tag))
    except ValueError:
        return None
    return f"{int(j):04d}-{int(monat):02d}-{int(tag):02d}"


def _datum_kanon_wert(wert: str) -> str | None:
    wert = wert.strip()
    mi = re.fullmatch(_ISO_RAW, wert)
    if mi:
        return _kanon_datum(mi.group(1), mi.group(2), mi.group(3))
    md = re.fullmatch(_DE_RAW, wert)
    if md:
        return _kanon_datum(md.group(3), md.group(2), md.group(1))
    return None


def _datum_kanons_in_zeile(zeile: str) -> set[str]:
    res: set[str] = set()
    for m in _DATUM_ISO.finditer(zeile):
        k = _kanon_datum(m.group(1), m.group(2), m.group(3))
        if k:
            res.add(k)
    for m in _DATUM_DE.finditer(zeile):
        k = _kanon_datum(m.group(3), m.group(2), m.group(1))
        if k:
            res.add(k)
    return res


# --------------------------------------------------------------------------
# Normalisierung — Aktenzeichen / Zitat (Whitespace-Kollabierung, wie
# aktenkopf-extraktor/executor.py:_ws_collapse)
# --------------------------------------------------------------------------

def _ws_collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _kanon_ziel(wert: str, typ: str) -> str | None:
    if typ == "datum":
        return _datum_kanon_wert(wert)
    if typ in ("aktenzeichen", "zitat"):
        return _ws_collapse(wert) or None
    return None


def _zeile_belegt(zeile: str, typ: str, ziel: str) -> bool:
    if typ == "datum":
        return ziel in _datum_kanons_in_zeile(zeile)
    if typ in ("aktenzeichen", "zitat"):
        return ziel in _ws_collapse(zeile)
    return False


def finde_beleg(wert: str, typ: str,
                quellen: list[tuple[str, list[str]]]) -> dict[str, Any] | None:
    """Sucht den ersten Beleg für `wert` in den Quelldateien. Rückgabe:
    Fundstelle `{datei, zeile, zitat}` oder None (nicht belegt)."""
    ziel = _kanon_ziel(wert, typ)
    if not ziel:
        return None
    for datei, zeilen in quellen:
        for i, zeile in enumerate(zeilen, start=1):
            if _zeile_belegt(zeile, typ, ziel):
                return {"datei": datei, "zeile": i, "zitat": zeile.strip()}
    return None


# --------------------------------------------------------------------------
# Schema-Prüfung (Eingang, Lücken-Disziplin)
# --------------------------------------------------------------------------

LUECKE_PFLICHT_EINGANG = ["absender", "datum_schreiben", "betreff"]
AZ_FELDER_OPTIONAL = ["aktenzeichen_fremd", "aktenzeichen_eigen"]


def _leer(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _nichtleer(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _luecken_felder(eingang: dict[str, Any]) -> set[str]:
    felder: set[str] = set()
    luecken = eingang.get("luecken")
    if isinstance(luecken, list):
        for l in luecken:
            if isinstance(l, dict) and isinstance(l.get("feld"), str):
                felder.add(l["feld"].strip())
    return felder


def pruefe_schema(eingang: dict[str, Any]) -> list[str]:
    fehler: list[str] = []

    if not isinstance(eingang, dict):
        return ["Wurzel: eingang.json muss ein JSON-Objekt sein"]

    for schluessel, typ in (("eingang", dict), ("fristindikatoren", list),
                            ("luecken", list)):
        if schluessel not in eingang:
            fehler.append(f"Wurzel: Pflichtschlüssel `{schluessel}` fehlt")
        elif not isinstance(eingang[schluessel], typ):
            fehler.append(f"Wurzel: `{schluessel}` muss vom Typ {typ.__name__} sein")

    gedeckt = _luecken_felder(eingang)

    ei = eingang.get("eingang")
    if isinstance(ei, dict):
        for feld in LUECKE_PFLICHT_EINGANG:
            if feld not in ei:
                fehler.append(f"eingang.{feld}: Pflichtfeld fehlt")
            elif _leer(ei[feld]) and f"eingang.{feld}" not in gedeckt:
                fehler.append(f"eingang.{feld}: leer und nicht als Lücke "
                              f"ausgewiesen (Lücken-Disziplin)")
        if not _leer(ei.get("datum_schreiben")) and not _ISO_DATUM_RE.match(
                str(ei.get("datum_schreiben"))):
            fehler.append(f"eingang.datum_schreiben: kein gültiges ISO-Datum "
                          f"JJJJ-MM-TT ({ei.get('datum_schreiben')!r})")
        for feld in AZ_FELDER_OPTIONAL:
            if feld in ei and ei[feld] is not None and not _nichtleer(ei[feld]):
                fehler.append(f"eingang.{feld}: muss `null` sein, wenn kein "
                              f"Aktenzeichen erkennbar ist (kein leerer String)")

    fristindikatoren = eingang.get("fristindikatoren")
    if isinstance(fristindikatoren, list):
        for i, f in enumerate(fristindikatoren):
            if not isinstance(f, dict):
                fehler.append(f"fristindikatoren[{i}]: muss ein Objekt sein")
                continue
            for feld in ("schluesselwort", "quelle_zitat"):
                if _leer(f.get(feld)):
                    fehler.append(f"fristindikatoren[{i}].{feld}: fehlt oder leer "
                                  f"(erkannte Indikatoren sind vollständig "
                                  f"anzugeben, kein Lücken-Konzept)")
            wort = f.get("schluesselwort")
            zitat = f.get("quelle_zitat")
            if _nichtleer(wort) and _nichtleer(zitat) and wort.lower() not in zitat.lower():
                fehler.append(f"fristindikatoren[{i}]: `schluesselwort` "
                              f"({wort!r}) kommt nicht in `quelle_zitat` vor "
                              f"— inkonsistenter Entwurf")

    luecken = eingang.get("luecken")
    if isinstance(luecken, list):
        for i, l in enumerate(luecken):
            if not isinstance(l, dict):
                fehler.append(f"luecken[{i}]: muss ein Objekt sein")
                continue
            for feld in ("feld", "grund"):
                if _leer(l.get(feld)):
                    fehler.append(f"luecken[{i}].{feld}: fehlt oder leer")

    return fehler


# --------------------------------------------------------------------------
# Provenienz-Prüfung
# --------------------------------------------------------------------------

def sammle_kritische_werte(eingang: dict[str, Any]) -> list[dict[str, str]]:
    """Kritische Werte (Provenienz-Pflicht): Datum, fremdes/eigenes
    Aktenzeichen, jedes Frist-Indikator-Zitat. `absender`/`betreff` sind zu
    variabel für einen verlässlichen Wortlaut-Abgleich und werden — wie
    Name/Anschrift in aktenkopf-extraktor — nur strukturell geprüft."""
    werte: list[dict[str, str]] = []

    ei = eingang.get("eingang")
    if isinstance(ei, dict):
        if _nichtleer(ei.get("datum_schreiben")):
            werte.append({"pfad": "eingang.datum_schreiben", "typ": "datum",
                          "wert": ei["datum_schreiben"]})
        for feld in AZ_FELDER_OPTIONAL:
            if _nichtleer(ei.get(feld)):
                werte.append({"pfad": f"eingang.{feld}", "typ": "aktenzeichen",
                              "wert": ei[feld]})

    fristindikatoren = eingang.get("fristindikatoren")
    if isinstance(fristindikatoren, list):
        for i, f in enumerate(fristindikatoren):
            if isinstance(f, dict) and _nichtleer(f.get("quelle_zitat")):
                werte.append({"pfad": f"fristindikatoren[{i}].quelle_zitat",
                              "typ": "zitat", "wert": f["quelle_zitat"]})

    return werte


def pruefe_provenienz(eingang: dict[str, Any],
                      quellen: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    ergebnisse: list[dict[str, Any]] = []
    for kw in sammle_kritische_werte(eingang):
        beleg = finde_beleg(kw["wert"], kw["typ"], quellen)
        if beleg is not None:
            ergebnisse.append({
                "pfad": kw["pfad"], "typ": kw["typ"], "wert": kw["wert"],
                "status": STATUS_BELEGT, "fundstelle": beleg,
                "begruendung": f"wörtlich in Quelle gefunden (Normalisierung: {kw['typ']})",
            })
        else:
            ergebnisse.append({
                "pfad": kw["pfad"], "typ": kw["typ"], "wert": kw["wert"],
                "status": STATUS_NICHT_BELEGT, "fundstelle": None,
                "begruendung": ("kein Vorkommen in den Quelldateien "
                                f"(Normalisierung: {kw['typ']}) — Wert streichen "
                                "oder als Lücke ausweisen"),
            })
    return ergebnisse


def bestimme_fristrelevant(provenienz: list[dict[str, Any]]) -> bool:
    """Deterministisch abgeleitet: true nur, wenn mindestens ein
    `fristindikatoren[].quelle_zitat` provenienzgeprüft `belegt` ist. Ein vom
    Modell behaupteter, aber nicht belegter Indikator zählt NICHT (verhindert,
    dass eine erfundene Fristnennung das Flag setzt) — P3, Deterministik-Grenze."""
    return any(p["status"] == STATUS_BELEGT
               for p in provenienz if p["pfad"].startswith("fristindikatoren["))


# --------------------------------------------------------------------------
# Mandats-Zuordnung (delegiert an core/calc/zuordnung/, wie email-akten-zuordnung)
# --------------------------------------------------------------------------

def lese_kontext_mandate(kontext_dir: Path) -> tuple[list[Mandat], list[str]]:
    """Wie email-akten-zuordnung/executor.py:lese_kontext_mandate — bewusst
    dupliziert (skill-lokal), keine Abhängigkeit zwischen Skill-Executors."""
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


def _kandidat_dict(k: Kandidat) -> dict[str, Any]:
    return {"az": k.az, "datei": k.datei, "stufe": k.stufe, "kategorie": k.kategorie,
            "score": k.score, "begruendung": k.begruendung}


def baue_zuordnung(eingang: dict[str, Any], quelltext_gesamt: str,
                   mandate: list[Mandat], schwelle: float) -> dict[str, Any]:
    ei = eingang.get("eingang") if isinstance(eingang.get("eingang"), dict) else {}
    dokument = Dokument(
        absender_name=ei.get("absender") or "",
        absender_adresse="",
        betreff=ei.get("betreff") or "",
        textauszug=quelltext_gesamt,
    )
    kandidaten = finde_kandidaten(dokument, mandate, schwelle)

    eindeutig = len(kandidaten) == 1 and kandidaten[0].kategorie == STUFE_TREFFER
    az_fuer_routing = kandidaten[0].az if eindeutig else None
    erfordert_rueckfrage = len(kandidaten) > 1 or (
        len(kandidaten) == 1 and not eindeutig)

    if not kandidaten:
        hinweis = ("Kein Mandat trifft zu (kein_treffer) — Eingang bleibt "
                   "`unzugeordnet`, bis die Kanzlei das zuständige Mandat "
                   "manuell bestimmt. Es wird kein Mandat geraten.")
    elif erfordert_rueckfrage:
        hinweis = ("Mehr als ein Kandidat oder nur ein `moeglicher_treffer` — "
                   "dies ist immer eine Rückfrage an die Kanzlei, welches "
                   "Mandat zutrifft. Der Eingang wird vorerst `unzugeordnet` "
                   "geroutet, nie automatisch einem Kandidaten zugewiesen.")
    else:
        hinweis = None

    return {
        "kandidaten": [_kandidat_dict(k) for k in kandidaten],
        "kein_treffer": not kandidaten,
        "eindeutig": eindeutig,
        "az_fuer_routing": az_fuer_routing,
        "erfordert_rueckfrage": erfordert_rueckfrage,
        "hinweis": hinweis,
    }


# --------------------------------------------------------------------------
# Routing-Plan (Dry-Run default; --ausfuehren kopiert tatsächlich)
# --------------------------------------------------------------------------

SLUG_MAX_LEN = 60
_SLUG_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                              "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_SLUG_NICHT_ERLAUBT_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, fallback: str) -> str:
    """Slug-Regel (identisch zu email-akten-zuordnung/executor.py:betreff_slug,
    hier auf den Absender angewandt): Umlaute transliterieren, kleinschreiben,
    alles außer a-z/0-9 zu '-' kollabieren, Ränder trimmen, kürzen."""
    basis = (text or "").translate(_SLUG_UMLAUT).lower()
    slug = _SLUG_NICHT_ERLAUBT_RE.sub("-", basis).strip("-")
    slug = slug[:SLUG_MAX_LEN].rstrip("-")
    return slug or fallback


def baue_routing_plan(eingang: dict[str, Any], zuordnung: dict[str, Any],
                      scan_dateien: list[Path], kontext_dir: Path,
                      ausfuehren: bool) -> dict[str, Any]:
    ei = eingang.get("eingang") if isinstance(eingang.get("eingang"), dict) else {}
    datum = ei.get("datum_schreiben")

    if not datum or not _ISO_DATUM_RE.match(str(datum)):
        return {
            "moeglich": False,
            "ziel_ordner": None,
            "dateien": [],
            "ausgefuehrt": False,
            "fehler": None,
            "hinweis": ("Kein auswertbares Datum des Schreibens — der Zielordner "
                        "(`JJJJ-MM-TT_<az|unzugeordnet>_<absender-slug>`) kann "
                        "nicht automatisch gebildet werden. Datum manuell "
                        "ergänzen, kein Datum wird erfunden."),
        }

    az_teil = zuordnung.get("az_fuer_routing") or "unzugeordnet"
    absender_slug = _slug(ei.get("absender") or "", "unbekannter-absender")
    ordner_name = f"{datum}_{az_teil}_{absender_slug}"
    ziel_ordner_rel = f"posteingang/{ordner_name}"
    ziel_ordner_abs = kontext_dir / "posteingang" / ordner_name

    dateien_plan = [
        {"quelle": str(q), "ziel": f"{ziel_ordner_rel}/{q.name}"}
        for q in scan_dateien
    ]

    plan: dict[str, Any] = {
        "moeglich": True,
        "ziel_ordner": ziel_ordner_rel,
        "dateien": dateien_plan,
        "ausgefuehrt": False,
        "fehler": None,
        "hinweis": ("Dry-Run — kein Dateisystemzugriff auf das Ziel. Mit "
                    "`--ausfuehren` tatsächlich kopieren (nie verschieben, nie "
                    "löschen, nie überschreiben)." if not dateien_plan else
                    "Dry-Run — mit `--ausfuehren` tatsächlich kopieren (nie "
                    "löschen, nie überschreiben)."),
    }

    if not ausfuehren or not dateien_plan:
        if ausfuehren and not dateien_plan:
            plan["hinweis"] = ("Keine `--scan-datei` angegeben — nichts zu "
                               "kopieren, Plan bleibt unausgeführt.")
        return plan

    if ziel_ordner_abs.exists():
        plan["fehler"] = (f"Kollision: Zielordner existiert bereits "
                          f"({ziel_ordner_rel}) — es wird nie überschrieben "
                          f"oder zusammengeführt.")
        return plan
    for q in scan_dateien:
        if not q.is_file():
            plan["fehler"] = f"Quelldatei nicht gefunden: {q}"
            return plan

    ziel_ordner_abs.mkdir(parents=True)
    for q in scan_dateien:
        shutil.copy2(q, ziel_ordner_abs / q.name)
    plan["ausgefuehrt"] = True
    plan["hinweis"] = f"Kopiert nach {ziel_ordner_rel} (Original unverändert, nichts gelöscht)."
    return plan


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def baue_report(eingang: dict[str, Any], quellen: list[tuple[str, list[str]]],
                eingang_datei: str, kontext_dir: Path, scan_dateien: list[Path],
                schwelle: float, ausfuehren: bool) -> dict[str, Any]:
    schema_fehler = pruefe_schema(eingang)
    provenienz = pruefe_provenienz(eingang, quellen)
    fristrelevant = bestimme_fristrelevant(provenienz)

    belegt = sum(1 for p in provenienz if p["status"] == STATUS_BELEGT)
    nicht_belegt = sum(1 for p in provenienz if p["status"] == STATUS_NICHT_BELEGT)

    luecken = eingang.get("luecken") if isinstance(eingang.get("luecken"), list) else []

    mandate, mandat_warnungen = lese_kontext_mandate(kontext_dir)
    quelltext_gesamt = "\n".join(zeilen_text for _, zeilen in quellen
                                 for zeilen_text in zeilen)
    zuordnung = baue_zuordnung(eingang, quelltext_gesamt, mandate, schwelle)
    routing_plan = baue_routing_plan(eingang, zuordnung, scan_dateien, kontext_dir,
                                     ausfuehren)

    return {
        "meta": {
            "erzeugt_von": ERZEUGT_VON,
            "eingang_datei": eingang_datei,
            "quelldateien": [datei for datei, _ in quellen],
            "kontext_verzeichnis": str(kontext_dir),
            "schwelle_moeglich": schwelle,
            "anzahl_kritische_werte": len(provenienz),
            "anzahl_mandate": len(mandate),
            "mandat_warnungen": mandat_warnungen,
            "hinweis": ("Der Skill berechnet NIE eine Frist. `fristrelevant` ist "
                        "ein deterministisch abgeleitetes Flag, keine "
                        "Fristberechnung — Fristen ausschließlich über den "
                        "Skill fristenrechner (Zweitkontrolle)."),
        },
        "schema_ok": not schema_fehler,
        "schema_fehler": schema_fehler,
        "provenienz": provenienz,
        "luecken": luecken,
        "fristrelevant": fristrelevant,
        "fristrelevant_hinweis": FRISTRELEVANT_HINWEIS if fristrelevant else None,
        "zuordnung": zuordnung,
        "routing_plan": routing_plan,
        "zusammenfassung": {
            "belegt": belegt,
            "nicht_belegt": nicht_belegt,
            "schema_fehler": len(schema_fehler),
        },
    }


def report_ist_sauber(report: dict[str, Any]) -> bool:
    z = report["zusammenfassung"]
    if z["nicht_belegt"] != 0 or z["schema_fehler"] != 0:
        return False
    if report["routing_plan"].get("fehler"):
        return False
    return True


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eingang", required=True,
                        help="Vom Modell erzeugter Eingangs-Entwurf (JSON)")
    parser.add_argument("--quelle", action="append", required=True,
                        help="Extrahierter Scan-Text (.txt/.md). Mehrfach angebbar.")
    parser.add_argument("--kontext", required=True, help="kontext/-Verzeichnis (Mandate)")
    parser.add_argument("--scan-datei", action="append", default=[], dest="scan_datei",
                        help="Datei(en), die beim Routing kopiert werden sollen "
                             "(Scan-Original und/oder Textauszug). Mehrfach angebbar.")
    parser.add_argument("--schwelle-moeglich", type=float, default=SCHWELLE_MOEGLICH_DEFAULT,
                        help=f"Fuzzy-Schwelle für Stufe Z4 (Default {SCHWELLE_MOEGLICH_DEFAULT})")
    parser.add_argument("--ausfuehren", action="store_true",
                        help="Routing-Plan tatsächlich ausführen (kopieren). "
                             "Ohne diese Option nur Dry-Run-Plan.")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    eingang_pfad = Path(args.eingang)
    if not eingang_pfad.is_file():
        print(f"Fehler: Eingang-Datei nicht gefunden: {eingang_pfad}", file=sys.stderr)
        return 2

    kontext_dir = Path(args.kontext)
    if not kontext_dir.is_dir():
        print(f"Fehler: kontext-Verzeichnis nicht gefunden: {kontext_dir}", file=sys.stderr)
        return 2

    if not (0.0 <= args.schwelle_moeglich <= 1.0):
        print(f"Fehler: --schwelle-moeglich muss zwischen 0.0 und 1.0 liegen, "
              f"ist: {args.schwelle_moeglich}", file=sys.stderr)
        return 2

    quellen: list[tuple[str, list[str]]] = []
    for q in args.quelle:
        qp = Path(q)
        if not qp.is_file():
            print(f"Fehler: Quelldatei nicht gefunden: {qp}", file=sys.stderr)
            return 2
        quellen.append((str(qp), qp.read_text(encoding="utf-8").splitlines()))

    scan_dateien: list[Path] = []
    for s in args.scan_datei:
        sp = Path(s)
        if not sp.is_file():
            print(f"Fehler: Scan-Datei nicht gefunden: {sp}", file=sys.stderr)
            return 2
        scan_dateien.append(sp)

    try:
        eingang = json.loads(eingang_pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Fehler: Eingang-Datei ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 2

    try:
        report = baue_report(eingang, quellen, eingang_datei=str(eingang_pfad),
                             kontext_dir=kontext_dir, scan_dateien=scan_dateien,
                             schwelle=args.schwelle_moeglich, ausfuehren=args.ausfuehren)
    except OSError as exc:
        print(f"Fehler: Routing konnte nicht ausgeführt werden: {exc}", file=sys.stderr)
        return 2

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Fehler: Report konnte nicht geschrieben werden: {exc}", file=sys.stderr)
            return 2
    else:
        print(ausgabe)

    return 0 if report_ist_sauber(report) else 1


if __name__ == "__main__":
    sys.exit(main())
