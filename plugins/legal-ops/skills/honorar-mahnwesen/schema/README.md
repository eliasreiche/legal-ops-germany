# Schema — honorar-mahnwesen

Datei-Kontrakt (P2) für den Executor
[`executor.py`](../executor.py), der den Kern
[`core/calc/opos/rechner.py`](../../../core/calc/opos/rechner.py) aufruft.
Kein Netzwerkzugriff, keine Datenbank — Datei rein, JSON-Report raus.

Genau **eine** der beiden Quellen wird angegeben:

| Quelle | Flag | Charakter |
|---|---|---|
| OPOS-CSV | `--opos-csv` | **präzise Primärquelle** — je Zeile ein offener Posten mit Fälligkeitsdatum |
| EXTF-Buchungsstapel | `--extf` | **ergänzend** — vereinfachte Belegfeld-1-Aggregation, siehe unten |

Zusätzlich immer `--stichtag JJJJ-MM-TT` (Bezugstag für „Tage seit
Fälligkeit" — kommt aus der Eingabe, **nie** aus der Wall-Clock, damit gleiche
Eingabe denselben Report ergibt).

## Quelle 1: OPOS-CSV (`--opos-csv`)

Semikolon-getrennte CSV mit Kopfzeile. Beträge in **deutscher Konvention**
(Dezimalkomma, ohne Tausendertrennzeichen, z. B. `1190,00`). Daten im
ISO-Format `JJJJ-MM-TT`.

| Spalte | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `rechnungsnummer` | **ja** | Text, eindeutig | Schlüssel des Postens (Duplikat = Fehler). |
| `rechnungsdatum` | **ja** | `JJJJ-MM-TT` | Datum der Rechnung. |
| `faelligkeitsdatum` | **ja** | `JJJJ-MM-TT` | Fälligkeit (nicht vor `rechnungsdatum`). |
| `betrag` | **ja** | Komma-Dezimal, > 0 | Rechnungsbetrag (brutto). |
| `mandant` | nein | Text | Für die Anrede im Schreiben-Entwurf. |
| `aktenzeichen` | nein | Text | Aktenbezug. |
| `bereits_gezahlt` | nein (Default `0`) | Komma-Dezimal, ≥ 0 | Bereits geleistete Teilzahlung. |

Beispiel: [`beispiel-opos.csv`](beispiel-opos.csv).

Jeder Formatfehler (fehlende Pflichtspalte, unbekannte Spalte, ungültiger
Betrag/Datum, doppelte Rechnungsnummer, Fälligkeit vor Rechnungsdatum) →
Exit 2 mit Zeilenangabe, **keine** Reparatur.

## Quelle 2: EXTF-Buchungsstapel (`--extf`)

Ein DATEV-EXTF-Buchungsstapel (Format 700, Kategorie 21 — wie ihn der Skill
[`datev-export`](../../datev-export/SKILL.md) erzeugt), gelesen vom strikten
Parser [`core/calc/extf/parser.py`](../../../core/calc/extf/parser.py).

**Vereinfachte Aggregation (v1, bewusste Grenze):** Buchungen werden über
**Belegfeld 1** (den OPOS-Schlüssel) gruppiert. Je Gruppe:

```
offener Rest = Σ Umsatz(Soll) − Σ Umsatz(Haben) − Σ Skonto(auf Haben)
Rechnungsdatum = frühestes Soll-Belegdatum der Gruppe
Fälligkeit     = Rechnungsdatum + --zahlungsziel-tage   (Default 14)
```

- EXTF trägt **kein Fälligkeitsdatum** — es wird über das Zahlungsziel
  angenommen (die Annahme steht als Hinweis am Posten). Das ist eine
  Zahlungsziel-Annahme, **keine** Verzugsfeststellung (§ 286 BGB bleibt
  Kanzleisache).
- **Mandant/Aktenzeichen** stehen nicht im EXTF → Lücke (nie geraten).
- Buchungen **ohne Belegfeld 1** sind nicht zuordenbar und erscheinen unter
  `nicht_zuordenbar` — nie stillschweigend verworfen.
- Ein Buchungsstapel enthält selten Rechnung und Zahlung zugleich; ein
  negativer offener Rest (Haben > Soll) wird als Anomalie markiert.

## Mahnstufen (`--mahnstufen-config`, optional)

Konfigurierbare Tagesschwellen. Default (in `core/calc/opos/rechner.py`,
`MAHNSTUFEN_DEFAULT`):

| Tage seit Fälligkeit | Mahnstufe |
|---|---|
| < 0 | `offen_nicht_faellig` |
| 0–13 | `zahlungserinnerung` |
| 14–29 | `1_mahnung` |
| ≥ 30 | `2_mahnung` |

Override per JSON-Datei:

```json
{ "stufen": [
  {"ab_tage": 30, "stufe": "2_mahnung", "bezeichnung": "2. Mahnung"},
  {"ab_tage": 14, "stufe": "1_mahnung", "bezeichnung": "1. Mahnung"},
  {"ab_tage": 0,  "stufe": "zahlungserinnerung", "bezeichnung": "Zahlungserinnerung"}
] }
```

Die Stufen sind eine **kalendarische** Einordnung — ob und wann tatsächlich
gemahnt wird, entscheidet die Kanzlei.

## Ausgabe: JSON-Report

```json
{
  "meta": { "erzeugt_von": "…/opos/rechner.py", "deterministik": "…",
            "verzugszins_hinweis": "…", "quelle_format": "opos-csv" },
  "stichtag": "2026-07-16",
  "mahnstufen_konfiguration": [ … ],
  "zusammenfassung": { "anzahl_offen": 3, "summe_offen": "3020.00",
                        "anzahl_ausgeglichen": 1, "anzahl_nicht_zuordenbar": 0 },
  "offene_posten": [
    { "rechnungsnummer": "RE-2026-001", "mandant": "Max Mustermann",
      "offener_rest": "1190.00", "faelligkeitsdatum": "2026-05-15",
      "tage_seit_faelligkeit": 62, "mahnstufe": "2_mahnung",
      "prioritaet": "73780.00", "verzugszins_hinweis": "…", "quelle": "opos-csv",
      "hinweise": [] }
  ],
  "ausgeglichene_posten": [ … ],
  "nicht_zuordenbar": [ … ]
}
```

- `offene_posten` sind nach **Priorität** (offener Rest × Tage seit
  Fälligkeit) absteigend sortiert; Posten ohne Fälligkeit stehen am Ende.
- Alle Zahlen-/Datums-/Geldwerte sind Executor-Ergebnisse (P3), als
  Decimal-Strings ausgegeben (keine float-Rundung).
- `verzugszins_hinweis` ist immer eine **Lücke**, nie eine Zahl (§ 288 BGB
  bewusst zurückgestellt, siehe SKILL.md).

## Bewusste Grenzen

- **Keine Verzugszinsen** (§ 288 BGB) und **keine** rechtliche
  Verzugsfeststellung (§ 286 BGB) — nur „Tage seit Fälligkeit".
- **EXTF-Quelle ist vereinfacht** (Belegfeld-1-Saldo, Zahlungsziel-Annahme)
  — die präzise Quelle ist die OPOS-CSV.
- **Kein Versand** — der Skill draftet allenfalls Entwürfe; Mahnung/Versand
  entscheidet die Kanzlei.
