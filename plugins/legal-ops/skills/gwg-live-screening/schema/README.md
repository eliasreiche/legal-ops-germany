# Schema — gwg-live-screening

Datei-Kontrakt (P2) für `executor.py`. Das Screening arbeitet **ausschließlich
auf lokalen Dateien** — kein Live-HTTP (Deterministik-Grenze P3). Der Abruf der
Listen ist in [`core/adapters/sanktionslisten/abruf.py`](../../../core/adapters/sanktionslisten/abruf.py)
getrennt.

## Eingabe 1: Parteien (Pflicht, `--parteien`)

Die zu prüfenden Personen/Organisationen. Zwei Formate, per Dateiendung
unterschieden:

**CSV** (`.csv`, `;`-getrennt, UTF-8, BOM toleriert) — Pflichtspalte `name`,
optional `typ` (nur zur Anzeige):

```csv
name;typ
Max Mustermann;natuerlich
Musterbau AG;juristisch
```

**JSON** (`.json`) — Liste von Objekten mit mindestens `name` (optional `typ`)
**oder** eine Liste von Namens-Strings:

```json
[
  {"name": "Max Mustermann", "typ": "natuerlich"},
  "Musterbau AG"
]
```

Nur `name` ist Pflicht. Fehlt `name` in einer Zeile/einem Eintrag, bricht der
Executor mit Exit 2 ab — es wird nie geraten (Anti-Halluzination).

## Eingabe 2: Listen-Verzeichnis (Pflicht, `--listen-verzeichnis`)

Ein Verzeichnis, das enthält:

- eine oder mehrere **Listen-Dateien** `*.xml` in einem der zwei unterstützten
  offiziellen Formate (EU-FSF „full file", UN Consolidated List) — Format wird
  je Datei automatisch an der XML-Wurzel erkannt;
- eine **`abruf-meta.json`** (schreibt `abruf.py`), die je Dateiname das
  Abrufdatum festhält:

```json
{
  "eu-fsf.xml": {"url": "https://…", "abgerufen_am": "2026-07-16"},
  "un-consolidated.xml": {"url": "https://…", "abgerufen_am": "2026-07-16"}
}
```

### Frische-Gate (D19-Muster, verbindlich)

Je Liste MUSS **beides** vorliegen: das **XML-Generierungsdatum** (aus der
Liste selbst — EU: `export/@generationDate`, UN: `CONSOLIDATED_LIST/@dateGenerated`)
UND `abgerufen_am` (aus `abruf-meta.json`). Fehlt eines → **harter Fehler
(Exit 3), kein Report**: ein Screening gegen eine undatierte Liste ist wertlos.

Ist eine Liste älter als **`WARN_ALTER_TAGE` = 7 Tage** (gemessen an
`abgerufen_am`), trägt der Report eine Warnung. Schwelle als dokumentierte
Konstante im Executor; Sanktionslisten ändern sich kurzfristig.

## Match-Stufen (analog interessenkollision-check, über `core/calc/matching`)

Jeder Parteiname wird gegen **Primärname UND alle Aliase** jedes
Listeneintrags geprüft, Reihenfolge S1 → S2 → S3 → S4; die stärkste greifende
Stufe je Eintrag gewinnt:

| Stufe | Kriterium | `stufe` | `score` |
|---|---|---|---|
| S1 | exakt nach Normalisierung | `treffer` | `1.0` |
| S2 | Token-Mengen-Gleichheit / -Teilmenge | `treffer` | `1.0` bzw. `\|kleiner\|/\|größer\|` |
| S3 | Kölner Phonetik je Token identisch | `moeglicher_treffer` | `1.0` |
| S4 | Fuzzy-Ratio ≥ `--schwelle-moeglich` (Default `0.80`) | `moeglicher_treffer` | Ähnlichkeitswert |
| — | keins der obigen | `kein_treffer` | — (als negative clearance dokumentiert) |

**Schwellen-Begründung (0.80, bewusst niedriger als die 0.85 des
interessenkollision-check):** Beim Sanktions-Screening ist ein übersehener
echter Treffer (falsch-negativ) teurer als eine zusätzliche händisch zu
prüfende Meldung (falsch-positiv). Die Schwelle ist deshalb konservativ
(rückruf-orientiert) angesetzt und per `--schwelle-moeglich` überschreibbar.

Normalisierung/Phonetik/Fuzzy: dieselbe Bibliothek
[`core/calc/matching`](../../../core/calc/matching/) wie beim
interessenkollision-check (Kleinschreibung, Umlaut-/ß-Transliteration,
Rechtsform-/Titel-Stripping, Kölner Phonetik, difflib-Fuzzy).

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(tatsächlich vom Executor aus [`beispiel-parteien.json`](beispiel-parteien.json)
und den Fixtures unter `../tests/fixtures/` erzeugt — mit je einem Treffer der
Stufen S1/S3/S4, einem organisationsseitigen Alias-Treffer und einer
Nicht-Treffer-Partei als negative clearance). Struktur:

```json
{
  "meta": { "schwelle_moeglich": 0.8, "bezugsdatum": "…", "deterministik": "…", "hinweis_massnahmen": "…" },
  "listen_frische": [
    {"liste": "…xml", "quelle": "EU-FSF|UN", "generierungsdatum": "…",
     "abgerufen_am": "…", "alter_tage": 1, "warnung_veraltet": false, "anzahl_eintraege": 3}
  ],
  "warnungen": ["…"],
  "parteien": [
    {
      "partei": {"name": "…", "typ": "…|null"},
      "ergebnis": "treffer | moeglicher_treffer | kein_treffer",
      "anzahl_treffer": 1, "anzahl_moegliche_treffer": 0,
      "treffer": [
        {"liste": "…xml", "quelle": "EU-FSF|UN", "listen_referenz": "…",
         "programm": "…|null", "eintrag_typ": "person|organisation|unbekannt",
         "geburtsdatum": "…|null", "gelisteter_name": "…",
         "namensfeld": "primaername|alias", "regel": "S1..S4",
         "stufe": "treffer|moeglicher_treffer", "score": 1.0, "begruendung": "…"}
      ]
    }
  ],
  "zusammenfassung": { "anzahl_parteien": 4, "parteien_ohne_treffer": 1, "…": "…" }
}
```

Jeder Zahlen-/Datums-/Score-Wert stammt aus `executor.py` bzw. dem Parser
(P3), nie vom Modell. Nicht-Treffer werden bewusst **mit** dokumentiert — die
negative clearance ist der Hauptzweck (GwG-Dokumentationspflicht).

## Fixtures

Die Fixtures unter [`../tests/fixtures/`](../tests/fixtures/) sind **fiktive**
Ausschnitte im jeweiligen Original-Schema (Struktur echt, Einträge frei
erfunden und als fiktiv erkennbar — „Max MUSTERMANN", „Musterbau AG"). Keine
kompletten Echtlisten (Größe + Pflegelast), keine echten Personendaten, keine
Netzwerkzugriffe in Tests.

## Bewusste Grenzen (v1)

- **Nur EU-FSF + UN.** Kein OFAC/UK, kein PEP-Screening (nur kommerzielle
  Quellen), kein Transparenzregister (nur über Reseller) — im SKILL.md als
  zurückgestellt dokumentiert.
- **Nur lateinische Schreibweisen belastbar** — Transliterations-Grenze
  (Kölner Phonetik/Fuzzy sind auf lateinische/deutsche Lautung ausgelegt).
- **Ein `kein_treffer` ist kein Freibrief** — Schreibvarianten jenseits der
  Stufen S1–S4 bleiben ggf. unentdeckt; die abschließende Bewertung und jede
  Maßnahme bleibt Sache des Verpflichteten.
