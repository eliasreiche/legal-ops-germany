# Plugin `legal-ops`

Ein einziges Plugin bündelt alle Skills **und** die geteilten Rechner/Verifier
unter `core/`. So umschließt die Plugin-Grenze (`plugins/legal-ops/`) den
`core/`-Baum — beim Install landen Executors und ihre Rechenkerne gemeinsam im
Cache, jeder Executor-Skill ist im Auslieferungszustand lauffähig.

```
plugins/legal-ops/
├── .claude-plugin/plugin.json
├── core/
│   ├── calc/{fristen, feiertage, rvg, gkg, matching, gwg, wertgebuehr_formel.py}
│   └── verify/struktur_lint.py
├── skills/          # alle Skills, inkl. zitat-verifier-de (Querschnitt)
└── README.md
```

Executor-Aufrufe in den SKILL.md adressieren plugin-relativ über
`${CLAUDE_PLUGIN_ROOT}` (absoluter Pfad zum installierten Plugin-Verzeichnis) —
kein Aufruf setzt ein bestimmtes Arbeitsverzeichnis voraus.

## Prozessbereiche

Die Skills sind fachlich nach sieben Prozesskategorien gegliedert (das Feld
`plugin:` im Frontmatter trägt den Bereich; die Auslieferung bleibt ein Plugin):

| Bereich | Skills |
|---|---|
| `intake` | akten-intake-strukturierer |
| `compliance` | konflikt-check-offline, gwg-risiko-check, gwg-live-screening |
| `fristen-termine` | fristenrechner-de, fristen-docketing-light, scheduling-assistent-de |
| `zeit-abrechnung` | rvg-gko-rechner, zeitnarrativ-rvg, passive-zeiterfassung, ar-mahnwesen-light |
| `post-akte` | email-triage-eakte, posteingang-ocr-routing |
| `kommunikation` | mandantenkommunikation-status |
| `wissen-qm` | wissensmanagement-precedents, kanzlei-sop-qualitygate, datev-buchhaltungsbruecke |
| `querschnitt` | zitat-verifier-de |

Reifegrade und Wellen-Zuordnung stehen in der Status-Tabelle der
[Repo-README](../../README.md). Hausregeln:
[CONVENTIONS.md](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/blob/main/CONVENTIONS.md).
