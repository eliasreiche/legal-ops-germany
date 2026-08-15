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
from pathlib import Path

from conftest import (BEISPIEL_KONTEXT, SKILLS, lauf,  # noqa: E402
                      neutralisiere, report, schreibe)

SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"
SCHEMA = SKILL / "schema"
TT_EXECUTOR = SKILLS / "taetigkeitstext-rvg" / "executor.py"

# Pfad-Felder dieses Reports, die vom Aufruf abhängen (siehe neutralisiere).
PFADFELDER = ("quelle_termine", "quelle_mails", "kontext_verzeichnis")


def _erzeuge_report() -> dict:
    return report(EXECUTOR,
                  "--termine", SCHEMA / "beispiel-termine.json",
                  "--mails", SCHEMA / "beispiel-mails.json",
                  "--config", SCHEMA / "beispiel-config.json",
                  "--kontext", BEISPIEL_KONTEXT)


def test_beispiel_report_ist_aktuell():
    frisch = neutralisiere(_erzeuge_report(), PFADFELDER)
    gespeichert = neutralisiere(
        json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8")),
        PFADFELDER)
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
    leistungen_pfad = schreibe(tmp_path / "leistungen.json", leistungen)

    ergebnis = lauf(TT_EXECUTOR, "--input", leistungen_pfad)
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
    tt_report = report(TT_EXECUTOR, "--input", SCHEMA / "beispiel-leistungen.json")
    assert tt_report["zusammenfassung"]["anzahl_ohne_az"] == 0
    assert tt_report["summen"]["je_az"] == {"2026-001": 117, "2026-002": 45}
