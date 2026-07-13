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
        "id": "fristenrechner",
        "executor": "core/calc/fristen/executor.py",
        "args": ["--input", "skills/fristenrechner/schema/beispiel-eingabe.json"],
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
        "id": "fristenrechner-kalender",
        "executor": "core/calc/fristen/kalender_executor.py",
        "args": ["--report", "skills/fristenrechner/schema/beispiel-report.json"],
        "exit": 0,
    },
    {
        "id": "rvg-gkg-rechner",
        "executor": "core/calc/rvg/executor.py",
        "args": ["--input", "skills/rvg-gkg-rechner/schema/beispiel-eingabe.json"],
        "exit": 0,
    },
    {
        "id": "gwg-risiko-check",
        "executor": "skills/gwg-risiko-check/executor.py",
        "args": ["--mandat", "skills/gwg-risiko-check/schema/beispiel-mandat.json"],
        "exit": 0,
    },
    {
        "id": "interessenkollision-check",
        "executor": "skills/interessenkollision-check/executor.py",
        "args": ["--liste", "skills/interessenkollision-check/schema/beispiel-mandantenliste.csv",
                 "--parteien", "skills/interessenkollision-check/schema/beispiel-neue-parteien.json"],
        "exit": 0,
    },
    {
        "id": "aktenkopf-extraktor",
        "executor": "skills/aktenkopf-extraktor/executor.py",
        "args": ["--aktenkopf", "skills/aktenkopf-extraktor/schema/beispiel-aktenkopf.json",
                 "--quelle", "skills/aktenkopf-extraktor/schema/beispiel-eingabe.md"],
        "exit": 0,
    },
    {
        "id": "zitat-pruefer",
        "executor": "skills/zitat-pruefer/executor.py",
        "args": ["--input", "skills/zitat-pruefer/schema/beispiel-eingabe.md",
                 "--registry", "skills/zitat-pruefer/schema/beispiel-registry.json"],
        "exit": 0,
    },
    {
        # Kontext-Layer-Fundament (D19): Schema-Validator gegen die
        # Beispiel-Fixture — muss core/context/schema.py aus dem reinen
        # Plugin-Cache heraus importieren können (kein Repo-Root im Pfad).
        "id": "kontext-validator",
        "executor": "core/context/validator.py",
        "args": ["--kontext", "core/context/beispiel-kontext"],
        "exit": 0,
    },
    {
        # Retention-Hinweis-Executor: importiert core/context/schema.py
        # relativ zu core/ — prüft denselben Cache-Import-Pfad wie oben,
        # nur aus core/calc/retention/ heraus.
        "id": "retention-hinweis",
        "executor": "core/calc/retention/executor.py",
        # kein --stichtag hier: _abs_args absolutiert jedes Nicht-"--"-Token,
        # ein Datumswert würde fälschlich zu einem Pfad gemacht. Der
        # Default (heute) genügt für den Cache-/Import-Smoke-Test.
        "args": ["--kontext", "core/context/beispiel-kontext"],
        "exit": 0,
    },
    {
        # filesystem-Referenzadapter: git-artiges Subcommand (`pull`) vor den
        # `--`-Optionen — kein Pfad, darf NICHT über _abs_args absolutiert
        # werden, deshalb `pre_args` statt `args` für dieses eine Token.
        # --kontext und --manifest existieren im Repo noch nicht (frisches
        # Ziel) und werden vom Adapter selbst angelegt — rein innerhalb des
        # Tmp-Caches, keine Repo-Nebenwirkung.
        "id": "kontext-sync-adapter-pull",
        "executor": "core/adapters/filesystem/adapter.py",
        "pre_args": ["pull"],
        "args": [
            "--quelle", "skills/kontext-sync/schema/smoke/quelle",
            "--kontext", "skills/kontext-sync/schema/smoke/kontext-ziel",
            "--manifest", "skills/kontext-sync/schema/smoke/manifest.json",
            "--mapping", "skills/kontext-sync/schema/smoke/mapping.json",
        ],
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
    # pre_args (z. B. ein git-artiges Subcommand wie "pull") werden unverändert
    # übernommen, nie über _abs_args absolutiert (kein Pfad-Argument).
    cmd = ([sys.executable, str(cache / skill["executor"])] + skill.get("pre_args", [])
          + _abs_args(cache, skill["args"]))
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
    skill = next(s for s in EXECUTOR_SKILLS if s["id"] == "fristenrechner")
    res = _lauf(cache, skill, neutral)
    assert res.returncode == 0, res.stderr
    report = json.loads(res.stdout)
    assert report["ergebnis"]["fristende"] == "2026-02-16", report["ergebnis"]
