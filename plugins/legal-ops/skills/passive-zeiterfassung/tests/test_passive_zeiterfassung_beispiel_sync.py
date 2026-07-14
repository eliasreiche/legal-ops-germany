"""Beispiel-Sync- und Integrations-Tests (P4) für passive-zeiterfassung.

- `beispiel-report.json` muss exakt dem entsprechen, was der Executor aktuell
  aus den Beispiel-Metadaten gegen `core/context/beispiel-kontext/`
  (read-only) erzeugt.
- `beispiel-leistungen.json` muss exakt die `leistung`-Objekte der eindeutigen
  Vorschläge sein.
- **Integrations-Round-Trip** (der wichtigste Test der Welle): die
  bestätigten Vorschläge → `leistungen.json` → laufen durch den ECHTEN
  `taetigkeitstext-rvg`-Executor (subprocess) → Exit 0 und konsistente Minuten.
  Erzwingt die Format-Kompatibilität zwischen Zulieferer und Abnehmer
  maschinell.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"
SCHEMA = SKILL / "schema"
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"
TT_EXECUTOR = REPO / "plugins" / "legal-ops" / "skills" / "taetigkeitstext-rvg" / "executor.py"


def _erzeuge_report() -> dict:
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--termine", str(SCHEMA / "beispiel-termine.json"),
         "--mails", str(SCHEMA / "beispiel-mails.json"),
         "--config", str(SCHEMA / "beispiel-config.json"),
         "--kontext", str(BEISPIEL_KONTEXT)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return json.loads(ergebnis.stdout)


def _neutralisiert(report: dict) -> dict:
    """Pfad-Präfixe in meta hängen vom Aufruf ab — für den Inhaltsvergleich
    auf den Dateinamen reduzieren, alles andere muss exakt stimmen."""
    report = json.loads(json.dumps(report))
    for feld in ("quelle_termine", "quelle_mails", "kontext_verzeichnis"):
        if report["meta"].get(feld):
            report["meta"][feld] = Path(report["meta"][feld]).name
    return report


def test_beispiel_report_ist_aktuell():
    frisch = _neutralisiert(_erzeuge_report())
    gespeichert = _neutralisiert(
        json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8")))
    assert frisch == gespeichert, (
        "schema/beispiel-report.json ist veraltet — neu erzeugen mit --output "
        f"{SCHEMA / 'beispiel-report.json'}")


def test_beispiel_leistungen_ist_aktuell():
    report = _erzeuge_report()
    erwartet_eintraege = [v["leistung"] for v in report["vorschlaege"]]
    gespeichert = json.loads((SCHEMA / "beispiel-leistungen.json").read_text(encoding="utf-8"))
    assert gespeichert["eintraege"] == erwartet_eintraege
    # Kein Takt hier — die Taktung macht taetigkeitstext-rvg downstream.
    assert gespeichert["config"] == {"takt_minuten": None}


def test_beispiel_alle_buckets_belegt():
    """Die Beispieldaten demonstrieren jeden relevanten Ausgabekanal."""
    report = _erzeuge_report()
    assert report["vorschlaege"], "kein eindeutiger Vorschlag im Beispiel"
    assert report["mehrdeutig"], "kein mehrdeutiger Fall im Beispiel"
    assert report["nicht_zuordenbar"], "kein nicht_zuordenbar-Fall im Beispiel"
    assert report["warnungen"], "kein Überlappungspaar im Beispiel"


# --------------------------------------------------------------------------
# Integrations-Round-Trip: leistungen.json -> taetigkeitstext-rvg-Executor
# --------------------------------------------------------------------------

def test_round_trip_durch_taetigkeitstext_rvg(tmp_path):
    report = _erzeuge_report()
    leistungen = {"eintraege": [v["leistung"] for v in report["vorschlaege"]],
                  "config": {"takt_minuten": None}}
    leistungen_pfad = tmp_path / "leistungen.json"
    leistungen_pfad.write_text(json.dumps(leistungen), encoding="utf-8")

    ergebnis = subprocess.run(
        [sys.executable, str(TT_EXECUTOR), "--input", str(leistungen_pfad)],
        capture_output=True, text=True)
    # Exit 0: das Format des Zulieferers ist für den Abnehmer gültig.
    assert ergebnis.returncode == 0, ergebnis.stderr
    tt_report = json.loads(ergebnis.stdout)

    # Keine Lücke: jeder Vorschlag trägt ein az, keiner landet in ohne_az.
    assert tt_report["zusammenfassung"]["anzahl_ohne_az"] == 0
    assert tt_report["zusammenfassung"]["anzahl_eintraege"] == len(report["vorschlaege"])

    # Konsistente Minuten: die az-Summen beider Executor stimmen überein
    # (ohne Taktung ist minuten == minuten_getaktet).
    assert tt_report["summen"]["je_az"] == report["summen"]["je_az"]


def test_round_trip_mit_beispiel_leistungen_datei():
    """Die eingecheckte beispiel-leistungen.json läuft direkt durch den
    Abnehmer-Executor (Golden-File-Kompatibilität)."""
    ergebnis = subprocess.run(
        [sys.executable, str(TT_EXECUTOR), "--input", str(SCHEMA / "beispiel-leistungen.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    tt_report = json.loads(ergebnis.stdout)
    assert tt_report["zusammenfassung"]["anzahl_ohne_az"] == 0
    assert tt_report["summen"]["je_az"] == {"2026-001": 117, "2026-002": 45}
