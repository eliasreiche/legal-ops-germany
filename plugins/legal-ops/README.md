# Plugin `legal-ops`

Ein einziges Plugin bündelt alle Skills **und** die geteilten Rechner/Verifier
unter `core/`. So umschließt die Plugin-Grenze (`plugins/legal-ops/`) den
`core/`-Baum — beim Install landen Executors und ihre Rechenkerne gemeinsam im
Cache, jeder Executor-Skill ist im Auslieferungszustand lauffähig.

Executor-Aufrufe in den SKILL.md adressieren plugin-relativ über
`${CLAUDE_PLUGIN_ROOT}` (absoluter Pfad zum installierten Plugin-Verzeichnis) —
kein Aufruf setzt ein bestimmtes Arbeitsverzeichnis voraus.

## Prozessbereiche

Die Skills sind fachlich nach sieben Prozesskategorien gegliedert (das Feld
`bereich:` im Frontmatter trägt den Bereich; die Auslieferung bleibt ein
Plugin). Bereich, Welle und Reifegrad je Skill stehen in der generierten
Status-Tabelle der [Repo-README](../../README.md). Hausregeln:
[CONVENTIONS.md](https://github.com/eliasreiche/legal-ops-germany/blob/main/CONVENTIONS.md).
