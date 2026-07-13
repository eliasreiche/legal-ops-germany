---
name: zitat-pruefer
description: "Extrahiert jede Norm-, Urteils- und Fundstellenangabe aus einem Text/Markdown-Dokument und markiert sie mit 3-Zustands-Marker (verifiziert / nicht prüfbar / abweichend) gegen eine Quellen-Registry. Querschnitts-Skill, den andere Skills am Ende mitnutzen. Triggert bei Zitate prüfen, Fundstellen verifizieren, Normzitat-Check, Belege gegen Registry."
status: beta
welle: 1
plugin: querschnitt
rdg_einordnung: "Reine Format- und Konsistenzprüfung von Zitaten gegen eine vom Nutzer mitgelieferte Quellen-Registry; keine rechtliche Bewertung des Inhalts einer Norm oder Entscheidung und keine Aussage zur Rechtslage."
daten_hinweis: "Dokumente können Mandatsbezug haben — vor Verarbeitung pseudonymisieren oder DSGVO-/BRAO-konformen Modellzugang nutzen (AWS-Bedrock-Pfad, § 203 StGB). Der Executor selbst arbeitet rein lokal, ohne Netzwerkzugriff."
haftung: "Ersetzt keine inhaltliche Prüfung der zitierten Quellen durch den Anwalt. ✅ verifiziert heißt nur: Angabe stimmt mit der mitgelieferten Registry überein — nicht, dass Norm oder Entscheidung inhaltlich einschlägig sind. Zweitkontrolle bleibt Kanzleisache."
---

# zitat-pruefer

> **Status: `beta`** — automatisierte Tests laufen grün in CI (`tests/test_executor.py`,
> 55 Fälle). Noch **nicht** händisch abgenommen — dafür wird `status: getestet` erst nach
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
