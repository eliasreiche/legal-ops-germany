# Schema — email-akten-zuordnung

Datei-Kontrakt (P2) für [`executor.py`](../executor.py). Kein Netzwerkzugriff,
keine Datenbank, keine Persistierung — Dateien rein, JSON-Report raus. Der
Executor **liest** `.eml`-Dateien/Metadaten und `kontext/mandate/*.md`,
**schreibt** aber nie in `posteingang/` oder in ein Mandat — das Ablegen
bleibt immer ein von Claude/der Kanzlei bestätigter, separater Schritt (siehe
[`SKILL.md`](../SKILL.md), Ablauf).

## Eingabe 1: E-Mails — zwei Wege, genau einer ist Pflicht

### `--eml` (EML-Dateien)

Eine einzelne `.eml`-Datei **oder** ein Verzeichnis (alle `*.eml`-Dateien
darin, alphabetisch sortiert verarbeitet). Parsing über die
Python-Standardbibliothek `email` (`BytesParser` mit `policy.default`) —
das dekodiert RFC-2047-kodierte Header (`=?utf-8?q?...?=`, z. B. Umlaute in
Absendername/Betreff) automatisch, ohne Zusatzcode.

Ausgewertete Header/Teile: `From` (Anzeigename + Adresse, erste Adresse bei
mehreren), `To`/`Cc` (nur Adressen), `Subject`, `Date` (auf ein ISO-Datum
`JJJJ-MM-TT` reduziert), sowie der erste `text/plain`-Teil (Textauszug, siehe
PII-Minimierung unten). Fehlt ein Header, wird das jeweilige Feld leer/`null`
— es wird nie ein Wert erfunden.

### `--input` (Metadaten-JSON, kontext-sync/M365-Weg)

Ein JSON-**Array** von Dokument-Objekten (auch bei nur einem Dokument):

```json
[
  {
    "quelle": "graph-message-id-oder-freier-bezeichner",
    "absender_name": "Muster AG",
    "absender_adresse": "recht@muster-ag.example",
    "empfaenger": ["kanzlei@beispiel.example"],
    "cc": [],
    "betreff": "Zahlungsaufforderung",
    "textauszug": "Sehr geehrte Damen und Herren, ...",
    "datum": "2026-06-25"
  }
]
```

Nur `absender_name`, `absender_adresse`, `betreff`, `textauszug` fließen in
die Zuordnung ein (identischer Kontrakt wie bei `--eml`); `quelle`,
`empfaenger`, `cc`, `datum` sind optional/informativ. `datum` muss, wenn
gesetzt, ein ISO-Datum (`JJJJ-MM-TT`) sein — ein ungültiges Format ist ein
Eingabefehler (Exit 2), es wird nie stillschweigend verworfen oder
umgedeutet. `textauszug` wird wie beim EML-Weg auf `TEXTAUSZUG_MAX_LEN`
gekürzt.

## Eingabe 2: `--kontext` (Pflicht)

Das `kontext/`-Verzeichnis nach [`core/context/README.md`](../../../core/context/README.md).
Mandate werden über `lese_mandate()`
([`core/context/schema.py`](../../../core/context/schema.py)) eingelesen —
keine erneute Schema-Prüfung (dafür ist `core/context/validator.py`
zuständig). Mandate ohne Aktenzeichen im Frontmatter können nicht
zugeordnet werden und werden mit einer Warnung in `meta.mandat_warnungen`
übersprungen statt geraten.

## PII-Minimierung (§ 203 StGB / DSGVO)

Der Report enthält **nie** den vollen E-Mail-Text — nur die Metadaten
(Absender, Empfänger-Adressen, Betreff, Datum) plus einen Textauszug von
höchstens `TEXTAUSZUG_MAX_LEN = 500` Zeichen des `text/plain`-Teils.
`textauszug_gekuerzt: true` zeigt an, dass der Originaltext länger war. Der
volle Mail-Text bleibt im Ursprungssystem (Mailserver/EML-Archiv/M365) —
der Executor liest ihn nur zum Kürzen, speichert ihn nie vollständig.

## Zuordnungs-Stufen (Z0-Z4)

Vollständig implementiert in
[`core/calc/zuordnung/`](../../../core/calc/zuordnung/) (siehe dortige
Docstrings für Herleitung/Grenzen). Kurzfassung, je (E-Mail × Mandat)-Paar:

| Stufe | Kriterium | Sucht in | `kategorie` |
|---|---|---|---|
| Z0 | eigenes Aktenzeichen wörtlich (nach Whitespace-Normalisierung) | Betreff, Textauszug | `treffer` |
| Z1 | Parteiname (`mandant`/`gegenseite`) als zusammenhängende Phrase nach Normalisierung | Betreff, Textauszug, Absendername | `treffer` |
| Z2 | alle normalisierten Namens-Tokens im Text (Wortreihenfolge unerheblich) | Betreff, Textauszug, Absendername | `treffer` |
| Z3 | alle Namens-Tokens phonetisch (Kölner Phonetik) im Text wiedergefunden | Betreff, Textauszug, Absendername | `moeglicher_treffer` |
| Z4 | Ø beste Zeichenketten-Ähnlichkeit je Namens-Token ≥ `--schwelle-moeglich` (Default `0.85`, wie `interessenkollision-check`) | Betreff, Textauszug, Absendername | `moeglicher_treffer` |

Z0 wird immer zuerst geprüft (sicherste Stufe): findet sich das Az, wird
für dieses Mandat kein Parteiname-Abgleich mehr durchgeführt. Pro
(E-Mail × Mandat)-Paar entsteht **höchstens ein** Kandidat (die beste
gefundene Stufe über Az, `mandant` und `gegenseite`) — ein Mandat erscheint
nie doppelt für dieselbe E-Mail. Trifft **keine** Stufe für ein Mandat zu,
erscheint es nicht in `kandidaten[]` (kein `kein_treffer`-Eintrag pro
Mandat — nur die leere Liste insgesamt bedeutet `kein_treffer`).

**Az-Normalisierung:** Mehrfach-Whitespace wird kollabiert, Groß-/
Kleinschreibung bleibt erhalten (Details:
[`core/calc/zuordnung/az.py`](../../../core/calc/zuordnung/az.py) — dort auch
die Begründung, warum das Muster von `aktenkopf-extraktor/executor.py`
übernommen statt importiert wird).

**Parteiname-Normalisierung:** dieselbe Pipeline wie
`interessenkollision-check` (Kleinschreibung, Umlaut-/ß-Transliteration,
Rechtsform-/Titel-Stripping — siehe
[`core/calc/matching/normalisierung.py`](../../../core/calc/matching/normalisierung.py)),
angewendet auf Name **und** Suchtext.

## Fristverdacht (regelbasiert, keine Fristberechnung)

Case-insensitive Substring-Suche über Betreff + Textauszug gegen eine feste
Wortliste (`FRISTVERDACHT_WOERTER` in `executor.py`): Frist, Urteil,
Beschluss, Bescheid, Zustellung, Mahnung, Kündigung, Klage, einstweilige.
Substring statt Wortgrenzen-Suche, damit zusammengesetzte Wörter erkannt
werden ("Kündigungsschreiben" enthält "kündigung"). Trifft eines der Wörter,
wird `fristverdacht: true` gesetzt samt festem Hinweistext
(`fristverdacht_hinweis`) — **keine Fristberechnung, kein Normzitat**, nur
der Verweis auf die Zweitkontrolle durch `fristenrechner`.

`prioritaet` ist `hoch`, wenn `fristverdacht` **oder** mindestens ein
Kandidat der Kategorie `treffer` vorliegt, sonst `normal`.

**Bewusste Grenze:** nur echte Umlaute erkannt (kein `kuendigung`
ASCII-Fallback); Substring-Suche kann selten auch inhaltlich unpassende
Treffer erzeugen (z. B. "frist" in einem unrelated Wort) — bewusster
Kompromiss zugunsten des Rückrufs, kein Ersatz für die menschliche
Durchsicht.

## Ablage-Vorschlag

Ziel-Dateiname: `posteingang/JJJJ-MM-TT-<betreff-slug>.eml`. `JJJJ-MM-TT`
stammt aus dem `Date`-Header (`--eml`) bzw. dem optionalen `datum`-Feld
(`--input`) — **ohne** auswertbares ISO-Datum wird nie eines erfunden,
stattdessen `ablage_vorschlag.moeglich: false` mit Hinweis (Lücke, manuell
zu ergänzen).

**Slug-Regel** (`betreff_slug()` in `executor.py`): Umlaute/ß transliterieren
(ä→ae, ö→oe, ü→ue, ß→ss), kleinschreiben, jede Zeichenfolge außerhalb
`[a-z0-9]` zu einem einzelnen `-` kollabieren, Ränder trimmen, auf 60
Zeichen kürzen. Leerer/fehlender Betreff ergibt `ohne-betreff` (kein
erfundener Titel).

**Kommunikations-Zeile** (Format exakt nach
[`core/context/README.md`](../../../core/context/README.md), Abschnitt
`## Kommunikation`): `JJJJ-MM-TT — Betreff — [Datei](../posteingang/<dateiname>)`.
Der relative Link geht von `mandate/<az>.md` aus (Konvention:
Mandats-Dateien liegen direkt unter `kontext/mandate/`).

## Ausgabe: JSON-Report

Siehe [`beispiel-report.json`](beispiel-report.json) — **tatsächlich vom
Executor erzeugt** aus den vier Beispiel-EMLs in diesem Ordner gegen
[`core/context/beispiel-kontext/`](../../../core/context/beispiel-kontext/)
(read-only genutzt). Struktur je Dokument-Eintrag:

```json
{
  "meta": {
    "erzeugt_von": "email-akten-zuordnung/executor.py",
    "quelle_typ": "eml | input",
    "kontext_verzeichnis": "…",
    "schwelle_moeglich": 0.85,
    "textauszug_max_len": 500,
    "anzahl_dokumente": 4,
    "anzahl_mandate": 2,
    "mandat_warnungen": []
  },
  "dokumente": [
    {
      "quelle": "…", "absender_name": "…", "absender_adresse": "…",
      "empfaenger": ["…"], "cc": [],
      "betreff": "…", "textauszug": "… (max. 500 Zeichen)",
      "textauszug_gekuerzt": false, "datum": "JJJJ-MM-TT oder null",
      "kandidaten": [
        {"az": "…", "datei": "mandate/….md", "stufe": "Z0…Z4",
         "kategorie": "treffer|moeglicher_treffer", "score": 0.0,
         "begruendung": "…"}
      ],
      "kein_treffer": false,
      "fristverdacht": false, "fristverdacht_hinweis": null,
      "prioritaet": "hoch|normal",
      "ablage_vorschlag": {
        "moeglich": true, "dateiname": "posteingang/….eml",
        "kommunikations_zeile": "JJJJ-MM-TT — … — [Datei](../posteingang/….eml)",
        "hinweis": null
      }
    }
  ]
}
```

### Beispiel-EMLs in diesem Ordner (fiktiv, `.example`-Domains)

| Datei | Demonstriert |
|---|---|
| [`beispiel-az-im-betreff.eml`](beispiel-az-im-betreff.eml) | Z0 — eigenes Az "2026-001" wörtlich im Betreff, plus Fristverdacht ("Frist"). |
| [`beispiel-nur-parteiname.eml`](beispiel-nur-parteiname.eml) | Z1 — nur Parteiname "Muster AG" (Gegenseite von 2026-001) im Text, kein Az erwähnt. |
| [`beispiel-kein-treffer.eml`](beispiel-kein-treffer.eml) | `kein_treffer` — Newsletter ohne jeden Mandats-/Parteibezug. |
| [`beispiel-fristverdacht.eml`](beispiel-fristverdacht.eml) | Fristverdacht ("Kündigung", RFC-2047-kodierter Umlaut-Betreff/-Body) **und** eine echte Mehrdeutigkeit: der Absender "Zweite Beispiel KG" trifft sowohl auf Mandat 2026-002 (Z1, eigener Mandantenname) als auch — über das gemeinsame Wort "Beispiel" — auf Mandat 2026-001 (Z1, `mandant: "Beispiel GmbH"`). Bewusst **nicht** bereinigt: zeigt, warum Mehrdeutigkeiten in `SKILL.md` immer als Rückfrage an die Kanzlei gehen, nie automatisch aufgelöst werden. |

## Bewusste Grenzen

- **Z1/Z2 sind bei kurzen/häufigen Namens-Token-Anteilen falsch-positiv-
  anfällig** (siehe Beispiel oben: "Beispiel" allein reicht für einen
  `treffer`). Eine `treffer`-Kategorie ist deshalb **kein** Freibrief für
  automatisches Ablegen — Konflikt-/Mehrdeutigkeitsfälle (mehr als ein
  Kandidat) gehen laut `SKILL.md` immer als Rückfrage an die Kanzlei.
- **Kein Abgleich gegen `absender_adresse`** für den Parteiname-Abgleich —
  eine E-Mail-Adresse ist kein Namens-Fließtext (siehe
  `core/calc/zuordnung/zuordnung.py`, `FELD_REIHENFOLGE`).
- **Az-Suche nur in Betreff/Textauszug**, nicht im Absendernamen (Az im
  Anzeigenamen ist untypisch).
- **Kölner Phonetik ist für deutsche Lautung entwickelt** — bei
  fremdsprachigen Namen ist die Trefferqualität nicht belastbar (geerbt von
  `core/calc/matching`).
- **`kein_treffer` ist kein Freibrief** — Spitznamen, Umfirmierungen oder
  völlig andere Schreibweisen jenseits der Z0-Z4-Stufen bleiben unentdeckt.
- **Kontakte (`kontakte.md`) fließen aktuell nicht in die Zuordnung ein** —
  nur `mandant`/`gegenseite` aus den Mandats-Frontmatters. Eine Erweiterung
  auf z. B. gegnerische Prozessbevollmächtigte aus `kontakte.md` ist denkbar,
  aber (noch) nicht umgesetzt (siehe Abschlussbericht der Implementierung).
