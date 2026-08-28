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

## Zuordnungs-Stufen (Z0-Z4, Z2N)

Vollständig implementiert in
[`core/calc/zuordnung/`](../../../core/calc/zuordnung/) (siehe dortige
Docstrings für Herleitung/Grenzen). Kurzfassung, je (E-Mail × Mandat)-Paar:

| Stufe | Kriterium | Sucht in | `kategorie` |
|---|---|---|---|
| Z0 | eigenes Aktenzeichen wörtlich (nach Whitespace-Normalisierung) | Betreff, Textauszug | `treffer` |
| Z1 | Parteiname (`mandant`/`gegenseite`) als zusammenhängende Phrase nach Normalisierung | Betreff, Textauszug, Absendername | `treffer` |
| Z2 | alle normalisierten Namens-Tokens im Text (Wortreihenfolge unerheblich) | Betreff, Textauszug, Absendername | `treffer` |
| Z2N | **Nachname + Korroboration**: die Nachnamen von `mandant` **und** `gegenseite` desselben Mandats stehen je **wörtlich** und in **Personen-Position** (Anrede davor oder expliziter Rubrum-Trenner "./."/" gegen " neben der anderen Partei — bloße Wort-Nachbarschaft reicht nicht) im Dokument | Betreff, Textauszug, Absendername | `moeglicher_treffer` |
| Z3 | alle Namens-Tokens phonetisch (Kölner Phonetik) im Text wiedergefunden | Betreff, Textauszug, Absendername | `moeglicher_treffer` |
| Z4 | Ø beste Zeichenketten-Ähnlichkeit je Namens-Token ≥ `--schwelle-moeglich` (Default `0.85`, wie `interessenkollision-check`) | Betreff, Textauszug, Absendername | `moeglicher_treffer` |

Z0 wird immer zuerst geprüft (sicherste Stufe): findet sich das Az, wird
für dieses Mandat kein Parteiname-Abgleich mehr durchgeführt. Pro
(E-Mail × Mandat)-Paar entsteht **höchstens ein** Kandidat (die beste
gefundene Stufe über Az, `mandant` und `gegenseite`) — ein Mandat erscheint
nie doppelt für dieselbe E-Mail. Trifft **keine** Stufe für ein Mandat zu,
erscheint es nicht in `kandidaten[]` (kein `kein_treffer`-Eintrag pro
Mandat — nur die leere Liste insgesamt bedeutet `kein_treffer`).

### Z2N — Nachname + Korroboration (warum, und wie eng)

Z1/Z2 verlangen den **vollständigen** `mandant`/`gegenseite`-String. Eigene
Kanzleikorrespondenz schreibt aber "Sehr geehrte Frau Dr. Merkel" — der
Vorname fehlt, Z2 scheitert an einem einzigen Token, und sachlich eindeutige
Post wurde als `kein_treffer` ausgewiesen (Pilot-Abnahme 2026-08: 2 von 6
Mails, ohne Aktenzeichen im Text, also auch ohne Z0). Z2N schließt diese
Lücke bewusst eng:

- **Ein Nachname allein ist nie ein Kandidat.** Es braucht ein zweites,
  wörtlich belegtes Nachname-Signal aus **demselben** Mandat — konkret den
  Nachnamen der `gegenseite`. Beide Signale müssen über dieselbe
  Normalisierung (Umlaut-/Titel-/Rechtsform-Stripping, Wortgrenzen)
  literal auffindbar sein; **phonetische oder fuzzy Fundstellen (Z3/Z4)
  zählen für Z2N nicht** — die schwächere Namens-Evidenz darf nicht
  zusätzlich auf geratenen Schreibweisen aufsetzen.
- **Nachname = letztes normalisiertes Token** des Mandatsfeldes
  (`nachname()` in `core/calc/zuordnung/parteisuche.py`); Titel/Rechtsform
  sind vorher gestrippt. Keine neue Datenpflege: Z2N nutzt ausschließlich
  `mandant`/`gegenseite`, die ohnehin im Mandats-Frontmatter stehen.
- **Das bloße Vorkommen dieses Tokens genügt nicht** — es muss im Text in
  **Personen-Position** stehen (`nachname_in_personen_position()`), und zwar
  auf genau einem von zwei Wegen:
  1. **Anrede unmittelbar davor** — "Sehr geehrte Frau Dr. Merkel", "mit
     Herrn Köhn".
  2. **Expliziter Rubrum-Trenner** aus einer geschlossenen Menge ("./.",
     " gegen ") unmittelbar zwischen dem Nachnamen und dem Nachnamen der
     anderen Partei desselben Mandats — "Merkel ./. Köhn", "Frank gegen
     Köln".

  **Bloße Wort-Nachbarschaft ohne einen der beiden Belege korroboriert
  NICHT** (D12-Nachreview, Regression behoben): eine frühere Fassung
  akzeptierte jedes unmittelbare Nachbar-Token der anderen Partei als
  "Rubrum" — dadurch korroborierte z. B. "Rechtsanwalt Frank, Köln" (Komma,
  kein Trenner) fälschlich gegen ein Mandat `mandant: "Peter Frank"` /
  `gegenseite: "Sparkasse Köln"`. Grund für die Personen-Position-Prüfung
  insgesamt: bei einer Organisation ist das letzte Token kein Nachname,
  sondern oft ein Orts-/Gattungswort — Gegenseite "Stadtwerke Berlin" würde
  sonst über `berlin` durch die Zeile "… vor dem Arbeitsgericht Berlin …"
  korroboriert. Ob ein Mandatsfeld eine natürliche Person meint, steht nicht
  im Mandats-Schema (`az`/`mandant`/`gegenseite` — kein `typ`-Feld wie bei
  `interessenkollision-check`), und eine Wortliste der Orts-, Behörden- und
  Branchenwörter wäre nie vollständig; geprüft wird deshalb die **Fundstelle**
  statt des Namens. Bewusste Folge: Z2N greift seltener (z. B. bei
  "Sehr geehrte Frau Rechtsanwältin Merkel" nicht, oder wenn zwei Nachnamen
  nur durch ein Komma statt einen Rubrum-Trenner getrennt stehen) —
  Enthaltung ist besser als ein falscher Kandidat.
- **Ein Mandat ohne `gegenseite` erreicht Z2N nie** — Post, die nur einen
  Einzelnamen nennt, bleibt `kein_treffer` statt geraten zu werden.
- **Kategorie immer `moeglicher_treffer`** — ein Nachname ist schwächere
  Evidenz als ein Vollname (Z1/Z2) und weit schwächer als ein Az (Z0). Z2N
  hebt deshalb auch die `prioritaet` nicht auf `hoch` und ist nie ein
  Freibrief fürs Ablegen (Bestätigung durch die Kanzlei bleibt Pflicht).
- **Mehrdeutigkeit = Enthaltung.** Passt dasselbe Nachname-Signal auf
  mehrere Z2N-fähige Mandate (z. B. zwei Mandate "Merkel"), entsteht für
  **keines** von ihnen ein Kandidat; der Grund steht je E-Mail in
  `zuordnung_hinweise[]` (siehe Report-Struktur), damit die Enthaltung
  sichtbar ist statt als stilles `kein_treffer` unterzugehen. Eindeutig
  bleibt eine **Kombination**: teilt ein anderes Mandat nur den
  Mandanten-Nachnamen, ohne dass dessen Gegenseite im Text vorkommt, ist es
  nicht Z2N-fähig und löst keine Enthaltung aus.

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
        {"az": "…", "datei": "mandate/….md", "stufe": "Z0…Z4 | Z2N",
         "kategorie": "treffer|moeglicher_treffer", "score": 0.0,
         "begruendung": "…"}
      ],
      "kein_treffer": false,
      "zuordnung_hinweise": ["Mandat …: Nachname-Signal … trifft auf mehrere Mandate zu — keine Zuordnung über Stufe Z2N (Enthaltung, Rückfrage an die Kanzlei)."],
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
- **Z1/Z2 verlangen den vollständigen `mandant`/`gegenseite`-String** —
  fehlt im Dokument auch nur ein Namens-Token (typisch: die Anrede "Sehr
  geehrte/r Herr/Frau <Nachname>" ohne Vorname, der Normalfall eigener
  ausgehender Kanzleipost), greifen sie nicht. Diese Falsch-Negativ-Klasse
  war bis zur Pilot-Abnahme 2026-08 undokumentiert; seither fängt Stufe Z2N
  sie **nur** ab, wenn ein zweites Nachname-Signal desselben Mandats
  korroboriert. Nicht abgedeckt bleibt damit: Post mit nur einem Nachnamen
  ohne Gegenseite im Mandat, ohne Aktenzeichen im Text — sie ist und bleibt
  `kein_treffer` und braucht die Zuordnung durch die Kanzlei.
- **Z2N erbt die Nachname-Heuristik** "letztes normalisiertes Token"
  (`nachname()`): bei Namenspräfixen ("van der Berg") ist das nur der Kern
  des Nachnamens, bei Firmen ohne Rechtsform-Zusatz das letzte Firmenwort.
  Für einen Kandidaten muss dieses Token wörtlich im Text stehen **und**
  korroboriert sein — der Fehler wirkt also in Richtung Enthaltung, nicht in
  Richtung falscher Zuordnung.
- **Kein Abgleich gegen `absender_adresse`** für den Parteiname-Abgleich —
  eine E-Mail-Adresse ist kein Namens-Fließtext (siehe
  `core/calc/zuordnung/zuordnung.py`, `FELD_REIHENFOLGE`).
- **Az-Suche nur in Betreff/Textauszug**, nicht im Absendernamen (Az im
  Anzeigenamen ist untypisch).
- **Kölner Phonetik ist für deutsche Lautung entwickelt** — bei
  fremdsprachigen Namen ist die Trefferqualität nicht belastbar (geerbt von
  `core/calc/matching`).
- **`kein_treffer` ist kein Freibrief** — Spitznamen, Umfirmierungen oder
  völlig andere Schreibweisen jenseits der Stufen Z0-Z4/Z2N bleiben
  unentdeckt.
- **Kontakte (`kontakte.md`) fließen aktuell nicht in die Zuordnung ein** —
  nur `mandant`/`gegenseite` aus den Mandats-Frontmatters. Eine Erweiterung
  auf z. B. gegnerische Prozessbevollmächtigte aus `kontakte.md` ist denkbar,
  aber (noch) nicht umgesetzt (siehe Abschlussbericht der Implementierung).
