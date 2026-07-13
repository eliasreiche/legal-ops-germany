"""Install-Smoke-Test (CI-Gate A) — prüft das *ausgelieferte* Artefakt.

Claude Code bündelt beim Install nur das `source`-Dir eines Plugins
(`plugins/legal-ops/`) in den Cache — der Repo-Root ist dort nicht vorhanden.
Dieser Test bildet genau das nach: er kopiert **ausschließlich**
`plugins/legal-ops/` in ein Temp-Verzeichnis und führt jeden Executor-Skill
gegen seine Beispiel-Eingabe aus — mit **absoluten** Pfaden und einem neutralen
Arbeitsverzeichnis (weder Repo-Root noch Plugin-Root), sodass keine
CWD-Annahme durchrutschen kann.

Der Test schlägt fehl, wenn `core/` nicht Teil des Plugins ist (der Bug, den
D14 behebt): dann findet ein Executor sein Rechen-Paket nicht und bricht ab.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_SRC = REPO / "plugins" / "legal-ops"

# Jeder Executor-Skill: Aufruf relativ zum Plugin-Root + erwarteter Exit-Code
# und (wo prüfbar) ein bekannter Ergebniswert. Pfad-Argumente (keine --flags)
# werden zur Laufzeit gegen den kopierten Plugin-Cache absolut gemacht.
EXECUTOR_SKILLS = [
    {
        "id": "fristenrechner-de",
        "executor": "core/calc/fristen/executor.py",
        "args": ["--input", "skills/fristenrechner-de/schema/beispiel-eingabe.json"],
        "exit": 0,
        "assert": lambda r: r["ergebnis"]["fristende"] == "2026-02-16",
        "assert_desc": 'ergebnis.fristende == "2026-02-16"',
    },
    {
        # Zweiter Executor desselben Skills: Kalender-/Docketing-Export aus dem
        # Fristen-Report (calc → export). Prüft, dass auch er self-contained
        # aus dem reinen Plugin-Cache läuft (D14).
        # Nur Datei-Argumente als Werte (der Smoke-Helper macht jeden
        # Nicht-`--`-Token absolut) — Format bleibt Default `ics`.
        "id": "fristenrechner-de-kalender",
        "executor": "core/calc/fristen/kalender_executor.py",
        "args": ["--report", "skills/fristenrechner-de/schema/beispiel-report.json"],
        "exit": 0,
    },
    {
        "id": "rvg-gko-rechner",
        "executor": "core/calc/rvg/executor.py",
        "args": ["--input", "skills/rvg-gko-rechner/schema/beispiel-eingabe.json"],
        "exit": 0,
    },
    {
        "id": "gwg-risiko-check",
        "executor": "skills/gwg-risiko-check/executor.py",
        "args": ["--mandat", "skills/gwg-risiko-check/schema/beispiel-mandat.json"],
        "exit": 0,
    },
    {
        "id": "konflikt-check-offline",
        "executor": "skills/konflikt-check-offline/executor.py",
        "args": ["--liste", "skills/konflikt-check-offline/schema/beispiel-mandantenliste.csv",
                 "--parteien", "skills/konflikt-check-offline/schema/beispiel-neue-parteien.json"],
        "exit": 0,
    },
    {
        "id": "akten-intake-strukturierer",
        "executor": "skills/akten-intake-strukturierer/executor.py",
        "args": ["--aktenkopf", "skills/akten-intake-strukturierer/schema/beispiel-aktenkopf.json",
                 "--quelle", "skills/akten-intake-strukturierer/schema/beispiel-eingabe.md"],
        "exit": 0,
    },
    {
        "id": "zitat-verifier-de",
        "executor": "skills/zitat-verifier-de/executor.py",
        "args": ["--input", "skills/zitat-verifier-de/schema/beispiel-eingabe.md",
                 "--registry", "skills/zitat-verifier-de/schema/beispiel-registry.json"],
        "exit": 0,
    },
]


def _install_cache(tmp_path: Path) -> Path:
    """Kopiert nur plugins/legal-ops/ (ohne Repo-Root) in den simulierten Cache."""
    cache = tmp_path / "install-cache" / "legal-ops"
    # 1:1 wie der reale Install: das gesamte Plugin-Dir kopieren (inkl. der
    # skill-internen tests/), nur Python-Artefakte auslassen.
    shutil.copytree(PLUGIN_SRC, cache,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return cache


def _abs_args(cache: Path, args: list[str]) -> list[str]:
    return [a if a.startswith("--") else str(cache / a) for a in args]


def test_core_wird_mit_ausgeliefert(tmp_path):
    # Kernannahme von D14: core/ liegt INNERHALB des Plugins und landet im Cache.
    cache = _install_cache(tmp_path)
    assert (cache / "core" / "calc").is_dir()
    assert (cache / "core" / "verify" / "struktur_lint.py").is_file()


def _lauf(cache: Path, skill: dict, cwd: Path) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(cache / skill["executor"])] + _abs_args(cache, skill["args"])
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def test_alle_executor_skills_laufen_im_cache(tmp_path):
    """Jeder Executor-Skill läuft aus dem reinen Plugin-Cache heraus mit dem
    dokumentierten Exit-Code — CWD ist bewusst neutral (nicht das Plugin)."""
    cache = _install_cache(tmp_path)
    neutral = tmp_path / "neutral-cwd"
    neutral.mkdir()
    for skill in EXECUTOR_SKILLS:
        res = _lauf(cache, skill, neutral)
        assert res.returncode == skill["exit"], (
            f"{skill['id']}: exit {res.returncode} != {skill['exit']}\n{res.stderr}")
        pruef = skill.get("assert")
        if pruef is not None:
            report = json.loads(res.stdout)
            assert pruef(report), (
                f"{skill['id']}: Ergebnis-Assertion verletzt "
                f"({skill.get('assert_desc')})")


def test_fristenrechner_liefert_bekanntes_fristende(tmp_path):
    """Expliziter Kern-Nachweis des ausgelieferten Artefakts (Brief-Vorgabe)."""
    cache = _install_cache(tmp_path)
    neutral = tmp_path / "cwd"
    neutral.mkdir()
    skill = next(s for s in EXECUTOR_SKILLS if s["id"] == "fristenrechner-de")
    res = _lauf(cache, skill, neutral)
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    assert report["ergebnis"]["fristende"] == "2026-02-16", report["ergebnis"]
