---
name: akten-intake-strukturierer
status: beta
welle: 2
plugin: intake
rdg_einordnung: "Organisatorische Strukturierung und Extraktion eingehender Mandats-Dokumente in einen Aktenkopf; keine rechtliche Ersteinschätzung, keine Subsumtion, keine Fristberechnung. Erkannte Datumsnennungen sind Rohmaterial für die Aktenanlage, keine Rechtsdienstleistung."
daten_hinweis: "Mandantendaten im Input — nur über DSGVO-/BRAO-konformen Modellzugang (AWS-Bedrock-Pfad) verarbeiten; § 203 StGB beachten. Der Executor arbeitet rein lokal, ohne Netzwerkzugriff, und liest nur die übergebenen Dateien."
haftung: "Erkannte Fristen/Datumsnennungen sind bloße Hinweise, keine Fristenkontrolle und keine Fristberechnung — dafür ist ausschließlich der Skill fristenrechner-de als Zweitkontrolle zuständig. Die Vollständigkeit der Extraktion (insb. der Lückenliste) bleibt anwaltlich zu prüfen."
---

# akten-intake-strukturierer

> **Status: `beta`** — automatisierte Tests laufen grün in CI
> (`tests/test_akten_intake_executor.py`, 34 Fälle). Noch **nicht** händisch
> abgenommen —
> `status: getestet` vergibt erst der Maintainer nach eigener Prüfung (siehe
> [CONVENTIONS.md](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/blob/main/CONVENTIONS.md), Reifegrad-Leiter).

## Zweck

Strukturiert eingehende Mandats-Dokumente (Anspruchsschreiben, Kündigung,
behördliches Schreiben u. Ä.) zu einem maschinenlesbaren **Aktenkopf**:
Kurzrubrum, Sachverhalt, Parteien, erkannte **Datumsnennungen**, Geldbeträge,
fremde Aktenzeichen und — zentral — einer **Lückenliste** der für die
Aktenanlage noch fehlenden Pflichtangaben.

Die inhaltliche Extraktion macht **das Modell (Claude)** — es liest das
Dokument und füllt das Schema. Damit dabei nichts erfunden wird, prüft ein
deterministischer Executor die Ausgabe (P3 / Anti-Halluzination maschinell
erzwungen):

- **Schema-Konformität** des `aktenkopf.json` (Pflichtstruktur, ISO-Datumsformate),
- **Provenienz**: jeder kritische Wert (Datum, Geldbetrag, Aktenzeichen, IBAN,
  E-Mail, Telefonnummer) muss — nach definierter Normalisierung — **wörtlich in
  mindestens einer Quelldatei** vorkommen; die Fundstelle (Datei + Zeile) steht
  im Report. Nicht belegte Werte werden als `nicht_belegt` ausgewiesen,
- **Lücken-Disziplin**: ein leeres Pflichtfeld ist nur zulässig, wenn es
  explizit im `luecken`-Array steht — sonst Schema-Fehler.

> ⚠️ **Keine Fristberechnung, keine Fristenkontrolle.** Die `fristen_hinweise`
> sind bloß *erkannte Datumsnennungen* aus dem Text (mit vermuteter Bedeutung),
> **kein** berechnetes Fristende und keine Notfrist-Bewertung. Jede tatsächliche
> Fristberechnung läuft ausschließlich über den Skill
> [`fristenrechner-de`](../fristenrechner-de/SKILL.md)
> als deterministische Zweitkontrolle. Dieser Skill ersetzt keinen
> Fristenkalender.

**PDF/Scan ist out of scope.** Der Skill verarbeitet Text-/Markdown-Quellen.
Die Aufbereitung eingescannter Post (OCR, Klassifikation) übernimmt der Skill
`posteingang-ocr-routing` (Welle 4).

## Eingaben (Datei-Kontrakt, P2)

| Eingabe | Pflicht | Format | Beschreibung |
|---|---|---|---|
| Aktenkopf | ja | `.json` | Vom Modell nach Schema erzeugter Aktenkopf. Struktur: [`schema/README.md`](schema/README.md), Beispiel: [`schema/beispiel-aktenkopf.json`](schema/beispiel-aktenkopf.json). |
| Quelldokument(e) | ja | `.txt` / `.md`, UTF-8 | Das/die zugrunde liegende(n) Dokument(e). Mehrfach angebbar (`--quelle` je Datei). Beispiel: [`schema/beispiel-eingabe.md`](schema/beispiel-eingabe.md). |

Der Executor liest nur diese Dateien, kein Netzwerk, keine Datenbank.

## Ablauf

1. **Claude liest das/die Quelldokument(e) und extrahiert nach Schema** in einen
   `aktenkopf.json` — es **erfindet nichts**: Was nicht im Text steht, wird nicht
   ergänzt, sondern als Eintrag in `luecken` ausgewiesen (mit Begründung, warum
   die Angabe für die Aktenanlage nötig ist). Datumsnennungen kommen als
   `fristen_hinweise` mit wörtlichem `quelle_zitat` in den Aktenkopf, nie als
   berechnete Frist.
2. **Claude ruft den Executor auf** (kein eigenes Prüfen durch das Modell):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/akten-intake-strukturierer/executor.py \
     --aktenkopf <aktenkopf.json> \
     --quelle <dokument.md> [--quelle <weitere.txt> ...] \
     --output <report.json>
   ```

3. **Der Executor prüft deterministisch** (P3): Schema, Provenienz jedes
   kritischen Werts (belegt/`nicht_belegt` mit Fundstelle) und die
   Lücken-Disziplin. Exit-Code `0` = sauber, `1` = mindestens ein
   `nicht_belegt`-Wert und/oder Schema-Fehler, `2` = Eingabefehler.
4. **Bei `nicht_belegt` oder Schema-Fehler korrigiert Claude** den Aktenkopf —
   einen nicht belegten Wert entweder **streichen** (er stand nicht im Dokument)
   oder als **Lücke** ausweisen; ein leeres Pflichtfeld mit einem `luecken`-
   Eintrag versehen — und ruft den Executor erneut auf, bis er sauber läuft.
5. **Claude stellt das Ergebnis in Markdown dar**: Aktenkopf, Parteien-Tabelle,
   Frist-Hinweise **mit deutlichem Haftungshinweis** (erkannte Datumsnennungen,
   keine Fristenkontrolle; Fristberechnung nur über `fristenrechner-de`) und die
   Lückenliste. Jeder als `nicht_belegt` gemeldete Wert wird nie stillschweigend
   übernommen.

## Output-Format

JSON-Report nach [`schema/README.md`](schema/README.md), Beispiel:
[`schema/beispiel-report.json`](schema/beispiel-report.json) (erzeugt aus
[`schema/beispiel-aktenkopf.json`](schema/beispiel-aktenkopf.json) +
[`schema/beispiel-eingabe.md`](schema/beispiel-eingabe.md)). Kernfelder:
`schema_ok`, `schema_fehler[]`, `provenienz[]` (je Wert `status`, `fundstelle`,
`begruendung`), `luecken[]`, `zusammenfassung`.

Jeder Beleg-Zustand im Report stammt aus `executor.py`, nie vom Modell (P3).

## Beispiele

### Beispiel 1 — Anspruchsschreiben nach Verkehrsunfall (alles belegt)

Eingabe: [`schema/beispiel-eingabe.md`](schema/beispiel-eingabe.md) (fiktives
gegnerisches Anspruchsschreiben, Verkehrsunfall, mit Zahlungsfrist, mehreren
Beträgen, fremdem Aktenzeichen und Bankverbindung). Claude erzeugt daraus
[`schema/beispiel-aktenkopf.json`](schema/beispiel-aktenkopf.json); der Executor
belegt alle 11 kritischen Werte (Exit 0). Von Claude präsentiert:

**Aktenkopf** — Mustermann ./. Beispiel (Verkehrsunfall), Eingang 05.03.2026.

| Rolle | Name | Typ | Anschrift | vertreten durch |
|---|---|---|---|---|
| Mandant | Max Mustermann | natürlich | Musterweg 3, 20099 Hamburg | — |
| Gegner | Erika Beispiel | natürlich | *(Lücke)* | Dr. Petra Gegner |
| Sonstige | Dr. Gegner & Kollegen | juristisch | Musterallee 100, 20095 Hamburg | — |

**Frist-Hinweise** (⚠️ erkannte Datumsnennungen — **keine Fristberechnung**,
Zweitkontrolle über `fristenrechner-de`):

| Datum (im Text) | Vermutete Bedeutung |
|---|---|
| 20.03.2026 | Von der Gegenseite gesetzte Zahlungsfrist (außergerichtlich), keine gesetzliche Notfrist |
| 12.02.2026 | Unfalltag — möglicher Verjährungsbeginn, anwaltlich zu prüfen |

**Lücken für die Aktenanlage**: Anschrift der Gegnerin fehlt im Schreiben;
Telefon/E-Mail des Mandanten beim Erstkontakt zu erfragen.

### Beispiel 2 — erfundener Wert wird abgefangen

Trägt der Aktenkopf einen Betrag oder ein Datum, das **nicht** im Dokument
steht, meldet der Executor es als `nicht_belegt` (Exit 1) mit dem Hinweis „Wert
streichen oder als Lücke ausweisen". Claude übernimmt einen solchen Wert nie,
sondern streicht ihn oder führt ihn als Lücke — so wird die Anti-Halluzinations-
Regel maschinell erzwungen.

## Grenzen

- **Keine Fristberechnung / kein Fristende** — nur erkannte Datumsnennungen
  (siehe Haftungshinweis oben); Fristen ausschließlich über `fristenrechner-de`.
- **PDF/Scan** out of scope → `posteingang-ocr-routing` (Welle 4).
- **Provenienz ist ein Beleg-, kein Richtigkeitsnachweis**: `belegt` heißt nur,
  dass der Wert (nach Normalisierung) im Text vorkommt — nicht, dass er
  rechtlich zutrifft oder das Modell ihn dem richtigen Feld zugeordnet hat. Die
  Zuordnung (welche Partei, welche Bedeutung) bleibt anwaltlich zu prüfen.
- **Normalisierungsgrenzen**: Telefonnummern werden nur um Trennzeichen bereinigt
  verglichen (keine Ländervorwahl-Äquivalenz `+49` ↔ `0`); Datums-/Geldformate
  sind in [`schema/README.md`](schema/README.md) abschließend dokumentiert.
