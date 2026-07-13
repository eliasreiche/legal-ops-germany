---
name: gwg-risiko-check
description: "GwG-Risikoscoring eines Mandats anhand der Katalogfaktoren der Anlagen 1 und 2 GwG mit Dokumentations-Output für die interne Akte — offline, deterministisch, regelbasierter Klassifikationsvorschlag mit Fundstellen. Triggert bei Geldwäsche-Risiko, GwG-Prüfung, Risikoklassifizierung Mandat, Sorgfaltspflichten, § 10 GwG. Die Bewertung bleibt beim Verpflichteten."
status: beta
welle: 2
plugin: compliance
rdg_einordnung: "Strukturierte Dokumentationshilfe zu gesetzlichen Katalogfaktoren (Anlagen 1/2 GwG) mit regelbasiertem Klassifikationsvorschlag; keine Rechtsdienstleistung — die Risikobewertung und die Maßnahmenentscheidung trifft der Verpflichtete (§ 10 Abs. 2 GwG)."
daten_hinweis: "KYC-/Mandatsdaten im Input — pseudonymisieren oder DSGVO-/BRAO-konformen Modellzugang nutzen (AWS-Bedrock-Pfad, § 203 StGB). Der Executor arbeitet rein lokal, ohne Netzwerkzugriff."
haftung: "Ersetzt keine GwG-Pflichtenprüfung; das Scoring ist ein Vorschlag zur Aktendokumentation, kein Verwaltungsakt-sicherer Nachweis. Zweitkontrolle und Bewertung bleiben Kanzleisache. Anlagen-Inhalte und Länderliste sind vor produktiver Nutzung gegen gesetze-im-internet.de bzw. die Delegierte Verordnung (EU) 2016/1675 zu prüfen."
---

# gwg-risiko-check

> **Status: `beta`** — automatisierte Tests laufen grün in CI
> (`tests/test_gwg_rechner.py` + `tests/test_gwg_executor_cli.py`, 34 Fälle). Noch
> **nicht** händisch abgenommen: Die Katalog-Fundstellen der Anlagen 1/2 GwG und
> die Hochrisiko-Länderliste sind Platzhalter und vor produktiver Nutzung gegen
> die aktuelle Gesetzesfassung zu prüfen. `status: getestet` wird erst nach
> dieser Prüfung durch den Maintainer gesetzt (siehe
> [CONVENTIONS.md](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/blob/main/CONVENTIONS.md), Reifegrad-Leiter).

## Zweck

GwG-Risikoscoring eines Mandats anhand der Katalogfaktoren nach den Anlagen 1
und 2 GwG mit einem Dokumentations-Output für die interne Akte — vollständig
offline und deterministisch. Das Ergebnis ist ein **regelbasierter
Klassifikationsvorschlag** (keine numerischen Gewichts-Scores), der die
angewandten Faktoren mit exakter Fundstelle und die anwendbaren
Sorgfaltspflichten benennt. Die **Bewertung selbst trifft der Verpflichtete**
(risikobasierter Ansatz, § 10 Abs. 2 GwG).

## Eingaben (Datei-Kontrakt, P2)

| Eingabe | Pflicht | Format | Beschreibung |
|---|---|---|---|
| Mandats-Fragebogen | ja | `.json` | Strukturierter Fragebogen zum Mandat — siehe [`schema/README.md`](schema/README.md) und [`schema/beispiel-mandat.json`](schema/beispiel-mandat.json). Fehlende Felder = `unklar` (nie geraten). |

Die Katalogfaktoren (Fundstelle + Paraphrase) liegen als Daten in
[`core/calc/gwg/anlage1.json`](../../core/calc/gwg/anlage1.json),
[`core/calc/gwg/anlage2.json`](../../core/calc/gwg/anlage2.json) und
[`core/calc/gwg/hochrisiko_drittstaaten.json`](../../core/calc/gwg/hochrisiko_drittstaaten.json).

> ⚠️ **Anti-Halluzination.** Die Faktoren sind **Paraphrasen** mit exakter
> Fundstelle (z. B. „Anlage 2 Nr. 1 Buchst. e GwG"), **kein** Wortlaut-Zitat.
> Die Buchstaben-Zuordnung der Anlagen und die Zusammensetzung der
> Hochrisiko-Länderliste (Delegierte Verordnung (EU) 2016/1675) ändern sich und
> sind vor produktiver Nutzung gegen gesetze-im-internet.de bzw. die aktuelle
> EU-Fassung zu prüfen. Jede Norm-Fundstelle im Output trägt einen
> 3-Zustands-Marker.

## Ablauf

1. **Claude füllt den Fragebogen** ausschließlich aus dem, was Nutzer oder Akte
   hergeben. Was nicht belegt ist, bleibt `unklar` — **nie raten** (P-Anti-
   Halluzination). Ergebnis: eine Mandatsdatei nach
   [`schema/README.md`](schema/README.md).

2. **Der Executor rechnet und klassifiziert** (kein eigenes Scoring durch das
   Modell, P3):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/gwg-risiko-check/executor.py \
     --mandat <mandat.json> \
     [--output <report.json>]
   ```

   Der regelbasierte Rechner ([`core/calc/gwg/rechner.py`](../../core/calc/gwg/rechner.py))
   entscheidet über die erste greifende Regel: Anwendbarkeits-Gate
   (§ 2 Abs. 1 Nr. 10 GwG) → kritische Lücken → § 15 (PEP/Hochrisiko-Drittstaat)
   → nur Anlage-1-Faktoren → sonst. Claude liest **nur** den erzeugten Report
   und übernimmt Status, Faktoren und Fundstellen unverändert.

3. **Claude rendert den Report als Akten-Dokumentation** (Markdown):
   Anwendbarkeit, Faktoren-Tabelle mit Fundstellen (jede mit ihrem
   3-Zustands-Marker), Klassifikationsvorschlag mit Begründung, Pflichten-
   Hinweise (§§ 10/14/15/43 GwG) und Lücken. Jeder Zahlen-/Status-/
   Fundstellenwert stammt aus dem Report, nicht aus dem Modell.

4. **zitat-verifier-Lauf** als letzter Schritt: Die gerenderte Markdown-Doku
   wird durch [`zitat-verifier-de`](../zitat-verifier-de/SKILL.md)
   mit der mitgelieferten Registry geprüft, damit die §-Zitate nicht unmarkiert
   bleiben:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/zitat-verifier-de/executor.py \
     --input <akten-doku.md> \
     --registry ${CLAUDE_PLUGIN_ROOT}/skills/gwg-risiko-check/schema/quellen-registry.json
   ```

   Die Anlagen-Fundstellen sind kein §-Zitat und werden vom Verifier nicht
   erfasst; sie behalten ihren ⚠️-Marker und gehören zur händischen Abnahme.

## Output-Format

JSON-Report nach [`schema/README.md`](schema/README.md), Beispiel:
[`schema/beispiel-report.json`](schema/beispiel-report.json) (erzeugt aus
[`schema/beispiel-mandat.json`](schema/beispiel-mandat.json)).

Der Klassifikationsvorschlag ist einer von:
`nicht_verpflichtet`, `unvollstaendig`, `niedrig`, `mittel`, `hoch`. Bei
`nicht_verpflichtet`/`unvollstaendig` wird **bewusst keine Risikoklasse**
vergeben. Jeder Wert trägt `quelle: "executor"` (P3).

## Beispiele

### Beispiel 1 — mittleres Risiko (allgemeine Sorgfaltspflichten)

Ein Immobilienkauf-Mandat einer deutschen GmbH, wirtschaftlich Berechtigter
geklärt, kein PEP, aber bargeldintensiv. Der Executor liefert
`klassifikationsvorschlag: "mittel"` mit dem Faktor „Anlage 2 Nr. 1 Buchst. e
GwG" (bargeldintensiv) und dem Hinweis auf § 10 GwG
([`schema/beispiel-report.json`](schema/beispiel-report.json)).

### Beispiel 2 — hohes Risiko (PEP)

Ist im Fragebogen `pep: "ja"` gesetzt, greift Regel 2: Ergebnis `hoch` mit dem
Faktor „§ 15 Abs. 3 Nr. 1 GwG" und dem Pflichten-Hinweis auf die verstärkten
Sorgfaltspflichten (§ 15 GwG). Bei `sitz_land` in einem hinterlegten
Hochrisiko-Drittstaat greift dieselbe Regel über „Anlage 2 Nr. 3 Buchst. a GwG"
/ § 15 Abs. 3 Nr. 2 GwG — der Länder-Treffer wird immer mit dem Vorbehalt
„Liste ändert sich laufend — Stand prüfen" gekennzeichnet.

### Beispiel 3 — nicht verpflichtet

Ist `kataloggeschaeft: "keins"`, ist der Rechtsanwalt insoweit kein
Verpflichteter (§ 2 Abs. 1 Nr. 10 GwG): Ergebnis `nicht_verpflichtet`, keine
Risikoklasse, mit dem Vorbehalt „Einordnung prüfen".

## Grenzen (bewusst)

- **Kein Rechtsrat, keine Bewertung** — nur Dokumentationshilfe; die
  Risikobewertung trifft der Verpflichtete (§ 10 Abs. 2 GwG).
- **Anlagen-Inhalte und Länderliste sind Platzhalter** — vor produktiver
  Nutzung gegen die aktuelle Gesetzes-/EU-Fassung zu prüfen (Reifegrad
  `getestet`).
- **Keine PEP-Ermittlung, kein Sanktionslisten-Abgleich, keine
  Identifizierung** — dafür ist der Live-Screening-Pfad bzw. eine eigene
  Prüfung nötig.
