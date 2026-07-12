# core/calc — geteilte deterministische Rechner

Ein Rechner, viele Skills — keine Duplikation. Jeder Rechner: pytest-Unit-Tests
+ Orakel-Fälle gegen borghei `legal_calc` (P4).

| Rechner | Stand | Inhalt |
|---|---|---|
| [`feiertage/`](feiertage/) | umgesetzt | Gesetzliche Feiertage aller 16 Bundesländer, berechnet (Gaußsche Osterformel), teilgebietliche Feiertage ehrlich gekennzeichnet. |
| [`fristen/`](fristen/) | umgesetzt | Fristberechnung §§ 186–193 BGB / § 222 ZPO mit nachvollziehbarer Rechenkette; Fristarten-Katalog als Daten ([`fristen/fristarten.json`](fristen/fristarten.json)); CLI-Executor JSON rein → JSON raus. |
| [`rvg/`](rvg/) | umgesetzt | RVG-Wertgebühren (§ 13 RVG als Stufenformel + versionierte Parameterdaten, KostRÄG 2021 / KostBRÄG 2025, Stichtag § 60 RVG); VV-Katalog als Daten ([`rvg/vv-katalog.json`](rvg/vv-katalog.json)); Anrechnung Vorbem. 3 Abs. 4 VV RVG; gemeinsamer CLI-Executor ([`rvg/executor.py`](rvg/executor.py)) für RVG **und** GKG. Nur `decimal.Decimal`, nie float. |
| [`gkg/`](gkg/) | umgesetzt | GKG-Gerichtskosten (§ 34 GKG analog als Formel + versionierte Daten, Stichtag § 71 GKG); KV-Katalog als Daten ([`gkg/kv-katalog.json`](gkg/kv-katalog.json)); Streitwert-Höchstgrenze § 39 Abs. 2 GKG. Gemeinsame Stufenformel in [`wertgebuehr_formel.py`](wertgebuehr_formel.py). |
| `verjaehrung`, `extf` | geplant | — |

Tests liegen beim nutzenden Skill (z. B.
[`plugins/fristen-termine/skills/fristenrechner-de/tests/`](../../plugins/fristen-termine/skills/fristenrechner-de/tests/)).
