---
name: zitat-pruefer
description: "Extrahiert jede Norm-, Urteils- und Fundstellenangabe aus einem Text/Markdown-Dokument und markiert sie mit 3-Zustands-Marker (verifiziert / nicht prüfbar / abweichend) gegen eine Quellen-Registry. Querschnitts-Skill, den andere Skills am Ende mitnutzen. Triggert bei Zitate prüfen, Fundstellen verifizieren, Normzitat-Check, Belege gegen Registry."
status: beta
welle: 1
bereich: querschnitt
rdg_einordnung: "Reine Format- und Konsistenzprüfung von Zitaten gegen eine vom Nutzer mitgelieferte Quellen-Registry; keine rechtliche Bewertung des Inhalts einer Norm oder Entscheidung und keine Aussage zur Rechtslage."
daten_hinweis: "Dokumente können Mandatsbezug haben — vor Verarbeitung pseudonymisieren oder DSGVO-/BRAO-konformen Modellzugang nutzen (AWS-Bedrock-Pfad, § 203 StGB). Der Executor selbst arbeitet rein lokal, ohne Netzwerkzugriff."
haftung: "Ersetzt keine inhaltliche Prüfung der zitierten Quellen durch den Anwalt. ✅ verifiziert heißt nur: Angabe stimmt mit der mitgelieferten Registry überein — nicht, dass Norm oder Entscheidung inhaltlich einschlägig sind. Zweitkontrolle bleibt Kanzleisache."
---

# zitat-pruefer

> **Status: `beta`** — automatisierte Tests laufen grün in CI (`tests/test_executor.py`
> und `tests/test_zitat_pruefer_encoding_und_registries.py`, 73 Fälle). Noch **nicht**
> händisch abgenommen — dafür wird `status: getestet` erst nach
> Prüfung durch den Maintainer gesetzt (siehe [CONVENTIONS.md](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/blob/main/CONVENTIONS.md),
> Reifegrad-Leiter).

## Zweck

Extrahiert jede Norm-, Urteils- und Fundstellen-Angabe aus einem Text- oder
Markdown-Dokument und markiert sie mit dem 3-Zustands-Marker aus
[CONVENTIONS.md](https://github.com/eliasreiche/claude-for-legal-non-billable-germany/blob/main/CONVENTIONS.md#zitierdisziplin-3-zustands-marker):

- ✅ **verifiziert** — gegen eine mitgelieferte Quellen-Registry geprüft und bestätigt
- ⚠️ **nicht prüfbar** — keine Registry-Angabe zu diesem Zitat vorhanden
- ❌ **abweichend** — Registry-Angabe widerspricht dem Zitat, mit Begründung

Dies ist ein **Querschnitts-Skill** (`plugin: querschnitt`): Er wird nicht nur
eigenständig aufgerufen, sondern soll von anderen Skills, die Texte mit Zitaten
erzeugen (Voten, Schreiben-Entwürfe, Zusammenfassungen), am Ende des Ablaufs
mitgenutzt werden, damit generierte Texte nie unmarkierte Zitate enthalten.

## Eingaben (Datei-Kontrakt, P2)

| Eingabe | Pflicht | Format | Beschreibung |
|---|---|---|---|
| Quelldokument | ja | `.md` / `.txt`, UTF-8 | Text mit den zu prüfenden Zitaten. Fließtext und Fußnotenzeilen werden gleich behandelt. |
| Quellen-Registry | nein | `.json` | Liste bekannter Normen, Entscheidungen, Fundstellen — siehe [`schema/README.md`](schema/README.md) für das genaue Schema und [`schema/beispiel-registry.json`](schema/beispiel-registry.json) als Beispiel. |

Ohne Registry bleibt jedes inhaltlich zu prüfende Zitat `nicht_pruefbar` — nur die
quellenfreien Formatprüfungen (bekanntes Gesetzeskürzel aus
[`schema/gesetzeskuerzel.json`](schema/gesetzeskuerzel.json), plausible
Abs./Satz/Nr.-Syntax, §/§§-Konsistenz) laufen trotzdem.

Vollständige Format-Spezifikation: [`schema/README.md`](schema/README.md).

> ⚠️ **Wichtiger Hinweis zur Registry-Vollständigkeit:** Eine **unvollständige**
> Normen-Registry (ein Gesetzeskürzel ist gelistet, aber nicht alle seine
> tatsächlich existierenden Paragraphen sind enthalten) erzeugt **systematisch
> falsche ❌ `abweichend`** auf Normen, die in Wirklichkeit gültig sind — die
> Prämisse des Executors ist: *die mitgelieferte Normliste je Gesetz ist für den
> übergebenen Ausschnitt vollständig* (Details: [`schema/README.md`](schema/README.md)
> unter „Bewusst asymmetrisch"). Wer nur einen Teil der Paragraphen eines Gesetzes
> in die Registry aufnimmt, muss mit falschen ❌ auf den fehlenden Paragraphen
> rechnen. Vor Nutzung: Registry je Gesetz möglichst vollständig aus einer
> verlässlichen Quelle (Gesetzesdatenbank, Kommentar) ziehen — kein bloßer Auszug
> der im Dokument ohnehin schon zitierten Normen.

## Voraussetzungen & PDF-Praxis

Zwei Punkte aus der händischen Real-World-Abnahme (LG-Berlin-Urteil, 2026-07-15):

### 1. Encoding-Falle bei Gerichts-PDFs

Manche Gerichts-PDFs tragen ein Custom-Font-Encoding, bei dem die **Textebene**
das Paragraphenzeichen verfälscht: `§` erscheint als `$`, `§§` als `SS` (real
beobachtet: „auf `$ 826 BGB` gestützt", „`(SS 37, 37b Abs. 1 StBerG)`"). Ohne
Reparatur erkennt der Executor solche Zitate gar nicht als Normzitate.

Der optionale Reparatur-Schritt `--repariere-encoding` ersetzt **kontextsensitiv**
`$`→`§` und `SS`→`§§` — **nur** dort, wo ein echtes Normzitat vorliegt (Marker +
Ziffernblock + **bekanntes** Gesetzeskürzel dahinter). Geldangaben wie `$ 50 Euro`
oder Wörter wie `PASSAU` bleiben unangetastet. Jede Ersetzung wird im Report unter
`meta.encoding_reparaturen` mit **Position, Zeile, Original, Ersetzung und Kontext**
dokumentiert, damit die Kanzlei die Reparatur zweitkontrollieren kann. Der Schritt
ist standardmäßig **aus** — er ändert Zeichen im Dokument und wird deshalb nur bei
Bedarf explizit zugeschaltet.

> **Kein OCR.** Dies repariert ausschließlich eine bekannte Encoding-Falle in der
> bereits vorhandenen Textebene. Ein OCR-Fallback für gescannte Bild-PDFs (ohne
> brauchbare Textebene) ist **nicht** Teil dieses Skills — er kommt separat mit
> Skill #11 [`posteingang-ocr-verteilung`](../posteingang-ocr-verteilung/SKILL.md)
> (Welle 4).

### 2. Standard-Registries (BGB, ZPO, StGB)

Ohne Registry bleibt jedes Norm-Zitat ⚠️ `nicht_pruefbar` — nur die Formatprüfung
läuft. Für die drei am häufigsten zitierten Gesetze liegen fertige Registries bei:

```
schema/standard-registries/bgb.json
schema/standard-registries/zpo.json
schema/standard-registries/stgb.json
```

Sie sind maschinell aus der amtlichen Gesetzes-XML von `gesetze-im-internet.de`
erzeugt (Generator: [`schema/standard-registries/generiere_registries.py`](schema/standard-registries/generiere_registries.py),
Provenienz-Felder `quelle_url` / `abgerufen_am` je Datei). Aufgehobene/weggefallene
Paragraphen sind mit `"aufgehoben": true` aufgenommen, damit ein Zitat auf eine
historische Nummer nicht fälschlich als ❌ `abweichend` gemeldet wird. Übergabe an
den Executor über `--registry`:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/zitat-pruefer/executor.py \
  --input <urteil.md> \
  --registry ${CLAUDE_PLUGIN_ROOT}/skills/zitat-pruefer/schema/standard-registries/bgb.json \
  --repariere-encoding
```

> **Frische:** Gesetze ändern sich laufend. Die Registries sind Momentaufnahmen
> zum `abgerufen_am`-Datum (Muster analog zum Frische-Gate des `gwg-risiko-check`,
> D19) und vor produktiver Nutzung gegen den aktuellen Stand abzugleichen —
> Neu-Erzeugung per `generiere_registries.py` (nur der Generator geht ins Netz;
> der Executor selbst bleibt strikt offline, P3). Der Executor bezieht **immer nur
> genau eine** Registry-Datei je Lauf; ein Zitat gegen ein anderes Gesetz (z. B.
> `§ 37b StBerG` bei übergebener BGB-Registry) bleibt korrekt ⚠️ `nicht_pruefbar`.

## Ablauf

1. **Claude ruft den Executor auf** (kein eigenes Zitat-Parsing durch das Modell):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/zitat-pruefer/executor.py \
     --input <dokument.md> \
     [--registry <quellen-registry.json>] \
     --output <report.json>
   ```

2. **Der Executor entscheidet den Zustand jedes Zitats deterministisch** (P3,
   Deterministik-Grenze). Claude liest ausschließlich den erzeugten JSON-Report —
   Claude vergibt selbst nie `verifiziert`/`nicht_pruefbar`/`abweichend`, sondern
   übernimmt den vom Executor gesetzten Wert unverändert.
3. Claude stellt den Report in Markdown dar: jedes Zitat mit seinem Marker
   (✅/⚠️/❌) und — bei ⚠️ oder ❌ — der `begruendung` aus dem Report. Format-
   warnungen werden zusätzlich als Hinweis angezeigt, unabhängig vom Zustand.
4. Bei ❌ `abweichend`-Treffern weist Claude explizit auf Zweitkontrolle-Bedarf
   hin (Berufsrechts-Gate, `haftung`-Feld oben).

## Output-Format

JSON-Report nach [`schema/README.md`](schema/README.md), Beispiel:
[`schema/beispiel-report.json`](schema/beispiel-report.json) (erzeugt aus
[`schema/beispiel-eingabe.md`](schema/beispiel-eingabe.md) +
[`schema/beispiel-registry.json`](schema/beispiel-registry.json)).

Jeder Zahlen-/Datums-/Statuswert im Report stammt aus `executor.py`, nie vom Modell
generiert (P3).

## Beispiele

### Beispiel 1 — mit Quellen-Registry (drei Zustände gemischt)

Eingabe (`schema/beispiel-eingabe.md`, Auszug):

```
Der Anwalt ist nach § 203 StGB und § 43a Abs. 2 BRAO zur Verschwiegenheit
verpflichtet. [...] Zeugnisverweigerungsrechte folgen aus §§ 53, 97 StPO.

Vgl. BGH, Urt. v. 12.01.2023 – IX ZR 15/22; siehe auch BVerfG NJW 2020, 300.
```

Aufruf:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/zitat-pruefer/executor.py \
  --input schema/beispiel-eingabe.md \
  --registry schema/beispiel-registry.json
```

Von Claude präsentiertes Ergebnis (Markdown, aus dem Report übernommen):

| Zitat | Zustand | Begründung |
|---|---|---|
| § 203 StGB | ✅ verifiziert | in Quellen-Registry gefunden |
| § 43a Abs. 2 BRAO | ✅ verifiziert | in Quellen-Registry gefunden |
| Art. 44 DSGVO | ⚠️ nicht prüfbar | keine Registry-Angabe zu DSGVO |
| §§ 53, 97 StPO | ❌ abweichend | § 97 StPO nicht in der Normliste für StPO enthalten (nur § 53 mitgeliefert) |
| BGH, Urt. v. 12.01.2023 – IX ZR 15/22 | ✅ verifiziert | Aktenzeichen + Datum stimmen mit Registry überein |
| BVerfG NJW 2020, 300 | ✅ verifiziert | Fundstelle in Registry gefunden |

### Beispiel 2 — ohne Quellen-Registry (nur Formatprüfung)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/zitat-pruefer/executor.py --input entwurf.md
```

Bei `§§ 5 StGB` (Plural-Zeichen, aber nur eine Paragraphennummer) liefert der
Report `zustand: nicht_pruefbar` (keine Registry vorhanden) **und zusätzlich**
`formatwarnungen: ["§§ (Plural) mit nur einer Paragraphennummer angegeben —
vermutlich '§' gemeint"]`. Claude zeigt beides an: den Marker ⚠️ für den
Zitierzustand sowie separat den Formathinweis.

## Erkannte Zitatformen und Grenzen

Details, Randfälle (§§-Ketten, Abs./Satz/Nr./lit., Klammerzusätze, Fließtext vs.
Fußnotenstil) und bewusste Nicht-Erkennungen: siehe
[`schema/README.md`](schema/README.md#erkannte-zitatformen) und
[`schema/README.md`](schema/README.md#bewusst-nicht-erkannt-grenzen).
