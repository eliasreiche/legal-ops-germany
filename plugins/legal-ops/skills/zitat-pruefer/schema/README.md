# Schema — zitat-pruefer

Datei-Kontrakt (P2) für `executor.py`. Kein Netzwerkzugriff, keine Datenbank — alles
über Dateien.

## Eingabe 1: Quelldokument (Pflicht)

Beliebige Text- oder Markdown-Datei (`--input`), UTF-8. Der Executor durchsucht den
Volltext nach Zitaten — Fließtext und Fußnotenzeilen (`12 Vgl. § 203 StGB.`) werden
gleich behandelt, da keine Struktur vorausgesetzt wird.

## Eingabe 2: Quellen-Registry (optional, `--registry`)

JSON-Datei nach folgendem Schema. Fehlt sie, wird jedes inhaltlich zu prüfende Zitat
als `nicht_pruefbar` markiert — nur die quellenfreien Formatprüfungen laufen weiter.

```json
{
  "normen": [
    {"kuerzel": "StGB", "paragraph": "203", "bezeichnung": "Verletzung von Privatgeheimnissen"}
  ],
  "entscheidungen": [
    {"gericht": "BGH", "aktenzeichen": "IX ZR 15/22", "datum": "2023-01-12",
     "fundstelle": "NJW 2023, 1234"}
  ],
  "fundstellen": [
    {"zeitschrift": "NJW", "jahr": 2020, "seite": 300, "gericht": "BVerfG"}
  ]
}
```

Felder:

- `normen[].kuerzel` — Gesetzeskürzel wie im Zitat verwendet (Groß-/Kleinschreibung zählt).
- `normen[].paragraph` — Paragraphen-/Artikelnummer als String, inkl. Buchstabensuffix
  (`"43a"`). **Die Registry gilt pro Kürzel als das, was mitgeliefert wurde** — ein
  Paragraph, der zu einem in der Registry vorhandenen Kürzel gehört, aber dort fehlt,
  gilt als `abweichend` (Prämisse: die Normliste je Gesetz ist vollständig für den
  mitgelieferten Ausschnitt). Ein Kürzel, das in der Registry gar nicht vorkommt,
  bleibt `nicht_pruefbar`.
- `entscheidungen[].datum` — ISO-Format `JJJJ-MM-TT`.
- `entscheidungen[].aktenzeichen` — wird whitespace-normalisiert verglichen.
- `fundstellen[]` — `zeitschrift` + `jahr` + `seite` bilden den Schlüssel; `gericht`
  ist optional und wird nur bei Angabe im Zitat gegengeprüft.

**Bewusst asymmetrisch:** Bei Gerichtsentscheidungen und Fundstellen wird ein *fehlender*
Registry-Treffer **nicht** als `abweichend` gewertet (anders als bei Normen), sondern als
`nicht_pruefbar`. Begründung: Eine Normliste für ein einzelnes Gesetz lässt sich in der
Praxis vollständig mitliefern (z. B. Auszug aus einer Gesetzesdatenbank); eine Liste aller
Entscheidungen eines Gerichts oder aller Fundstellen einer Zeitschrift ist das nicht.
Ein fehlender Treffer würde sonst reihenweise falsche `abweichend`-Meldungen erzeugen.

## Gesetzeskürzel-/Gerichts-/Zeitschriften-Listen

`gesetzeskuerzel.json`, `gerichte.json`, `zeitschriften.json` — Datendateien für die
quellenfreien Formatprüfungen (bekanntes Kürzel ja/nein) und für die Erkennungs-Regex
selbst (Gerichte/Zeitschriften müssen aus einer bekannten Liste stammen, sonst wird ein
Treffer gar nicht erst als Zitat erkannt). Erweiterbar per Pull Request; nicht
abschließend.

## Ausgabe: JSON-Report

Siehe [`beispiel-report.json`](beispiel-report.json) für ein vollständiges Beispiel.
Struktur:

```json
{
  "meta": {
    "quelle_datei": "…",
    "registry_datei": "… oder null",
    "erzeugt_von": "zitat-pruefer/executor.py",
    "anzahl_zitate": 3
  },
  "zitate": [
    {
      "id": 1,
      "typ": "norm | gerichtsentscheidung | fundstelle",
      "roh": "§ 203 StGB",
      "zeile": 4,
      "zustand": "verifiziert | nicht_pruefbar | abweichend",
      "marker": "✅ | ⚠️ | ❌",
      "begruendung": "…",
      "details": { "…typspezifisch…": "…" },
      "formatwarnungen": ["…"]
    }
  ],
  "zusammenfassung": {"verifiziert": 1, "nicht_pruefbar": 1, "abweichend": 0}
}
```

`formatwarnungen` ist unabhängig von `zustand` — auch ein `verifiziert`-Zitat kann eine
Formatwarnung tragen (z. B. bekanntes, aber unüblich geschriebenes Kürzel).

## Erkannte Zitatformen

| Typ | Beispiele |
|---|---|
| Normzitat | `§ 203 StGB`, `§ 43a Abs. 2 BRAO`, `Art. 44 DSGVO`, `§§ 53, 97 StPO`, `§ 312c Abs. 1 Satz 1 Nr. 3 BGB (n.F.)` |
| Gerichtsentscheidung | `BGH, Urt. v. 12.01.2023 – IX ZR 15/22`, `OLG München, Beschl. v. 3.4.19 – 7 U 12/18` |
| Fundstelle | `BVerfG NJW 2020, 300`, `NJW 2020, 300` (ohne Gericht) |

## Bewusst nicht erkannt/geprüft (Grenzen)

- Aktenzeichen ohne vorangestelltes, aus der Gerichtsliste bekanntes Gericht (z. B. nur
  `1 BvR 123/20` im Fließtext) — ohne Gerichtszuordnung ist der Registry-Abgleich nicht
  sinnvoll möglich, daher kein Zitat-Treffer.
- Zeitschriften/Gerichte außerhalb der mitgelieferten Listen in `schema/`.
- Freitext-Fundstellen ohne `Jahr, Seite`-Schema (z. B. reine Randnummer-Zitate „Rn. 12").
- Inhaltliche Richtigkeit einer Norm/Entscheidung — nur der in `zustand` markierte
  Abgleich gegen die mitgelieferte Registry, keine Bewertung des Inhalts.
- **Abs./Satz/Nr./lit. eines Normzitats** — die Normen-Registry hat nur Paragraphen-
  Granularität (`kuerzel` + `paragraph`), kein Feld für Absatz/Satz/Nummer/Buchstabe.
  Ein Zitat wie `§ 203 Abs. 99 StGB` wird daher **nicht** als vollständig geprüft
  behandelt, nur weil der Paragraph (203) in der Registry steht: der Executor vergibt
  höchstens ✅ **mit einer expliziten Formatwarnung** „Abs./Satz/Nr./lit. nicht gegen
  Registry prüfbar", und die `begruendung` benennt den tatsächlich geprüften Umfang
  („… — nur Paragraph 203 geprüft; Abs./Satz/Nr./lit. nicht gegen Registry prüfbar").
  Dieselbe Einschränkung gilt für einen offenen `ff.`-Bereich (`§§ 249 ff. BGB`):
  nur der genannte Paragraph (249) ist geprüft, der offene Bereich dahinter nicht —
  Formatwarnung „offener ff.-Bereich nicht prüfbar".
- **Datum einer Gerichtsentscheidung ohne `datum`-Feld in der Registry** — trägt der
  passende Registry-Eintrag (Gericht + Aktenzeichen stimmen) kein `datum`-Feld, wird
  das im Zitat genannte Datum nicht geprüft. Zustand bleibt ✅, aber mit Formatwarnung
  „Datum nicht in Registry hinterlegt, nicht geprüft" und einer Begründung, die den
  geprüften Umfang benennt („nur Gericht und Aktenzeichen geprüft").
- **i.V.m.-Kettenglieder ohne eigenes Gesetzeskürzel** (`§ 823 i.V.m. § 249 BGB`) —
  das erste Kettenglied (`§ 823`) übernimmt für die Prüfung das Kürzel des letzten
  Kettenglieds, das sein eigenes Gesetz trägt (`§ 249 BGB`). Das ist eine Annahme
  („gleiche Anspruchsgrundlage im selben Gesetz"), keine Garantie — im Report ist das
  über die Formatwarnung „Gesetzeskürzel aus i.V.m.-Kette übernommen (von '…')"
  transparent gemacht.
