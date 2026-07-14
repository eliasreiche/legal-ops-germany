# Schema — taetigkeitstext-rvg

Datei-Kontrakt (P2) für den Executor [`executor.py`](../executor.py) und die
Bibliothek [`core/calc/zeit/`](../../../core/calc/zeit/). Kein
Netzwerkzugriff, keine Datenbank. Zwei Modi, zwei Datei-Kontrakte.

## Modus 1 (rechnen) — Eingabe: Leistungen (JSON, `--input`)

**Das ist die Schnittstelle zum Skill `passive-zeiterfassung`** (dieselbe
Welle): dessen Zeiterfassungs-Vorschläge lassen sich, sobald der Nutzer sie
bestätigt hat, unverändert in dieses Format überführen und hier weiter-
verarbeiten. Beispiel: [`beispiel-leistungen.json`](beispiel-leistungen.json).

```json
{
  "eintraege": [
    {
      "datum": "2026-07-01",
      "az": "12/2026",
      "minuten": null,
      "start": "2026-07-01T09:00:00",
      "ende": "2026-07-01T09:47:00",
      "stichworte": ["Telefonat mit Mandant", "Sachstand besprochen"],
      "quelle": "kalender"
    }
  ],
  "config": { "takt_minuten": 6 }
}
```

### Feld-Kontrakt je Eintrag (`eintraege[]`)

| Feld | Pflicht | Typ / Werte | Bedeutung |
|---|---|---|---|
| `datum` | ja | ISO-Datum `JJJJ-MM-TT` | Tag der Tätigkeit (für die Aggregation je (`az`, `datum`) und die Anzeige). |
| `az` | nein (Default `null`) | Text oder `null` | Internes Aktenzeichen (Repo-Konvention, z. B. `12/2026`). `null`/leer/fehlend → Eintrag landet in `ohne_az[]` (Lücke, nie geraten). |
| `minuten` | nein (Default `null`) | ganze Zahl > 0 oder `null` | Direkte Minutenangabe. **Entweder** dies **oder** `start`+`ende` — beides zugleich oder nur eine Seite von `start`/`ende` ist ein Eingabefehler (Exit 2). |
| `start` / `ende` | nein (Default `null`) | ISO-8601-Zeitstempel oder `null` | Kalender-Zeitraum, aus dem die Dauer berechnet wird (`core/calc/zeit`, Aufrunden auf volle Minuten). Beide Felder müssen zusammen gesetzt sein. |
| `stichworte` | ja | Liste nicht-leerer Texte | Rohmaterial für die Formulierung durch Claude (Schritt 2 im SKILL.md-Ablauf) — wird vom Executor wörtlich in den Report übernommen, nie interpretiert. Dünne Listen (1 Stichwort) sind zulässig, führen aber zu einem knappen Text (siehe SKILL.md). |
| `quelle` | ja | `kalender` \| `mail` \| `manuell` | Herkunft des Eintrags — reine Dokumentation, keine Rechenwirkung. |

Ein unbekanntes Feld in einem Eintrag ist ein Eingabefehler (Tippfehler-
Diagnose, Exit 2), ebenso ein fehlendes Pflichtfeld (`datum`, `stichworte`,
`quelle`).

### `config` (optional)

| Feld | Pflicht | Typ | Bedeutung |
|---|---|---|---|
| `takt_minuten` | nein | ganze Zahl > 0 oder `null` | Abrechnungstakt (z. B. `6`). Wird **immer aufgerundet** (kaufmännisches Runden ist hier ausdrücklich nicht gewollt) — dokumentierte Kanzlei-Konvention der Abrechnungspraxis, **keine RVG-Vorgabe**. Fehlt `config` oder `takt_minuten`, bleibt die Minutenangabe ungerundet (`minuten_getaktet == minuten`). |

## Modus 1 — Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(erzeugt aus [`beispiel-leistungen.json`](beispiel-leistungen.json)). Struktur:

```json
{
  "meta": { "erzeugt_von": "…", "eingabe_datei": "…",
            "config": { "takt_minuten": 6 }, "deterministik": "…" },
  "eintraege": [
    { "index": 0, "datum": "2026-07-01", "az": "12/2026",
      "minuten": 47, "minuten_getaktet": 48,
      "quelle_zeit": "minuten | start_ende",
      "stichworte": ["…"], "quelle": "kalender" }
  ],
  "ohne_az": [ "… gleiche Struktur, az immer null …" ],
  "summen": {
    "je_az": { "12/2026": 78 },
    "je_az_und_datum": [ { "az": "12/2026", "datum": "2026-07-01", "minuten": 78 } ]
  },
  "zusammenfassung": {
    "anzahl_eintraege": 5, "anzahl_mit_az": 4, "anzahl_ohne_az": 1,
    "minuten_gesamt": 134, "minuten_gesamt_getaktet": 144
  }
}
```

- **`eintraege[]`** enthält nur Einträge **mit** `az` (Aggregationsbasis).
  Einträge ohne `az` stehen ausschließlich in **`ohne_az[]`** — die Lücke
  wird nie stillschweigend in die Summen gemischt.
- **`minuten`** ist der rohe Executor-Wert (aus `minuten` übernommen oder aus
  `start`/`ende` berechnet); **`minuten_getaktet`** ist derselbe Wert nach
  Anwendung von `config.takt_minuten` (identisch, wenn keine Taktung
  konfiguriert ist). Die Summen (`summen.*`, `zusammenfassung.*_getaktet`)
  rechnen mit den **getakteten** Minuten — das ist der abrechnungsrelevante
  Wert.
- **`quelle_zeit`** dokumentiert, welche der beiden Eingabe-Varianten den
  Minutenwert geliefert hat (`minuten` oder `start_ende`) — Transparenz für
  die spätere Prüfung, kein Rechenwert.
- Jeder Zahlen-/Datumswert stammt aus `executor.py`, nie vom Modell (P3).

## Modus 2 (Provenienz-Gate) — Eingabe

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/taetigkeitstext-rvg/executor.py \
  --pruefe-text <entwurf.md> --report <report.json> [--output <pruef-report.json>]
```

| Flag | Pflicht | Bedeutung |
|---|---|---|
| `--pruefe-text` | ja | Der von Claude formulierte Leistungsnachweis-Text (Markdown/Text). |
| `--report` | ja | Der Report aus Modus 1. Muss `meta.erzeugt_von` mit `taetigkeitstext-rvg/executor.py` tragen — ein modellgenerierter oder fremder Report wird abgelehnt (Exit 2, P3). |
| `--output` | nein | Zieldatei für den Prüf-Report (Default: stdout). |

### Geprüfte Werte und Normalisierung

- **Minuten/Stunden** — erkannt werden Zahlen mit den Einheiten `Minuten`/
  `Minute`/`Min.` sowie `Stunden`/`Stunde`/`Std.` (deutsches Dezimalkomma,
  z. B. `1,5 Stunden`). Stunden werden auf Minuten normalisiert
  (`1,5 Stunden` ≡ `90 Minuten`); ergibt die Umrechnung keine ganze
  Minutenzahl, gilt der Wert als nicht normalisierbar und damit als Befund.
  Geprüft wird gegen **alle** Minutenwerte im Report: `minuten` und
  `minuten_getaktet` je Eintrag (auch `ohne_az`), `summen.je_az`,
  `summen.je_az_und_datum` sowie `zusammenfassung.minuten_gesamt` /
  `minuten_gesamt_getaktet`.
- **Daten** — ISO (`JJJJ-MM-TT`) und deutsches Format (`TT.MM.JJJJ`) werden
  erkannt und auf ISO kanonisiert; geprüft gegen `datum` aus allen
  Einträgen (inkl. `ohne_az`) und `summen.je_az_und_datum`.
- **Aktenzeichen** — Heuristik-Muster `Ziffern/Jahr` (z. B. `12/2026`, die
  Repo-Konvention des `az`-Felds); geprüft gegen die `az`-Werte der
  Einträge **mit** Aktenzeichen. Andere Kanzlei-Aktenzeichen-Formate
  (z. B. Gerichts-Aktenzeichen wie „12 O 345/26") erkennt dieses Muster
  nicht — dokumentierte Grenze, siehe [SKILL.md](../SKILL.md) „Grenzen".

### Ausgabe: Prüf-Report

Vollständiges Beispiel: [`beispiel-pruef-report.json`](beispiel-pruef-report.json)
(erzeugt aus [`beispiel-entwurf.md`](beispiel-entwurf.md) gegen
[`beispiel-report.json`](beispiel-report.json)). Struktur:

```json
{
  "meta": { "erzeugt_von": "…", "text_datei": "…", "report_datei": "…", "deterministik": "…" },
  "gefundene_werte": {
    "minuten": [ { "roh": "47 Minuten", "normalisiert": 47, "typ": "minuten", "status": "belegt|fremd" } ],
    "daten": [ { "roh": "01.07.2026", "normalisiert": "2026-07-01", "status": "belegt|fremd" } ],
    "aktenzeichen": [ { "roh": "12/2026", "status": "belegt|fremd" } ]
  },
  "befunde": [ { "typ": "fremde_zahl|fremdes_datum|fremdes_aktenzeichen", "roh": "…", "hinweis": "…" } ],
  "zusammenfassung": { "anzahl_gefunden": 14, "anzahl_befunde": 0 },
  "ergebnis": "sauber | abweichend"
}
```

Exit-Codes Modus 2: `0` = `ergebnis: "sauber"` (keine Befunde), `1` =
mindestens ein Befund, `2` = Eingabefehler (Datei fehlt, kaputtes JSON,
Report ist kein gültiger Executor-Report).

## Bewusste Grenzen

- **Aktenzeichen-Erkennung ist eine Heuristik** (`Ziffern/Jahr`) — kein
  vollständiger Parser für alle denkbaren Kanzlei- oder Gerichts-
  Aktenzeichen-Formate.
- **Zahlen ohne Zeiteinheit werden nicht geprüft** — nur explizit als
  Minuten/Stunden gekennzeichnete Zahlen sind Gegenstand des Provenienz-
  Gates (bewusst eng, um Falschtreffer auf andere Zahlen im Text zu
  vermeiden).
- **`belegt` ist ein Vorkommens-, kein Richtigkeitsnachweis**: das Gate
  prüft, ob ein Zahlen-/Datums-/Az-Wert im Report existiert — nicht, ob er
  zum richtigen Absatz oder zur richtigen Tätigkeit gehört. Diese Zuordnung
  bleibt beim Modell und bei der Kanzlei-Abnahme vor Rechnungsstellung.
