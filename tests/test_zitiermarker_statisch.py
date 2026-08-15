"""CI-Test: Marker-Konsistenz für statische Norm-Belehrungen in Executor-Outputs.

Hintergrund: Statische Norm-Belehrungen in Executor-Outputs
(`core/calc/retention/executor.py`, `core/calc/fristen/kalender_executor.py`,
`core/calc/fristen/executor.py`) tragen einen 3-Zustands-Zitiermarker nach
CONVENTIONS.md ("Zitierdisziplin"). ⚠️ ("nicht prüfbar") ist semantisch falsch,
sobald eine Quellen-Registry die zitierte Norm führt; ✅ ("verifiziert") ist
umgekehrt nur ehrlich, wenn die Norm dort auch wirklich steht.

**Was dieser Test prüft — und was nicht.** Er prüft ausschließlich
*Konsistenz* zwischen dem im Quelltext deklarierten Marker und der
handgepflegten Registry `tests/fixtures/statische_normen_registry.json`:

  (a) jede Belehrung mit ✅ zitiert nur Normen, die die Registry führt,
  (b) jede Belehrung, deren Zitate die Registry vollständig führt, trägt
      kein ⚠️ mehr,
  (c) jede Belehrung mit einem nicht geführten Zitat trägt ⚠️.

Er prüft **nicht** inhaltlich, ob eine Fundstelle stimmt — das ist die
Maintainer-Abnahme, dokumentiert in der Registry selbst (`geprueft_am`,
`geprueft_von`, `quelle` je Eintrag). Der frühere Weg über den
`zitat-pruefer`-CLI ist entfallen (Skill 2026-07-16 zurückgestellt); diese
Fassung kommt ohne ihn aus und liest nur die Registry.

Die Belehrungen kommen aus der je Modul exportierten Konstante
`STATISCHE_NORM_BELEHRUNGEN` (kein fragiles Quelltext-Grep). Mehrere
Normzitate in einer Belehrung (z. B. "§ 224 Abs. 2 ZPO" und "§§ 233 ff. ZPO"
im selben Fließtext) werden nach Worst Case aggregiert: ein einziges nicht
geführtes Zitat macht die ganze Belehrung zu ⚠️.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
CALC_DIR = REPO / "plugins" / "legal-ops" / "core" / "calc"
REGISTRY = Path(__file__).resolve().parent / "fixtures" / "statische_normen_registry.json"

# Module, deren STATISCHE_NORM_BELEHRUNGEN-Konstante dieser Test prüft.
_MODULE = [
    ("core/calc/retention/executor.py", CALC_DIR / "retention" / "executor.py"),
    ("core/calc/fristen/kalender_executor.py", CALC_DIR / "fristen" / "kalender_executor.py"),
    ("core/calc/fristen/executor.py", CALC_DIR / "fristen" / "executor.py"),
]

# Normzitat im Fließtext: "§ 694 ZPO", "§ 224 Abs. 1 Satz 2 ZPO",
# "§§ 233 ff. ZPO", "§ 50 Abs. 1 BRAO". Bewusst eng — ein Zitat in einer
# hier nicht erfassten Schreibweise fällt nicht still durch, sondern lässt die
# Belehrung als "kein Normzitat erkannt" auflaufen (siehe Test unten).
_NORM_RE = re.compile(
    r"§§?\s*(\d+[a-z]?)"
    r"(?:\s+Abs\.\s*\d+)?"
    r"(?:\s+Satz\s*\d+)?"
    r"(?:\s+ff\.)?"
    r"\s+([A-ZÄÖÜ][A-Za-zÄÖÜ]{1,9})")


def _lade_modul_isoliert(pfad: Path, name: str) -> ModuleType:
    """Lädt ein Executor-Modul unter eindeutigem Namen (nicht als 'executor'),
    damit die gleichnamigen executor.py mehrerer Skills sich in sys.modules
    nicht gegenseitig überschreiben."""
    spec = importlib.util.spec_from_file_location(name, pfad)
    assert spec and spec.loader, f"Modul nicht ladbar: {pfad}"
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _zitate(text: str) -> list[tuple[str, str]]:
    """Alle Normzitate eines Belehrungstexts als (kuerzel, paragraph)."""
    return [(kuerzel, paragraph) for paragraph, kuerzel in _NORM_RE.findall(text)]


def _gefuehrte_normen() -> set[tuple[str, str]]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {(n["kuerzel"], str(n["paragraph"])) for n in registry["normen"]}


def test_registry_fixture_vorhanden():
    assert REGISTRY.is_file(), (
        f"Test-Registry fehlt: {REGISTRY} — ohne sie ist der Test witzlos")
    assert _gefuehrte_normen(), "Test-Registry führt keine einzige Norm"


def test_statische_norm_belehrungen_tragen_konsistenten_marker():
    """Kernprüfung: deklarierter Marker == Marker, den die Registry-Deckung
    hergibt — in beide Richtungen (kein ✅ ohne Registry-Eintrag, kein ⚠️
    trotz vollständiger Deckung)."""
    gefuehrt = _gefuehrte_normen()
    abweichungen: list[str] = []

    for modul_label, modul_pfad in _MODULE:
        modul = _lade_modul_isoliert(modul_pfad, f"_zitiermarker_{modul_pfad.stem}_"
                                                 f"{modul_pfad.parent.name}")
        belehrungen = getattr(modul, "STATISCHE_NORM_BELEHRUNGEN", None)
        assert belehrungen, (
            f"{modul_label}: STATISCHE_NORM_BELEHRUNGEN fehlt oder ist leer — "
            "erwartet eine Liste von {'marker': ..., 'text': ...}-Einträgen")

        for eintrag in belehrungen:
            deklariert = eintrag["marker"]
            text = eintrag["text"]
            zitate = _zitate(text)

            if not zitate:
                abweichungen.append(
                    f"{modul_label}: kein Normzitat im Belehrungstext erkannt "
                    f"(Text: {text!r})")
                continue

            fehlend = [z for z in zitate if z not in gefuehrt]
            erwartet = "⚠️" if fehlend else "✅"
            if deklariert != erwartet:
                grund = (f"nicht in der Registry: "
                         f"{', '.join(f'§ {p} {k}' for k, p in fehlend)}"
                         if fehlend else "alle Zitate sind in der Registry geführt")
                abweichungen.append(
                    f"{modul_label}: Marker {deklariert!r} deklariert, "
                    f"{erwartet!r} erwartet ({grund}) — Text: {text!r}")

    assert not abweichungen, (
        "Marker-Inkonsistenz zwischen statischer Norm-Belehrung und "
        "Quellen-Registry (Zitierdisziplin, CONVENTIONS.md):\n"
        + "\n".join(f"  - {a}" for a in abweichungen))


def test_erkennung_und_bewertung_greifen():
    """Selbstkontrolle: der Zitat-Extraktor erkennt die im Repo vorkommenden
    Schreibweisen, und eine nicht geführte Norm kippt die Bewertung auf ⚠️."""
    assert _zitate("✅ Notfrist (§ 224 Abs. 1 Satz 2 ZPO), sonst §§ 233 ff. ZPO.") == [
        ("ZPO", "224"), ("ZPO", "233")]
    assert _zitate("✅ § 50 Abs. 1 BRAO — Handakten") == [("BRAO", "50")]
    gefuehrt = _gefuehrte_normen()
    assert ("ZPO", "999") not in gefuehrt
    assert [z for z in _zitate("§ 999 ZPO") if z not in gefuehrt] == [("ZPO", "999")]
