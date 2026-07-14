# Schema — passive-zeiterfassung

Datei-Kontrakt (P2) für [`executor.py`](../executor.py). Kein Netzwerkzugriff,
keine Datenbank, keine Persistierung — Dateien rein, JSON-Report raus. Der
Executor **liest** Kalender-/Mail-Metadaten und `kontext/mandate/*.md`,
**schreibt** aber nie eine Zeiterfassung: jeder Vorschlag ist ein von der
Kanzlei zu bestätigender Entwurf (siehe [`SKILL.md`](../SKILL.md), Ablauf).

Die Zulieferer-Bibliotheken sind [`core/calc/zeit`](../../../core/calc/zeit/)
(Termin-Dauer) und [`core/calc/zuordnung`](../../../core/calc/zuordnung/)
(Akten-Zuordnung Z0–Z4); der Abnehmer ist
[`taetigkeitstext-rvg`](../../taetigkeitstext-rvg/schema/README.md) — jeder
eindeutige Vorschlag trägt bereits einen fertigen `leistungen.json`-Eintrag.

## M365-Mapping

Die beiden Eingabedateien sind ein **Metadaten-Abzug**, kein Voll-Export. Sie
entstehen entweder über den [`kontext-sync`](../../kontext-sync/SKILL.md)-Weg
(offizieller Microsoft-365-MCP-Konnektor, D11a) oder als manueller Export.
Das Feld-Mapping aus MS Graph:

| Report-Feld | MS-Graph-Quelle (Kalender / Mail) |
|---|---|
| `termine[].betreff` | Event `subject` |
| `termine[].start` / `ende` | Event `start.dateTime` / `end.dateTime` |
| `termine[].teilnehmer` | Event `attendees[].emailAddress.name` |
| `termine[].ort` | Event `location.displayName` |
| `mails[].zeitstempel` | Message `sentDateTime` / `receivedDateTime` |
| `mails[].betreff` | Message `subject` |
| `mails[].absender` | Message `from.emailAddress.name` |
| `mails[].empfaenger` | Message `toRecipients[].emailAddress.address` |
| `mails[].richtung` | abgeleitet: eigener Tenant = `from` → `ausgehend`, sonst `eingehend` |

**Bewusst KEINE Mail-Bodies** (PII-Minimierung, § 203 StGB / DSGVO): der
Executor bekommt nur Metadaten, nie Inhalte. Ein Zeitwert je Mail wird nie
aus dem Inhalt geschätzt, sondern ausschließlich aus der Kanzlei-Konvention
`config.mail_pauschale_minuten` (siehe unten).

## Eingabe 1: `--termine` (Kalender-Metadaten)

```json
{
  "termine": [
    { "betreff": "Besprechung Az. 2026-001",
      "start": "2026-07-06T09:00:00", "ende": "2026-07-06T09:45:00",
      "teilnehmer": ["RA Dr. Klein"], "ort": "Kanzlei" }
  ]
}
```

| Feld | Pflicht | Typ / Werte | Bedeutung |
|---|---|---|---|
| `betreff` | ja | Text | Terminbetreff — Rohmaterial für Zuordnung und Stichworte. |
| `start` / `ende` | ja | ISO-8601-Zeitstempel | Termin-Zeitraum. Dauer via `core/calc/zeit.dauer_minuten` (angebrochene Minute wird aufgerundet). `ende` ≤ `start` ist ein Eingabefehler (Exit 2). |
| `teilnehmer` | nein (Default `[]`) | Liste von Texten | Namen/Adressen — fließen als Text in die Zuordnung ein; die Anzahl wird als Faktum in die Stichworte übernommen. |
| `ort` | nein (Default `null`) | Text oder `null` | Ort — als Faktum in die Stichworte übernommen. |

## Eingabe 2: `--mails` (Mail-Metadaten)

```json
{
  "mails": [
    { "zeitstempel": "2026-07-06T13:15:00", "betreff": "Az. 2026-001 - Rückfrage",
      "absender": "Kanzlei", "empfaenger": ["kontakt@muster-ag.example"],
      "richtung": "ausgehend" }
  ]
}
```

| Feld | Pflicht | Typ / Werte | Bedeutung |
|---|---|---|---|
| `zeitstempel` | ja | ISO-8601-Zeitstempel | Sende-/Empfangszeit; das Datum (`JJJJ-MM-TT`) wird für den Leistungseintrag daraus abgeleitet. |
| `betreff` | ja | Text | Betreff — Rohmaterial für Zuordnung und Stichworte. |
| `absender` | nein (Default `""`) | Text | Absendername — fließt in die Zuordnung ein (Parteiname-Abgleich). |
| `empfaenger` | nein (Default `[]`) | Liste von Texten | Empfänger — fließen als Text in die Zuordnung ein. |
| `richtung` | ja | `eingehend` \| `ausgehend` | Richtung — als Faktum in die Stichworte übernommen. |

Mindestens eines von `--termine`/`--mails` ist Pflicht. Ein unbekanntes Feld
in einem Termin/einer Mail ist ein Eingabefehler (Tippfehler-Diagnose,
Exit 2), ebenso ein fehlendes Pflichtfeld.

## Eingabe 3: `--config` (optional)

```json
{ "mail_pauschale_minuten": 6 }
```

| Feld | Pflicht | Typ | Bedeutung |
|---|---|---|---|
| `mail_pauschale_minuten` | nein | ganze Zahl > 0 oder `null` | **Kanzlei-Konvention** für den Zeitansatz je Mail — nie ein Modell- oder Default-Wert. Ohne Config oder bei `null` bekommt jede Mail **keinen** Zeitwert und landet in `ohne_zeitwert[]` (Lücke; die Kanzlei trägt Minuten manuell nach). Ein Takt wird hier bewusst nicht gesetzt — die Taktung übernimmt `taetigkeitstext-rvg` downstream. |

## Eingabe 4: `--kontext` (Pflicht)

Das `kontext/`-Verzeichnis nach
[`core/context/README.md`](../../../core/context/README.md). Mandate werden
über `lese_mandate()`
([`core/context/schema.py`](../../../core/context/schema.py)) eingelesen.
Mandate ohne Aktenzeichen im Frontmatter können nicht zugeordnet werden und
erscheinen als Warnung in `meta.mandat_warnungen`.

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(erzeugt aus [`beispiel-termine.json`](beispiel-termine.json),
[`beispiel-mails.json`](beispiel-mails.json) und
[`beispiel-config.json`](beispiel-config.json) gegen
`core/context/beispiel-kontext/`). Struktur:

```json
{
  "meta": { "erzeugt_von": "…", "quelle_termine": "…", "quelle_mails": "…",
            "mail_pauschale_minuten": 6, "mandat_warnungen": [], "deterministik": "…" },
  "vorschlaege": [
    { "quelle_typ": "kalender", "betreff": "…", "datum": "2026-07-06",
      "leistung": { "datum": "2026-07-06", "az": "2026-001", "minuten": null,
                    "start": "…", "ende": "…", "stichworte": ["…"], "quelle": "kalender" },
      "zuordnung": { "az": "2026-001", "datei": "mandate/2026-001.md",
                     "stufe": "Z0", "kategorie": "treffer", "score": 1.0, "begruendung": "…" },
      "status": "zu_bestaetigen" }
  ],
  "mehrdeutig": [ { "betreff": "…", "datum": "…", "kandidaten": [ … ], "hinweis": "…" } ],
  "nicht_zuordenbar": [ { "betreff": "…", "datum": "…", "hinweis": "…" } ],
  "ohne_zeitwert": [ { "betreff": "…", "richtung": "…", "zuordnung_status": "…",
                       "az": null, "kandidaten": [ … ], "hinweis": "…" } ],
  "warnungen": [ { "typ": "termin_ueberlappung", "termin_a": { … }, "termin_b": { … } } ],
  "summen": { "je_az": { "2026-001": 117 }, "minuten_gesamt": 162 }
}
```

### Zuordnung (Stufen Z0–Z4)

Delegiert vollständig an [`core/calc/zuordnung`](../../../core/calc/zuordnung/)
(dort Stufen-Definition und Schwellenwert-Begründung):

- **genau ein `treffer`** (Z0 Az wörtlich, Z1/Z2 Parteiname) → `vorschlaege[]`
  mit diesem `az`.
- **mehrere `treffer`** ODER **nur `moeglicher_treffer`** (Z3 phonetisch, Z4
  fuzzy) → `mehrdeutig[]` (Kandidatenliste; die Kanzlei entscheidet, nie
  automatisch).
- **kein Kandidat** → `nicht_zuordenbar[]` (Lücke, nie geraten).

### `leistung` = fertiger `taetigkeitstext-rvg`-Eintrag

Jeder Vorschlag enthält unter `leistung` bereits einen gültigen Eintrag im
[`leistungen.json`](../../taetigkeitstext-rvg/schema/README.md)-Format:
Kalender-Termine liefern `start`+`ende` (`minuten: null`), Mails die Pauschale
als `minuten` (`start`/`ende: null`). `stichworte` sind ausschließlich Fakten
aus den Metadaten (Betreff, Ort, Teilnehmerzahl bzw. Richtung) — nichts
Formuliertes, nichts Erfundenes; die Formulierung übernimmt `taetigkeitstext-
rvg`. So läuft eine bestätigte Auswahl ohne Umbau durch dessen Executor
(maschinell erzwungen durch den Round-Trip-Test).

### `summen`

`je_az` summiert die Minuten **nur über die eindeutigen Vorschläge** (via
`core/calc/zeit.summe_je_az`) — mehrdeutige, nicht zuordenbare und mail-ohne-
Zeitwert-Einträge fließen nie in eine Summe. Jeder Zahlen-/Datums-/
Zuordnungswert stammt aus `executor.py`, nie vom Modell (P3).

## Beispieldateien (Golden Files, nie handeditiert)

`beispiel-report.json` und `beispiel-leistungen.json` werden **per Executor**
erzeugt und von Sync-Tests (`tests/test_passive_zeiterfassung_beispiel_sync.py`)
gegen den aktuellen Code gehalten. `beispiel-leistungen.json` sind die
bestätigten Vorschläge im `taetigkeitstext-rvg`-Format — der Round-Trip-Test
lässt sie durch dessen echten Executor laufen und prüft konsistente Minuten.

Neu erzeugen:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/passive-zeiterfassung/executor.py \
  --termine schema/beispiel-termine.json --mails schema/beispiel-mails.json \
  --config schema/beispiel-config.json \
  --kontext <repo>/plugins/legal-ops/core/context/beispiel-kontext \
  --output schema/beispiel-report.json
```
