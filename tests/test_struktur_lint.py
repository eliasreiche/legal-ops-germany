"""Tests für core/verify/struktur_lint.py — der Lint ist selbst getestet (P4)."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "verify"))

import struktur_lint  # noqa: E402


def test_frontmatter_liest_quoted_werte():
    fm = struktur_lint.frontmatter(
        '---\nname: foo\nstatus: Work-in-progress\nhaftung: "Zweitkontrolle."\n---\n# x\n')
    assert fm == {"name": "foo", "status": "Work-in-progress",
                  "haftung": "Zweitkontrolle."}


def test_frontmatter_fehlt():
    assert struktur_lint.frontmatter("# kein Frontmatter\n") is None


def test_alle_skills_gefunden():
    # 18 Skill-Kandidaten sind von Anfang an sichtbar (D8); #19 kontext-sync
    # kommt mit dem Kontext-Layer-Fundament (D19) hinzu.
    assert len(struktur_lint.skill_dirs()) == 19


def _skill(tmp_path, name, status, extra="", mit_tests=False):
    skill = tmp_path / name
    (skill / "tests").mkdir(parents=True)
    (skill / "tests" / ".gitkeep").write_text("")
    if mit_tests:
        (skill / "tests" / "test_x.py").write_text("def test_x(): pass\n")
    (skill / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "x"\nstatus: {status}\nwelle: 1\n'
        f'plugin: intake\n'
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
    assert "description" in meldungen   # Pflicht seit 197a96f (Skill-Discovery)
    assert "rdg_einordnung" in meldungen
    assert "daten_hinweis" in meldungen
    assert "haftung" in meldungen
    assert "Work-in-progress`, `beta` oder `getestet" in meldungen


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
        [sys.executable, str(REPO / "plugins" / "legal-ops" / "core" / "verify" / "struktur_lint.py")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr


# --------------------------------------------------------------------------
# Containment-Regel (Gate B) — Executor-Pfade und Doku-Links dürfen die
# Plugin-Grenze nicht verlassen. Genau die Regel, die den fehlenden-core-Bug
# gefangen hätte.
# --------------------------------------------------------------------------

def _plugin_skill(tmp_path, name="demo-skill", skill_md="", core_files=()):
    """Baut plugins/legal-ops/{core,skills/<name>} unter tmp_path nach, damit
    plugin_root(skill) == .../legal-ops und ${CLAUDE_PLUGIN_ROOT} auf legal-ops
    zeigt."""
    plugin = tmp_path / "plugins" / "legal-ops"
    skill = plugin / "skills" / name
    skill.mkdir(parents=True)
    for rel in core_files:
        f = plugin / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
    (skill / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return skill


def test_containment_akzeptiert_plugin_relative_referenzen(tmp_path):
    md = ("# demo\n"
          "python3 ${CLAUDE_PLUGIN_ROOT}/core/calc/fristen/executor.py --input x.json\n"
          "Siehe [Rechner](../../core/calc/fristen/executor.py) und "
          "[Konvention](https://example.org/CONVENTIONS.md).\n")
    skill = _plugin_skill(tmp_path, skill_md=md,
                          core_files=["core/calc/fristen/executor.py"])
    fehler: list[str] = []
    struktur_lint.pruefe_containment(skill, fehler)
    assert fehler == [], fehler


def test_containment_meldet_escape_doku_link(tmp_path):
    md = "# demo\nSiehe [CONVENTIONS](../../../../CONVENTIONS.md).\n"
    skill = _plugin_skill(tmp_path, skill_md=md)
    fehler: list[str] = []
    struktur_lint.pruefe_containment(skill, fehler)
    assert any("verlässt die Plugin-Grenze" in f for f in fehler), fehler


def test_containment_meldet_cwd_relativen_executor(tmp_path):
    md = "# demo\npython3 core/calc/fristen/executor.py --input x.json\n"
    skill = _plugin_skill(tmp_path, skill_md=md,
                          core_files=["core/calc/fristen/executor.py"])
    fehler: list[str] = []
    struktur_lint.pruefe_containment(skill, fehler)
    assert any("nicht plugin-relativ" in f for f in fehler), fehler


def test_containment_meldet_fehlenden_executor(tmp_path):
    md = ("# demo\n"
          "python3 ${CLAUDE_PLUGIN_ROOT}/core/calc/fehlt/executor.py --input x.json\n")
    skill = _plugin_skill(tmp_path, skill_md=md)
    fehler: list[str] = []
    struktur_lint.pruefe_containment(skill, fehler)
    assert any("existiert nicht" in f for f in fehler), fehler


# --------------------------------------------------------------------------
# Kontext-Layer (D11, D19) — optionale kontext_reads/kontext_writes-Felder.
# --------------------------------------------------------------------------

def test_liste_feld_flow_stil():
    text = "---\nkontext_reads: [mandate/*.md, kontakte.md]\n---\n# x\n"
    assert struktur_lint.liste_feld(text, "kontext_reads") == ["mandate/*.md", "kontakte.md"]


def test_liste_feld_block_stil():
    text = "---\nkontext_writes:\n  - mandate/*.md\n  - kontakte.md\n---\n# x\n"
    assert struktur_lint.liste_feld(text, "kontext_writes") == ["mandate/*.md", "kontakte.md"]


def test_liste_feld_einzelner_skalar():
    text = "---\nkontext_reads: mandate/*.md\n---\n# x\n"
    assert struktur_lint.liste_feld(text, "kontext_reads") == ["mandate/*.md"]


def test_liste_feld_nicht_vorhanden_ist_none():
    text = "---\nname: x\n---\n# x\n"
    assert struktur_lint.liste_feld(text, "kontext_reads") is None


def test_pruefe_kontext_felder_gueltige_muster_sind_sauber():
    text = "---\nkontext_reads: [mandate/*.md, kanzlei.md]\nkontext_writes: [export/*]\n---\n"
    fehler: list[str] = []
    struktur_lint.pruefe_kontext_felder(text, "ref", fehler)
    assert fehler == []


def test_pruefe_kontext_felder_leere_liste_ist_fehler():
    text = "---\nkontext_reads: []\n---\n"
    fehler: list[str] = []
    struktur_lint.pruefe_kontext_felder(text, "ref", fehler)
    assert any("leer" in f for f in fehler)


def test_pruefe_kontext_felder_muster_ohne_dokumentierten_bereich_ist_fehler():
    text = "---\nkontext_reads: [irgendwo/x.md]\n---\n"
    fehler: list[str] = []
    struktur_lint.pruefe_kontext_felder(text, "ref", fehler)
    assert any("dokumentierten kontext/-Bereich" in f for f in fehler)


def test_pruefe_kontext_felder_leeres_muster_ist_fehler():
    text = "---\nkontext_reads: [mandate/*.md, \"\"]\n---\n"
    fehler: list[str] = []
    struktur_lint.pruefe_kontext_felder(text, "ref", fehler)
    assert any("leeres Muster" in f for f in fehler)


def test_pruefe_skill_ohne_kontext_felder_bleibt_gueltig(tmp_path):
    # Kein Pflichtfeld — bestehende Skills ohne kontext_reads/writes bleiben
    # gültig (Regressionsschutz für die 18 bestehenden Skills).
    fehler: list[str] = []
    struktur_lint.pruefe_skill(_skill(tmp_path, "beta-skill", "beta", mit_tests=True), fehler)
    assert fehler == []


def test_pruefe_skill_mit_gueltigen_kontext_feldern_bleibt_gueltig(tmp_path):
    fehler: list[str] = []
    struktur_lint.pruefe_skill(
        _skill(tmp_path, "beta-skill", "beta", mit_tests=True,
               extra="kontext_reads: [mandate/*.md]\nkontext_writes: [kontakte.md]\n"),
        fehler)
    assert fehler == []


def test_pruefe_skill_mit_ungueltigem_kontext_feld_meldet_fehler(tmp_path):
    fehler: list[str] = []
    struktur_lint.pruefe_skill(
        _skill(tmp_path, "beta-skill", "beta", mit_tests=True,
               extra="kontext_reads: [irgendwo/x.md]\n"),
        fehler)
    assert any("dokumentierten kontext/-Bereich" in f for f in fehler)


def test_containment_meldet_mehrzeilige_cwd_relative_invocation(tmp_path):
    # Bash-Zeilenfortsetzung: `python3` auf Zeile 1, `executor.py` auf der
    # Folgezeile. Ohne das Zusammenfassen der `\`-Fortsetzungen rutschte diese
    # (CWD-relative, also im Cache nicht lauffähige) Invocation durch.
    md = ("# demo\n"
          "python3 \\\n"
          "  core/calc/fristen/executor.py \\\n"
          "  --input x.json\n")
    skill = _plugin_skill(tmp_path, skill_md=md,
                          core_files=["core/calc/fristen/executor.py"])
    fehler: list[str] = []
    struktur_lint.pruefe_containment(skill, fehler)
    assert any("nicht plugin-relativ" in f for f in fehler), fehler
