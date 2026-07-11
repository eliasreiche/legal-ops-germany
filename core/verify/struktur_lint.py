#!/usr/bin/env python3
"""Struktur-Lint (P4/P5) — erzwingt die Hausregeln des Repos.

Prüft:
  * jedes SKILL.md trägt die Pflichtfelder aus P5 (rdg_einordnung,
    daten_hinweis, haftung) sowie name/status/welle/plugin,
  * status ist `ungetestet`, `beta` oder `getestet` (Reifegrad-Leiter, D8-Nachtrag):
      - `beta`     = Tests gegen Testdaten/Orakel laufen grün in CI
                     → setzt echte Testdateien in tests/ voraus (.gitkeep zählt nicht)
      - `getestet` = zusätzlich händisch abgenommen
                     → setzt außerdem `haendisch_getestet: <JJJJ-MM-TT>` im Frontmatter voraus,
  * name im Frontmatter == Verzeichnisname,
  * jedes Plugin hat .claude-plugin/plugin.json und README.md,
  * die Status-Tabelle im Repo-README ist synchron (--check, Default in CI);
    --write-readme regeneriert sie.

Nur Standardbibliothek — kein PyYAML, damit der Lint ohne Installation läuft.
Exit-Code 0 = sauber, 1 = Verstöße (CI failt).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PFLICHTFELDER = ["name", "status", "welle", "plugin",
                 "rdg_einordnung", "daten_hinweis", "haftung"]
STATUS_WERTE = {"ungetestet", "beta", "getestet"}
TABELLE_START = "<!-- skill-status:start -->"
TABELLE_ENDE = "<!-- skill-status:ende -->"


def frontmatter(text: str) -> dict[str, str] | None:
    """Liest den YAML-Frontmatter-Block als flache key:value-Paare."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return None
    felder: dict[str, str] = {}
    for zeile in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", zeile)
        if km:
            wert = km.group(2).strip()
            if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "'\"":
                wert = wert[1:-1]
            felder[km.group(1)] = wert
    return felder


def skill_dirs() -> list[Path]:
    dirs = [p.parent for p in sorted(REPO.glob("plugins/*/skills/*/SKILL.md"))]
    dirs += [p.parent for p in sorted(REPO.glob("core/verify/*/SKILL.md"))]
    return dirs


def hat_echte_tests(skill: Path) -> bool:
    tests = skill / "tests"
    return tests.is_dir() and any(
        f.is_file() and f.name != ".gitkeep" for f in tests.rglob("*"))


def pruefe_skill(skill: Path, fehler: list[str]) -> dict[str, str] | None:
    fm = frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
    try:
        ref = skill.relative_to(REPO) / "SKILL.md"
    except ValueError:  # Skill außerhalb des Repos (z. B. in Tests)
        ref = skill / "SKILL.md"
    if fm is None:
        fehler.append(f"{ref}: kein Frontmatter-Block")
        return None
    for feld in PFLICHTFELDER:
        if not fm.get(feld, "").strip():
            fehler.append(f"{ref}: Pflichtfeld `{feld}` fehlt oder ist leer (P5)")
    status = fm.get("status")
    if status not in STATUS_WERTE:
        fehler.append(f"{ref}: status muss `ungetestet`, `beta` oder `getestet` "
                      f"sein, ist: `{status}` (D8-Nachtrag)")
    if fm.get("name") != skill.name:
        fehler.append(f"{ref}: name `{fm.get('name')}` != Verzeichnis `{skill.name}`")
    if status in ("beta", "getestet") and not hat_echte_tests(skill):
        fehler.append(f"{ref}: status `{status}` ohne Testdateien in tests/ (P4)")
    if status == "getestet" and not re.match(
            r"^\d{4}-\d{2}-\d{2}$", fm.get("haendisch_getestet", "")):
        fehler.append(f"{ref}: status `getestet` verlangt "
                      f"`haendisch_getestet: <JJJJ-MM-TT>` im Frontmatter "
                      f"(händische Abnahme, D8-Nachtrag)")
    return fm


def pruefe_plugins(fehler: list[str]) -> None:
    for plugin in sorted((REPO / "plugins").iterdir()):
        if not plugin.is_dir():
            continue
        if not (plugin / ".claude-plugin" / "plugin.json").is_file():
            fehler.append(f"plugins/{plugin.name}: .claude-plugin/plugin.json fehlt")
        if not (plugin / "README.md").is_file():
            fehler.append(f"plugins/{plugin.name}: README.md fehlt")


def status_tabelle(skills: list[tuple[Path, dict[str, str]]]) -> str:
    zeilen = ["| Skill | Plugin | Welle | Status |", "|---|---|---|---|"]
    def sortkey(eintrag):
        pfad, fm = eintrag
        return (int(fm.get("welle", "9")), fm.get("plugin", ""), fm.get("name", ""))
    for pfad, fm in sorted(skills, key=sortkey):
        rel = pfad.relative_to(REPO) / "SKILL.md"
        status = fm.get("status", "?")
        badge = {"getestet": "✅ `getestet`",
                 "beta": "🧪 `beta`"}.get(status, "🚧 `ungetestet`")
        zeilen.append(f"| [`{fm.get('name')}`]({rel}) | `{fm.get('plugin')}` "
                      f"| {fm.get('welle')} | {badge} |")
    return "\n".join(zeilen)


def readme_sync(tabelle: str, schreiben: bool, fehler: list[str]) -> None:
    readme = REPO / "README.md"
    text = readme.read_text(encoding="utf-8")
    if TABELLE_START not in text or TABELLE_ENDE not in text:
        fehler.append(f"README.md: Marker {TABELLE_START} / {TABELLE_ENDE} fehlen")
        return
    neu = re.sub(
        re.escape(TABELLE_START) + r".*?" + re.escape(TABELLE_ENDE),
        TABELLE_START + "\n" + tabelle + "\n" + TABELLE_ENDE,
        text, flags=re.DOTALL)
    if schreiben:
        if neu != text:
            readme.write_text(neu, encoding="utf-8")
            print("README.md: Status-Tabelle aktualisiert")
    elif neu != text:
        fehler.append("README.md: Status-Tabelle nicht synchron — "
                      "`python3 core/verify/struktur_lint.py --write-readme` ausführen")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-readme", action="store_true",
                        help="Status-Tabelle im README regenerieren statt nur prüfen")
    args = parser.parse_args()

    fehler: list[str] = []
    skills: list[tuple[Path, dict[str, str]]] = []
    for skill in skill_dirs():
        fm = pruefe_skill(skill, fehler)
        if fm:
            skills.append((skill, fm))
    pruefe_plugins(fehler)
    readme_sync(status_tabelle(skills), args.write_readme, fehler)

    if fehler:
        print(f"Struktur-Lint: {len(fehler)} Verstöße\n", file=sys.stderr)
        for f in fehler:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print(f"Struktur-Lint: sauber ({len(skills)} Skills geprüft)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
