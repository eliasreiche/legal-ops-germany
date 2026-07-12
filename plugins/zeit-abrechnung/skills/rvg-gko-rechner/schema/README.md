# Schema — rvg-gko-rechner

Datei-Kontrakt (P2) für den Executor
[`core/calc/rvg/executor.py`](../../../../../core/calc/rvg/executor.py).
Kein Netzwerkzugriff, keine Datenbank — JSON-Datei rein, JSON-Report raus.

## Eingabe: RVG-/GKG-Anfrage (JSON, `--input`)

Die Anfrage trägt zwei unabhängige, optionale Blöcke — **mindestens einer**
ist Pflicht:

```json
{
  "rvg": { "...": "Anwaltsvergütung, siehe unten" },
  "gkg": { "...": "Gerichtskosten, siehe unten" }
}
```

RVG- und GKG-Beträge werden **nicht** automatisch addiert (unterschiedliche
Forderungen, unterschiedliche Kostenschuldner — Anwaltshonorar vs.
Gerichtskasse).

### Block `rvg`

Volle Form mit **Angelegenheiten-Gruppierung** (außergerichtliche Vertretung
und gerichtliches Verfahren sind verschiedene Angelegenheiten, §§ 16 ff. RVG
— je Angelegenheit fallen eine **eigene** Auslagenpauschale Nr. 7002 und eine
**eigene** USt-Basis an):

```json
{
  "auftragsdatum": "2026-03-01",
  "streitwert": "10000.00",
  "angelegenheiten": [
    {
      "bezeichnung": "Außergerichtliche Vertretung",
      "tatbestaende": [{"nr": "2300", "satz": "1.3"}]
    },
    {
      "bezeichnung": "Rechtsstreit erster Instanz",
      "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]
    }
  ],
  "anrechnung_2300_auf_3100": true,
  "auslagenpauschale": true,
  "umsatzsteuer": true
}
```

Kurzform für genau **eine** Angelegenheit (`tatbestaende` flach statt
`angelegenheiten` — nie beide Felder zugleich):

```json
{
  "auftragsdatum": "2026-03-01",
  "streitwert": "5000.00",
  "tatbestaende": [
    {"nr": "3100"},
    {"nr": "3104"},
    {"nr": "1000"}
  ]
}
```

| Feld | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `auftragsdatum` | **ja** | ISO-Datum `JJJJ-MM-TT` | Stichtag für die Tabellenstand-Wahl: Zeitpunkt der Erteilung des unbedingten Auftrags (§ 60 Abs. 1 RVG). |
| `streitwert` | **ja** | Dezimalstring, z. B. `"5000.00"`, oder ganze Zahl | Gegenstandswert (gilt für alle Angelegenheiten der Anfrage). **Kein JSON-`float`** — float-Rundungsfehler (0,1+0,2-Falle) sind bei Geldbeträgen ein Haftungsrisiko, der Executor lehnt float strikt ab. Werte über 30 Mio. € werden nach § 22 Abs. 2 Satz 1 RVG **gekappt** (Rechenketten-Zeile + Warnung + `wertkappung`-Block im Report); in Kombination mit Nr. 1008 wird stattdessen abgelehnt (§ 22 Abs. 2 Satz 2 RVG nicht modelliert, siehe „Bewusste Grenzen"). |
| `angelegenheiten` | entweder dies … | Liste von Objekten `{"bezeichnung", "tatbestaende", optional "auslagenpauschale"/"umsatzsteuer"}` | Volle Form; je Angelegenheit eigene Gebühren, eigene 7002-Pauschale (je 20 %, max. je 20 €), eigene USt. |
| `tatbestaende` | … oder dies | Liste von Objekten | Kurzform für genau eine Angelegenheit. **Teil-2- und Teil-3-Tatbestände zusammen sind hier ein Eingabefehler** — dann `angelegenheiten` verwenden. |
| `anrechnung_2300_auf_3100` | nein (Default `false`) | `true`/`false` | Anrechnung der Geschäftsgebühr auf die Verfahrensgebühr (Vorbem. 3 Abs. 4 VV RVG) — verbindet zwei Angelegenheiten; verlangt genau eine `2300` und genau eine `3100` über alle Angelegenheiten hinweg. |
| `auslagenpauschale` | nein (Default `true`) | `true`/`false` | Nr. 7002 VV RVG (20 % der Gebühren, höchstens 20 € — **je Angelegenheit**). Pro Angelegenheit überschreibbar. |
| `umsatzsteuer` | nein (Default `true`) | `true`/`false` | Nr. 7008 VV RVG (19 % — Basis **je Angelegenheit**). Pro Angelegenheit überschreibbar. |

#### Gebührentatbestands-Katalog (RVG, `vv-katalog.json`)

Nur Wertgebühren in Zivilsachen — Katalog liegt als Datendatei bei
[`core/calc/rvg/vv-katalog.json`](../../../../../core/calc/rvg/vv-katalog.json):

| Nr. | VV-Teil | Bezeichnung | Art | Satz | Zusatzfelder in `tatbestaende` |
|---|---|---|---|---|---|
| `2300` | 2 (außergerichtlich) | Geschäftsgebühr | Satzrahmen 0,5–2,5 | **Pflichtangabe** `satz` (keine stille Annahme des Regelsatzes 1,3) | `"satz": "1.3"` |
| `3100` | 3 (gerichtlich) | Verfahrensgebühr | Festsatz | 1,3 | — (gesetzlich fix, `satz` darf nicht überschrieben werden) |
| `3104` | 3 (gerichtlich) | Terminsgebühr | Festsatz | 1,2 | — |
| `1000` | 1 (allgemein) | Einigungsgebühr | Festsatz | 1,5 | — |
| `1003` | 1 (allgemein) | Einigungsgebühr bei anhängiger Sache | Festsatz | 1,0 | — |
| `1008` | 1 (allgemein) | Erhöhungsgebühr für weitere Auftraggeber | Erhöhung | 0,3 je weiterem Auftraggeber, gekappt auf Gebührensatz 2,0 | `"erhoeht_position": "3100"` (oder `"2300"`), `"weitere_auftraggeber": 1` |

**Teil-Kollisionsregel:** Teil-2- (`2300`) und Teil-3-Tatbestände
(`3100`/`3104`) in **derselben** Angelegenheit sind ein Eingabefehler —
außergerichtliche Vertretung und gerichtliches Verfahren sind verschiedene
Angelegenheiten. Teil-1-Gebühren entstehen neben den Gebühren der anderen
Teile (Vorbem. 1 VV RVG) und dürfen in jeder Angelegenheit stehen.

`7002` (Auslagenpauschale) und `7008` (Umsatzsteuer) sind **keine**
`tatbestaende`-Einträge — sie werden über die Flags `auslagenpauschale` /
`umsatzsteuer` gesteuert (je Angelegenheit angewendet).

**Scope-Grenze (bewusst):** Betragsrahmengebühren (Straf-/Sozialrecht),
PKH-Vergütung (§ 49 RVG) und Beratungshilfe sind nicht im Katalog. Eine
unbekannte oder außerhalb des Scopes liegende Nr. führt zu Exit 2 mit
Begründung — nie zu einem geratenen Betrag.

### Block `gkg`

```json
{
  "verfahrenseinleitungsdatum": "2026-03-01",
  "streitwert": "5000.00",
  "positionen": [
    {"nr": "1210"}
  ]
}
```

| Feld | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `verfahrenseinleitungsdatum` | **ja** | ISO-Datum `JJJJ-MM-TT` | Stichtag für die Tabellenstand-Wahl: Zeitpunkt, zu dem die Rechtsstreitigkeit anhängig geworden ist (§ 71 Abs. 1 GKG) — **nicht** das Auftragsdatum wie beim RVG-Block. |
| `streitwert` | **ja** | Dezimalstring oder ganze Zahl | Streitwert. Werte über 30.000.000 € werden nach § 39 Abs. 2 GKG **gekappt** (Kappungsgrenze, keine Zulässigkeitsgrenze) — mit Rechenketten-Zeile, Warnung und `wertkappung`-Block im Report. |
| `positionen` | **ja** | Liste von Objekten `{"nr": "1210"}` | Siehe [KV-GKG-Katalog](#gebührentatbestands-katalog-gkg-kv-katalogjson) unten. |

#### Gebührentatbestands-Katalog (GKG, `kv-katalog.json`)

Katalog liegt bei
[`core/calc/gkg/kv-katalog.json`](../../../../../core/calc/gkg/kv-katalog.json):

| Nr. | Bezeichnung | Satz | Hinweis |
|---|---|---|---|
| `1100` | Mahnverfahren (Antrag auf Mahnbescheid/Europ. Zahlungsbefehl) | 0,5 | Eigener, versionierter Mindestbetrag (36 € / 38 €, siehe unten) statt der allgemeinen 15-€-Mindestgebühr. |
| `1210` | Verfahren im Allgemeinen, 1. Rechtszug | 3,0 | Schließt sich mit `1211` aus. |
| `1211` | Ermäßigung von `1210` (früher Verfahrensabschluss) | 1,0 | — |
| `1220` | Berufung, Verfahren im Allgemeinen | 4,0 | Schließt sich mit `1222` aus. |
| `1222` | Ermäßigung von `1220` | 2,0 | — |

Gerichtsgebühren sind nicht umsatzsteuerpflichtig — der GKG-Block kennt keine
7002-/7008-Entsprechung.

## Tabellenstände (versioniert)

Beide Rechner unterstützen zwei Gültigkeitszeiträume, jeweils mit
Gesetzesfundstelle (siehe `core/calc/rvg/gebuehrentabelle.json` bzw.
`core/calc/gkg/gebuehrentabelle.json`):

| Stand-id | Gültig | Rechtsgrundlage |
|---|---|---|
| `kostraeg_2021` | 01.01.2021 – 31.05.2025 | KostRÄG 2021 |
| `kostbraeg_2025` | ab 01.06.2025 | KostBRÄG 2025 |

Für einen Stichtag vor dem 01.01.2021 gibt es keinen hinterlegten Stand —
Exit 2 statt eines geratenen Betrags. Der Report weist unter
`rvg.tabellenstand` / `gkg.tabellenstand` immer aus, welcher Stand
tatsächlich angewendet wurde.

**Wichtig:** RVG (§ 60 Abs. 1 RVG: Auftragserteilung) und GKG (§ 71 Abs. 1
GKG: Anhängigkeit) haben **unterschiedliche** Stichtagsregeln — deshalb zwei
getrennte Datumsfelder (`auftragsdatum` vs. `verfahrenseinleitungsdatum`),
die in ein und derselben Anfrage auf unterschiedliche Tabellenstände zeigen
können (z. B. Auftrag im Mai 2025, Klageeinreichung erst im Juni 2025).

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(erzeugt aus [`beispiel-eingabe.json`](beispiel-eingabe.json)). Ein zweites
Beispiel mit zwei Angelegenheiten, Anrechnung und Erhöhungsgebühr:
[`beispiel-eingabe-anrechnung.json`](beispiel-eingabe-anrechnung.json).

Struktur je Block (`rvg`/`gkg`, sofern angefragt):

```json
{
  "meta": { "erzeugt_von": "core/calc/rvg/executor.py",
            "deterministik": "…", "hinweis_getrennte_kostenarten": "…" },
  "rvg": {
    "eingabe": { "…normalisierte Eingabe…": "…" },
    "tabellenstand": { "id": "kostbraeg_2025", "bezeichnung": "…",
                       "gueltig_ab": "…", "gueltig_bis": null, "fundstelle": "…" },
    "wertkappung": null,
    "einfachgebuehr": "652.00",
    "angelegenheiten": [
      {
        "bezeichnung": "Rechtsstreit erster Instanz",
        "positionen": [
          { "nr": "3100", "bezeichnung": "…", "norm": "Nr. 3100 VV RVG",
            "satz": "1.3", "betrag": "847.60",
            "mindestbetrag_gegriffen": false, "hinweise": [],
            "quelle": "executor" }
        ],
        "ergebnis": { "zwischensumme_gebuehren": "…",
                      "auslagenpauschale": "…", "netto": "…",
                      "ust_satz": "0.19", "ust": "…", "gesamt": "…",
                      "quelle": "executor" }
      }
    ],
    "anrechnung": null,
    "rechenkette": [
      { "schritt": 1, "norm": "§ 60 Abs. 1 RVG", "beschreibung": "…",
        "ergebnis": "kostbraeg_2025", "quelle": "executor" }
    ],
    "ergebnis": { "gesamt_verguetung": "…", "gesamt_hinweis": "…",
                  "quelle": "executor" },
    "warnungen": []
  },
  "gkg": { "…analog: positionen flach, ergebnis.gesamt, wertkappung, ohne Auslagenpauschale/USt…": "…" }
}
```

- **`angelegenheiten`** (nur RVG): je Angelegenheit ein Block mit eigenen
  Positionen, eigener Auslagenpauschale (Nr. 7002, je max. 20 €), eigener
  USt-Basis und eigenem `gesamt`. `ergebnis.gesamt_verguetung` ist die Summe
  über die Angelegenheiten (gleicher Gläubiger — die Angelegenheiten bleiben
  gebührenrechtlich getrennt, nur die Vergütungsforderung wird addiert).
- **`wertkappung`**: gefüllt, wenn der Wert nach § 22 Abs. 2 Satz 1 RVG bzw.
  § 39 Abs. 2 GKG auf 30 Mio. € gekappt wurde (`streitwert_eingabe`,
  `streitwert_angewendet`, `norm`) — zusätzlich als Rechenketten-Zeile und
  Warnung ausgewiesen; sonst `null`.
- **`rechenkette`** ist die nachvollziehbare Herleitung: ggf. Wert-Kappung,
  Tabellenstand-Wahl, 1,0-Gebühr, je Position ein Schritt, ggf. Anrechnung,
  je Angelegenheit Zwischensumme/7002/Netto/USt/Gesamt, ggf.
  Gesamtvergütung — jeder Schritt mit `quelle: "executor"` (P3).
- **`positionen[].mindestbetrag_gegriffen`**: `true`, wenn der berechnete
  Betrag unter dem gesetzlichen Mindestbetrag lag und auf diesen angehoben
  wurde (§ 13 Abs. 3 RVG / § 34 Abs. 2 GKG bzw. KV 1100).
- **Alle Geldbeträge sind Dezimalstrings** (z. B. `"847.60"`), niemals
  JSON-Zahlen — vermeidet Float-Rundungsfehler beim Weiterverarbeiten.

## Bewusste Grenzen

- **Nur Wertgebühren (Zivil).** Betragsrahmengebühren, PKH-Vergütung,
  Beratungshilfe: nicht unterstützt, siehe oben.
- **§ 22 Abs. 2 Satz 2 RVG nicht modelliert**: Sind mehrere Personen wegen
  verschiedener Gegenstände Auftraggeber, gilt die 30-Mio-Grenze je Person
  (insgesamt höchstens 100 Mio. €). Die Kombination Erhöhungsgebühr Nr. 1008
  + Gegenstandswert über 30 Mio. € wird deshalb abgelehnt (Exit 2) statt
  möglicherweise falsch auf 30 Mio. € gekappt — anwaltlich prüfen, Werte je
  Auftraggeber getrennt ansetzen.
- **Keine automatische Gesamtsumme über RVG und GKG** — unterschiedliche
  Kostenschuldner, siehe `meta.hinweis_getrennte_kostenarten`.
- **Keine Kostenverteilung** (§ 91 ff. ZPO, Kostenquote): der Rechner
  ermittelt die Höhe der Gebühren, nicht, wer sie im Ergebnis trägt.
- **Anrechnung nur bei identischem Streitwert**: Weichen die
  Gegenstandswerte von Geschäfts- und Verfahrensgebühr voneinander ab (z. B.
  nur teilweise identischer Gegenstand), rechnet dieser Executor nicht —
  anwaltliche Schätzung nach § 14 Abs. 1 RVG bleibt Kanzleisache.
- **§ 14 RVG-Ermessen für die Geschäftsgebühr** (Nr. 2300, Satz zwischen 0,5
  und 2,5): Der Executor verlangt den Satz als Eingabe und weist bei Satz
  > 1,3 nur auf die Begründungspflicht hin — er trifft die
  Billigkeitsentscheidung nicht selbst.
