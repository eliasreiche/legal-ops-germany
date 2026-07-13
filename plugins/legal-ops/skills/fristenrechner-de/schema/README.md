# Schema — fristenrechner-de

Datei-Kontrakt (P2) für den Executor
[`core/calc/fristen/executor.py`](../../../core/calc/fristen/executor.py).
Kein Netzwerkzugriff, keine Datenbank — JSON-Datei rein, JSON-Report raus.

## Eingabe: Fristanfrage (JSON, `--input`)

```json
{
  "ereignis_datum": "2026-01-15",
  "fristart": "berufung",
  "bundesland": "NW"
}
```

oder als freie Fristangabe:

```json
{
  "ereignis_datum": "2025-08-01",
  "dauer": 2,
  "einheit": "wochen",
  "fristtyp": "ereignis",
  "bundesland": "BY"
}
```

Felder:

| Feld | Pflicht | Werte | Bedeutung |
|---|---|---|---|
| `ereignis_datum` | ja | ISO-Datum `JJJJ-MM-TT` | Fristauslösendes Ereignis (z. B. Zustellung) bzw. Anfangstag bei einer Beginnfrist. Ob das Ereignis rechtlich wirksam ist (z. B. wirksame Zustellung), prüft der Executor nicht. |
| `fristart` | entweder dies … | id aus dem [Fristarten-Katalog](../../../core/calc/fristen/fristarten.json) | Vordefinierte Frist; Dauer/Einheit/Fristtyp kommen aus dem Katalog. |
| `dauer` + `einheit` | … oder dies | ganze Zahl ≥ 1; `tage` / `wochen` / `monate` / `jahre` | Freie Fristangabe. Genau eine der beiden Varianten — nie beide. |
| `fristtyp` | nein | `ereignis` (Default) / `beginn` | § 187 Abs. 1 BGB (Ereignistag zählt nicht) oder § 187 Abs. 2 BGB (Anfangstag zählt mit). |
| `bundesland` | **ja** | `BW BY BE BB HB HH HE MV NI NW RP SL SN ST SH TH` | Feiertage am **Fristende-Ort** (§ 193 BGB) — bei gerichtlichen Fristen der Sitz des Gerichts. |
| `paragraf_193_anwenden` | nein | `true` (Default) / `false` | `false` nur für Zeitraumberechnungen, auf die § 193 BGB nicht anwendbar ist (z. B. Beginn eines Zinslaufs). |

## Fristarten-Katalog (JSON-Daten)

Der Katalog liegt als Datendatei beim Executor:
[`core/calc/fristen/fristarten.json`](../../../core/calc/fristen/fristarten.json)
— dort, damit alle Skills denselben Katalog nutzen (keine Duplikation, P3:
Daten statt hartkodierter Logik). Enthalten (Stand siehe `stand`-Feld):

| id | Frist | Norm | Dauer |
|---|---|---|---|
| `berufung` | Berufungsfrist (Notfrist) | § 517 ZPO | 1 Monat |
| `berufungsbegruendung` | Berufungsbegründung (verlängerbar) | § 520 Abs. 2 ZPO | 2 Monate |
| `einspruch_versaeumnisurteil` | Einspruch gegen VU (Notfrist) | § 339 Abs. 1 ZPO | 2 Wochen |
| `widerspruch_mahnbescheid` | Widerspruch gegen Mahnbescheid — **kein Fristende im technischen Sinn** | § 692 Abs. 1 Nr. 3, § 694 ZPO | 2 Wochen |
| `revision` | Revisionsfrist (Notfrist) | § 548 ZPO | 1 Monat |
| `revisionsbegruendung` | Revisionsbegründung (verlängerbar) | § 551 Abs. 2 ZPO | 2 Monate |
| `anhoerungsruege` | Anhörungsrüge (Notfrist) | § 321a Abs. 2 ZPO | 2 Wochen |
| `wiedereinsetzung` | Wiedereinsetzungsantrag (Regelfall) | § 234 Abs. 1, 2 ZPO | 2 Wochen |
| `wiedereinsetzung_begruendungsfrist` | Wiedereinsetzung bei versäumter Begründungsfrist | § 234 Abs. 1, 2 ZPO | 1 Monat |

Jeder Eintrag trägt `notfrist`, `verlaengerbar`, ggf.
`kein_technisches_fristende` sowie `hinweise` — diese werden unverändert in
den Report übernommen. Erweiterbar per Pull Request.

## Ausgabe: JSON-Report

Vollständiges Beispiel: [`beispiel-report.json`](beispiel-report.json)
(erzeugt aus [`beispiel-eingabe.json`](beispiel-eingabe.json)). Struktur:

```json
{
  "meta": { "erzeugt_von": "core/calc/fristen/executor.py",
            "katalog_stand": "…", "feiertagsregeln_stand": "…",
            "deterministik": "…" },
  "eingabe": { "…Echo der normalisierten Eingabe…": "…" },
  "fristart": { "…Katalogeintrag oder null bei freier Frist…": "…" },
  "rechenkette": [
    { "schritt": 1, "norm": "§ 187 Abs. 1 BGB",
      "beschreibung": "…", "ergebnis": "2026-01-16", "quelle": "executor" }
  ],
  "ergebnis": {
    "fristbeginn": "2026-01-16",
    "fristende_rechnerisch": "2026-02-15",
    "fristende": "2026-02-16",
    "verschoben": true,
    "verschiebungen": [ { "von": "…", "auf": "…", "grund": "…", "norm": "…" } ],
    "fristende_bei_teilgebietlichem_feiertag": null,
    "kein_technisches_fristende": false,
    "quelle": "executor"
  },
  "warnungen": ["…"],
  "hinweise": ["…"]
}
```

- **`rechenkette`** ist die nachvollziehbare Herleitung: jedes
  Zwischenergebnis (Fristbeginn, rechnerisches Ende nach § 188 BGB, jede
  Verschiebung nach § 193 BGB / § 222 Abs. 2 ZPO mit Grund und Norm) als
  eigener Schritt, jeweils mit `quelle: "executor"` (P3).
- **`fristende_bei_teilgebietlichem_feiertag`** ist gefüllt, wenn ein nur
  teilgebietlich geltender Feiertag (BY: Mariä Himmelfahrt, Augsburger
  Friedensfest; SN/TH: Fronleichnam in einzelnen Gemeinden) das Ergebnis
  ändern **könnte** — dann stehen beide möglichen Enden im Report und
  `warnungen` erklärt die Prüfpflicht für die konkrete Gemeinde. Nie wird
  ein teilgebietlicher Feiertag stillschweigend angenommen oder weggelassen.
- **`kein_technisches_fristende`** (nur `widerspruch_mahnbescheid`): das
  Datum ist der Ablauf der Zwei-Wochen-Frist aus der Belehrung
  (§ 692 Abs. 1 Nr. 3 ZPO); Widerspruch bleibt bis zur Verfügung des
  Vollstreckungsbescheids möglich, verspäteter Widerspruch gilt als
  Einspruch (§ 694 ZPO).

## Bewusste Grenzen

- **Keine Zustellungs-/Bekanntgabefiktionen**: § 130 Abs. 1 BGB,
  Zustellungsfiktionen (§ 179 ff. ZPO), die Drei-/Viertagesfiktion des
  Verwaltungsrechts u. Ä. rechnet der Executor nicht — das `ereignis_datum`
  ist Input und anwaltlich zu bestimmen.
- **Keine Fristbeginn-Alternativen**: die „spätestens fünf Monate nach
  Verkündung"-Alternative (§§ 517, 520, 548, 551 ZPO) wird als Hinweis
  ausgegeben, nicht mitberechnet.
- **Feiertagsregeln**: aktuelle Rechtslage (siehe
  `meta.feiertagsregeln_stand`); für Jahre vor 1995 warnt der Report, statt
  historisch falsche Ergebnisse als sicher auszugeben.
- **Uhrzeiten**: Fristen enden mit Ablauf des letzten Tages (24:00 Uhr);
  der Executor rechnet tagesgenau, keine Stundenfristen (§ 187 ff. BGB
  kennen hier nur Tagesgrenzen).
