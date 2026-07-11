# core/calc — geteilte deterministische Rechner

Ein Rechner, viele Skills — keine Duplikation. Jeder Rechner: pytest-Unit-Tests
+ Orakel-Fälle gegen borghei `legal_calc` (P4).

| Rechner | Stand | Inhalt |
|---|---|---|
| [`feiertage/`](feiertage/) | umgesetzt | Gesetzliche Feiertage aller 16 Bundesländer, berechnet (Gaußsche Osterformel), teilgebietliche Feiertage ehrlich gekennzeichnet. |
| [`fristen/`](fristen/) | umgesetzt | Fristberechnung §§ 186–193 BGB / § 222 ZPO mit nachvollziehbarer Rechenkette; Fristarten-Katalog als Daten ([`fristen/fristarten.json`](fristen/fristarten.json)); CLI-Executor JSON rein → JSON raus. |
| `rvg`, `gkg`, `verjaehrung`, `extf` | geplant | — |

Tests liegen beim nutzenden Skill (z. B.
[`plugins/fristen-termine/skills/fristenrechner-de/tests/`](../../plugins/fristen-termine/skills/fristenrechner-de/tests/)).
