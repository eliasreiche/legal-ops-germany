"""Tests für core/verify/struktur_lint.py — der Lint ist selbst getestet (P4)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "core" / "verify"))

import struktur_lint  # noqa: E402


def test_frontmatter_liest_quoted_werte():
    fm = struktur_lint.frontmatter(
        '---\nname: foo\nstatus: ungetestet\nhaftung: "Zweitkontrolle."\n---\n# x\n')
    assert fm == {"name": "foo", "status": "ungetestet",
                  "haftung": "Zweitkontrolle."}


def test_frontmatter_fehlt():
    assert struktur_lint.frontmatter("# kein Frontmatter\n") is None


def test_alle_skills_gefunden():
    # 18 Skill-Kandidaten sind von Anfang an sichtbar (D8)
    assert len(struktur_lint.skill_dirs()) == 18


def _skill(tmp_path, name, status, extra="", mit_tests=False):
    skill = tmp_path / name
    (skill / "tests").mkdir(parents=True)
    (skill / "tests" / ".gitkeep").write_text("")
    if mit_tests:
        (skill / "tests" / "test_x.py").write_text("def test_x(): pass\n")
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\nstatus: {status}\nwelle: 1\nplugin: intake\n"
        f'rdg_einordnung: "x"\ndaten_hinweis: "x"\nhaftung: "x"\n{extra}---\n# x\n',
        encoding="utf-8")
    return skill


def test_pruefe_skill_meldet_fehlende_pflichtfelder(tmp_path):
    skill = tmp_path / "kaputter-skill"
    (skill / "tests").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: kaputter-skill\nstatus: stable\n---\n# x\n", encoding="utf-8")
    fehler: list[str] = []
    struktur_lint.pruefe_skill(skill, fehler)
    meldungen = "\n".join(fehler)
    assert "rdg_einordnung" in meldungen
    assert "daten_hinweis" in meldungen
    assert "haftung" in meldungen
    assert "ungetestet`, `beta` oder `getestet" in meldungen


def test_beta_verlangt_echte_tests(tmp_path):
    fehler: list[str] = []
    struktur_lint.pruefe_skill(_skill(tmp_path, "leerer-skill", "beta"), fehler)
    assert any("ohne Testdateien" in f for f in fehler)


def test_beta_mit_tests_ist_sauber(tmp_path):
    fehler: list[str] = []
    struktur_lint.pruefe_skill(
        _skill(tmp_path, "beta-skill", "beta", mit_tests=True), fehler)
    assert fehler == []


def test_getestet_verlangt_haendische_abnahme(tmp_path):
    fehler: list[str] = []
    struktur_lint.pruefe_skill(
        _skill(tmp_path, "auto-skill", "getestet", mit_tests=True), fehler)
    assert any("haendisch_getestet" in f for f in fehler)


def test_getestet_mit_abnahme_und_tests_ist_sauber(tmp_path):
    fehler: list[str] = []
    struktur_lint.pruefe_skill(
        _skill(tmp_path, "fertig-skill", "getestet",
               extra="haendisch_getestet: 2026-07-11\n", mit_tests=True), fehler)
    assert fehler == []


def test_lint_laeuft_sauber_auf_dem_repo():
    ergebnis = subprocess.run(
        [sys.executable, str(REPO / "core" / "verify" / "struktur_lint.py")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
