"""CI-Test (Maintainer-Entscheidung 2026-07-14): Marker-Konsistenz für
statische Norm-Belehrungen in Executor-Outputs.

Hintergrund: Zwei D12-Reviews (Kalender-Export-PR, Kontext-Layer-PR) haben
denselben Minor notiert — statische Norm-Belehrungen in Executor-Outputs
(`core/calc/fristen/kalender_executor.py`, `core/calc/retention/executor.py`)
tragen ein hartkodiertes ⚠️-Präfix statt eines echten 3-Zustands-
Zitiermarkers nach CONVENTIONS.md ("Zitierdisziplin"). Die Normzitate selbst
sind korrekt; ⚠️ ("nicht prüfbar") ist aber semantisch falsch, sobald eine
Quellen-Registry die Norm tatsächlich kennt — und ✅ ("verifiziert") wäre nur
mit maschineller Absicherung ehrlich.

Dieser Test schließt die Lücke: er liest die je Modul exportierte
`STATISCHE_NORM_BELEHRUNGEN`-Konstante (kein fragiles Quelltext-Grep), jagt
jeden Belehrungstext durch den echten `zitat-pruefer`-Executor gegen eine
dedizierte Test-Registry (`tests/fixtures/statische_normen_registry.json`)
und erzwingt Konsistenz in BEIDE Richtungen zwischen dem im Quelltext
deklarierten Marker und dem vom Executor bestimmten Zustand:

  (a) ein nicht verifizierbares Zitat darf kein ✅ tragen,
  (b) ein maschinell verifiziertes Zitat darf kein ⚠️ mehr tragen.

Mehrere Normzitate innerhalb einer einzigen Belehrung (z. B. "§ 224 Abs. 2
ZPO" und "§§ 233 ff. ZPO" im selben Fließtext) werden — wie beim
zitat-pruefer selbst für i.V.m.-Ketten — nach Worst-Case aggregiert: der
"schlechteste" Teilzustand bestimmt den für die gesamte Belehrung erwarteten
Marker.

Stand 2026-07-14 (siehe Report des Inventar-Agenten): Die Test-Registry
deckt § 50 Abs. 1 BRAO, § 224 ZPO, § 233 ZPO und § 694 ZPO ab. Die Marker
in beiden Modulen sind maschinell gedeckt: dieser Test erzwingt Konsistenz
in beide Richtungen (verifizierbares Zitat mit ⚠️ = rot, nicht
verifizierbares Zitat mit ✅ = rot). Historie: eingeführt zusammen mit der
Marker-Umstellung ⚠️→✅ (2026-07-14).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
CALC_DIR = REPO / "plugins" / "legal-ops" / "core" / "calc"
ZITAT_PRUEFER_EXECUTOR = (
    REPO / "plugins" / "legal-ops" / "skills" / "zitat-pruefer" / "executor.py")
REGISTRY = Path(__file__).resolve().parent / "fixtures" / "statische_normen_registry.json"

# Zustands-/Marker-Rangfolge wie im zitat-pruefer-Executor selbst (siehe dort
# _RANG): der "schlechteste" Marker gewinnt bei mehreren Zitaten in einem Text.
_MARKER_RANG = {"❌": 2, "⚠️": 1, "✅": 0}

# Module, deren STATISCHE_NORM_BELEHRUNGEN-Konstante dieser Test prüft.
_MODULE = [
    ("core/calc/retention/executor.py", CALC_DIR / "retention" / "executor.py"),
    ("core/calc/fristen/kalender_executor.py", CALC_DIR / "fristen" / "kalender_executor.py"),
]


def _lade_modul_isoliert(pfad: Path, name: str) -> ModuleType:
    """Lädt ein Executor-Modul über einen eindeutigen Namen (nicht als
    'executor'), damit core/calc/retention/executor.py und
    core/calc/fristen/kalender_executor.py nicht mit dem gleichnamigen
    skills/zitat-pruefer/executor.py in sys.modules kollidieren."""
    spec = importlib.util.spec_from_file_location(name, pfad)
    assert spec and spec.loader, f"Modul nicht ladbar: {pfad}"
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _pruefe_text_gegen_zitat_pruefer(tmp_path: Path, text: str) -> dict:
    """Führt `text` durch den echten zitat-pruefer-CLI-Executor gegen die
    dedizierte Test-Registry und gibt den geparsten JSON-Report zurück."""
    eingabe = tmp_path / "belehrung.md"
    eingabe.write_text(text, encoding="utf-8")
    ausgabe = tmp_path / "report.json"
    ergebnis = subprocess.run(
        [sys.executable, str(ZITAT_PRUEFER_EXECUTOR),
         "--input", str(eingabe), "--registry", str(REGISTRY),
         "--output", str(ausgabe)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, (
        f"zitat-pruefer-Executor fehlgeschlagen (exit {ergebnis.returncode}): "
        f"{ergebnis.stderr}")
    return json.loads(ausgabe.read_text(encoding="utf-8"))


def _worst_case_marker(report: dict) -> str | None:
    """Aggregiert alle Norm-Zitate im Report zum 'schlechtesten' Marker.
    None, wenn der Text gar kein Normzitat enthält (Konfigurationsfehler in
    der Test-Konstante, kein Marker-Konsistenz-Fall)."""
    normzitate = [z for z in report["zitate"] if z["typ"] == "norm"]
    if not normzitate:
        return None
    return max((z["marker"] for z in normzitate), key=lambda m: _MARKER_RANG[m])


def test_registry_fixture_vorhanden():
    assert REGISTRY.is_file(), (
        f"Test-Registry fehlt: {REGISTRY} — ohne sie bleibt jedes Zitat "
        "nicht_pruefbar und der Test ist witzlos")


def test_statische_norm_belehrungen_tragen_konsistenten_marker(tmp_path):
    """Kernprüfung: deklarierter Marker (Quelltext-Konstante) muss mit dem
    von zitat-pruefer bestimmten Marker übereinstimmen — in beide Richtungen
    (a) kein ✅ ohne maschinelle Bestätigung, (b) kein ⚠️ mehr, sobald die
    Registry das Zitat bestätigt."""
    abweichungen: list[str] = []

    for modul_label, modul_pfad in _MODULE:
        modul = _lade_modul_isoliert(modul_pfad, f"_test_{modul_pfad.stem}_{modul_label!r}")
        belehrungen = getattr(modul, "STATISCHE_NORM_BELEHRUNGEN", None)
        assert belehrungen, (
            f"{modul_label}: STATISCHE_NORM_BELEHRUNGEN fehlt oder ist leer — "
            "erwartet eine Liste von {'marker': ..., 'text': ...}-Einträgen")

        for eintrag in belehrungen:
            deklariert = eintrag["marker"]
            text = eintrag["text"]
            report = _pruefe_text_gegen_zitat_pruefer(tmp_path, text)
            erwartet = _worst_case_marker(report)

            if erwartet is None:
                abweichungen.append(
                    f"{modul_label}: kein Normzitat im Belehrungstext erkannt "
                    f"(Text: {text!r})")
                continue

            if deklariert != erwartet:
                abweichungen.append(
                    f"{modul_label}: deklarierter Marker {deklariert!r} != "
                    f"von zitat-pruefer bestimmter Marker {erwartet!r} "
                    f"— Text: {text!r}")

    assert not abweichungen, (
        "Marker-Inkonsistenz zwischen statischer Norm-Belehrung und "
        "zitat-pruefer-Executor (Zitierdisziplin, CONVENTIONS.md):\n"
        + "\n".join(f"  - {a}" for a in abweichungen))
