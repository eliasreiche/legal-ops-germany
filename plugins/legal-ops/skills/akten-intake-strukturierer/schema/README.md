# Schema — akten-intake-strukturierer

Datei-Kontrakt (P2) für [`executor.py`](../executor.py). Kein Netzwerkzugriff,
keine Datenbank — Dateien rein, JSON-Report raus. Der Kontrakt wird in **beide
Richtungen** dokumentiert: die Eingabe `aktenkopf.json` (vom Modell erzeugt) und
die Ausgabe `report.json` (vom Executor erzeugt).

## Eingabe 1: Aktenkopf (`--aktenkopf`, JSON, Pflicht)

Vom Modell aus dem/den Quelldokument(en) erzeugt. Vollständiges Beispiel:
[`beispiel-aktenkopf.json`](beispiel-aktenkopf.json).

```json
{
  "aktenkopf": {
    "kurzrubrum": "Mustermann ./. Beispiel (Verkehrsunfall)",
    "sachverhalt_kurz": "Gegnerisches Anspruchsschreiben nach Verkehrsunfall …",
    "eingangsdatum": "2026-03-05"
  },
  "parteien": [
    {
      "rolle": "mandant",
      "name": "Max Mustermann",
      "typ": "natuerlich",
      "anschrift": "Musterweg 3, 20099 Hamburg",
      "kontakt": { "email": "", "telefon": "", "iban": "" },
      "vertreten_durch": null
    }
  ],
  "fristen_hinweise": [
    {
      "datum_im_text": "2026-03-20",
      "originalschreibweise": "20.03.2026",
      "quelle_zitat": "… bis zum 20.03.2026 …",
      "vermutete_bedeutung": "Von der Gegenseite gesetzte Zahlungsfrist — keine gesetzliche Frist."
    }
  ],
  "betraege": [
    { "betrag": "1.234,56 €", "kontext": "Reparaturkosten", "quelle_zitat": "… 1.234,56 € …" }
  ],
  "aktenzeichen_fremd": [
    { "aktenzeichen": "045/26 K01", "stelle": "Kanzlei der Gegenseite", "quelle_zitat": "Unser Zeichen: 045/26 K01" }
  ],
  "luecken": [
    { "feld": "parteien[1].anschrift", "grund": "Anschrift der Gegnerin fehlt im Schreiben; für Zustellungen nötig." }
  ]
}
```

### Felder

**`aktenkopf`** (Objekt, Pflicht):

| Feld | Pflicht | Wert | Bedeutung |
|---|---|---|---|
| `kurzrubrum` | ja¹ | String | Kurzbezeichnung „A ./. B". |
| `sachverhalt_kurz` | ja¹ | String | 1–3 Sätze Sachverhalt, aus dem Dokument. |
| `eingangsdatum` | ja¹ | ISO `JJJJ-MM-TT` | Eingang bei der Kanzlei bzw. Datum des Dokuments. Wird als kritischer Wert auf Provenienz geprüft. |

**`parteien[]`** (Liste, mind. 1 Eintrag = Mandant):

| Feld | Pflicht | Wert | Bedeutung |
|---|---|---|---|
| `rolle` | ja | `mandant` / `gegner` / `sonstige` | Enum — kein Lücken-Feld: leer/ungültig = Schema-Fehler. |
| `name` | ja¹ | String | Name der Partei. |
| `typ` | ja | `natuerlich` / `juristisch` | Enum — kein Lücken-Feld. |
| `anschrift` | ja¹ | String | Postanschrift. |
| `kontakt` | ja (Objekt) | `{email, telefon, iban}` | Alle drei optional; falls gesetzt, werden sie als kritische Werte auf Provenienz geprüft. |
| `vertreten_durch` | ja (Schlüssel) | String / `null` | Bevollmächtigte(r); `null`, wenn keine Vertretung. |

**`fristen_hinweise[]`** (Liste) — **erkannte Datumsnennungen, keine
Fristberechnung.** Jeder Eintrag ist vollständig anzugeben (kein Lücken-Konzept):

| Feld | Wert | Bedeutung |
|---|---|---|
| `datum_im_text` | ISO `JJJJ-MM-TT` | Normalisiertes Datum. Kritischer Wert (Provenienz). |
| `originalschreibweise` | String | Datum wie im Text (`20.03.2026`). |
| `quelle_zitat` | String | Wörtliche Textstelle. |
| `vermutete_bedeutung` | String | Deutung (z. B. „Zahlungsfrist der Gegenseite") — **nie** ein berechnetes Fristende. |

**`betraege[]`** (Liste): `betrag` (String inkl. Währung, kritischer Wert),
`kontext`, `quelle_zitat`. Alle Felder Pflicht je Eintrag.

**`aktenzeichen_fremd[]`** (Liste): `aktenzeichen` (String, kritischer Wert),
`stelle`, `quelle_zitat`. Alle Felder Pflicht je Eintrag.

**`luecken[]`** (Liste): `feld` (Pfad der fehlenden Angabe, z. B.
`parteien[1].anschrift`), `grund` (warum für die Aktenanlage nötig). Siehe
Lücken-Disziplin unten.

¹ **Lücken-Disziplin**: Diese Pflichtfelder dürfen leer (`""`/`null`) sein —
aber **nur**, wenn ein `luecken`-Eintrag mit exakt passendem `feld`-Pfad
existiert. Lücken-fähig sind `aktenkopf.kurzrubrum`, `aktenkopf.sachverhalt_kurz`,
`aktenkopf.eingangsdatum`, `parteien[i].name`, `parteien[i].anschrift`. Ein
leeres Lücken-fähiges Feld **ohne** passenden `luecken`-Eintrag ist ein
Schema-Fehler. Zusätzliche `luecken`-Einträge (für Angaben außerhalb dieser
Felder, z. B. fehlende Dokumente) sind erlaubt.

## Eingabe 2: Quelldokument(e) (`--quelle`, `.txt`/`.md`, Pflicht)

Das/die zugrunde liegende(n) Dokument(e), UTF-8. Mehrfach angebbar — der
Executor durchsucht alle Quellen; die erste Fundstelle je Wert gewinnt.

## Provenienz & Normalisierung

Ein kritischer Wert gilt als **belegt**, wenn er nach folgender Normalisierung
wörtlich in einer Quellzeile vorkommt:

| Typ | kritische Felder | Normalisierung |
|---|---|---|
| `datum` | `eingangsdatum`, `fristen_hinweise[].datum_im_text` | ISO ↔ deutsch: `2026-03-01` = `01.03.2026` = `1.3.2026`; 2-stellige Jahre (`26`) → `20xx`/`19xx`. |
| `geld` | `betraege[].betrag` | Währung (€/EUR/Euro) entfernt; `.` = Tausender, `,` = Dezimal → `1.234,56 €` = `1234,56 EUR` = `1234.56`. |
| `aktenzeichen` | `aktenzeichen_fremd[].aktenzeichen` | Mehrfach-Whitespace kollabiert; Groß-/Kleinschreibung zählt. |
| `iban` | `parteien[].kontakt.iban` | Whitespace entfernt, Großschreibung — `DE02 1203 …` = `DE021203…`. |
| `email` | `parteien[].kontakt.email` | Whitespace getrimmt, Kleinschreibung. |
| `telefon` | `parteien[].kontakt.telefon` | Trennzeichen (Leerzeichen, `/`, `-`, `.`, Klammern) entfernt. **Keine** Ländervorwahl-Äquivalenz (`+49` ↔ `0`). |

Nicht belegte Werte → `nicht_belegt` (Exit-Code ≠ 0). Anschrift und Name werden
**nicht** auf Provenienz geprüft (nur strukturell auf Nicht-Leere bzw.
Lücken-Disziplin) — sie sind für einen verlässlichen Wortlaut-Abgleich zu
variabel.

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json) (erzeugt
aus [`beispiel-aktenkopf.json`](beispiel-aktenkopf.json) +
[`beispiel-eingabe.md`](beispiel-eingabe.md)). Struktur:

```json
{
  "meta": {
    "erzeugt_von": "akten-intake-strukturierer/executor.py",
    "aktenkopf_datei": "…",
    "quelldateien": ["…"],
    "anzahl_kritische_werte": 11,
    "hinweis": "Erkannte Datumsnennungen sind KEINE Fristberechnung — …"
  },
  "schema_ok": true,
  "schema_fehler": ["…"],
  "provenienz": [
    {
      "pfad": "betraege[0].betrag",
      "typ": "geld",
      "wert": "1.234,56 €",
      "status": "belegt | nicht_belegt",
      "fundstelle": { "datei": "…", "zeile": 25, "zitat": "…" },
      "begruendung": "…"
    }
  ],
  "luecken": [ { "feld": "…", "grund": "…" } ],
  "zusammenfassung": { "belegt": 11, "nicht_belegt": 0, "schema_fehler": 0 }
}
```

- **`schema_ok` / `schema_fehler`** — Ergebnis der Strukturprüfung (inkl.
  Lücken-Disziplin und ISO-Datumsformate).
- **`provenienz[]`** — je kritischem Wert der Beleg-Zustand; bei `belegt` mit
  `fundstelle` (Datei + 1-basierte Zeile + gestripptes Zitat), bei `nicht_belegt`
  ist `fundstelle` `null`.
- **`luecken[]`** — unverändertes Echo des Lücken-Arrays aus dem Aktenkopf.

### Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Schema in Ordnung **und** alle kritischen Werte belegt. |
| `1` | Mindestens ein `nicht_belegt`-Wert **und/oder** mindestens ein Schema-Fehler. |
| `2` | Eingabefehler (Aktenkopf-/Quelldatei fehlt, kaputtes JSON, Ziel nicht schreibbar). |

## Bewusste Grenzen

- **Keine Fristberechnung**: `fristen_hinweise` sind erkannte Datumsnennungen,
  kein Fristende. Fristen ausschließlich über
  [`fristenrechner-de`](../../fristenrechner-de/SKILL.md).
- **Provenienz = Beleg, nicht Richtigkeit**: `belegt` bestätigt nur das
  Vorkommen im Text, nicht die rechtliche Richtigkeit oder die Feldzuordnung.
- **PDF/Scan** out of scope → `posteingang-ocr-routing` (Welle 4).
- **Geld-Heuristik**: der numerische Abgleich ignoriert die Währung; ein Betrag,
  der zufällig einer Jahreszahl entspricht, kann formal als belegt gelten — die
  inhaltliche Zuordnung bleibt anwaltlich zu prüfen.
