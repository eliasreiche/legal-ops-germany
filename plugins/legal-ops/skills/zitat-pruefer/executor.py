#!/usr/bin/env python3
"""zitat-pruefer — deterministischer Executor (P2/P3).

Extrahiert deutsche Rechtszitate (Normen, Gerichtsentscheidungen, Fundstellen)
aus einem Text-/Markdown-Dokument und vergibt für jedes Zitat einen der drei
Zustände aus CONVENTIONS.md:

    verifiziert   — gegen eine mitgelieferte Quellen-Registry geprüft und bestätigt
    nicht_pruefbar — keine Registry-Angabe zu diesem Zitat vorhanden
    abweichend    — Registry-Angabe widerspricht dem Zitat (mit Begründung)

Zusätzlich, unabhängig von der Registry: reine Formatprüfungen (bekanntes
Gesetzeskürzel, plausible Abs./Satz/Nr.-Syntax, §/§§-Konsistenz).

WICHTIG (Deterministik-Grenze, P3): Dieses Modul entscheidet die Zustände.
Ein Modell (Claude) darf den Report orchestrieren und in Markdown mit den
drei Markern (✅/⚠️/❌) darstellen und erläutern — es darf keinen Zustand
selbst vergeben oder überschreiben.

Nur Standardbibliothek. Kein Netzwerkzugriff. Datei rein → JSON-Report raus.

CLI:
    python3 executor.py --input DATEI.md [--registry REGISTRY.json]
                         [--schema-dir SCHEMA_DIR] [--output REPORT.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

SCHEMA_DIR_DEFAULT = Path(__file__).resolve().parent / "schema"

ZUSTAND_VERIFIZIERT = "verifiziert"
ZUSTAND_NICHT_PRUEFBAR = "nicht_pruefbar"
ZUSTAND_ABWEICHEND = "abweichend"

MARKER = {
    ZUSTAND_VERIFIZIERT: "✅",       # ✅
    ZUSTAND_NICHT_PRUEFBAR: "⚠️",  # ⚠️
    ZUSTAND_ABWEICHEND: "❌",        # ❌
}

# Zustands-Rangfolge für die Aggregation von Ketten-Zitaten (§§ 53, 97 StPO):
# der "schlechteste" Teilzustand bestimmt den Gesamtzustand.
_RANG = {ZUSTAND_ABWEICHEND: 2, ZUSTAND_NICHT_PRUEFBAR: 1, ZUSTAND_VERIFIZIERT: 0}


def _aggregiere(zustaende: list[str]) -> str:
    return max(zustaende, key=lambda z: _RANG[z])


# --------------------------------------------------------------------------
# Schema laden
# --------------------------------------------------------------------------

def lade_kuerzelliste(schema_dir: Path) -> set[str]:
    daten = json.loads((schema_dir / "gesetzeskuerzel.json").read_text(encoding="utf-8"))
    return set(daten["kuerzel"])


def lade_gerichte(schema_dir: Path) -> dict[str, list[str]]:
    daten = json.loads((schema_dir / "gerichte.json").read_text(encoding="utf-8"))
    return {
        "ohne_ort": daten["oberste_bundesgerichte"] + daten["europaeisch"] + daten["sonstige"],
        "mit_ort": daten["mit_ortszusatz"],
    }


def lade_zeitschriften(schema_dir: Path) -> list[str]:
    daten = json.loads((schema_dir / "zeitschriften.json").read_text(encoding="utf-8"))
    # Längste zuerst, damit z. B. "NJW-RR" vor "NJW" greift.
    return sorted(daten["zeitschriften"], key=len, reverse=True)


class RegistryFehler(Exception):
    """R2/R3: strukturell ungültige Quellen-Registry (kaputtes JSON oder
    Einträge ohne Pflichtfelder) — wird vom CLI sauber abgefangen (Exit 2)
    statt als Traceback durchzuschlagen."""


def validiere_registry(daten: dict[str, Any]) -> None:
    """R3: Registry-Einträge ohne Pflichtfelder (z. B. `kuerzel`/`paragraph`
    bei einer Norm) würden weiter unten in pruefe_norm()/pruefe_entscheidung()/
    pruefe_fundstelle() zu einem KeyError-Traceback führen, sobald ein
    beliebiges Zitat gegen die Registry geprüft wird. Deshalb hier einmalig
    beim Laden validieren und mit klarer Fehlermeldung ablehnen."""
    for i, n in enumerate(daten.get("normen", [])):
        for feld in ("kuerzel", "paragraph"):
            if feld not in n or not str(n[feld]).strip():
                raise RegistryFehler(
                    f"normen[{i}]: Pflichtfeld '{feld}' fehlt oder ist leer")
    for i, e in enumerate(daten.get("entscheidungen", [])):
        for feld in ("gericht", "aktenzeichen"):
            if feld not in e or not str(e[feld]).strip():
                raise RegistryFehler(
                    f"entscheidungen[{i}]: Pflichtfeld '{feld}' fehlt oder ist leer")
    for i, f in enumerate(daten.get("fundstellen", [])):
        for feld in ("zeitschrift", "jahr", "seite"):
            if feld not in f:
                raise RegistryFehler(
                    f"fundstellen[{i}]: Pflichtfeld '{feld}' fehlt oder ist leer")


def lade_registry(pfad: Path | None) -> dict[str, Any]:
    if pfad is None:
        return {"normen": [], "entscheidungen": [], "fundstellen": []}
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    if not isinstance(daten, dict):
        raise RegistryFehler("Registry muss ein JSON-Objekt mit den Schlüsseln "
                              "normen/entscheidungen/fundstellen sein")
    daten.setdefault("normen", [])
    daten.setdefault("entscheidungen", [])
    daten.setdefault("fundstellen", [])
    validiere_registry(daten)
    return daten


# --------------------------------------------------------------------------
# Regex-Bausteine
# --------------------------------------------------------------------------

# Römische Zahlen längster-zuerst, für SGB-Bücher (SGB II, SGB XII, ...).
_ROEMISCH = ("XII", "VIII", "VII", "III", "XI", "IV", "IX", "VI", "II",
             "X", "V", "I")
_ROEMISCH_ALT = "|".join(_ROEMISCH)

# I–XX für die Absatz-Kurzschreibweise (B1: "§ 823 I BGB", auch "Abs. I") —
# ein größerer Bereich als bei SGB-Büchern (die nur bis XII gehen), da
# Absatzzählungen in Ausnahmefällen weiter reichen. Längster-zuerst, damit
# z. B. "XVIII" vor "X" greift.
_ROEMISCH_ABS = ("XVIII", "VIII", "XIII", "XVII", "III", "VII", "XII", "XIV",
                  "XVI", "XIX", "II", "IV", "VI", "IX", "XI", "XV", "XX",
                  "I", "V", "X")
_ROEMISCH_ABS_ALT = "|".join(_ROEMISCH_ABS)

# NBSP (U+00A0) und schmales Leerzeichen (U+202F) treten in Word-/PDF-Kopien
# regelmäßig als Trenner auf (B4, z. B. zwischen "§" und der Paragraphenzahl).
# \s deckt beide bereits ab (Unicode-Whitespace-Property); die expliziten
# [ \t]-Zeichenklassen im Normzitat-Pattern müssen sie separat aufnehmen.
_WS = r"[ \t  ]"

# Kopf eines Normzitats bis (exklusive) Gesetzeskürzel — als eigener Baustein,
# damit dieselbe Grammatik sowohl für vollständige Normzitate (_NORM_RE, mit
# Gesetz) als auch für "kürzellose" Kettenglieder in i.V.m.-Verweisen (B2,
# siehe _NORM_FRAGMENT_RE / extrahiere_ivm_ketten) verwendet werden kann.
_NORM_KOPF = (
    r"(?P<marker>§§|§|Art\.)"
    r"" + _WS + r"*"
    r"(?P<nummern>\d+[a-z]?(?:\s*(?:,|und|u\.)\s*\d+[a-z]?)*)"
    r"(?P<ff>\s*ff?\.)?"
    r"(?P<abs>\s*(?:(?:Abs\.|Absatz)\s*(?:\d+[a-z]?|(?:" + _ROEMISCH_ABS_ALT + r"))"
    r"|(?:" + _ROEMISCH_ABS_ALT + r")))?"
    r"(?P<satz>\s*(?:S\.|Satz)\s*\d+)?"
    r"(?P<nr>\s*(?:Nr\.|Nummer)\s*\d+[a-z]?)?"
    r"(?P<lit>\s*(?:lit\.|Buchst\.)\s*[a-z]\)?)?"
)

# Gleiche Grammatik wie _NORM_KOPF, aber ohne benannte Gruppen — zur Mehrfach-
# verwendung innerhalb der i.V.m.-Ketten-Regex (Python erlaubt keine doppelten
# Gruppennamen in einem Pattern).
_NORM_KOPF_ANON = (
    r"(?:§§|§|Art\.)"
    r"" + _WS + r"*"
    r"\d+[a-z]?(?:\s*(?:,|und|u\.)\s*\d+[a-z]?)*"
    r"(?:\s*ff?\.)?"
    r"(?:\s*(?:(?:Abs\.|Absatz)\s*(?:\d+[a-z]?|(?:" + _ROEMISCH_ABS_ALT + r"))"
    r"|(?:" + _ROEMISCH_ABS_ALT + r")))?"
    r"(?:\s*(?:S\.|Satz)\s*\d+)?"
    r"(?:\s*(?:Nr\.|Nummer)\s*\d+[a-z]?)?"
    r"(?:\s*(?:lit\.|Buchst\.)\s*[a-z]\)?)?"
)

_NORM_RE = re.compile(
    _NORM_KOPF +
    r"" + _WS + r"+"
    r"(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*"
    r"(?:" + _WS + r"(?:" + _ROEMISCH_ALT + r"))?)"
    r"(?P<klammer>" + _WS + r"*\([^)\n]*\))?"
)

# Kürzellose Kettenglieder für i.V.m.-Erkennung (B2) — dieselbe Grammatik wie
# _NORM_RE, aber ohne das mandatorische Gesetz am Ende.
_NORM_FRAGMENT_RE = re.compile(_NORM_KOPF)

# "i.V.m." case-insensitiv, ohne globales IGNORECASE zu setzen (das würde auch
# Gesetzeskürzel case-insensitiv machen, was Groß-/Kleinschreibungsfehler bei
# Kürzeln verschleiern würde).
_IVM_SEP = r"\s*[iI]\.\s*[vV]\.\s*[mM]\.\s*"

_IVM_KETTE_RE = re.compile(
    r"(?P<kette>" + _NORM_KOPF_ANON + r"(?:" + _IVM_SEP + _NORM_KOPF_ANON + r")+)"
    r"" + _WS + r"+"
    r"(?P<gesetz>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*"
    r"(?:" + _WS + r"(?:" + _ROEMISCH_ALT + r"))?)"
)

_TRENN_RE = re.compile(r"\s*(?:,|und|u\.)\s*")


def _normalisiere_abs(roh: str | None) -> str | None:
    """Vereinheitlicht die Abs.-Angabe: bare römische Kurzschreibweise ("I")
    wird wie "Abs. I" dargestellt (B1), ohne dass sich das Verhalten für die
    bereits mit "Abs."/"Absatz" eingeleiteten Treffer ändert."""
    wert = (roh or "").strip()
    if not wert:
        return None
    if not re.match(r"(?i)^(abs\.?|absatz)\b", wert):
        wert = f"Abs. {wert}"
    return wert


def _aktenzeichen_pattern() -> str:
    # z. B. "IX ZR 15/22", "1 BvR 123/20", "3 StR 45/21"
    return r"[\dIVXLC]{1,3}\s?[A-Za-zÄÖÜ]{1,6}\s?\d{1,6}/\d{2,4}"


# R1 (ReDoS): Whitespace-Läufe zwischen den Bestandteilen einer Gerichts-
# entscheidung werden auf max. 10 Zeichen begrenzt statt mit unbegrenztem
# \s* zu arbeiten. Mehrere benachbarte unbegrenzte \s*-Gruppen kombiniert mit
# optionalen Literal-Gruppen dazwischen führen bei langen Whitespace-Läufen zu
# exponentiellem Backtracking, sobald der Gesamt-Match am Ende scheitert
# (Repro: "Siehe BGH" + 2000 Leerzeichen + "kein Az hier." hängt >20s mit
# unbegrenztem \s*). Mit begrenzten Quantifizierern schlägt der Versuch, mehr
# als 10 Whitespace-Zeichen an einer Stelle zu konsumieren, sofort fehl, statt
# alle Aufteilungen des Laufs auf die Gruppen durchzuprobieren. 10 Zeichen sind
# für reale Zitate (auch mit Zeilenumbrüchen/mehrfachen Leerzeichen) reichlich.
_WS01 = r"\s{0,10}"
_WS1 = r"\s{1,10}"

# B3: mehrwortige Ortsnamen ("Frankfurt am Main") und Bindestrich-Ortsnamen
# ("Baden-Baden") nach Gerichten mit Ortszusatz (OLG, LG, ...) zulassen, statt
# nur ein einzelnes Ortswort zu fangen.
_ORT_ZUSATZ = (
    r"[A-ZÄÖÜ][A-Za-zäöüßÄÖÜ]*(?:-[A-ZÄÖÜ][A-Za-zäöüßÄÖÜ]*)?"
    r"(?:" + _WS1 + r"(?:am|an|der|auf|im|in)" + _WS1 +
    r"[A-ZÄÖÜ][A-Za-zäöüßÄÖÜ]*)?"
)


def _gericht_pattern(gerichte_ohne_ort: list[str], gerichte_mit_ort: list[str]) -> str:
    """Baut nur die (?P<gericht>...)-Gruppe — von _entscheidung_re und
    _fundstelle_re unterschiedlich eingebettet (Pflicht- vs. optionales
    Präfix), daher hier zentral, um B3/R1 an einer Stelle zu pflegen."""
    ohne_ort = "|".join(re.escape(g) for g in sorted(gerichte_ohne_ort, key=len, reverse=True))
    mit_ort = "|".join(re.escape(g) for g in sorted(gerichte_mit_ort, key=len, reverse=True))
    return (
        r"(?P<gericht>(?:" + mit_ort + r")\s?" + _ORT_ZUSATZ +
        r"|(?:" + ohne_ort + r"))"
    )


def _entscheidung_re(gerichte_ohne_ort: list[str], gerichte_mit_ort: list[str]) -> re.Pattern:
    gericht_gruppe = _gericht_pattern(gerichte_ohne_ort, gerichte_mit_ort)
    return re.compile(
        gericht_gruppe +
        r",?" + _WS01 +
        r"(?P<art>Urt(?:eil)?\.?|Beschl(?:uss)?\.?|Vorlagebeschl(?:uss)?\.?)?" +
        _WS01 + r"(?:v\.|vom)?" + _WS01 +
        r"(?P<datum>\d{1,2}\.\d{1,2}\.\d{2,4})?" +
        _WS01 + r"[–\-—]?" + _WS01 +
        r"(?P<az>" + _aktenzeichen_pattern() + r")"
    )


def _fundstelle_re(gerichte_ohne_ort: list[str], gerichte_mit_ort: list[str],
                    zeitschriften: list[str]) -> re.Pattern:
    zs = "|".join(re.escape(z) for z in zeitschriften)
    gericht_gruppe = (
        r"(?:" + _gericht_pattern(gerichte_ohne_ort, gerichte_mit_ort) + _WS1 + r")?"
    )
    return re.compile(
        gericht_gruppe +
        r"(?P<zeitschrift>" + zs + r")" +
        _WS1 + r"(?P<jahr>\d{4})," + _WS01 + r"(?P<seite>\d+)"
    )


# --------------------------------------------------------------------------
# Datenklassen
# --------------------------------------------------------------------------

@dataclass
class Zitat:
    id: int
    typ: str
    roh: str
    zeile: int
    zustand: str
    marker: str
    begruendung: str
    details: dict[str, Any] = field(default_factory=dict)
    formatwarnungen: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _zeile_von(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# --------------------------------------------------------------------------
# Extraktion: Normzitate
# --------------------------------------------------------------------------

def extrahiere_normzitate(text: str) -> list[dict[str, Any]]:
    treffer = []
    for m in _NORM_RE.finditer(text):
        gesetz = m.group("gesetz")
        nummern = [n.strip() for n in _TRENN_RE.split(m.group("nummern")) if n.strip()]
        treffer.append({
            "span": m.span(),
            "roh": m.group(0).strip(),
            "marker_zeichen": m.group("marker"),
            "gesetz": gesetz,
            "paragraphen": nummern,
            "ff": bool(m.group("ff")),
            "abs": _normalisiere_abs(m.group("abs")),
            "satz": (m.group("satz") or "").strip() or None,
            "nr": (m.group("nr") or "").strip() or None,
            "lit": (m.group("lit") or "").strip() or None,
            "klammer": (m.group("klammer") or "").strip() or None,
            "zeile": _zeile_von(text, m.start()),
        })
    treffer.extend(extrahiere_ivm_ketten(text))
    treffer.sort(key=lambda t: t["span"][0])
    return treffer


def extrahiere_ivm_ketten(text: str) -> list[dict[str, Any]]:
    """B2: 'i.V.m.'-Ketten wie '§ 823 i.V.m. § 249 BGB'.

    Alle Kettenglieder außer dem letzten tragen kein eigenes Gesetzeskürzel;
    _NORM_RE verwirft sie stillschweigend, weil das Gesetz-Segment mandatorisch
    ist (ihr Nachfolge-Token ist "i.V.m." statt eines Gesetzeskürzels). Damit
    kein Zitat unmarkiert verschwindet, erben sie hier explizit das Kürzel des
    letzten Kettenglieds (das sein eigenes Gesetz trägt und ohnehin bereits
    separat über _NORM_RE erfasst wird) und werden als eigene Treffer mit dem
    Flag `ivm_geerbt` ausgewiesen — pruefe_norm() hängt dafür eine
    Formatwarnung an, sodass die Herkunft im Report sichtbar bleibt.
    """
    treffer = []
    for m in _IVM_KETTE_RE.finditer(text):
        kette_start = m.start("kette")
        kette_text = m.group("kette")
        gesetz = m.group("gesetz")
        glieder = list(_NORM_FRAGMENT_RE.finditer(kette_text))
        if len(glieder) < 2:
            continue
        letzte_roh = f"{glieder[-1].group(0).strip()} {gesetz}"
        for g in glieder[:-1]:
            nummern = [n.strip() for n in _TRENN_RE.split(g.group("nummern")) if n.strip()]
            treffer.append({
                "span": (kette_start + g.start(), kette_start + g.end()),
                "roh": g.group(0).strip(),
                "marker_zeichen": g.group("marker"),
                "gesetz": gesetz,
                "paragraphen": nummern,
                "ff": bool(g.group("ff")),
                "abs": _normalisiere_abs(g.group("abs")),
                "satz": (g.group("satz") or "").strip() or None,
                "nr": (g.group("nr") or "").strip() or None,
                "lit": (g.group("lit") or "").strip() or None,
                "klammer": None,
                "zeile": _zeile_von(text, kette_start + g.start()),
                "ivm_geerbt": True,
                "ivm_quelle": letzte_roh,
            })
    return treffer


def _zahl_aus(feld: str | None) -> str | None:
    if not feld:
        return None
    m = re.search(r"\d+[a-z]?", feld)
    return m.group(0) if m else None


def _paragraphen_umfang_text(paragraphen: list[str]) -> str:
    if len(paragraphen) == 1:
        return f"nur Paragraph {paragraphen[0]} geprüft"
    return f"nur Paragraphen ({', '.join(paragraphen)}) geprüft"


def pruefe_norm(treffer: dict[str, Any], registry: dict[str, Any],
                 kuerzel_bekannt: set[str]) -> tuple[str, str, list[str]]:
    formatwarnungen: list[str] = []
    gesetz = treffer["gesetz"]

    if gesetz not in kuerzel_bekannt:
        formatwarnungen.append(f"unbekanntes Gesetzeskürzel: '{gesetz}'")

    if treffer["marker_zeichen"] == "§§" and len(treffer["paragraphen"]) == 1 and not treffer["ff"]:
        formatwarnungen.append(
            "§§ (Plural) mit nur einer Paragraphennummer angegeben — vermutlich '§' gemeint")
    if treffer["marker_zeichen"] == "§" and len(treffer["paragraphen"]) > 1:
        formatwarnungen.append(
            "§ (Singular) mit mehreren Paragraphennummern angegeben — vermutlich '§§' gemeint")

    for feld_name, feld_wert in (("Abs.", treffer["abs"]), ("Satz", treffer["satz"]),
                                  ("Nr.", treffer["nr"])):
        zahl = _zahl_aus(feld_wert)
        if zahl is not None and zahl.isdigit() and int(zahl) == 0:
            formatwarnungen.append(f"unplausible Nummerierung: {feld_name} 0 gibt es nicht")

    # F1/F3: Die Registry hat nur Paragraphen-Granularität. Abs./Satz/Nr./lit.
    # und ein offener ff.-Bereich werden von ihr gar nicht geprüft — das darf
    # sich nie in einem uneingeschränkten ✅ verstecken. Die Blindstelle wird
    # daher immer explizit als Formatwarnung ausgewiesen (unabhängig vom
    # erreichten Zustand) und, wenn der Zustand verifiziert lautet, zusätzlich
    # im geprüften Umfang der Begründung genannt.
    sub_komponenten_vorhanden = any(
        treffer.get(feld) for feld in ("abs", "satz", "nr", "lit"))
    if sub_komponenten_vorhanden:
        formatwarnungen.append("Abs./Satz/Nr./lit. nicht gegen Registry prüfbar")
    if treffer.get("ff"):
        formatwarnungen.append("offener ff.-Bereich nicht prüfbar")

    # B2: i.V.m.-Kettenglied ohne eigenes Gesetzeskürzel — Herkunft transparent
    # machen, damit die Kürzel-Übernahme im Report nachvollziehbar bleibt.
    if treffer.get("ivm_geerbt"):
        formatwarnungen.append(
            f"Gesetzeskürzel aus i.V.m.-Kette übernommen (von '{treffer.get('ivm_quelle')}')")

    # Registry-Abgleich: pro Paragraph, dann aggregieren.
    normen_registry = registry.get("normen", [])
    bekannte_kuerzel_registry = {n["kuerzel"] for n in normen_registry}
    bekannte_paare = {(n["kuerzel"], str(n["paragraph"])) for n in normen_registry}

    teilzustaende: list[str] = []
    teilbegruendungen: list[str] = []
    for p in treffer["paragraphen"]:
        if (gesetz, p) in bekannte_paare:
            teilzustaende.append(ZUSTAND_VERIFIZIERT)
        elif gesetz in bekannte_kuerzel_registry:
            teilzustaende.append(ZUSTAND_ABWEICHEND)
            teilbegruendungen.append(
                f"§ {p} {gesetz}: nicht in der mitgelieferten Normliste für {gesetz} enthalten")
        else:
            teilzustaende.append(ZUSTAND_NICHT_PRUEFBAR)

    gesamt = _aggregiere(teilzustaende) if teilzustaende else ZUSTAND_NICHT_PRUEFBAR

    if gesamt == ZUSTAND_VERIFIZIERT:
        begruendung = (
            f"alle Paragraphen ({', '.join(treffer['paragraphen'])}) "
            f"in Quellen-Registry für {gesetz} gefunden")
        eingeschraenkt = []
        if sub_komponenten_vorhanden:
            eingeschraenkt.append("Abs./Satz/Nr./lit. nicht gegen Registry prüfbar")
        if treffer.get("ff"):
            eingeschraenkt.append("offener ff.-Bereich nicht prüfbar")
        if eingeschraenkt:
            begruendung += (
                f" — {_paragraphen_umfang_text(treffer['paragraphen'])}; "
                + "; ".join(eingeschraenkt))
    elif gesamt == ZUSTAND_ABWEICHEND:
        begruendung = "; ".join(teilbegruendungen)
    else:
        begruendung = f"keine Quellen-Registry-Angabe zu {gesetz} vorhanden — Angabe stammt unverifiziert aus dem Input"

    return gesamt, begruendung, formatwarnungen


# --------------------------------------------------------------------------
# Extraktion: Gerichtsentscheidungen
# --------------------------------------------------------------------------

def extrahiere_gerichtsentscheidungen(text: str, gerichte: dict[str, list[str]]) -> list[dict[str, Any]]:
    pattern = _entscheidung_re(gerichte["ohne_ort"], gerichte["mit_ort"])
    treffer = []
    for m in pattern.finditer(text):
        treffer.append({
            "span": m.span(),
            "roh": m.group(0).strip(),
            "gericht": m.group("gericht").strip(),
            "art": (m.group("art") or "").strip() or None,
            "datum": m.group("datum"),
            "aktenzeichen": re.sub(r"\s+", " ", m.group("az").strip()),
            "zeile": _zeile_von(text, m.start()),
        })
    return treffer


def _datum_iso(d: str | None) -> str | None:
    if not d:
        return None
    teile = d.split(".")
    if len(teile) != 3:
        return None
    tag, monat, jahr = teile
    if len(jahr) == 2:
        jahr = ("20" if int(jahr) <= 69 else "19") + jahr
    try:
        return f"{int(jahr):04d}-{int(monat):02d}-{int(tag):02d}"
    except ValueError:
        return None


def pruefe_entscheidung(treffer: dict[str, Any],
                          registry: dict[str, Any]) -> tuple[str, str, list[str]]:
    formatwarnungen: list[str] = []
    datum_iso = _datum_iso(treffer["datum"])

    az_jahr_match = re.search(r"/(\d{2,4})$", treffer["aktenzeichen"])
    if az_jahr_match and treffer["datum"]:
        az_jahr = az_jahr_match.group(1)
        az_jahr_voll = ("20" if len(az_jahr) == 2 and int(az_jahr) <= 69 else "19") + az_jahr \
            if len(az_jahr) == 2 else az_jahr
        entscheidungsjahr = treffer["datum"].split(".")[-1]
        if len(entscheidungsjahr) == 2:
            entscheidungsjahr = ("20" if int(entscheidungsjahr) <= 69 else "19") + entscheidungsjahr
        if az_jahr_voll.isdigit() and entscheidungsjahr.isdigit() \
                and int(az_jahr_voll) > int(entscheidungsjahr):
            formatwarnungen.append(
                "unplausibel: Aktenzeichen-Jahr liegt nach dem Entscheidungsdatum")

    entscheidungen = registry.get("entscheidungen", [])
    treffer_norm_az = re.sub(r"\s+", " ", treffer["aktenzeichen"]).strip()

    for e in entscheidungen:
        reg_az = re.sub(r"\s+", " ", str(e.get("aktenzeichen", ""))).strip()
        if reg_az == treffer_norm_az and e.get("gericht") == treffer["gericht"]:
            reg_datum = e.get("datum")
            # F2: Zitat nennt ein Datum, aber der Registry-Eintrag hat gar
            # kein datum-Feld — das Datum wird dann überhaupt nicht geprüft
            # und darf nicht stillschweigend als bestätigt gelten. Bleibt bei
            # ✅ (Gericht + Aktenzeichen stimmen), aber mit Warnung und einer
            # Begründung, die den geprüften Umfang exakt benennt.
            if datum_iso and not reg_datum:
                formatwarnungen.append("Datum nicht in Registry hinterlegt, nicht geprüft")
                return (ZUSTAND_VERIFIZIERT,
                        f"{treffer['gericht']}, Az. {treffer['aktenzeichen']} in Quellen-Registry "
                        "gefunden — nur Gericht und Aktenzeichen geprüft, Datum nicht in Registry "
                        "hinterlegt",
                        formatwarnungen)
            if datum_iso and reg_datum and reg_datum != datum_iso:
                return (ZUSTAND_ABWEICHEND,
                        f"Datum weicht von Quelle ab: Zitat nennt {treffer['datum']}, "
                        f"Registry nennt {reg_datum}",
                        formatwarnungen)
            return (ZUSTAND_VERIFIZIERT,
                    f"{treffer['gericht']}, Az. {treffer['aktenzeichen']} in Quellen-Registry gefunden",
                    formatwarnungen)

    return (ZUSTAND_NICHT_PRUEFBAR,
            "keine Quellen-Registry-Angabe zu diesem Aktenzeichen vorhanden — "
            "Angabe stammt unverifiziert aus dem Input",
            formatwarnungen)


# --------------------------------------------------------------------------
# Extraktion: Fundstellen
# --------------------------------------------------------------------------

def extrahiere_fundstellen(text: str, gerichte: dict[str, list[str]],
                             zeitschriften: list[str],
                             belegte_spans: list[tuple[int, int]]) -> list[dict[str, Any]]:
    pattern = _fundstelle_re(gerichte["ohne_ort"], gerichte["mit_ort"], zeitschriften)
    treffer = []
    for m in pattern.finditer(text):
        span = m.span()
        # Überschneidet sich mit einem bereits erfassten Gerichtsentscheidung-Zitat?
        if any(span[0] < b[1] and span[1] > b[0] for b in belegte_spans):
            continue
        treffer.append({
            "span": span,
            "roh": m.group(0).strip(),
            "gericht": (m.group("gericht") or "").strip() or None,
            "zeitschrift": m.group("zeitschrift"),
            "jahr": int(m.group("jahr")),
            "seite": int(m.group("seite")),
            "zeile": _zeile_von(text, m.start()),
        })
    return treffer


def pruefe_fundstelle(treffer: dict[str, Any],
                        registry: dict[str, Any]) -> tuple[str, str, list[str]]:
    for f in registry.get("fundstellen", []):
        if (f.get("zeitschrift") == treffer["zeitschrift"]
                and int(f.get("jahr", -1)) == treffer["jahr"]
                and int(f.get("seite", -1)) == treffer["seite"]):
            reg_gericht = f.get("gericht")
            if treffer["gericht"] and reg_gericht and reg_gericht != treffer["gericht"]:
                return (ZUSTAND_ABWEICHEND,
                        f"Gericht weicht von Quelle ab: Zitat nennt {treffer['gericht']}, "
                        f"Registry nennt {reg_gericht}", [])
            return (ZUSTAND_VERIFIZIERT,
                    f"{treffer['zeitschrift']} {treffer['jahr']}, {treffer['seite']} "
                    "in Quellen-Registry gefunden", [])
    return (ZUSTAND_NICHT_PRUEFBAR,
            "keine Quellen-Registry-Angabe zu dieser Fundstelle vorhanden — "
            "Angabe stammt unverifiziert aus dem Input", [])


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def baue_report(text: str, registry: dict[str, Any], schema_dir: Path,
                 quelle_datei: str, registry_datei: str | None) -> dict[str, Any]:
    kuerzel_bekannt = lade_kuerzelliste(schema_dir)
    gerichte = lade_gerichte(schema_dir)
    zeitschriften = lade_zeitschriften(schema_dir)

    zitate: list[Zitat] = []
    zaehler = 0

    for t in extrahiere_normzitate(text):
        zaehler += 1
        zustand, begruendung, warnungen = pruefe_norm(t, registry, kuerzel_bekannt)
        details = {k: v for k, v in t.items() if k not in ("span", "roh", "zeile")}
        zitate.append(Zitat(zaehler, "norm", t["roh"], t["zeile"], zustand,
                             MARKER[zustand], begruendung, details, warnungen))

    entscheidungs_treffer = extrahiere_gerichtsentscheidungen(text, gerichte)
    belegte_spans = [t["span"] for t in entscheidungs_treffer]
    for t in entscheidungs_treffer:
        zaehler += 1
        zustand, begruendung, warnungen = pruefe_entscheidung(t, registry)
        details = {k: v for k, v in t.items() if k not in ("span", "roh", "zeile")}
        zitate.append(Zitat(zaehler, "gerichtsentscheidung", t["roh"], t["zeile"], zustand,
                             MARKER[zustand], begruendung, details, warnungen))

    for t in extrahiere_fundstellen(text, gerichte, zeitschriften, belegte_spans):
        zaehler += 1
        zustand, begruendung, warnungen = pruefe_fundstelle(t, registry)
        details = {k: v for k, v in t.items() if k not in ("span", "roh", "zeile")}
        zitate.append(Zitat(zaehler, "fundstelle", t["roh"], t["zeile"], zustand,
                             MARKER[zustand], begruendung, details, warnungen))

    zitate.sort(key=lambda z: (z.zeile, z.id))
    for neu_id, z in enumerate(zitate, start=1):
        z.id = neu_id

    zusammenfassung = {
        ZUSTAND_VERIFIZIERT: sum(1 for z in zitate if z.zustand == ZUSTAND_VERIFIZIERT),
        ZUSTAND_NICHT_PRUEFBAR: sum(1 for z in zitate if z.zustand == ZUSTAND_NICHT_PRUEFBAR),
        ZUSTAND_ABWEICHEND: sum(1 for z in zitate if z.zustand == ZUSTAND_ABWEICHEND),
    }

    return {
        "meta": {
            "quelle_datei": quelle_datei,
            "registry_datei": registry_datei,
            "erzeugt_von": "zitat-pruefer/executor.py",
            "anzahl_zitate": len(zitate),
        },
        "zitate": [z.as_dict() for z in zitate],
        "zusammenfassung": zusammenfassung,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Text-/Markdown-Datei mit Zitaten")
    parser.add_argument("--registry", help="Optionale Quellen-Registry (JSON)")
    parser.add_argument("--schema-dir", default=str(SCHEMA_DIR_DEFAULT),
                        help="Verzeichnis mit gesetzeskuerzel.json/gerichte.json/zeitschriften.json")
    parser.add_argument("--output", help="Zieldatei für den JSON-Report (Default: stdout)")
    args = parser.parse_args(argv)

    input_pfad = Path(args.input)
    if not input_pfad.is_file():
        print(f"Fehler: Eingabedatei nicht gefunden: {input_pfad}", file=sys.stderr)
        return 2

    registry_pfad = Path(args.registry) if args.registry else None
    if registry_pfad is not None and not registry_pfad.is_file():
        print(f"Fehler: Registry-Datei nicht gefunden: {registry_pfad}", file=sys.stderr)
        return 2

    text = input_pfad.read_text(encoding="utf-8")
    try:
        registry = lade_registry(registry_pfad)
    except json.JSONDecodeError as exc:
        print(f"Fehler: Registry-Datei ist kein gültiges JSON: {exc}", file=sys.stderr)
        return 2
    except RegistryFehler as exc:
        print(f"Fehler: Registry-Datei ist strukturell ungültig: {exc}", file=sys.stderr)
        return 2
    schema_dir = Path(args.schema_dir)

    report = baue_report(text, registry, schema_dir,
                          quelle_datei=str(input_pfad),
                          registry_datei=str(registry_pfad) if registry_pfad else None)

    ausgabe = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(ausgabe + "\n", encoding="utf-8")
    else:
        print(ausgabe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
