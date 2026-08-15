# core/adapters — Live-Adapter für den Kontext-Layer (D11, D11a)

Der Kontext-Layer (`kontext/`, siehe [`core/context/README.md`](../context/README.md))
ist die **einzige** Schnittstelle der Skills zu Kanzlei-Wissen (D11). Kein
Skill spricht Kanzleisoftware direkt an — Anbindung läuft ausschließlich über
Adapter oder MCP-Sync nach `kontext/`.

## Stand D11a (Maintainer-Entscheidung)

- **Microsoft 365 (Mail/Kalender/Kontakte):** kein eigener `msgraph`-Adapter
  mehr geplant — stattdessen der **offizielle M365-MCP-Konnektor**
  (Microsoft-eigener MCP-Server). Claude synchronisiert darüber nach
  `kontext/`; siehe Skill
  [`kontext-sync`](../../skills/kontext-sync/SKILL.md).
- **Andere Kanzleisysteme** (DATEV, Advoware, RA-MICRO, beA) — **„Integration
  geplant"**, kein Code in diesem Repo. Bei Bedarf zuerst die
  Anbieter-API-Dokumentation heranziehen (z. B. DATEV: developer.datev.de;
  beA: BRAK-Schnittstellenkonzept / bea.expert) und die Anbindung analog zum
  `filesystem`-Referenzadapter oder per eigenem MCP-Server umsetzen.
- **`filesystem/`** (dieses Verzeichnis) — **Referenz-Adapter und
  Agnostik-Garantie**: beweist, dass `kontext/` mit reinen Dateien
  funktioniert, unabhängig von jeder Kanzleisoftware. Jeder künftige Adapter
  erfüllt denselben Vertrag (`pull`/`push`, Hash-Manifest, Konflikt-Handling
  ohne stillschweigendes Überschreiben) — siehe
  [`filesystem/README.md`](filesystem/README.md).
- **Sanktionslisten (EU-/UN-Listen):** unverändert außerhalb des
  Kontext-Layers geplant (Datenquelle für `gwg-live-screening`, Welle 4,
  keine Kanzlei-Wissens-Anbindung im Sinne von D11).

## Was die Adapter können

- **`filesystem/`** — synchronisiert Dokumente in beide Richtungen (`pull` und
  `push`) zwischen einem externen Datei-Export und `kontext/`; keine Kalender-
  oder Mail-Daten. Details: [`filesystem/README.md`](filesystem/README.md).
- **`sanktionslisten/`** — lädt die offiziellen EU-/UN-Listen als XML herunter
  und parst sie; reines Lesen, kein `push`, kein `kontext/`-Bezug. Details:
  [`sanktionslisten/README.md`](sanktionslisten/README.md).

## Grundsatz (unverändert)

Adapter füttern dieselbe Datei-Schnittstelle, die jeder Skill über `kontext/`
ohnehin hat — nie einen Sonderpfad direkt in den Skill hinein. Pro
Pilotkanzlei verhandelbar, nie Kern des Repos: proprietäre ODBC-/API-Anbindung
einzelner Kanzleisoftware.
