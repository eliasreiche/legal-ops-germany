# core/adapters/sanktionslisten — EU-/UN-Sanktionslisten-Adapter

Datenquellen-Adapter **außerhalb** des Kontext-Layers (siehe
[`../README.md`](../README.md): „Sanktionslisten … unverändert außerhalb des
Kontext-Layers … keine Kanzlei-Wissens-Anbindung im Sinne von D11"). Er füttert
die Datei-Schnittstelle des Skills
[`gwg-live-screening`](../../../skills/gwg-live-screening/SKILL.md), bindet
aber keine Kanzleisoftware an.

## Zwei Teile, bewusst getrennt (P3-Deterministik)

| Datei | Netzwerk? | Zweck |
|---|---|---|
| [`parser.py`](parser.py) | nein | Wandelt EU-FSF- und UN-XML in `Sanktionsliste`/`SanktionsEintrag`. Reine Stdlib (`xml.etree`), namensraum-tolerant. |
| [`abruf.py`](abruf.py) | **ja** (nur hier) | Lädt die zwei offiziellen URLs lokal (Stdlib `urllib`) und schreibt `abruf-meta.json` mit `abgerufen_am`. |

Der **Screening-Executor macht nie Live-HTTP** — er arbeitet nur auf den
lokalen Dateien, die `abruf.py` (oder ein manueller `curl`) ablegt. Das ist die
Deterministik-Grenze (CONVENTIONS.md P3).

## Formate

- **EU-FSF „full file"** — Wurzel `<export generationDate="…">` (Namensraum
  `http://eu.europa.ec/fpi/fsd/export`), darunter `<sanctionEntity>` mit
  `<subjectType code="person|enterprise">`, `<nameAlias wholeName firstName
  lastName>`, `<birthdate>`, `<regulation programme numberTitle
  publicationDate>`.
- **UN Consolidated List** — Wurzel `<CONSOLIDATED_LIST dateGenerated="…">`
  mit `<INDIVIDUALS>`/`<ENTITIES>`, Namensteilen `<FIRST_NAME>…<FOURTH_NAME>`,
  `<INDIVIDUAL_ALIAS>`/`<ENTITY_ALIAS>` (`<ALIAS_NAME>`),
  `<INDIVIDUAL_DATE_OF_BIRTH>`, `<REFERENCE_NUMBER>`, `<UN_LIST_TYPE>`.

Schema-Herkunft (verifiziert 2026-07-16): UN gegen die Live-Datei geprüft;
EU-FSF-Tags gegen den öffentlichen Referenz-Parser des OpenSanctions-Projekts
(`zavod.shed.fsf`, der dieselben Tags liest). Beide Parser vergleichen über den
**lokalen** Tag-Namen, damit ein Namensraum-Präfix oder eine Schema-Minor-
Version die Extraktion nicht bricht.

## Abruf

```bash
python3 abruf.py --ziel <verzeichnis> [--nur eu|un] [--eu-url "<URL inkl. Token>"]
```

Die EU-FSF-URL verlangt einen öffentlichen Token-Parameter (laut EU-Doku); er
ist bewusst **nicht** im Repo hinterlegt (kann sich ändern) und beim Abruf über
`--eu-url` zu übergeben. `abruf.py` wird in CI **nicht** netzwerk-getestet —
getestet sind nur das URL-Format und das lokale Schreiben von `abruf-meta.json`.
Manuelle `curl`-Alternative: siehe
[`gwg-live-screening/SKILL.md`](../../../skills/gwg-live-screening/SKILL.md).

## Grenzen

Nur die für ein Namens-Screening nötigen Felder werden extrahiert (Primärname,
Aliase, Typ, Geburtsdatum, Referenz/Programm, Listen-Generierungsdatum).
Adressen, Staatsangehörigkeiten, Ausweisnummern werden bewusst nicht gelesen.
Nicht-lateinische Schreibweisen werden übernommen, sind im Downstream-Matching
aber nicht belastbar (Transliterations-Grenze).
