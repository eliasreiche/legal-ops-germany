# Schema — datev-export

Datei-Kontrakt (P2) für den Executor
[`core/calc/extf/executor.py`](../../../core/calc/extf/executor.py).
Kein Netzwerkzugriff, keine Datenbank — JSON-Datei rein, EXTF-CSV +
JSON-Report raus.

> ⚠️ Dieses Schema ist ein **eigenes JSON-Schema** (kein DATEV-Standard) —
> der Executor übersetzt es deterministisch in die DATEV-EXTF-Feldstruktur
> (Kategorie 21, Formatversion 700). Diese Feldstruktur selbst ist nicht
> primärquellen-verifiziert, siehe [`core/calc/extf/README.md`](../../../core/calc/extf/README.md).

## Eingabe (JSON, `--input`)

```json
{
  "header": { "...": "Metadaten für die EXTF-Kopfzeile, siehe unten" },
  "buchungen": [ { "...": "ein Buchungssatz, siehe unten" } ]
}
```

Beide Top-Level-Felder sind Pflicht; unbekannte Top-Level-Felder sind ein
Eingabefehler (Tippfehler-Schutz).

### `header`

```json
{
  "erzeugt_am": "2026-07-13T10:00:00",
  "exportiert_von": "Kanzlei Mustermann",
  "beraternummer": 12345,
  "mandantennummer": 100,
  "wirtschaftsjahresbeginn": "2026-01-01",
  "sachkontenlaenge": 4,
  "buchungszeitraum_von": "2026-01-01",
  "buchungszeitraum_bis": "2026-12-31",
  "bezeichnung": "Buchungsstapel Juli 2026",
  "diktatkuerzel": "EM",
  "buchungstyp": 1,
  "waehrung": "EUR",
  "formatversion": 5,
  "herkunft": "RE"
}
```

| Feld | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `erzeugt_am` | **ja** | ISO-Datum+Zeit `JJJJ-MM-TTTHH:MM:SS` | Zeitstempel der EXTF-Kopfzeile — kommt aus der Eingabe, **nie** aus der Wall-Clock (Idempotenz: gleiche Eingabe → byte-identische Datei). |
| `exportiert_von` | **ja** | Text, max. 25 Zeichen | Name der erzeugenden Software/Kanzlei (EXTF-Feld „Exportiert von"). |
| `beraternummer` | **ja** | Ganzzahl, 1–7 Stellen | DATEV-Beraternummer. |
| `mandantennummer` | **ja** | Ganzzahl, 1–5 Stellen | DATEV-Mandantennummer. |
| `wirtschaftsjahresbeginn` | **ja** | ISO-Datum `JJJJ-MM-TT` | Beginn des Wirtschaftsjahres. |
| `sachkontenlaenge` | nein (Default `4`) | Ganzzahl, 4–8 | Stellenzahl der Sachkonten — bestimmt die erlaubte Konto-/Gegenkonto-Länge (siehe unten). **Kein Kontenrahmen-Default** — nur die Stellenzahl. |
| `buchungszeitraum_von` / `_bis` | **ja** | ISO-Datum `JJJJ-MM-TT` | Rahmen, in dem alle Belegdaten liegen müssen — jedes `belegdatum` einer Buchung wird dagegen geprüft (Exit 2 bei Verstoß), bevor es auf `TTMM` gekürzt wird. |
| `bezeichnung` | **ja** | Text, max. 30 Zeichen | Bezeichnung des Buchungsstapels. |
| `diktatkuerzel` | nein | Text, max. 2 Zeichen | z. B. Kürzel der Sachbearbeitung. |
| `buchungstyp` | nein (Default `1`) | `1` oder `2` | 1 = Finanzbuchführung, 2 = Jahresabschluss. |
| `waehrung` | nein (Default `"EUR"`) | Text, max. 3 Zeichen | Währungskennzeichen der Kopfzeile. |
| `formatversion` | nein (Default `5`) | Ganzzahl | ⚠️ Unverifizierte Annahme (Minimal-Buchungssatz ohne Erweiterungsfelder) — vor Echt-Import prüfen. |
| `herkunft` | nein (Default `"RE"`) | Text, 2 Zeichen | Herkunfts-Kennzeichen. |

Alle Textfelder werden vor dem Export auf CP1252-Kodierbarkeit geprüft
(Umlaute/ß sind unproblematisch, Emoji o. Ä. sind ein Formatfehler).

### `buchungen` (Liste, mind. ein Eintrag)

```json
{
  "umsatz": "952.50",
  "soll_haben": "S",
  "wkz_umsatz": null,
  "kurs": null,
  "basisumsatz": null,
  "wkz_basisumsatz": null,
  "konto": "1200",
  "gegenkonto": "8400",
  "bu_schluessel": null,
  "belegdatum": "2026-03-15",
  "belegfeld1": "RE-2026-042",
  "belegfeld2": null,
  "skonto": null,
  "buchungstext": "Honorar Müller ./. Schmidt",
  "quelle": null,
  "bestaetigt": null
}
```

| Feld | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `umsatz` | **ja** | Decimal-String, z. B. `"952.50"` | Betrag, **immer positiv** (> 0). Kein `float` — der Executor lehnt float-Eingaben strikt ab. |
| `soll_haben` | **ja** | `"S"` oder `"H"` | Soll-/Haben-Kennzeichen bezogen auf `konto`. |
| `wkz_umsatz` | nein | Text, 3 Zeichen | Leer/`null` = Währung aus dem Header übernehmen. |
| `kurs` | nein | Decimal-String | Fremdwährungskurs; `0` ist unzulässig, falls angegeben. |
| `basisumsatz` | nein | Decimal-String | Nur zusammen mit `wkz_basisumsatz` (beide oder keines). |
| `wkz_basisumsatz` | nein | Text, 3 Zeichen | Siehe `basisumsatz`. |
| `konto` | **ja** | numerischer String | Länge muss `header.sachkontenlaenge` (Sachkonto) oder `sachkontenlaenge + 1` (Personenkonto) sein. **Nur Formatprüfung** — nie ein SKR03/SKR04-Kontenrahmen-Rat. |
| `gegenkonto` | **ja** | numerischer String | Wie `konto`. |
| `bu_schluessel` | nein | Text, max. 4 Zeichen | Steuer-/Berichtigungsschlüssel. |
| `belegdatum` | **ja** | ISO-Datum `JJJJ-MM-TT` | **Volles Datum** (mit Jahr) — der Executor prüft, dass es im Header-Buchungszeitraum liegt, und gibt es dann als `TTMM` aus (Jahr steckt im Wirtschaftsjahr). |
| `belegfeld1` | nein | Text, max. 36 Zeichen, nur `A-Za-z0-9$&%*+-/` | Rechnungs-/Belegnummer (OPOS-Schlüssel). |
| `belegfeld2` | nein | Text, max. 12 Zeichen, gleiches Zeichenset | Zusatz-Belegnummer. |
| `skonto` | nein | Decimal-String | `0` ist unzulässig, falls angegeben. |
| `buchungstext` | nein | Text, max. 60 Zeichen | Freitext. |
| `quelle` | nein | `"modell-extraktion"` oder weggelassen | Siehe „Modell-Extraktion" unten. |
| `bestaetigt` | nein | `true`/`false` | Pflicht `true`, wenn `quelle` gesetzt ist. |

## Modell-Extraktion (P3-Wahrung, D20)

Claude darf aus einer Rechnung (PDF/Text) einen JSON-**Entwurf**
erstellen. Jede Buchung, deren Zahlenwerte Claude dabei **aus dem Dokument
ausgelesen** hat (statt vom Nutzer strukturiert übergeben zu bekommen),
markiert Claude mit `"quelle": "modell-extraktion"`. Der Executor
**exportiert eine so markierte Buchung nur**, wenn zusätzlich
`"bestaetigt": true` gesetzt ist — sonst Exit 2. Direkt strukturiert
gelieferte Buchungen (Nutzer diktiert/liefert die Werte) brauchen kein
`quelle`-Feld.

**Granularität: die gesamte Buchungszeile**, nicht das einzelne Zahlenfeld
— alle Werte einer Buchung stammen aus demselben Beleg und werden gemeinsam
vom Nutzer bestätigt. Das ist eine bewusste Vereinfachung dieses eigenen
Schemas (kein DATEV-Standard); eine feingranularere Markierung je Feld wäre
in einer künftigen Version möglich, ist aber für v1 nicht erforderlich.

## Ausgabe: EXTF-Datei

CSV, **CP1252-kodiert**, Semikolon-getrennt, `\r\n`-Zeilenenden:

- **Zeile 1** — Metadaten-Header, 31 Felder nach
  [`header_format_700.json`](../../../core/calc/extf/header_format_700.json).
- **Zeile 2** — Spaltenköpfe (20 Spalten, jeweils in Anführungszeichen).
- **ab Zeile 3** — je Buchung eine Zeile, 20 Spalten nach
  [`buchungssatz_spalten_700.json`](../../../core/calc/extf/buchungssatz_spalten_700.json).
  Spalten 15–20 (Postensperre, Diverse Adressnummer,
  Geschäftspartnerbank, Sachverhalt, Zinssperre, Beleglink) sind in v1
  immer leer (Positions-Platzhalter, siehe Grenzen in der SKILL.md).

Beispiel: [`beispiel-stapel.csv`](beispiel-stapel.csv), erzeugt aus
[`beispiel-eingabe.json`](beispiel-eingabe.json).

## Ausgabe: JSON-Report

Beispiel: [`beispiel-report.json`](beispiel-report.json) (vom Executor
regeneriert, siehe `tests/test_executor_cli.py::test_beispiel_report_synchron`).

```json
{
  "meta": { "erzeugt_von": "core/calc/extf/executor.py",
            "formatversion_hinweis": "⚠️ …", "scope_hinweis": "…" },
  "header": { "…normalisierte Header-Werte…": "…", "quelle": "executor" },
  "buchungen_anzahl": 1,
  "buchungen": [
    { "index": 1, "umsatz": "952.50", "soll_haben": "S", "konto": "1200",
      "gegenkonto": "8400", "belegdatum_ttmm": "1503",
      "belegdatum_iso": "2026-03-15", "belegfeld1": "RE-2026-042",
      "buchungstext": "Honorar Müller ./. Schmidt", "quelle": "executor" }
  ],
  "warnungen": []
}
```

## Bewusste Grenzen

- **Nur Buchungsstapel** — kein Parser, keine Stammdaten (Kategorie 16),
  kein Import (D20).
- **Nur 20 Spalten** (Umsatz bis Beleglink) — Kostenstellen, Beleginfo,
  EU-USt-Felder u. a. Erweiterungen der realen DATEV-Schnittstelle fehlen.
- **Kein Kontenrahmen-Raten** — Konto/Gegenkonto nur formatgeprüft.
- **⚠️ Formatversion 700 nicht primärquellen-verifiziert** — vor
  Echt-Import gegen aktuelle DATEV-Dokumentation prüfen.
