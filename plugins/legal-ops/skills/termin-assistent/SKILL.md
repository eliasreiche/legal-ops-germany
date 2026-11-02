---
name: termin-assistent
description: "Schlägt Termine unter Berücksichtigung von Gerichtsterminen, Fristen und Kanzlei-Kalender (MS Graph oder iCal) vor. Triggert bei Terminvorschlag, Terminfindung, Kalender-Planung, freie Slots — und bei Termin eintragen, Gerichtstermin in den Kalender, Terminladung/Ladung notieren, Outlook-Termin anlegen (dafür gilt schon jetzt die Regel „Termin eintragen“). Work-in-progress (Welle 5)."
status: Work-in-progress
welle: 5
bereich: fristen-termine
rdg_einordnung: "Organisatorische Terminfindung; keine Rechtsdienstleistung."
daten_hinweis: "Kalenderdaten des Kanzlei-Tenants — DSGVO beachten."
haftung: "Terminvorschläge kollidierende Fristen sind Hinweise; Bestätigung durch die Kanzlei erforderlich."
---

# termin-assistent

> **Status: `Work-in-progress`** — Stub aus dem Repo-Gerüst (Welle-1-Fundament). Implementierung folgt gemäß Build-Reihenfolge (Welle 5).

## Zweck

Schlägt Termine unter Berücksichtigung von Gerichtsterminen, Fristen und Kanzlei-Kalender (MS Graph oder iCal-Datei) vor.

## Termin eintragen (Gerichtstermin, Ladung) — gilt schon jetzt

Die Terminfindung ist noch nicht gebaut. Diese Regel gilt trotzdem ab sofort,
sobald der Nutzer einen Termin in einen Kalender eintragen lassen will:

1. **Ein Termin ist keine Frist.** Einen Gerichtstermin (Datum, Uhrzeit, Ort,
   Saal) legt Claude nie als Frist (`frist_anlegen` o. ä.) oder als
   Wiedervorlage an, auch nicht „ersatzweise“. Eine Frist entsteht nur, wenn
   der Nutzer ausdrücklich eine will (etwa eine Vorbereitungsfrist), und dann
   als eigene, so benannte Frist zusätzlich zum Termin.
2. **Outlook:** Steht das Werkzeug `outlook_create_event` zur Verfügung, legt
   Claude den Termin damit an:
   - Betreff: Art des Termins, Gericht, internes Aktenzeichen,
   - Beginn und Ende mit Uhrzeit (Zeitzone Europe/Berlin); nennt die Ladung
     kein Ende, fragt Claude nach der Dauer oder schlägt eine Stunde vor und
     nennt das als Annahme,
   - Ort: Gericht, Anschrift, Saal,
   - Beschreibung: Aktenbezug und woher der Termin stammt (Ladung vom …),
   - eine Erinnerung.

   **Keine Teilnehmer.** Ein Termin mit Teilnehmern verschickt sofort
   Einladungen an diese Personen. Claude trägt Teilnehmer nur auf
   ausdrückliche Anweisung ein, mit Namen und Adresse, und fragt vorher noch
   einmal nach. Vor dem Anlegen zeigt Claude alle Felder; Claude Desktop
   fragt zusätzlich im Bestätigungsdialog.
3. **Kein passendes Werkzeug:** Fehlt `outlook_create_event` und gibt es in
   der Kanzleisoftware kein echtes Termin-Werkzeug, sagt Claude offen, dass
   der Termin nicht eingetragen wurde und warum, und bietet eine
   `.ics`-Datei zum Import an. Claude stellt eine Behelfslösung nie als
   (Teil-)Erledigung dar.
4. **Kanzleisoftware** (z. B. Actaport): Termine nur über ein Werkzeug, das
   ausdrücklich Termine anlegt. Gibt es keines, sagt Claude das.
5. **Datum und Uhrzeit** stammen nur aus der Ladung oder vom Nutzer, nie
   geschätzt. Widersprechen sich Angaben, fragt Claude nach.

## Eingaben (Datei-Kontrakt, P2)

*Noch zu spezifizieren in `schema/` — jeder Skill definiert Ein-/Ausgaben als Dateien; Live-Connectoren sind optionale Adapter.*

## Ablauf

*Folgt mit der Implementierung.*

## Output-Format

*Folgt mit der Implementierung. Deterministik-Grenze (P3): Jeder Zahlen-/Datums-/Geldwert im Output stammt aus einem Executor und ist als solcher markiert.*
