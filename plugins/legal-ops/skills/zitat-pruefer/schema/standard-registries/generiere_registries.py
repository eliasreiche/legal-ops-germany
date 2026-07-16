#!/usr/bin/env python3
"""Generator für die Standard-Registries (BGB, ZPO, StGB) des zitat-pruefer.

NICHT Teil des Laufzeit-Pfads. Der Executor (`executor.py`) bleibt strikt
offline (P3) — er liest nur die fertig generierten `<abk>.json`-Dateien. Netz-
zugriff findet ausschließlich hier statt, beim manuellen Neu-Erzeugen der
Registries, und ist zur Laufzeit nie nötig.

Quelle: offizielle Gesetzes-XML von gesetze-im-internet.de (Bundesamt für
Justiz / juris), je Gesetz als `xml.zip`. Aus dem XML wird pro `<norm>` die
Einzelnorm-Bezeichnung `<enbez>` (z. B. „§ 826", „§ 312a") gelesen und die
Paragraphennummer extrahiert — inklusive Buchstaben-Paragraphen (312a, 37b).

Regel für aufgehobene/weggefallene Normen: Sie werden **aufgenommen**, aber mit
`"aufgehoben": true` gekennzeichnet. Begründung: Ein Zitat auf eine (historisch
gültige, heute weggefallene) Paragraphennummer soll vom Prüfer NICHT als
❌ abweichend gemeldet werden — die Nummer hat im Numerierungssystem des
Gesetzes existiert. Der `aufgehoben`-Marker macht den Status im Registry-Eintrag
transparent, ohne die Format-Prüfung zu verfälschen. Weggefallen-Sammeleinträge
im XML in Bereichs- oder Aufzählungsform („§§ 116 bis 119", „§§ 214 und 215")
werden in ihre Einzelnummern expandiert (nur rein numerische Bereiche;
Buchstaben-Bereiche sind im Bestand nicht relevant und werden übersprungen).

Nur Standardbibliothek. Aufruf:

    python3 generiere_registries.py            # alle drei Gesetze neu erzeugen
    python3 generiere_registries.py --gesetz BGB
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

HIER = Path(__file__).resolve().parent

# (Kürzel wie im Zitat, gesetze-im-internet.de-Kurzform, Klartext-Titel)
GESETZE = {
    "BGB": ("bgb", "Bürgerliches Gesetzbuch"),
    "ZPO": ("zpo", "Zivilprozessordnung"),
    "StGB": ("stgb", "Strafgesetzbuch"),
}
BASIS_URL = "https://www.gesetze-im-internet.de/{abk}/xml.zip"

_EINZEL_RE = re.compile(r"^§\s*(\d+[a-z]*)$")
_BEREICH_RE = re.compile(r"§+\s*(\d+)\s*bis\s*(\d+)")
_AUFZAEHLUNG_RE = re.compile(r"§+\s*(\d+[a-z]*(?:\s*(?:,|und|u\.)\s*\d+[a-z]*)+)")
_ZAHL_RE = re.compile(r"\d+[a-z]*")


def lade_xml(abk: str) -> ET.Element:
    url = BASIS_URL.format(abk=abk)
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (feste amtliche Domain)
        roh = resp.read()
    zf = zipfile.ZipFile(io.BytesIO(roh))
    xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
    return ET.fromstring(zf.read(xml_name).decode("utf-8"))


def _ist_weggefallen(norm: ET.Element, enbez: str) -> bool:
    if "weggefallen" in enbez.lower():
        return True
    txt = norm.find("textdaten")
    if txt is None:
        return False
    body = " ".join(txt.itertext()).strip().lower()
    return "weggefallen" in body and len(body) < 200


def extrahiere_paragraphen(root: ET.Element) -> list[dict]:
    """Liste von {paragraph, aufgehoben} in Dokumentreihenfolge, dedupliziert."""
    gesehen: dict[str, dict] = {}

    def merke(paragraph: str, aufgehoben: bool) -> None:
        # Erster Treffer gewinnt; ein späterer aktiver Treffer hebt einen
        # zuvor als aufgehoben markierten auf (defensiv, kommt real kaum vor).
        if paragraph not in gesehen:
            gesehen[paragraph] = {"paragraph": paragraph, "aufgehoben": aufgehoben}
        elif not aufgehoben:
            gesehen[paragraph]["aufgehoben"] = False

    for norm in root.iter("norm"):
        md = norm.find("metadaten")
        if md is None:
            continue
        enb = md.find("enbez")
        if enb is None or not enb.text:
            continue
        enbez = enb.text.strip()

        m = _EINZEL_RE.match(enbez)
        if m:
            merke(m.group(1), _ist_weggefallen(norm, enbez))
            continue

        # Sammel-/Bereichseinträge sind praktisch immer Weggefallen-Gruppen.
        bereich = _BEREICH_RE.search(enbez)
        if bereich:
            von, bis = int(bereich.group(1)), int(bereich.group(2))
            if 0 < bis - von < 200:
                for n in range(von, bis + 1):
                    merke(str(n), True)
            continue
        aufz = _AUFZAEHLUNG_RE.search(enbez)
        if aufz:
            for zahl in _ZAHL_RE.findall(aufz.group(0)):
                merke(zahl, True)
            continue
        # Alles andere (Inhaltsübersicht, Anlagen ohne §-Nummer) übergehen.

    return list(gesehen.values())


def baue_registry(kuerzel: str, abk: str, titel: str, heute: str) -> dict:
    root = lade_xml(abk)
    eintraege = extrahiere_paragraphen(root)
    normen = []
    for e in eintraege:
        eintrag = {"kuerzel": kuerzel, "paragraph": e["paragraph"]}
        if e["aufgehoben"]:
            eintrag["aufgehoben"] = True
            eintrag["bezeichnung"] = "(weggefallen)"
        normen.append(eintrag)
    aktiv = sum(1 for e in eintraege if not e["aufgehoben"])
    aufgehoben = len(eintraege) - aktiv
    return {
        "_hinweis": (
            f"Standard-Registry für {kuerzel} ({titel}) im Format von "
            "plugins/legal-ops/skills/zitat-pruefer/schema/README.md. "
            "Maschinell erzeugt aus der amtlichen Gesetzes-XML; NICHT von Hand "
            "editieren, sondern mit generiere_registries.py neu erzeugen. "
            "Aufgehobene/weggefallene Paragraphen sind mit \"aufgehoben\": true "
            "aufgenommen, damit ein Zitat auf eine historische Nummer nicht "
            "fälschlich als ❌ abweichend gemeldet wird."),
        "quelle_url": BASIS_URL.format(abk=abk),
        "abgerufen_am": heute,
        "frische_hinweis": (
            "Gesetze ändern sich laufend (neue, geänderte, aufgehobene §§). "
            "Diese Registry ist eine Momentaufnahme zum abgerufen_am-Datum und "
            "vor produktiver Nutzung gegen den aktuellen Stand auf "
            "gesetze-im-internet.de abzugleichen; Neu-Erzeugung per "
            "generiere_registries.py. Analog zum Frische-Gate des "
            "gwg-risiko-check (D19)."),
        "stand": {"paragraphen_aktiv": aktiv, "paragraphen_aufgehoben": aufgehoben},
        "normen": normen,
        "entscheidungen": [],
        "fundstellen": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gesetz", choices=sorted(GESETZE), action="append",
                        help="Nur dieses Gesetz erzeugen (mehrfach möglich). "
                             "Default: alle drei.")
    parser.add_argument("--abgerufen-am", default=date.today().isoformat(),
                        help="Provenienz-Datum (Default: heute).")
    args = parser.parse_args(argv)

    ziel_gesetze = args.gesetz or sorted(GESETZE)
    for kuerzel in ziel_gesetze:
        abk, titel = GESETZE[kuerzel]
        print(f"… {kuerzel} ({abk}) von gesetze-im-internet.de", file=sys.stderr)
        registry = baue_registry(kuerzel, abk, titel, args.abgerufen_am)
        ziel = HIER / f"{abk}.json"
        ziel.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        stand = registry["stand"]
        print(f"  → {ziel.name}: {stand['paragraphen_aktiv']} aktiv, "
              f"{stand['paragraphen_aufgehoben']} aufgehoben", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
