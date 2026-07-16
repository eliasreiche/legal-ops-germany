# Schema — posteingang-ocr-verteilung

Datei-Kontrakt (P2) für [`executor.py`](../executor.py). Kein OCR-Code, kein
Netzwerkzugriff, keine Datenbank — Dateien rein, JSON-Report raus. Der
Kontrakt wird in **beide Richtungen** dokumentiert: die Eingabe
`eingang.json` (vom Modell erzeugt) und die Ausgabe `report.json` (vom
Executor erzeugt).

## Voraussetzung: bereits extrahierter Scan-Text

Dieser Skill enthält **kein OCR**. Er setzt voraus, dass zu jedem Scan
bereits ein Text vorliegt — entweder als `<scan>.txt`/`.md`-Datei neben der
Scan-Datei (erzeugt durch ein externes, lokales Werkzeug, z. B. macOS
Texterkennung/Vision-Framework, `pdftotext` oder `markitdown`; **lokale
Verarbeitung bevorzugt**, § 203 StGB), **oder** Claude liest den Scan direkt
(z. B. ein Bild/PDF multimodal) und schreibt den erkannten Text selbst in
eine Textdatei. In beiden Fällen gilt für den Executor **derselbe
Provenienz-Kontrakt**: er sieht nur Text, nie das Bild/PDF selbst, und prüft
jeden kritischen Wert wörtlich gegen diesen Text. Eine Repo-weite
Konvertierungs-Standard-Entscheidung ist beim Maintainer offen — dieser
Skill bindet keine bestimmte OCR-Lösung ein.

## Eingabe 1: Eingangs-Entwurf (`--eingang`, JSON, Pflicht)

Vom Modell aus dem/den extrahierten Scan-Text(en) erzeugt — **nie** frei aus
dem Gedächtnis, immer aus dem vorliegenden Text abgeleitet (wie
[`aktenkopf-extraktor`](../../aktenkopf-extraktor/SKILL.md)). Vollständiges
Beispiel: [`beispiel-eingang.json`](beispiel-eingang.json).

```json
{
  "eingang": {
    "absender": "Muster AG",
    "datum_schreiben": "2026-07-01",
    "aktenzeichen_fremd": "VB-2026-77",
    "aktenzeichen_eigen": "2026-001",
    "betreff": "Mahnung und Fristsetzung"
  },
  "fristindikatoren": [
    { "schluesselwort": "Mahnung", "quelle_zitat": "Mahnung und Fristsetzung" }
  ],
  "luecken": [
    { "feld": "eingang.aktenzeichen_eigen", "grund": "kein eigenes Aktenzeichen im Schreiben erwähnt" }
  ]
}
```

### Felder

**`eingang`** (Objekt, Pflicht):

| Feld | Pflicht | Wert | Bedeutung |
|---|---|---|---|
| `absender` | ja¹ | String | Absender des Schreibens. **Nicht** provenienzgeprüft (zu variabel für Wortlaut-Abgleich, wie Name/Anschrift in `aktenkopf-extraktor`) — fließt aber in die Mandats-Zuordnung ein. |
| `datum_schreiben` | ja¹ | ISO `JJJJ-MM-TT` | Datum des Schreibens. Kritischer Wert (Provenienz). Speist den Zielordner-Namen. |
| `aktenzeichen_fremd` | nein | String / `null` | Aktenzeichen des Absenders/der Behörde ("Unser Zeichen"). `null`, wenn keins erkennbar — **kein** leerer String. Kritischer Wert, falls gesetzt. |
| `aktenzeichen_eigen` | nein | String / `null` | Das eigene (Kanzlei-/Mandats-)Aktenzeichen, falls im Schreiben genannt ("Ihr Zeichen"). `null`, wenn keins erkennbar. Kritischer Wert, falls gesetzt. |
| `betreff` | ja¹ | String | Betreff/Mandatsbezug. **Nicht** provenienzgeprüft (wie `absender`) — fließt in die Mandats-Zuordnung ein. |

**`fristindikatoren[]`** (Liste) — **Schlüsselwörter, keine Fristberechnung.**
Jeder Eintrag ist vollständig anzugeben (kein Lücken-Konzept — leer heißt
"kein Indikator gefunden", ausgedrückt durch eine leere Liste):

| Feld | Wert | Bedeutung |
|---|---|---|
| `schluesselwort` | String | z. B. „Frist", „binnen", „spätestens", „Zustellung", „zugestellt", „Zustellungsurkunde", „Mahnung", „Kündigung", „Bescheid", „Urteil", „Beschluss", „Klage" — Beispiele, keine abschließende Liste. |
| `quelle_zitat` | String | Wörtliche Textstelle, die das Schlüsselwort enthält. Kritischer Wert (Provenienz) — und muss (case-insensitiv) das `schluesselwort` selbst enthalten (Schema-Konsistenz). |

**`luecken[]`** (Liste): `feld` (Pfad der fehlenden Angabe, z. B.
`eingang.betreff`), `grund`. Lücken-fähig sind `eingang.absender`,
`eingang.datum_schreiben`, `eingang.betreff` — ein leeres Lücken-fähiges Feld
**ohne** passenden `luecken`-Eintrag ist ein Schema-Fehler.
`aktenzeichen_fremd`/`aktenzeichen_eigen` sind **nicht** lücken-fähig: fehlt
eins, ist der Wert `null`, kein Lücken-Eintrag nötig.

¹ **Lücken-Disziplin**: `absender`, `datum_schreiben`, `betreff` dürfen leer
(`""`/`null`) sein — aber nur mit passendem `luecken`-Eintrag.

## Eingabe 2: Scan-Text(e) (`--quelle`, `.txt`/`.md`, Pflicht)

Der/die extrahierte(n) Text(e), UTF-8. Mehrfach angebbar (z. B. mehrseitiger
Scan als mehrere Textdateien) — der Executor durchsucht alle Quellen; die
erste Fundstelle je Wert gewinnt.

## Eingabe 3: `--kontext` (Pflicht)

Das `kontext/`-Verzeichnis nach
[`core/context/README.md`](../../../core/context/README.md). Mandate werden
über `lese_mandate()` eingelesen (keine erneute Schema-Prüfung). Mandate
ohne Aktenzeichen werden mit einer Warnung in `meta.mandat_warnungen`
übersprungen statt geraten.

## Eingabe 4: `--scan-datei` (optional, mehrfach angebbar)

Datei(en), die der Routing-Plan (Schritt 5) kopieren soll — üblicherweise
das Scan-Original (PDF/Bild) und/oder seine Textauszugs-Datei. Ohne
`--scan-datei` enthält der `routing_plan` einen leeren `dateien`-Array (nur
Zielordner-Name wird berechnet, nichts zum Kopieren).

## Provenienz & Normalisierung

| Typ | kritische Felder | Normalisierung |
|---|---|---|
| `datum` | `eingang.datum_schreiben` | ISO ↔ deutsch: `2026-07-01` = `01.07.2026` = `1.7.2026`; 2-stellige Jahre → `20xx`/`19xx` (identisch zu `aktenkopf-extraktor`). |
| `aktenzeichen` | `eingang.aktenzeichen_fremd`, `eingang.aktenzeichen_eigen` | Mehrfach-Whitespace kollabiert; Groß-/Kleinschreibung zählt (identisch zu `core/calc/zuordnung/az.py`). |
| `zitat` | `fristindikatoren[].quelle_zitat` | Mehrfach-Whitespace kollabiert; Groß-/Kleinschreibung zählt (wörtliches Zitat). |

Nicht belegte Werte → `nicht_belegt` (Exit-Code ≠ 0). `absender` und
`betreff` werden **nicht** auf Provenienz geprüft (zu variabel, wie
Name/Anschrift in `aktenkopf-extraktor`) — nur strukturell (Lücken-Disziplin).

## Fristrelevanz (deterministisch abgeleitet, keine Fristberechnung)

`fristrelevant` ist **niemals eine Modell-Behauptung**: der Executor setzt
`true` ausschließlich dann, wenn mindestens ein
`fristindikatoren[].quelle_zitat` provenienzgeprüft **belegt** ist. Ein vom
Modell behaupteter, aber nicht im Quelltext auffindbarer Indikator zählt
nicht mit (P3, Deterministik-Grenze) — verhindert, dass eine erfundene
Fristnennung das Flag setzt. `fristrelevant_hinweis` enthält **keine
Fristberechnung und kein Normzitat**, nur den Verweis auf die Zweitkontrolle
durch [`fristenrechner`](../../fristenrechner/SKILL.md).

**Bewusste Grenze**: Die Vollständigkeit der vom Modell gefundenen
Indikatoren ist nicht maschinell erzwingbar — übersieht das Modell ein
Schlüsselwort im Text, bleibt `fristrelevant` u. U. `false`, obwohl das
Schreiben fristauslösend ist. Das Ablauf-Kapitel in
[`SKILL.md`](../SKILL.md) gibt deshalb eine konkrete Wortliste als
Arbeitsanweisung vor (kein Ersatz für die anwaltliche Durchsicht).

## Mandats-Zuordnung

Delegiert vollständig an
[`core/calc/zuordnung/`](../../../core/calc/zuordnung/) — dieselbe
Bibliothek wie [`email-akten-zuordnung`](../../email-akten-zuordnung/SKILL.md)
(Stufen Z0–Z4, siehe dortiges `schema/README.md` für die vollständige
Herleitung). `absender` und `betreff` aus dem Eingang sowie der
**gesamte** extrahierte Scan-Text bilden das `Dokument` für den
Zuordnungs-Abgleich (Az-Suche über Z0 findet damit jedes im Text erwähnte
Aktenzeichen, nicht nur die separat extrahierten Felder).

- **`eindeutig: true`** — genau **ein** Kandidat der Kategorie `treffer` ⇒
  `az_fuer_routing` gesetzt.
- **Alles andere** (kein Kandidat, mehr als ein Kandidat, oder nur
  `moeglicher_treffer`) ⇒ `az_fuer_routing: null`, `erfordert_rueckfrage: true`
  — **immer** eine Rückfrage an die Kanzlei, nie eine automatische Wahl
  (identische Regel wie `email-akten-zuordnung`). Der Eingang routet in
  diesem Fall vorläufig nach `unzugeordnet`.

## Routing-Plan (Dry-Run per Default)

Zielordner-Muster:
`posteingang/JJJJ-MM-TT_<az|unzugeordnet>_<absender-slug>/`. `JJJJ-MM-TT`
stammt aus `eingang.datum_schreiben` — **ohne** gültiges ISO-Datum wird
**nie** eines erfunden, stattdessen `routing_plan.moeglich: false` mit
Hinweis (Lücke, manuell zu ergänzen). Absender-Slug-Regel: Umlaute/ß
transliterieren, kleinschreiben, alles außer `[a-z0-9]` zu `-` kollabiert,
auf 60 Zeichen gekürzt (identisch zur Slug-Regel in
`email-akten-zuordnung/executor.py:betreff_slug`, hier auf `absender`
angewandt).

- **Default (kein `--ausfuehren`)**: reiner Plan, kein Dateisystemzugriff auf
  das Ziel. `ausgefuehrt: false`.
- **`--ausfuehren`**: kopiert (nie verschiebt, nie löscht) die per
  `--scan-datei` übergebenen Dateien nach `<kontext>/<ziel_ordner>/`.
  Existiert der Zielordner bereits, ist das eine **Kollision** —
  `routing_plan.fehler` wird gesetzt, **nichts** wird kopiert/überschrieben,
  Exit-Code 1.

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(**tatsächlich vom Executor erzeugt** aus
[`beispiel-eingang.json`](beispiel-eingang.json) +
[`beispiel-scan.txt`](beispiel-scan.txt) gegen
[`core/context/beispiel-kontext/`](../../../core/context/beispiel-kontext/),
read-only genutzt). Kernfelder: `schema_ok`, `schema_fehler[]`,
`provenienz[]`, `luecken[]`, `fristrelevant`, `fristrelevant_hinweis`,
`zuordnung` (`kandidaten[]`, `eindeutig`, `az_fuer_routing`,
`erfordert_rueckfrage`), `routing_plan` (`ziel_ordner`, `dateien[]`,
`ausgefuehrt`, `fehler`), `zusammenfassung`.

### Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Schema in Ordnung, alle kritischen Werte belegt, Routing (falls `--ausfuehren`) ohne Kollision durchgeführt. |
| `1` | Mindestens ein `nicht_belegt`-Wert, ein Schema-Fehler und/oder ein Routing-Fehler (Kollision). |
| `2` | Eingabefehler (Datei/Verzeichnis fehlt, kaputtes JSON, ungültige Schwelle). |

## Bewusste Grenzen

- **Kein OCR-Code, keine Bildverarbeitung** — der Executor liest nur bereits
  extrahierten Text.
- **Keine Fristberechnung**: `fristrelevant` ist ein Flag, kein Fristende.
  Fristen ausschließlich über
  [`fristenrechner`](../../fristenrechner/SKILL.md).
- **Provenienz = Beleg, nicht Richtigkeit** (wie `aktenkopf-extraktor`).
- **Fristindikator-Vollständigkeit** nicht maschinell erzwingbar (siehe oben).
- **Z1–Z4 der Mandats-Zuordnung erben die Grenzen von
  `core/calc/zuordnung/`** (kurze/häufige Namens-Token können mehrdeutig
  treffen) — deshalb ist mehr als ein Kandidat immer eine Rückfrage.
- **Kopieren, nie Löschen**: das Original bleibt an seinem Ort. Ein
  nachträgliches Entfernen des Originals ist eine bewusste, separate
  Kanzlei-Entscheidung außerhalb dieses Skills.
