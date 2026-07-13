# Schema — gwg-risiko-check

Datei-Kontrakt (P2) für den Executor
[`executor.py`](../executor.py) und den Rechner
[`core/calc/gwg/rechner.py`](../../../core/calc/gwg/rechner.py).
Kein Netzwerkzugriff, keine Datenbank — JSON-Datei rein, JSON-Report raus.

## Eingabe: Mandats-Fragebogen (JSON, `--mandat`)

Strukturierter Fragebogen zu einem Mandat. **Fehlende Felder werden als
`unklar` behandelt — nie geraten.** Ein unbekanntes Feld ist ein Eingabefehler
(Tippfehler-Diagnose, Exit 2). Beispiel:
[`beispiel-mandat.json`](beispiel-mandat.json).

| Feld | Werte | Bedeutung / abgeleiteter Katalogfaktor |
|---|---|---|
| `kataloggeschaeft` | `immobilien_gewerbe_kauf`, `vermoegensverwaltung`, `konten_depot`, `gesellschaft_mittelbeschaffung`, `treuhand_gesellschaft`, `finanz_immobilien_transaktion`, `keins`, `unklar` | Anwendbarkeits-Gate § 2 Abs. 1 Nr. 10 GwG. `keins` → `nicht_verpflichtet`; `unklar` → `unvollstaendig`. |
| `mandant_typ` | `natuerliche_person`, `juristische_person`, `trust_aehnlich`, `unklar` | Dokumentation; fließt in die Lücken-Ausweisung ein. |
| `sitz_land` | ISO-3166-alpha-2 (z. B. `DE`) oder `unklar` | Geografie: EU-Mitgliedstaat (Anlage 1 Nr. 3 Buchst. a) bzw. Treffer auf einer der drei Hochrisiko-Listen (EU/FATF-schwarz/FATF-grau, Anlage 2 Nr. 3 Buchst. a bei EU-Treffer). **Kritische Angabe.** |
| `pep` | `ja`, `nein`, `unklar` | Politisch exponierte Person (§ 15 Abs. 3 Nr. 1 GwG). **Kritische Angabe.** |
| `wirtschaftlich_berechtigter_geklaert` | `ja`, `nein`, `unklar` | Klärung des wB (§ 10 Abs. 1 Nr. 2 GwG). **Kritisch** — nur `ja` erlaubt eine Klassifikation. |
| `bargeldintensiv` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 1 Buchst. e GwG. |
| `komplexe_eigentumsstruktur` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 1 Buchst. f GwG. |
| `distanzgeschaeft` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 2 Buchst. c GwG. |
| `herkunft_der_mittel_klar` | `ja`, `nein`, `unklar` | Dokumentation (Mittelherkunft); als offene Frage in `luecken`. |
| `boersennotiert_reguliert` | `ja`, `nein`, `unklar` | Anlage 1 Nr. 1 Buchst. a GwG. |
| `oeffentliche_stelle` | `ja`, `nein`, `unklar` | Anlage 1 Nr. 1 Buchst. b GwG. |
| `nominee_inhaberaktien` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 1 Buchst. d GwG. |
| `private_vermoegensstruktur` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 1 Buchst. c GwG. |
| `anonymitaets_produkt` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 2 Buchst. b GwG. |
| `zahlung_unbekannte_dritte` | `ja`, `nein`, `unklar` | Anlage 2 Nr. 2 Buchst. d GwG. |

Die Katalogfaktoren mit exakter Fundstelle und Paraphrase liegen als Daten in
[`core/calc/gwg/anlage1.json`](../../../core/calc/gwg/anlage1.json) und
[`core/calc/gwg/anlage2.json`](../../../core/calc/gwg/anlage2.json); die
Hochrisiko-Länderliste in
[`core/calc/gwg/hochrisiko_drittstaaten.json`](../../../core/calc/gwg/hochrisiko_drittstaaten.json).

## Klassifikationsregeln (regelbasiert, keine Gewichts-Scores)

Erste greifende Regel entscheidet (Details im Rechner-Docstring):

0. **Anwendbarkeits-Gate** — kein Kataloggeschäft → `nicht_verpflichtet`;
   unklar → `unvollstaendig`.
1. **Kritische Lücke** (PEP, Sitzland, wirtschaftlich Berechtigter nicht
   belastbar) → `unvollstaendig`, keine Risikoklasse.
2. **PEP oder Hochrisiko-Drittstaat** (§ 15 GwG) → `hoch`.
3. **Nur Anlage-1-Faktoren, kein Anlage-2-Faktor** → `niedrig` (§ 14 GwG
   *möglich*).
4. **Sonst** → `mittel` (§ 10 GwG).

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(erzeugt aus [`beispiel-mandat.json`](beispiel-mandat.json)). Struktur:

```json
{
  "meta": { "erzeugt_von": "…", "deterministik": "…", "hinweis_bewertung": "…" },
  "eingabe_normalisiert": { "…alle Felder mit aufgelösten Defaults…": "…" },
  "anwendbarkeit": {
    "status": "verpflichtet | nicht_verpflichtet | unklar",
    "kataloggeschaeft": "…", "fundstelle": "§ 2 Abs. 1 Nr. 10 … GwG",
    "paraphrase": "…", "marker": "⚠️", "marker_begruendung": "…",
    "begruendung": "…", "vorbehalt": "… (nur bei nicht_verpflichtet/unklar)"
  },
  "klassifikationsvorschlag": "nicht_verpflichtet | unvollstaendig | niedrig | mittel | hoch",
  "klassifikation_begruendung": "…",
  "regel_angewendet": "anwendbarkeits_gate | kritische_luecke | paragraph_15 | nur_anlage1 | allgemein",
  "angewandte_faktoren": [
    { "id": "…", "anlage": 1, "fundstelle": "Anlage 1 Nr. 3 Buchst. a GwG",
      "paraphrase": "…", "kategorie": "kundenrisiko | produkt-transaktionsrisiko | geografisch",
      "quelle": "executor", "marker": "⚠️", "marker_begruendung": "…", "detail": "…" }
  ],
  "pflichten_hinweise": [ { "norm": "§ 10 GwG", "hinweis": "…", "marker": "⚠️", "…": "…" } ],
  "luecken": [ { "feld": "pep", "frage": "…", "kritisch": true } ],
  "vorbehalte": [ "…" ],
  "stand": { "anlage1": "…", "anlage2": "…",
             "hochrisiko_drittstaaten": { "eu-hochrisiko": "…", "fatf-blacklist": "…", "fatf-greylist": "…" },
             "hochrisiko_abgerufen_am": "2026-07-13", "hinweis": "…" },
  "laender_listen_treffer": {
    "iso2": "IR", "land": "Iran", "listen": ["eu-hochrisiko", "fatf-blacklist"],
    "je_liste": [ { "liste": "eu-hochrisiko", "bezeichnung": "…", "rechtsfolge": "…", "stand_quelle": "…", "url": "…" } ]
  }
}
```

- **`laender_listen_treffer`** — `null`, solange `sitz_land` auf keiner der
  drei Listen (EU-Hochrisiko, FATF-Schwarzliste, FATF-Grauliste) in
  [`core/calc/gwg/hochrisiko_drittstaaten.json`](../../../core/calc/gwg/hochrisiko_drittstaaten.json)
  steht; sonst ein Objekt mit `listen` (welche Liste(n) getroffen haben) und
  `je_liste` (Rechtsfolge/Quelle je Liste). Nur ein EU-Hochrisiko-Treffer ist
  ein gesetzlicher Trigger nach § 15 Abs. 3 Nr. 2 GwG — ein reiner
  FATF-Treffer ohne EU-Listung ist eine konservative Haus-Einstufung (siehe
  [SKILL.md](../SKILL.md), Abschnitt „Gewichtungs-Entscheidung").

- **`marker`** (3-Zustands-Marker, CONVENTIONS.md): der Executor prüft nicht
  gegen den Gesetzestext, daher stets ⚠️ „nicht prüfbar". Die §-Fundstellen
  werden im letzten Skill-Schritt durch `zitat-pruefer` gegen
  [`quellen-registry.json`](quellen-registry.json) verifiziert; die
  Anlagen-Fundstellen bleiben ⚠️ und sind bei der händischen Abnahme zu prüfen.
- **`quelle: "executor"`** kennzeichnet jeden Wert als Rechner-Ergebnis (P3) —
  kein Wert wird vom Modell erzeugt.

## Zitat-Prüfer-Integration

[`quellen-registry.json`](quellen-registry.json) listet alle GwG-`§`-Normen,
die die gerenderte Doku zitiert. Der SKILL.md-Ablauf sieht als letzten Schritt
vor, die erzeugte Markdown-Doku durch `zitat-pruefer` mit dieser Registry
zu prüfen.

## Bewusste Grenzen

- **Kein Rechtsrat, keine Bewertung.** Das Ergebnis ist ein Vorschlag zur
  Aktendokumentation; die Risikobewertung trifft der Verpflichtete
  (§ 10 Abs. 2 GwG).
- **Anlagen-1/2-Fundstellen sind Platzhalter** und vor produktiver Nutzung
  gegen gesetze-im-internet.de zu prüfen (Reifegrad `getestet`). Die
  Hochrisiko-Länderliste ist am 2026-07-13 browser-verifiziert (Quellen in
  `hochrisiko_drittstaaten.json` → `quellen`), ändert sich aber laufend
  (FATF-Plenum ca. Feb/Jun/Okt) — Quartals-Review Pflicht; ein CI-Test warnt
  ab 4 Monaten Alter (`abgerufen_am`) und schlägt hart fehl ab 12 Monaten.
- **FATF-Grauliste-Treffer ohne EU-Listung begründen keine Gesetzespflicht**
  — die Klassifikation `hoch` ist dort konservative Haus-Einstufung, kein
  Verwaltungsakt-sicherer Nachweis (siehe `laender_listen_treffer` oben).
- **PEP-Ermittlung, Sanktionslisten-Abgleich und Identifizierung** sind nicht
  Gegenstand dieses Offline-Skills — hierfür ist der Sanktionslisten-/
  Live-Screening-Pfad bzw. eine eigene Prüfung nötig.
