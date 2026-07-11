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


def test_pruefe_skill_meldet_fehlende_pflichtfelder(tmp_path):
    skill = tmp_path / "kaputter-skill"
    (skill / "tests").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: kaputter-skill\nstatus: beta\n---\n# x\n", encoding="utf-8")
    fehler: list[str] = []
    struktur_lint.pruefe_skill(skill, fehler)
    meldungen = "\n".join(fehler)
    assert "rdg_einordnung" in meldungen
    assert "daten_hinweis" in meldungen
    assert "haftung" in meldungen
    assert "getestet` oder `ungetestet" in meldungen


def test_getestet_verlangt_echte_tests(tmp_path):
    skill = tmp_path / "leerer-skill"
    (skill / "tests").mkdir(parents=True)
    (skill / "tests" / ".gitkeep").write_text("")
    (skill / "SKILL.md").write_text(
        "---\nname: leerer-skill\nstatus: getestet\nwelle: 1\nplugin: intake\n"
        'rdg_einordnung: "x"\ndaten_hinweis: "x"\nhaftung: "x"\n---\n# x\n',
        encoding="utf-8")
    fehler: list[str] = []
    struktur_lint.pruefe_skill(skill, fehler)
    assert any("ohne Testdateien" in f for f in fehler)


def test_lint_laeuft_sauber_auf_dem_repo():
    ergebnis = subprocess.run(
        [sys.executable, str(REPO / "core" / "verify" / "struktur_lint.py")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
