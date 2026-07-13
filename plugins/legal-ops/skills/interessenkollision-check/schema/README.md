# Schema — interessenkollision-check

Datei-Kontrakt (P2) für `executor.py`. Kein Netzwerkzugriff, keine
Datenbank, keine Persistierung — alles über Dateien, die der Executor nur
liest.

## Eingabe 1: Mandanten-/Gegnerliste (Pflicht, `--liste`)

CSV, Trennzeichen `;`, UTF-8 (BOM wird toleriert — eine Datei mit
`﻿`-Präfix wird korrekt gelesen). Pflichtspalten: `name;rolle;typ`,
optional zusätzlich `az;notiz`. Spaltenreihenfolge ist beliebig, die Namen
der Kopfzeile entscheiden.

| Spalte | Pflicht | Werte |
|---|---|---|
| `name` | ja | Freitext — voller Name der Person/Firma |
| `rolle` | ja | `mandant` \| `gegner` \| `sonstige` |
| `typ` | ja | `natuerlich` \| `juristisch` |
| `az` | nein | Aktenzeichen, Freitext |
| `notiz` | nein | Freitext |

Fehlt eine Pflichtspalte in der Kopfzeile oder ein Pflichtfeld in einer
Datenzeile, oder enthält `rolle`/`typ` einen nicht erlaubten Wert, bricht der
Executor mit einer Fehlermeldung ab (Exit 2) — es wird nie stillschweigend
übersprungen oder geraten.

Beispiel: [`beispiel-mandantenliste.csv`](beispiel-mandantenliste.csv).

## Eingabe 2: Neue Parteien (Pflicht, `--parteien`)

Zwei Formate, per Dateiendung unterschieden:

**CSV** (`.csv`) — gleicher Grundkontrakt wie die Mandantenliste, aber nur
`name` ist Pflicht; `rolle`, `typ`, `az`, `notiz` sind optional (wenn
angegeben, gelten dieselben erlaubten Werte für `rolle`/`typ` wie oben).

**JSON** (`.json`) — Liste von Objekten mit denselben Feldnamen:

```json
[
  {"name": "Erika Mustermann", "rolle": "mandant", "typ": "natuerlich"},
  {"name": "Beispiel Handels GmbH"}
]
```

Nur `name` ist Pflicht; fehlende optionale Felder werden als `null` im
Report geführt. Beispiel: [`beispiel-neue-parteien.json`](beispiel-neue-parteien.json).

`rolle`/`typ` der neuen Parteien beschreiben die Rolle **im neuen Mandat**
(z. B. "das ist die Gegenseite in der neuen Sache") — sie fließen nicht in
die Matching-Logik selbst ein (die vergleicht ausschließlich Namen), sondern
nur in die Darstellung des Reports, insbesondere den Hinweis auf die
anwaltliche Kollisionsprüfung bei Gegner-Rollen-Treffern.

## Match-Stufen

Der Executor prüft jedes Paar (neue Partei × Listeneintrag) in der
Reihenfolge S1 → S2 → S3 → S4; die erste zutreffende Stufe gewinnt (kein
Paar wird doppelt gezählt):

| Stufe | Kriterium | `stufe` im Report | `score` |
|---|---|---|---|
| S1 | exakt nach Normalisierung | `treffer` | `1.0` |
| S2 | Token-Mengen-Gleichheit bzw. -Teilmenge nach Normalisierung (Wortreihenfolge unerheblich) | `treffer` | `1.0` (Gleichheit) bzw. `\|kleinere Menge\| / \|größere Menge\|` (Teilmenge) |
| S3 | Kölner Phonetik je Token identisch (primär Personennamen: Meyer/Maier/Mayr, Schmidt/Schmitt) | `moeglicher_treffer` | `1.0` |
| S4 | Fuzzy-Ratio ≥ `--schwelle-moeglich` (Default `0.85`) | `moeglicher_treffer` | Ähnlichkeitswert (`sequenz_ratio`/`token_alignment_ratio`, jeweils der höhere) |
| — | keins der obigen Kriterien trifft zu | `kein_treffer` — **erscheint nicht im Report**, nur als Anzahl in `zusammenfassung.anzahl_geprueft_paare` abzüglich Treffer/mögliche Treffer | — |

**Normalisierung** (Details: [`core/calc/matching/normalisierung.py`](../../../core/calc/matching/normalisierung.py)):
Kleinschreibung, Umlaut-/ß-Transliteration (ä→ae, ö→oe, ü→ue, ß→ss),
Rechtsform-Stripping (GmbH, mbH, GmbH & Co. KG, AG, KG, OHG, GbR,
UG (haftungsbeschränkt), e.V., e.K., PartG, PartG mbB, SE, Stiftung),
Titel-Stripping bei Personen (Dr., Prof., Dipl.-Ing. u. a.), Interpunktion
und Mehrfach-Whitespace.

**Schwellenwert-Begründung (0.85):** bewusst hoch angesetzter Kompromiss
zwischen Rückruf (Tippfehler-/OCR-Varianten erkennen) und Präzision (kurze
oder häufige Namensbestandteile nicht reihenweise als möglichen Treffer
melden — siehe die False-Positive-Tests in `tests/`, z. B. "Müller GmbH" vs.
"Schulze GmbH", die trotz gemeinsamer Rechtsform **nicht** matchen dürfen).
Überschreibbar per `--schwelle-moeglich`.

## Ausgabe: JSON-Report

Siehe [`beispiel-report.json`](beispiel-report.json) für ein vollständiges,
tatsächlich vom Executor erzeugtes Beispiel (aus
[`beispiel-mandantenliste.csv`](beispiel-mandantenliste.csv) +
[`beispiel-neue-parteien.json`](beispiel-neue-parteien.json), mit je einem
Treffer auf jeder der vier Stufen sowie einer echten Nichttreffer-Partei).
Struktur:

```json
{
  "meta": {
    "liste_datei": "…",
    "parteien_datei": "…",
    "erzeugt_von": "interessenkollision-check/executor.py",
    "schwelle_moeglich": 0.85
  },
  "kandidaten": [
    {
      "neue_partei": {"name": "…", "rolle": "mandant|gegner|sonstige|null", "typ": "…"},
      "listeneintrag": {"name": "…", "rolle": "…", "typ": "…", "az": "… oder null"},
      "regel": "S1 | S2 | S3 | S4",
      "stufe": "treffer | moeglicher_treffer",
      "score": 0.0,
      "begruendung": "…"
    }
  ],
  "zusammenfassung": {
    "anzahl_neue_parteien": 5,
    "anzahl_listeneintraege": 5,
    "anzahl_geprueft_paare": 25,
    "anzahl_treffer": 2,
    "anzahl_moegliche_treffer": 2
  }
}
```

`regel` (S1–S4) ist eine zusätzliche, über die Auftragsvorgabe hinausgehende
Angabe für Nachvollziehbarkeit — `stufe` bleibt das maßgebliche Feld für die
Kategorisierung (`treffer`/`moeglicher_treffer`). `kandidaten` ist sortiert:
`treffer` vor `moeglicher_treffer`, innerhalb dessen absteigend nach `score`.

## Bewusste Grenzen (siehe auch normalisierung.py/koelner_phonetik.py/fuzzy.py)

- **Rechtsform-/Titel-Stripping ist tokenbasiert, nicht positionsbasiert.**
  Ein Namensbestandteil, der zufällig mit einer bekannten Rechtsform oder
  einem Titel identisch ist, wird ebenfalls entfernt (dokumentierter
  Randfall, siehe `normalisierung.py`).
- **Rechtsform-Gleichheit allein ist nie ein Treffer.** "Müller GmbH" und
  "Schulze GmbH" bleiben nach Normalisierung "mueller" und "schulze" —
  eindeutig verschieden (Regressionstest in `tests/`).
- **S2-Teilmengen-Treffer können sehr kurz sein.** Ein einzelnes gemeinsames
  Token (z. B. ein häufiger Nachname) genügt für einen `treffer` der Stufe
  S2 — der niedrige `score` (Verhältnis der Mengengrößen) macht diesen Fall
  im Report sichtbar, ersetzt aber nicht die menschliche Prüfung.
- **Kölner Phonetik ist für deutsche Lautung entwickelt** — bei
  fremdsprachigen Namen ist die Trefferqualität nicht belastbar.
- **Kurze Namen bergen ein erhöhtes Fuzzy-False-Positive-Risiko** (wenige
  Zeichen → zufällig hohe Ähnlichkeit). Die Schwelle 0.85 mindert, beseitigt
  aber nicht dieses Risiko — bei sehr kurzen Namen ist besondere Vorsicht
  bei der manuellen Prüfung von `moeglicher_treffer`-Ergebnissen geboten.
- **Kein Abgleich über Aktenzeichen/Notiz-Text** — die Matching-Logik
  vergleicht ausschließlich `name`-Felder; `az`/`notiz` werden nur zur
  Anzeige durchgereicht.
- **Kein Fuzzy-Vorschlag bei völlig fehlender Überschneidung** — Stufe S4
  greift nur, wenn die Ähnlichkeit die Schwelle erreicht; ein `kein_treffer`
  ist **kein Freibrief**: Schreibweisen-Lücken jenseits der hier
  implementierten Stufen (z. B. Spitznamen, komplett andere Firmierung nach
  Umfirmierung, Transliterationen aus anderen Schriftsystemen) bleiben
  unentdeckt. Die abschließende Kollisionsprüfung bleibt Kanzleipflicht.
