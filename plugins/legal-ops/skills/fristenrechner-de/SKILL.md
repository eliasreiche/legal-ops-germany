---
name: fristenrechner-de
status: beta
welle: 1
plugin: fristen-termine
rdg_einordnung: "Rechnerische Fristermittlung nach §§ 186–193 BGB / § 222 ZPO ohne Subsumtion des Einzelfalls; die rechtliche Einordnung des fristauslösenden Ereignisses (wirksame Zustellung, richtige Fristart, Fristbeginn-Alternativen) bleibt beim Anwalt."
daten_hinweis: "Benötigt nur Datum, Fristart und Bundesland — keine Mandantendaten erforderlich. Der Executor arbeitet rein lokal, ohne Netzwerkzugriff."
haftung: "Zweitkontrolle, zwingend: Der Rechner ist das zweite Augenpaar, nie das erste — er ersetzt keine Fristenkontrolle der Kanzlei (Fristenkalender, Vier-Augen-Prinzip, anwaltliche Endkontrolle bleiben unberührt). Bei Notfristen und teilgebietlichen Feiertagen gilt das doppelt."
---

# fristenrechner-de

> **Status: `beta`** — automatisierte Tests laufen grün in CI (`tests/`,
> inkl. Orakel-Fälle gegen borghei `legal_calc`). Noch **nicht** händisch
> abgenommen — `status: getestet` vergibt erst der Maintainer nach eigener
> Prüfung (siehe [CONVENTIONS.md](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/blob/main/CONVENTIONS.md), Reifegrad-Leiter).

## Zweck

Berechnet Fristen nach §§ 186–193 BGB und § 222 ZPO deterministisch über den
Executor [`core/calc/fristen/`](../../core/calc/fristen/) — mit
vollständiger, nachvollziehbarer **Rechenkette**: Fristbeginn (§ 187 BGB),
rechnerisches Ende (§ 188 BGB, inkl. Monatsende-Fall des Abs. 3), jede
Verschiebung wegen Sonnabend/Sonntag/Feiertag (§ 193 BGB / § 222 Abs. 2 ZPO)
einzeln mit Grund und Norm. Die Feiertage des Fristende-Orts liefert
[`core/calc/feiertage/`](../../core/calc/feiertage/) (alle 16
Bundesländer, berechnet für beliebige Jahre, teilgebietliche Feiertage ehrlich
gekennzeichnet).

**Positionierung: strikt Zweitkontrolle.** Der Rechner ersetzt keine
Fristenkontrolle der Kanzlei — er ist das zweite Augenpaar neben
Fristenkalender und Vier-Augen-Prinzip. Ein abweichendes Ergebnis ist ein
Anlass zur Prüfung, nie eine Freigabe.

**Deterministik-Grenze (P3):** Claude rechnet nie selbst — kein Kopfrechnen,
kein Datums-Schätzen, auch nicht bei „einfachen" Fristen. Jeder Datumswert in
der Antwort stammt unverändert aus dem Executor-Report.

## Eingaben (Datei-Kontrakt, P2)

| Eingabe | Pflicht | Format | Beschreibung |
|---|---|---|---|
| Fristanfrage | ja | `.json` | `ereignis_datum`, `fristart` (Katalog-id) **oder** `dauer`+`einheit`, optional `fristtyp` (`ereignis`/`beginn`), `bundesland` (Pflicht). Schema: [`schema/README.md`](schema/README.md), Beispiele: [`schema/beispiel-eingabe.json`](schema/beispiel-eingabe.json), [`schema/beispiel-eingabe-frei.json`](schema/beispiel-eingabe-frei.json). |

Vordefinierte Fristarten (Berufung § 517 ZPO, Berufungsbegründung § 520 Abs. 2
ZPO, Einspruch gegen Versäumnisurteil § 339 ZPO, Widerspruch gegen Mahnbescheid
§§ 692, 694 ZPO, Revision/Revisionsbegründung §§ 548, 551 ZPO, Anhörungsrüge
§ 321a ZPO, Wiedereinsetzung § 234 ZPO) liegen als Daten im
[Fristarten-Katalog](../../core/calc/fristen/fristarten.json) —
Übersicht in [`schema/README.md`](schema/README.md).

Das `bundesland` ist Pflicht, weil § 193 BGB auf die Feiertage am
**Fristende-Ort** abstellt (bei gerichtlichen Fristen: Sitz des Gerichts).
Nennt der Nutzer kein Bundesland, fragt Claude nach — nie ein Bundesland
annehmen oder „bundesweit" rechnen.

## Ablauf

1. **Claude schreibt die Fristanfrage als JSON-Datei** (nach
   [`schema/README.md`](schema/README.md)). Fehlende Pflichtangaben
   (Ereignisdatum, Fristart bzw. Dauer, Bundesland) werden beim Nutzer
   erfragt, nie ergänzt (Anti-Halluzination).
2. **Claude ruft den Executor auf** (kein eigenes Rechnen durch das Modell):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/core/calc/fristen/executor.py \
     --input <anfrage.json> \
     --output <report.json>
   ```

3. **Der Executor entscheidet jedes Datum deterministisch** (P3). Claude
   liest ausschließlich den JSON-Report und übernimmt Fristbeginn,
   rechnerisches Ende, Verschiebungen und Fristende unverändert.
4. **Claude stellt den Report als Rechenkette dar**: jeder Schritt mit Norm
   und Zwischenergebnis, alle `warnungen` und `hinweise` sichtbar. Dabei
   immer ausweisen:
   - **Notfrist / verlängerbar** (aus dem Katalog übernommen),
   - **teilgebietliche Feiertage**: sind beide möglichen Enden im Report
     (`fristende_bei_teilgebietlichem_feiertag`), zeigt Claude **beide** und
     die Prüfpflicht für die konkrete Gemeinde — nie eines unterschlagen,
   - **kein technisches Fristende** beim Widerspruch gegen den Mahnbescheid,
   - den Zweitkontroll-Hinweis aus `haftung` (immer, bei jeder Antwort).
5. Bei Exit-Code 2 (Eingabefehler) gibt Claude die Fehlermeldung wieder und
   korrigiert die Eingabe bzw. fragt nach — er rät kein Ergebnis.

## Output-Format

JSON-Report nach [`schema/README.md`](schema/README.md), Beispiel:
[`schema/beispiel-report.json`](schema/beispiel-report.json). Kernfelder:
`rechenkette` (Schritte mit `norm`, `beschreibung`, `ergebnis`,
`quelle: "executor"`), `ergebnis.fristende`,
`ergebnis.fristende_bei_teilgebietlichem_feiertag`, `warnungen`, `hinweise`.

Jeder Datumswert im Report stammt aus `executor.py`, nie vom Modell (P3).

## Beispiele

### Beispiel 1 — Berufungsfrist (Katalog), Verschiebung nach § 193 BGB

Eingabe ([`schema/beispiel-eingabe.json`](schema/beispiel-eingabe.json)):
Zustellung des Urteils am 15.01.2026, Fristart `berufung`, Bundesland NW.

Von Claude präsentiertes Ergebnis (aus dem Report übernommen):

| Schritt | Norm | Ergebnis |
|---|---|---|
| Ereignistag 15.01.2026 (Do) zählt nicht mit | § 187 Abs. 1 BGB | Fristbeginn 16.01.2026 |
| 1 Monat: der Zahl nach entsprechender Tag | § 188 Abs. 2 Alt. 1 BGB | 15.02.2026 (So) |
| Sonntag → nächster Werktag | § 193 BGB / § 222 Abs. 2 ZPO | **16.02.2026 (Mo)** |

Hinweise (aus dem Report): Notfrist (§ 224 Abs. 1 ZPO), Fristbeginn spätestens
fünf Monate nach Verkündung (§ 517 ZPO). **Zweitkontrolle durch die Kanzlei
bleibt zwingend.**

### Beispiel 2 — freie Frist, teilgebietlicher Feiertag (beide Enden)

Eingabe ([`schema/beispiel-eingabe-frei.json`](schema/beispiel-eingabe-frei.json)):
2 Wochen ab 01.08.2025, Bundesland BY. Das rechnerische Ende 15.08.2025 (Fr)
ist Mariä Himmelfahrt — in Bayern nur in Gemeinden mit überwiegend
katholischer Bevölkerung Feiertag. Der Report weist **beide** Enden aus:

- Fristende **15.08.2025 (Fr)**, falls der Fristende-Ort keinen Feiertag hat,
- Fristende **18.08.2025 (Mo)**, falls Mariä Himmelfahrt dort gilt
  (`fristende_bei_teilgebietlichem_feiertag`),

mit Warnung: konkrete Gemeinde prüfen. Claude zeigt immer beide Daten und
empfiehlt, vorsorglich das frühere Ende zu notieren.

### Beispiel 3 — Widerspruch gegen Mahnbescheid (kein technisches Fristende)

Fristart `widerspruch_mahnbescheid`: Der Report berechnet den Ablauf der
Zwei-Wochen-Frist aus der Belehrung (§ 692 Abs. 1 Nr. 3 ZPO), kennzeichnet
aber `kein_technisches_fristende: true` — Widerspruch bleibt möglich, solange
der Vollstreckungsbescheid nicht verfügt ist; verspäteter Widerspruch gilt
als Einspruch (§ 694 ZPO). Claude gibt das Datum nie als „harte" Frist aus.
