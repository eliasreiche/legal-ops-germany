#!/usr/bin/env python3
"""sanktionslisten/abruf — Abruf der offiziellen EU-/UN-Sanktionslisten (P2).

Bewusst **getrennt** vom Screening-Executor (Deterministik-Grenze,
CONVENTIONS.md P3): der Screening-Executor macht nie Live-HTTP, er arbeitet
nur auf lokalen Dateien. Dieses Skript ist der einzige Ort mit Netzwerkzugriff
— reine Stdlib (`urllib`), keine neuen Abhängigkeiten.

Es lädt die zwei offiziellen, öffentlich abrufbaren Listen in ein
Zielverzeichnis und schreibt eine `abruf-meta.json`, die je Datei das
Abrufdatum (`abgerufen_am`) und die Quell-URL festhält. Genau diese
Metadatei speist das Frische-Gate des Screening-Executors (fehlt
`abgerufen_am` → harter Fehler, kein Report).

CI-Hinweis: Dieses Skript wird **nicht** netzwerk-getestet. Getestet sind nur
das URL-Format (`test_gwg_live_screening_abruf.py`) und das Schreiben der
Metadatei aus bereits lokal vorliegenden Dateien (`schreibe_meta`). Der echte
Abruf ist manuell bzw. per Cron/launchd auszulösen; alternativ die
dokumentierten `curl`-Kommandos (siehe README.md / SKILL.md).

CLI:
    python3 abruf.py --ziel <verzeichnis> [--nur eu|un]

Exit-Codes: 0 = geladen, 2 = Eingabe-/Abruffehler.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# Offizielle, öffentlich abrufbare Quell-URLs (Stand 2026-07-16).
#   EU: Konsolidierte Finanzsanktionsliste, „full file" XML-Export. Der Export
#       verlangt einen (öffentlichen, in der EU-Doku genannten) Token-Parameter;
#       er ist hier NICHT hinterlegt, weil er sich ändern kann und nicht ins
#       Repo gehört — beim Abruf über --eu-url übergeben.
#   UN: Consolidated List, frei abrufbar.
QUELLEN: dict[str, dict[str, str]] = {
    "eu": {
        "dateiname": "eu-fsf.xml",
        "url": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content",
    },
    "un": {
        "dateiname": "un-consolidated.xml",
        "url": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    },
}


def _heute_iso() -> str:
    return _dt.date.today().isoformat()


def _lade(url: str, ziel: Path) -> int:
    """Lädt `url` nach `ziel`; gibt die Bytegröße zurück. Nur hier: Netzwerk."""
    req = Request(url, headers={"User-Agent": "legal-ops-germany/sanktionslisten-abruf"})
    with urlopen(req, timeout=120) as antwort:  # noqa: S310 (feste offizielle URLs)
        daten = antwort.read()
    ziel.write_bytes(daten)
    return len(daten)


def schreibe_meta(ziel_dir: Path, eintraege: dict[str, dict[str, str]]) -> Path:
    """Schreibt/mergt abruf-meta.json (Dateiname → {url, abgerufen_am}).

    Rein lokal, ohne Netzwerk — deshalb separat testbar. Bestehende Einträge
    für nicht neu geladene Dateien bleiben erhalten (Merge), damit ein
    Teil-Abruf (--nur) die Metadaten der anderen Liste nicht verwirft.
    """
    meta_pfad = ziel_dir / "abruf-meta.json"
    bestand: dict[str, dict[str, str]] = {}
    if meta_pfad.is_file():
        try:
            geladen = json.loads(meta_pfad.read_text(encoding="utf-8"))
            if isinstance(geladen, dict):
                bestand = {k: v for k, v in geladen.items() if isinstance(v, dict)}
        except json.JSONDecodeError:
            bestand = {}
    bestand.update(eintraege)
    meta_pfad.write_text(json.dumps(bestand, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    return meta_pfad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ziel", required=True,
                        help="Zielverzeichnis für die Listen + abruf-meta.json")
    parser.add_argument("--nur", choices=["eu", "un"],
                        help="nur eine Liste laden (Default: beide)")
    parser.add_argument("--eu-url", help="EU-FSF-URL überschreiben (inkl. Token)")
    args = parser.parse_args(argv)

    ziel_dir = Path(args.ziel)
    ziel_dir.mkdir(parents=True, exist_ok=True)

    zu_laden = [args.nur] if args.nur else ["eu", "un"]
    heute = _heute_iso()
    neue_meta: dict[str, dict[str, str]] = {}
    for schluessel in zu_laden:
        quelle = QUELLEN[schluessel]
        url = args.eu_url if (schluessel == "eu" and args.eu_url) else quelle["url"]
        dateiname = quelle["dateiname"]
        try:
            groesse = _lade(url, ziel_dir / dateiname)
        except (URLError, OSError, ValueError) as exc:
            print(f"Fehler: Abruf {schluessel.upper()} fehlgeschlagen: {exc}",
                  file=sys.stderr)
            return 2
        neue_meta[dateiname] = {"url": url, "abgerufen_am": heute}
        print(f"{schluessel.upper()}: {groesse} Bytes → {dateiname}", file=sys.stderr)

    meta_pfad = schreibe_meta(ziel_dir, neue_meta)
    print(f"Metadaten aktualisiert: {meta_pfad}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
