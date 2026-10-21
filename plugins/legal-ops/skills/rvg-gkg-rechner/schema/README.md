# Schema — rvg-gkg-rechner

Datei-Kontrakt (P2) für den Executor
[`core/calc/rvg/executor.py`](../../../core/calc/rvg/executor.py).
Kein Netzwerkzugriff, keine Datenbank — JSON-Datei rein, JSON-Report raus.

## Eingabe: RVG-/GKG-/FamGKG-Anfrage (JSON, `--input`)

Die Anfrage trägt bis zu drei optionale Blöcke — **mindestens einer** ist
Pflicht, `gkg` und `famgkg` schließen sich aus (ein Verfahren läuft entweder
nach dem GKG oder, als Familiensache, nach dem FamGKG; beide zugleich: Exit 2):

```json
{
  "rvg": { "...": "Anwaltsvergütung, siehe unten" },
  "gkg": { "...": "Gerichtskosten Zivilsachen, siehe unten" },
  "famgkg": { "...": "Gerichtskosten Familiensachen, siehe unten" }
}
```

Anwaltsvergütung und Gerichtskosten werden **nicht** automatisch addiert
(unterschiedliche Forderungen, unterschiedliche Kostenschuldner —
Anwaltshonorar vs. Gerichtskasse).

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
| `streitwert` | **ja** | Dezimalstring, z. B. `"5000.00"`, oder ganze Zahl — oder der Literal-String `"famgkg.verfahrenswert"` (Querverweis, siehe Block `famgkg`) | Gegenstandswert (gilt für jeden Tatbestand ohne eigenen `gegenstandswert`). **Kein JSON-`float`** — float-Rundungsfehler (0,1+0,2-Falle) sind bei Geldbeträgen ein Haftungsrisiko, der Executor lehnt float strikt ab. Werte über 30 Mio. € werden nach § 22 Abs. 2 Satz 1 RVG **gekappt** (Rechenketten-Zeile + Warnung + `wertkappung`-Block im Report); in Kombination mit Nr. 1008 wird stattdessen abgelehnt (§ 22 Abs. 2 Satz 2 RVG nicht modelliert, siehe „Bewusste Grenzen"). |
| `angelegenheiten` | entweder dies … | Liste von Objekten `{"bezeichnung", "tatbestaende", optional "auslagenpauschale"/"umsatzsteuer"}` | Volle Form; je Angelegenheit eigene Gebühren, eigene 7002-Pauschale (je 20 %, max. je 20 €), eigene USt. |
| `tatbestaende` | … oder dies | Liste von Objekten | Kurzform für genau eine Angelegenheit. **Teil-2- und Teil-3-Tatbestände zusammen sind hier ein Eingabefehler** — dann `angelegenheiten` verwenden. |
| `tatbestaende[].gegenstandswert` | nein | Dezimalstring | **Teilwert** dieses Tatbestands (z. B. Mehrwert eines Vergleichs); ohne Angabe gilt `streitwert`. Nicht bei `1008` (folgt der Basis-Position). Erlaubte Keys je Tatbestand: `nr`, `satz`, `gegenstandswert`, `erhoeht_position`, `weitere_auftraggeber` — jeder andere ist Exit 2. |
| `anrechnung_2300_auf_3100` | nein (Default `false`) | `true`/`false` | Anrechnung der Geschäftsgebühr auf die Verfahrensgebühr (Vorbem. 3 Abs. 4 VV RVG) — verbindet zwei Angelegenheiten; verlangt genau eine `2300` und genau eine `3100` über alle Angelegenheiten hinweg. |
| `auslagenpauschale` | nein (Default `true`) | `true`/`false` | Nr. 7002 VV RVG (20 % der Gebühren, höchstens 20 € — **je Angelegenheit**). Pro Angelegenheit überschreibbar. |
| `umsatzsteuer` | nein (Default `true`) | `true`/`false` | Nr. 7008 VV RVG (19 % — Basis **je Angelegenheit**). Pro Angelegenheit überschreibbar. |

#### Gebührentatbestands-Katalog (RVG, `vv-katalog.json`)

Nur Wertgebühren in Zivilsachen — Katalog liegt als Datendatei bei
[`core/calc/rvg/vv-katalog.json`](../../../core/calc/rvg/vv-katalog.json):

| Nr. | VV-Teil | Instanz | Bezeichnung | Art | Satz | Zusatzfelder in `tatbestaende` |
|---|---|---|---|---|---|---|
| `2300` | 2 (außergerichtlich) | — | Geschäftsgebühr | Satzrahmen 0,5–2,5 | **Pflichtangabe** `satz` (keine stille Annahme des Regelsatzes 1,3) | `"satz": "1.3"` |
| `3100` | 3 (gerichtlich) | 1 | Verfahrensgebühr (erster Rechtszug) | Festsatz | 1,3 | — (gesetzlich fix, `satz` darf nicht überschrieben werden) |
| `3101` | 3 (gerichtlich) | 1 | Verfahrensgebühr (erster Rechtszug), ermäßigt — u. a. Nr. 2: Einigung/Verhandlung über nicht rechtshängige Ansprüche | Festsatz | 0,8 | `gegenstandswert` (Wertteil); neben `3100` in derselben Angelegenheit → § 15 Abs. 3 RVG |
| `3104` | 3 (gerichtlich) | 1 | Terminsgebühr (erster Rechtszug) | Festsatz | 1,2 | — |
| `3200` | 3 (gerichtlich) | berufung | Verfahrensgebühr (Berufung) | Festsatz | 1,6 | — |
| `3201` | 3 (gerichtlich) | berufung | Verfahrensgebühr (Berufung), ermäßigt bei vorzeitiger Beendigung | Festsatz | 1,1 | — (alternativ zu 3200, nie kumulativ) |
| `3202` | 3 (gerichtlich) | berufung | Terminsgebühr (Berufung) | Festsatz | 1,2 | — |
| `3206` | 3 (gerichtlich) | revision | Verfahrensgebühr (Revision, ohne BGH-Vertretungszwang) | Festsatz | 1,6 | — |
| `3207` | 3 (gerichtlich) | revision | Verfahrensgebühr (Revision), ermäßigt | Festsatz | 1,1 | — (alternativ zu 3206) |
| `3208` | 3 (gerichtlich) | revision | Verfahrensgebühr (Revision), BGH-Vertretungszwang (Zivilrevision, § 78 Abs. 1 S. 3 ZPO) | Festsatz | 2,3 | — (statt 3206) |
| `3209` | 3 (gerichtlich) | revision | Verfahrensgebühr (Revision, BGH), ermäßigt | Festsatz | 1,8 | — (alternativ zu 3208) |
| `3210` | 3 (gerichtlich) | revision | Terminsgebühr (Revision) | Festsatz | 1,5 | — |
| `1000` | 1 (allgemein) | — | Einigungsgebühr | Festsatz | 1,5 | — |
| `1003` | 1 (allgemein) | — | Einigungsgebühr bei anhängiger Sache | Festsatz | 1,0 | — |
| `1004` | 1 (allgemein) | — | Einigungsgebühr im Berufungs-/Revisionsverfahren | Festsatz | 1,3 | — (**nur** in einer Angelegenheit mit einem Berufungs-/Revisions-Tatbestand) |
| `1008` | 1 (allgemein) | — | Erhöhungsgebühr für weitere Auftraggeber | Erhöhung | 0,3 je weiterem Auftraggeber, gekappt auf Gebührensatz 2,0 | `"erhoeht_position": "3100"` (auch `"3200"`, `"3206"`, `"3208"` oder `"2300"`), `"weitere_auftraggeber": 1` |

Alle Sätze der Berufungs-/Revisions-Positionen sowie Nr. 1004 sind am
2026-07-17 gegen gesetze-im-internet.de/rvg/anlage_1.html web-verifiziert
(Fundstelle je Eintrag im Katalog `vv-katalog.json`, Feld `quelle_hinweis`).

**§ 15 Abs. 3 RVG (verschiedene Sätze für Teile des Gegenstands):** Positionen
mit derselben `gruppe_15_abs_3` im Katalog — Verfahrensgebühr `3100`/`3101`,
Einigungsgebühr `1000`/`1003`/`1004` — dürfen in einer Angelegenheit
zusammen stehen, wenn **jede** ihren Wertteil als `gegenstandswert` trägt
(sonst Exit 2). Der Executor rechnet die Einzelgebühren und kappt ihre Summe
auf höchster Satz × 1,0-Gebühr aus der Summe der Wertteile — als eigene
Rechenketten-Zeile und im Block `kappungen_15_abs_3` der Angelegenheit, auch
wenn die Kappung nicht greift. Nr. `1008` auf eine so zusammengefasste
Position ist nicht modelliert (Exit 2).

**Teil-Kollisionsregel:** Teil-2- (`2300`) und Teil-3-Tatbestände
(`3100`/`3104`/`3200` ff.) in **derselben** Angelegenheit sind ein
Eingabefehler — außergerichtliche Vertretung und gerichtliches Verfahren sind
verschiedene Angelegenheiten. Teil-1-Gebühren entstehen neben den Gebühren der
anderen Teile (Vorbem. 1 VV RVG) und dürfen in jeder Angelegenheit stehen.

**Instanz-Kollisionsregel:** Teil-3-Tatbestände **verschiedener Instanzen**
(erste Instanz `3100`/`3104`, Berufung `3200`–`3202`, Revision `3206`–`3210`)
in **derselben** Angelegenheit sind ein Eingabefehler — jeder Rechtszug ist
eine eigene Angelegenheit (§ 17 Nr. 1 RVG) mit je eigener Auslagenpauschale
Nr. 7002 und eigener USt-Basis. Positionen **derselben** Instanz
(Verfahrens- + Terminsgebühr) sind zulässig. Mehrere Instanzen daher in
**getrennte** `angelegenheiten` legen. Die Einigungsgebühr **`1004`** (erhöhter
Satz) ist nur in einer Angelegenheit mit einem Berufungs-/Revisions-Tatbestand
zulässig — sonst greift `1000` (1,5) bzw. `1003` (1,0).

**Anrechnung nur auf den ersten Rechtszug:** `anrechnung_2300_auf_3100` rechnet
die Geschäftsgebühr ausschließlich auf die Verfahrensgebühr des **ersten**
Rechtszugs (`3100`) an (Vorbem. 3 Abs. 4 VV RVG, nach BGH der erste
Rechtszug), nie auf `3200`/`3206`/`3208`. Eine Anrechnungs-Anforderung ohne
`3100`, aber mit einer höherinstanzlichen Verfahrensgebühr, ist ein
Eingabefehler.

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

Mahnbescheid → Widerspruch → streitiges Verfahren (mit Anrechnung):

```json
{
  "verfahrenseinleitungsdatum": "2026-03-01",
  "streitwert": "10000.00",
  "positionen": [{"nr": "1100"}, {"nr": "1210"}],
  "anrechnung_1100_auf_1210": true
}
```

| Feld | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `verfahrenseinleitungsdatum` | **ja** | ISO-Datum `JJJJ-MM-TT` | Stichtag für die Tabellenstand-Wahl: Zeitpunkt, zu dem die Rechtsstreitigkeit anhängig geworden ist (§ 71 Abs. 1 GKG) — **nicht** das Auftragsdatum wie beim RVG-Block. |
| `streitwert` | **ja** | Dezimalstring oder ganze Zahl | Streitwert. Werte über 30.000.000 € werden nach § 39 Abs. 2 GKG **gekappt** (Kappungsgrenze, keine Zulässigkeitsgrenze) — mit Rechenketten-Zeile, Warnung und `wertkappung`-Block im Report. |
| `positionen` | **ja** | Liste von Objekten `{"nr": "1210"}`, optional `"gegenstandswert"` (Teilwert; Pflicht bei `1900`) | Siehe [KV-GKG-Katalog](#gebührentatbestands-katalog-gkg-kv-katalogjson) unten. Andere Keys: Exit 2. |
| `anrechnung_1100_auf_1210` | nein (Default `false`) | `true`/`false` | Anrechnung der Mahnverfahrensgebühr auf die Gebühr für das Verfahren im Allgemeinen beim Übergang in das streitige Verfahren (Anmerkung Abs. 1 zu KV 1210 GKG) — verlangt `1100` **und** `1210` in `positionen`. |

**Anrechnung KV 1100 → KV 1210 (Übergang aus dem Mahnverfahren):** Nach der
Anmerkung Abs. 1 zu KV 1210 GKG (Anlage 1 GKG, Teil 1 Hauptabschnitt 2
Abschnitt 1 Unterabschnitt 1) gilt: „Soweit wegen desselben Streitgegenstands
ein Mahnverfahren vorausgegangen ist, entsteht die Gebühr mit dem Eingang der
Akten bei dem Gericht, an das der Rechtsstreit nach Erhebung des Widerspruchs
oder Einlegung des Einspruchs abgegeben wird; in diesem Fall wird eine Gebühr
1100 nach dem Wert des Streitgegenstands angerechnet, der in das
Prozessverfahren übergegangen ist." Die Norm ordnet eine **Anrechnung** an,
keine Ermäßigung des Gebührensatzes: der Satz 3,0 von KV 1210 bleibt
unverändert, abgezogen wird der **Betrag** der Gebühr KV 1100 (inklusive
deren Mindestbetrags-Floor). Bei vollständigem Übergang bleibt damit
wirtschaftlich genau die 3,0-Gebühr als Summe beider Positionen stehen.
Der Executor rechnet das nur auf ausdrückliche Anforderung
(`anrechnung_1100_auf_1210: true`), nie automatisch — ob derselbe
Streitgegenstand vorausgegangen ist, ist keine Rechenfrage. Fehlt eine der
beiden Positionen, ist das ein Eingabefehler (Exit 2). Ist nur ein **Teil**
des Streitgegenstands übergegangen, rechnet der Executor die Anrechnung
**nicht** (siehe „Bewusste Grenzen"). KV 1211 (Ermäßigung) ist von der
Mechanik nicht erfasst.

**Strikte Key-Prüfung (alle Blöcke):** Ein in `rvg`, `gkg` oder `famgkg` nicht
vorgesehener Key ist ein Eingabefehler mit Exit 2 und Nennung des Keys — nie
ein stilles Ignorieren. Sonst liefe ein Tippfehler wie
`"anrechnung_1100_1210"` als *nicht* angeforderte Anrechnung durch und der
Report wiese einen zu hohen Betrag aus.

#### Gebührentatbestands-Katalog (GKG, `kv-katalog.json`)

Katalog liegt bei
[`core/calc/gkg/kv-katalog.json`](../../../core/calc/gkg/kv-katalog.json):

| Nr. | Bezeichnung | Satz | Hinweis |
|---|---|---|---|
| `1100` | Mahnverfahren (Antrag auf Mahnbescheid/Europ. Zahlungsbefehl) | 0,5 | Eigener, versionierter Mindestbetrag (36 € / 38 €, siehe unten) statt der allgemeinen 15-€-Mindestgebühr. Wird bei Übergang ins streitige Verfahren auf `1210` angerechnet (`anrechnung_1100_auf_1210`). |
| `1210` | Verfahren im Allgemeinen, 1. Rechtszug | 3,0 | Schließt sich mit `1211` aus. |
| `1211` | Ermäßigung von `1210` (früher Verfahrensabschluss) | 1,0 | — |
| `1220` | Berufung, Verfahren im Allgemeinen | 4,0 | Schließt sich mit `1222` aus. |
| `1222` | Ermäßigung von `1220` | 2,0 | — |
| `1230` | Revision, Verfahren im Allgemeinen | 5,0 | Schließt sich mit `1232` aus. |
| `1232` | Ermäßigung von `1230` | 3,0 | — |
| `1900` | Vergleich über nicht gerichtlich anhängige Gegenstände | 0,25 | `gegenstandswert` = Mehrwert (Pflicht). Mit der Gebühr für das Verfahren im Allgemeinen (`1210`/`1211`/`1220`/`1222`/`1230`/`1232`) gilt § 36 Abs. 3 GKG entsprechend (Anm. zu KV 1900): Summe höchstens höchster Satz × 1,0-Gebühr aus der Summe der Wertteile — Rechenketten-Zeile + Block `kappung_36_abs_3`, auch wenn sie nicht greift. Mit mehr als einer solchen Verfahrensgebühr in der Anfrage: Exit 2 (Rechtszug unklar). |

`1230`/`1232` am 2026-07-17 gegen gesetze-im-internet.de/gkg_2004/anlage_1.html
web-verifiziert (Fundstelle je Eintrag im Katalog `kv-katalog.json`).
Ausschlusspaare für dieselbe Instanz: `1210`/`1211`, `1220`/`1222`,
`1230`/`1232` — je nur eine der beiden Positionen angeben.

Gerichtsgebühren sind nicht umsatzsteuerpflichtig — der GKG-Block kennt keine
7002-/7008-Entsprechung.

### Block `famgkg`

Gerichtskosten in Familiensachen nach dem FamGKG — Executor
[`core/calc/famgkg/`](../../../core/calc/famgkg/). Verfahrenswert **direkt**:

```json
{
  "verfahrenseinleitungsdatum": "2026-03-01",
  "verfahrenswert": "15000.00",
  "positionen": [{"nr": "1220"}]
}
```

oder **ermittelt** (Scheidung im Verbund, § 44 FamGKG):

```json
{
  "verfahrenseinleitungsdatum": "2026-03-01",
  "verfahrenswert_ermittlung": {
    "ehesache": {"nettoeinkommen_monatlich": ["2800.00", "1700.00"]},
    "folgesachen": [
      {"art": "versorgungsausgleich", "anzahl_anrechte": 3},
      {"art": "kindesunterhalt", "monatsbetrag": "480.00"},
      {"art": "kindschaftssache", "gegenstand": "sorge"}
    ]
  },
  "positionen": [{"nr": "1110"}]
}
```

Selbständige Familiensache(n) statt Verbund:
`"verfahrenswert_ermittlung": {"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "umgang"}]}`.

| Feld | Pflicht | Format | Bedeutung |
|---|---|---|---|
| `verfahrenseinleitungsdatum` | **ja** | ISO-Datum `JJJJ-MM-TT` | Stichtag für Tabellenstand **und** versionierte Wertvorschriften: Tag, an dem das Verfahren anhängig geworden oder eingeleitet worden ist (§ 63 Abs. 1 Satz 1 FamGKG); bei einem Rechtsmittel der Tag seiner Einlegung (Satz 2) — liegt der in einem anderen Stand als die erste Instanz, Beschwerde in einer eigenen Anfrage rechnen. |
| `verfahrenswert` | entweder dies … | Dezimalstring oder ganze Zahl | Verfahrenswert direkt (z. B. vom Gericht festgesetzt oder für nicht modellierte Familiensachen). Im Report `quelle: "eingabe"`. |
| `verfahrenswert_ermittlung` | … oder dies | Objekt, siehe unten | Ermittlung nach §§ 33 ff. FamGKG. Nie beides, nie keines (Exit 2). |
| `positionen` | **ja** | Liste von `{"nr": "1110"}`, optional `"gegenstandswert"` (Pflicht bei `1500`) | Siehe KV-FamGKG-Katalog unten. Andere Keys: Exit 2. |

Werte über 30 Mio. € werden nach § 33 Abs. 2 FamGKG **gekappt**
(Rechenketten-Zeile, Warnung, `wertkappung`-Block), wie beim GKG.

#### Verfahrenswert-Ermittlung (`verfahrenswert_ermittlung`)

Oberste Ebene: **entweder** `ehesache` (Objekt, Verbund) mit optionalen
`folgesachen` (Liste) **oder** `gegenstaende` (nichtleere Liste,
selbständige Familiensachen; mehrere werden nach § 33 Abs. 1 Satz 1 FamGKG
zusammengerechnet); optional `verfahrenswert_festgesetzt` (ersetzt den
Gesamtwert, auch allein zulässig). Jeder unbekannte Key — auf oberster Ebene,
in `ehesache` und in jedem Gegenstand — ist Exit 2 mit Nennung. Geldbeträge
nur als Dezimalstring (oder ganze Zahl), `float` wird abgelehnt.

Die Werte gelten für den Stand nach `verfahrenseinleitungsdatum`
(KostBRÄG 2025 hat nur § 44 Abs. 2 und § 45 Abs. 1 geändert, Daten in
[`core/calc/famgkg/wertvorschriften.json`](../../../core/calc/famgkg/wertvorschriften.json)).

| `art` / Objekt | Felder | Norm | Regel im Executor |
|---|---|---|---|
| `ehesache` (Objekt) | `nettoeinkommen_monatlich` (Liste mit **genau zwei** Dezimalstrings ≥ 0, je Ehegatte das **bereinigte** Monatsnetto), optional `zuschlag` (> 0) + Pflicht-`begruendung` (String), optional `verfahrenswert_festgesetzt` | § 43 FamGKG | 3 × (Netto 1 + Netto 2) (Abs. 2) [+ Zuschlag als Nutzereingabe], dann mindestens 3.000 €, höchstens 1 Mio. € (Abs. 1 Satz 2). Abs. 1 Satz 1 ist Ermessen — Vermögen nur als `zuschlag` (`quelle: "eingabe"`); Abzüge vom Netto (z. B. für Kinder) sind Gerichtspraxis, nicht Gesetz. Mit `verfahrenswert_festgesetzt` kein `zuschlag`; `nettoeinkommen_monatlich` bleibt dann als Basis für den Versorgungsausgleich zulässig. |
| `versorgungsausgleich` | `anzahl_anrechte` (ganze Zahl ≥ 1), optional `ausgleich_nach_scheidung` (Boolean), `nettoeinkommen_monatlich` (nur selbständig; im Verbund verboten — Basis ist die Ehesache) | § 50 Abs. 1 FamGKG | Anrechte × 10 % (bei Ausgleichsansprüchen nach der Scheidung 20 %) × Drei-Monats-Netto beider Ehegatten, insgesamt mindestens 1.000 €. |
| `kindesunterhalt`, `ehegattenunterhalt` | `monatsbetrag` (> 0), optional `anzahl_monate` (1–12, nur wenn insgesamt weniger als zwölf Monatsbeträge gefordert sind), optional `rueckstaende` (≥ 0) | § 51 Abs. 1 Satz 1, Abs. 2 Satz 1 FamGKG | Monate (Default 12) × Monatsbetrag + bei Einreichung fällige Beträge. Dynamisierter Unterhalt: als `monatsbetrag` den Betrag nach dem Mindestunterhalt bei Einreichung eingeben (§ 51 Abs. 1 Satz 2). |
| `kindschaftssache` (selbständig) | `gegenstand`: `sorge`, `umgang`, `auskunft`, `herausgabe` | § 45 Abs. 1 Nr. 1–4, Abs. 2 FamGKG | Festwert 4.000 € (KostRÄG 2021) / 5.000 € (ab 01.06.2025) je Eintrag; mehrere Kinder = ein Gegenstand (Abs. 2) — derselbe `gegenstand` zweimal ist Exit 2. |
| `kindschaftssache` (Folgesache im Verbund) | `gegenstand`: `sorge`, `umgang`, `herausgabe` (§ 137 Abs. 3 FamFG) | § 44 Abs. 2 Satz 1 FamGKG | Erhöhung um 20 % des Ehesachenwerts, höchstens 4.000 € / ab 01.06.2025 5.000 € — je Kindschaftssache; mehrere Kinder = ein Gegenstand. |
| `geldforderung` | `betrag` (> 0) | § 35 FamGKG | Höhe der bezifferten Forderung (z. B. Zugewinnausgleich). |
| `auffangwert` | — | § 42 Abs. 3 FamGKG | 5.000 € — nur wenn keine besondere Wertvorschrift greift und keine genügenden Anhaltspunkte bestehen (Einordnung trifft die Kanzlei). |
| jede `art` | `verfahrenswert_festgesetzt` statt der Berechnungsfelder (bei `kindschaftssache` zusätzlich `gegenstand`) | gerichtliche Festsetzung | Der vom Gericht festgesetzte Wert schlägt die Berechnung (bei der Kindschafts-Folgesache = Erhöhungsbetrag, § 44 Abs. 3). Rechenschritt und Gegenstand `quelle: "eingabe"`. |

Verbund: Gesamt = Ehesache + Erhöhungen der Kindschafts-Folgesachen + Werte
der übrigen Folgesachen (§ 44 Abs. 1, 2 FamGKG; § 33 Abs. 1 Satz 2 nicht
anzuwenden). Die Gerichtsgebühr im Verbund ist KV `1110` aus dem Gesamtwert —
nicht je Folgesache eine eigene Position.

**Querverweis in den RVG-Block:** `"rvg": {"streitwert": "famgkg.verfahrenswert", ...}`
übernimmt den Verfahrenswert des `famgkg`-Blocks (§ 23 Abs. 1 Satz 1 RVG).
Im Report trägt `rvg.eingabe.streitwert` den übernommenen Wert,
`rvg.eingabe.streitwert_herkunft` den Verweis, und `rvg.rechenkette[0]` ist
der Übernahme-Schritt (`quelle` wie die des Verfahrenswerts). Ohne
`famgkg`-Block: Exit 2. Das ist die einzige Kopplung zwischen den Blöcken.

#### Gebührentatbestands-Katalog (FamGKG, `kv-katalog.json`)

Katalog bei [`core/calc/famgkg/kv-katalog.json`](../../../core/calc/famgkg/kv-katalog.json);
alle Sätze am 2026-10-22 gegen gesetze-im-internet.de/famgkg/anlage_1.html
und Wayback-Schnappschüsse der Fassung KostRÄG 2021 web-verifiziert (in
beiden Ständen identisch, Fundstelle je Eintrag im Feld `quelle_hinweis`).
Mindestbetrag jeder Gebühr 15 € (§ 28 Abs. 2 Satz 1 FamGKG).

| Nr. | Bezeichnung | Satz | Schließt sich aus mit |
|---|---|---|---|
| `1110` | Ehesache inkl. aller Folgesachen, 1. Rechtszug | 2,0 | `1111` |
| `1111` | Ermäßigung von `1110` | 0,5 | `1110` |
| `1120` | Ehesache, Beschwerde gegen die Endentscheidung | 3,0 | `1121`, `1122` |
| `1121` | Ermäßigung von `1120` (Rücknahme vor Begründung) | 0,5 | `1120`, `1122` |
| `1122` | Ermäßigung von `1120` (sonstige Beendigung) | 1,0 | `1120`, `1121` |
| `1220` | Selbständige Familienstreitsache, 1. Rechtszug | 3,0 | `1221` |
| `1221` | Ermäßigung von `1220` | 1,0 | `1220` |
| `1222` | Selbständige Familienstreitsache, Beschwerde | 4,0 | `1223`, `1224` |
| `1223` | Ermäßigung von `1222` (Rücknahme vor Begründung) | 1,0 | `1222`, `1224` |
| `1224` | Ermäßigung von `1222` (sonstige Beendigung) | 2,0 | `1222`, `1223` |
| `1310` | Selbständige Kindschaftssache, Verfahren vor dem Familiengericht | 0,5 | — (kein Ermäßigungstatbestand im KV) |
| `1314` | Kindschaftssache, Beschwerde | 1,0 | `1315` |
| `1315` | Ermäßigung von `1314` | 0,5 | `1314` |
| `1320` | Übrige FG-Familiensache (u. a. Abstammung, Ehewohnung/Haushalt, Gewaltschutz, Versorgungsausgleich), 1. Rechtszug | 2,0 | `1321` |
| `1321` | Ermäßigung von `1320` | 0,5 | `1320` |
| `1322` | Übrige FG-Familiensache, Beschwerde | 3,0 | `1323`, `1324` |
| `1323` | Ermäßigung von `1322` (Rücknahme vor Begründung) | 0,5 | `1322`, `1324` |
| `1324` | Ermäßigung von `1322` (sonstige Beendigung) | 1,0 | `1322`, `1323` |
| `1410` | Einstweilige Anordnung in Kindschaftssachen, 1. Rechtszug | 0,3 | — |
| `1420` | Einstweilige Anordnung in den übrigen Familiensachen, 1. Rechtszug | 1,5 | `1421` |
| `1421` | Ermäßigung von `1420` | 0,5 | `1420` |
| `1500` | Vergleich über nicht gerichtlich anhängige Gegenstände | 0,25 | — ; `gegenstandswert` Pflicht; mit der Gebühr für das Verfahren im Allgemeinen gilt § 30 Abs. 3 FamGKG entsprechend (Anm. zu KV 1500) — Block `kappung_30_abs_3`, auch wenn sie nicht greift; mehr als eine Verfahrensgebühr in der Anfrage: Exit 2. |

Nicht im Katalog (Exit 2 mit Begründung): Rechtsbeschwerde und
Sprungrechtsbeschwerde, vereinfachtes Verfahren über den Unterhalt
Minderjähriger (KV 1210 ff. FamGKG), Vormundschaft/Pflegschaft, Beschwerden
im einstweiligen Rechtsschutz, Festgebühren ohne Wertbezug, Vollstreckung,
Verfahrenskostenhilfe, Auslagen (Teil 2).

## Tabellenstände (versioniert)

Alle drei Rechner unterstützen zwei Gültigkeitszeiträume, jeweils mit
Gesetzesfundstelle (siehe `core/calc/rvg/gebuehrentabelle.json`,
`core/calc/gkg/gebuehrentabelle.json` bzw.
`core/calc/famgkg/gebuehrentabelle.json`):

| Stand-id | Gültig | Rechtsgrundlage |
|---|---|---|
| `kostraeg_2021` | 01.01.2021 – 31.05.2025 | KostRÄG 2021 |
| `kostbraeg_2025` | ab 01.06.2025 | KostBRÄG 2025 |

Für einen Stichtag vor dem 01.01.2021 gibt es keinen hinterlegten Stand —
Exit 2 statt eines geratenen Betrags. Der Report weist unter
`rvg.tabellenstand` / `gkg.tabellenstand` / `famgkg.tabellenstand` immer
aus, welcher Stand tatsächlich angewendet wurde. FamGKG: Stichtag nach § 63
Abs. 1 FamGKG (Anhängigkeit/Einleitung, beim Rechtsmittel dessen
Einlegung); derselbe Stand bestimmt die versionierten Wertvorschriften
(§§ 44, 45 FamGKG).

**Wichtig:** RVG (§ 60 Abs. 1 RVG: Auftragserteilung) und GKG (§ 71 Abs. 1
GKG: Anhängigkeit) haben **unterschiedliche** Stichtagsregeln — deshalb zwei
getrennte Datumsfelder (`auftragsdatum` vs. `verfahrenseinleitungsdatum`),
die in ein und derselben Anfrage auf unterschiedliche Tabellenstände zeigen
können (z. B. Auftrag im Mai 2025, Klageeinreichung erst im Juni 2025).

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(erzeugt aus [`beispiel-eingabe.json`](beispiel-eingabe.json)); Familiensache
mit Verfahrenswert-Ermittlung und Querverweis:
[`beispiel-report-familiensache.json`](beispiel-report-familiensache.json)
(erzeugt aus [`beispiel-eingabe-familiensache.json`](beispiel-eingabe-familiensache.json)). Ein zweites
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
  "gkg": { "…analog: positionen flach, anrechnung (KV 1100 -> KV 1210, sonst null), ergebnis.gesamt, wertkappung, ohne Auslagenpauschale/USt…": "…" },
  "famgkg": {
    "eingabe": { "verfahrenseinleitungsdatum": "…", "verfahrenswert": "23310.00",
                 "verfahrenswert_herkunft": "verfahrenswert_ermittlung", "positionen": [] },
    "verfahrenswert": {
      "gesamt": "23310.00", "quelle": "executor", "form": "verbund",
      "wertvorschriften_stand": "kostbraeg_2025",
      "gegenstaende": [
        { "art": "ehesache", "bezeichnung": "…", "norm": "§ 43 FamGKG",
          "wert": "13500.00", "quelle": "executor",
          "rechenschritte": [ { "schritt": 1, "norm": "§ 43 Abs. 2 FamGKG", "…": "…" } ],
          "nutzereingaben": [], "hinweise": [ "…" ] }
      ],
      "rechenkette": [ { "schritt": 1, "norm": "§ 63 Abs. 1 FamGKG", "…": "…" } ],
      "hinweise": []
    },
    "tabellenstand": { "…": "…" }, "wertkappung": null, "einfachgebuehr": "435.50",
    "positionen": [ { "nr": "1110", "satz": "2.0", "betrag": "871.00", "…": "…" } ],
    "rechenkette": [ { "schritt": 1, "norm": "§§ 33 ff. FamGKG", "…": "…" } ],
    "ergebnis": { "gesamt": "871.00", "umsatzsteuerpflichtig": false, "quelle": "executor" },
    "warnungen": []
  }
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
- **Teilwerte**: nutzt die Anfrage `gegenstandswert`, trägt jede Position
  ihren Wert (`positionen[].gegenstandswert`), jede Rechenketten-Zeile nennt
  ihn, und jede weitere Wertstufe bekommt eine eigene 1,0-Gebühr-Zeile.
  `kappungen_15_abs_3` (RVG, je Angelegenheit) bzw. `kappung_36_abs_3`
  (GKG) weisen Summe der Einzelgebühren, Gesamtwert der Wertteile, höchsten
  Satz, Höchstbetrag, `gekappt` und `kuerzung` aus; die Kürzung ist in
  Zwischensumme bzw. `ergebnis.gesamt` bereits abgezogen.
- **`rechenkette`** ist die nachvollziehbare Herleitung: ggf. Wert-Kappung,
  Tabellenstand-Wahl, 1,0-Gebühr, je Position ein Schritt, ggf. Anrechnung,
  je Angelegenheit Zwischensumme/7002/Netto/USt/Gesamt, ggf.
  Gesamtvergütung — jeder Schritt mit `quelle: "executor"` (P3).
- **`positionen[].mindestbetrag_gegriffen`**: `true`, wenn der berechnete
  Betrag unter dem gesetzlichen Mindestbetrag lag und auf diesen angehoben
  wurde (§ 13 Abs. 3 RVG / § 34 Abs. 2 GKG bzw. KV 1100).
- **`famgkg.verfahrenswert`**: `form` ist `verbund`, `selbstaendig`,
  `festgesetzt` (nur Gesamt-Festsetzung) oder `direkt` (Wert als
  `verfahrenswert` eingegeben). `quelle` ist `"eingabe"`, sobald eine
  Nutzereingabe in den Gesamtwert einfließt (Ermessens-Zuschlag,
  festgesetzter Wert, direkte Eingabe) — die betroffenen Gegenstände und
  Rechenschritte tragen ebenfalls `quelle: "eingabe"`, `nutzereingaben`
  nennt Betrag und Begründung. `kappung_30_abs_3` entspricht
  `kappung_36_abs_3` beim GKG.
- **Alle Geldbeträge sind Dezimalstrings** (z. B. `"847.60"`), niemals
  JSON-Zahlen — vermeidet Float-Rundungsfehler beim Weiterverarbeiten.

## Bewusste Grenzen

- **RVG/GKG: nur Wertgebühren (Zivil).** Betragsrahmengebühren, PKH-Vergütung,
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
- **Anrechnung nur bei identischem Wert**: Tragen `2300` und `3100` (bzw.
  KV `1100` und `1210`) verschiedene Werte, ist die angeforderte Anrechnung
  ein Eingabefehler (Exit 2) — keine Teilanrechnung.
- **Wert-Höchstgrenze mit Teilwerten**: Nutzt die Anfrage `gegenstandswert`,
  wird jeder Wert über 30 Mio. € (Streitwert, Teilwert oder Summe der
  Wertteile nach § 15 Abs. 3 RVG / § 36 Abs. 3 GKG) abgelehnt statt je
  Position gekappt — § 22 Abs. 2 RVG / § 39 Abs. 2 GKG sind dafür nicht
  modelliert.
- **Anm. Abs. 1 zu Nr. 3101 VV RVG** (Anrechnung des über die Gebühr 3100
  hinausgehenden Betrags in einer anderen Angelegenheit) ist nicht
  modelliert — Hinweis an der Position.
- **Kein Teilübergang aus dem Mahnverfahren**: `anrechnung_1100_auf_1210`
  setzt den **vollständigen** Übergang voraus. Angerechnet wird nach der
  Anmerkung Abs. 1 zu KV 1210 GKG „eine Gebühr 1100 nach dem Wert des
  Streitgegenstands …, der in das Prozessverfahren übergegangen ist" — bei
  einem Teilübergang ist das ein **anderer (kleinerer) Wert** als der
  Streitwert des Prozessverfahrens. Verschiedene Teilwerte an KV 1100 und
  KV 1210 bei angeforderter Anrechnung sind deshalb ein Eingabefehler.
  Der Executor rechnet diesen Fall **nicht** — die
  Anrechnung beim Teilübergang bleibt händisch/anwaltlich zu ermitteln.
- **KV 1211 ohne Mahnverfahrens-Anrechnung**: `anrechnung_1100_auf_1210`
  verlangt KV 1210; die Ermäßigung KV 1211 ist von der Anmerkung nicht
  erfasst und wird als Eingabefehler abgelehnt statt geraten.
- **FamGKG — keine Billigkeit, kein Ermessen:** § 43 Abs. 1 Satz 1
  (Umfang, Bedeutung, Vermögen), § 41 (einstweilige Anordnung: in der Regel
  ermäßigt, Ausgangspunkt die Hälfte — eine Regel mit Ermessen, deshalb
  nicht ermittelt; den Wert direkt als `verfahrenswert` eingeben),
  §§ 44 Abs. 3, 45 Abs. 3, 50 Abs. 3 (Billigkeitskorrektur) — nur über
  `zuschlag` bzw. `verfahrenswert_festgesetzt` als Nutzereingabe.
- **FamGKG — nicht modellierte Wertvorschriften:** Abstammung (§ 47),
  Ehewohnung/Haushalt (§ 48), Gewaltschutz (§ 49), Versorgungsausgleich-
  Auskunft/Abtretung (§ 50 Abs. 2), Unterhaltssachen, die keine
  Familienstreitsachen sind (§ 51 Abs. 3), Kindschaftssache nach § 45
  Abs. 1 Nr. 5, vermögensrechtliche Kindschaftssachen (§ 46), § 33 Abs. 1
  Satz 2 FamGKG und innerhalb der zwölf Monate wechselnde Unterhalts-
  Monatsbeträge. Dafür den Verfahrenswert direkt eingeben.
- **FamGKG — Teil-Ermäßigung im Verbund** (Anm. Abs. 1 zu KV 1111/1122:
  nur die beendete Ehesache/Folgesache wird ermäßigt) ist nicht modelliert;
  `1110` und `1111` zusammen sind Exit 2. Ebenso die Anrechnung einer
  Mahnverfahrensgebühr KV 1100 GKG auf KV 1220 FamGKG (Anm. zu KV 1220).
- **Mehrere Kindschaftssachen:** Ob z. B. Sorge und Umgang in einem
  Verfahren getrennte Gegenstände sind, entscheidet die Kanzlei über die
  Zahl der Einträge; derselbe `gegenstand` zweimal (etwa je Kind) wird nach
  § 44 Abs. 2 Satz 1 / § 45 Abs. 2 FamGKG abgelehnt.
- **§ 14 RVG-Ermessen für die Geschäftsgebühr** (Nr. 2300, Satz zwischen 0,5
  und 2,5): Der Executor verlangt den Satz als Eingabe und weist bei Satz
  > 1,3 nur auf die Begründungspflicht hin — er trifft die
  Billigkeitsentscheidung nicht selbst.
