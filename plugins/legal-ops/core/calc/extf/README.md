# core/calc/extf — DATEV-EXTF-Buchungsstapel-Export

Erzeugt aus strukturierten Buchungsdaten (JSON) eine DATEV-EXTF-Datei
(Kategorie 21 „Buchungsstapel", Formatversion 700) zum Import beim
Steuerberater — CSV, CP1252-kodiert, Semikolon-getrennt, Textfelder in
doppelten Anführungszeichen.

> ⚠️ **Formatversion 700 ist NICHT primärquellen-verifiziert.**
> developer.datev.de blockt automatisierten Zugriff; die Feldliste wurde aus
> drei Sekundärquellen (smartkontoauszug.de, auditplan.io,
> clever-invoice.com) rekonstruiert und mit der Feldstruktur von
> [github.com/ledermann/datev](https://github.com/ledermann/datev)
> (MIT-Lizenz, Ruby) als reiner **Strukturreferenz** abgeglichen — kein Code
> aus diesem Projekt übernommen. **Vor dem ersten echten Import zwingend
> gegen die aktuelle DATEV-Dokumentation prüfen.**

## Scope (Maintainer-Entscheidung D20)

**Nur Buchungsstapel-Export.** Kein Parser (Rechnung → Buchung ist
Claude-Aufgabe, siehe SKILL.md), keine Stammdaten (Kategorie 16, Debitoren/
Kreditoren), kein Import. Kontenrahmen ist **konfigurierbar ohne Vorgabe** —
Konto/Gegenkonto sind Pflichtfelder, der Executor validiert nur das Format
(numerisch, Länge konsistent zur Header-Sachkontenlänge) und rät **nie**
SKR03/SKR04.

## CLI

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/core/calc/extf/executor.py \
  --input <eingabe.json> --output <stapel.csv> \
  [--output-report <report.json>]
```

Eingabe-Schema, Beispiele und die vollständige Reject-Matrix stehen bei
[`plugins/legal-ops/skills/datev-export/schema/README.md`](../../skills/datev-export/schema/README.md).

## Deterministik-Bausteine (P3)

- **Nur `decimal.Decimal`, nie `float`** — Geldbeträge/Kurse kommen als
  JSON-String oder ganze Zahl, float wird strikt abgelehnt (geteilte
  Prüfung mit `core/calc/rvg` und `core/calc/gkg` über
  [`wertgebuehr_formel.py`](../wertgebuehr_formel.py): `D()`,
  `parse_datum_strikt()`).
- **`erzeugt_am` kommt aus der Eingabe, nie aus der Wall-Clock** — wie
  `DTSTAMP` in `core/calc/fristen/kalender_executor.py`: gleiche Eingabe →
  byte-identische EXTF-Datei (Idempotenz, siehe `tests/`).
- **CP1252-Pflicht**: jedes Textfeld wird vor dem Schreiben auf verlustfreie
  CP1252-Kodierbarkeit geprüft (`formate.pruefe_cp1252`) — ein nicht
  kodierbares Zeichen (Emoji, Sonderanführungszeichen, …) ist Exit 2, keine
  stille Ersetzung/Transliteration.
- **Belegdatum-Konsistenz**: Ausgabeformat ist `TTMM` (das Jahr steckt im
  Header-Wirtschaftsjahr), aber die Eingabe ist ein volles ISO-Datum — der
  Executor prüft, dass jedes Belegdatum tatsächlich im
  Header-Buchungszeitraum (`buchungszeitraum_von`/`_bis`) liegt, bevor das
  Jahr verworfen wird.
- **Modell-Extraktion braucht Bestätigung**: eine Buchung mit
  `"quelle": "modell-extraktion"` (Claude hat sie aus einer Rechnung
  entworfen) wird nur exportiert, wenn zusätzlich `"bestaetigt": true`
  gesetzt ist — sonst Exit 2. Direkt strukturiert gelieferte Buchungen
  brauchen kein `quelle`-Feld.

## Fail-Fast, keine Datei bei Formatfehler

Der gesamte Export (Header-Zeile, Spaltenkopf-Zeile, alle Buchungszeilen)
wird vollständig im Speicher aufgebaut und validiert, **bevor** irgendeine
Datei geschrieben wird. Jeder Formatfehler (Betrag ≤ 0, Konto nicht
numerisch/falsche Länge, Belegdatum außerhalb des Buchungszeitraums,
Buchungstext > 60 Zeichen, nicht-CP1252-Zeichen, unbestätigte
Modell-Extraktion, …) → Exit 2, **keine** EXTF-Datei und **kein** Report
(Maintainer-Entscheidung D20: ein defektes EXTF beim Steuerberater ist
teurer als eine Ablehnung).

## Bewusste Grenzen

- **Nur die ersten 20 Buchungssatz-Spalten** implementiert (Umsatz bis
  Beleglink) — Kostenstellen (KOST1/KOST2), Beleginfo-Paare, EU-USt-Felder
  und weitere Erweiterungen der realen, weit über 100 Spalten umfassenden
  DATEV-Schnittstelle sind **nicht** unterstützt. Spalten 15–20 werden als
  Positions-Platzhalter mitgeführt (immer leer).
- **Kein Kontenrahmen-Raten** — Konto/Gegenkonto werden nur auf Format
  geprüft, nie auf SKR03/SKR04 oder einen anderen Kontenrahmen gemappt.
- **`status: getestet` erst nach echtem DATEV-Import** durch eine
  Steuerberatung — automatisierte Tests (Spec- und Golden-File-Tests)
  rechtfertigen nur `status: beta` (Reifegrad-Leiter, CONVENTIONS.md).
- **Formatversion/Feldliste nicht primärquellen-verifiziert** (siehe oben).
