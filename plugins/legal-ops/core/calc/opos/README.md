# core/calc/opos — Auswertung offener Posten (Honorar-Mahnwesen)

Deterministischer Kern (P3) hinter dem Skill
[`honorar-mahnwesen`](../../../skills/honorar-mahnwesen/SKILL.md). Nimmt offene
Posten aus zwei Datei-Quellen und rechnet je Posten offenen Restbetrag, Tage
seit Fälligkeit, Mahnstufe und Priorität — nie das Modell.

## Bausteine (`rechner.py`)

- `lade_opos_csv(...)` — liest die OPOS-CSV (präzise Primärquelle) strikt
  ein (Zeilenangabe bei Fehlern, keine stille Reparatur).
- `stapel_zu_posten(stapel, zahlungsziel_tage)` — aggregiert einen geparsten
  EXTF-Buchungsstapel (`core/calc/extf/parser.py`) über Belegfeld 1 zu
  offenen Posten (vereinfachte Quelle; Lücken werden ausgewiesen).
- `bewerte(posten, stichtag, mahnstufen, ...)` — der Auswertungskern:
  offener Rest = `betrag − bereits_gezahlt`; `tage_seit_faelligkeit =
  stichtag − faelligkeitsdatum`; Mahnstufe aus konfigurierbaren
  Tagesschwellen (`MAHNSTUFEN_DEFAULT`); Priorität = offener Rest × Alter.
- `lade_mahnstufen_config(...)` — validiert eine optionale Override-Konfiguration.

## Deterministik & bewusste Grenzen (P3)

- **Nur `decimal.Decimal`, nie `float`** — Beträge kommen als String und
  gehen über `wertgebuehr_formel.D()` (geteilt mit rvg/gkg/extf).
- **Stichtag aus der Eingabe, nie aus der Wall-Clock** — Idempotenz wie
  `erzeugt_am` im EXTF-Writer.
- **Keine Verzugszinsen** (§ 288 BGB — bräuchte Basiszinssatz-Stammdaten) und
  **keine** rechtliche Verzugsfeststellung (§ 286 BGB — verbraucherabhängig,
  Kanzleisache). Zinsen erscheinen im Report nur als Hinweis-Lücke
  (`VERZUGSZINS_HINWEIS`), nie als Zahl.
- **Anti-Halluzination** — fehlende Angaben (Mandant/Fälligkeit bei der
  EXTF-Quelle) bleiben Lücke; nicht zuordenbare Buchungen werden gemeldet,
  nie geraten.

Nur Standardbibliothek, kein Netzwerkzugriff. Datei-Kontrakt und Report-Form:
[`skills/honorar-mahnwesen/schema/README.md`](../../../skills/honorar-mahnwesen/schema/README.md).
